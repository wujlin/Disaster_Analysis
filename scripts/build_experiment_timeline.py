from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

NAME_DT_PATTERNS = [
    re.compile(r"(?P<date>20\d{6})_(?P<time>\d{4,6})(?:$|\.)"),
    re.compile(r"(?P<date>20\d{6})(?:$|\.)"),
]

NORMALIZE_PATTERNS = [
    re.compile(r"_20\d{6}_\d{4,6}$"),
    re.compile(r"_20\d{6}$"),
    re.compile(r"_\d{8}_\d{6}$"),
    re.compile(r"_\d{8}$"),
]

ANCHOR_FILE_NAMES = {
    "run.log",
    "pipeline.log",
    "status.json",
    "metadata.json",
}
ANCHOR_FILE_GLOBS = ["_log*.txt", "*.log"]

DEFAULT_ROOTS = [
    "outputs",
    "outputs_centerfix",
    "outputs_trackpath",
    "outputs_trackpath_v2",
    "outputs_trackpath_v3",
    "outputs_dfg_batch1",
    "outputs_dfg_batch1_anchor",
]


@dataclass
class ExperimentRecord:
    datetime: dt.datetime
    source: str
    root: str
    category: str
    key: str
    path: str
    mtime: dt.datetime
    has_log: int
    has_tables: int
    has_figures: int


def parse_name_datetime(name: str) -> dt.datetime | None:
    for pattern in NAME_DT_PATTERNS:
        match = pattern.search(name)
        if not match:
            continue
        date_txt = match.group("date")
        time_txt = match.groupdict().get("time")
        if not time_txt:
            return dt.datetime.strptime(date_txt, "%Y%m%d")
        if len(time_txt) == 4:
            time_txt = f"{time_txt}00"
        return dt.datetime.strptime(f"{date_txt}{time_txt}", "%Y%m%d%H%M%S")
    return None


def normalize_key(name: str) -> str:
    stem = Path(name).stem
    key = stem
    for pattern in NORMALIZE_PATTERNS:
        key = pattern.sub("", key)
    return key


def is_event_dir(path: Path) -> bool:
    return (path / "metadata.json").exists() and (path / "phi_heatmap").exists()


def has_anchor_files(path: Path) -> bool:
    for filename in ANCHOR_FILE_NAMES:
        if (path / filename).exists():
            return True
    for pattern in ANCHOR_FILE_GLOBS:
        if any(path.glob(pattern)):
            return True
    return False


def infer_category(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    rel_txt = rel.as_posix()
    if rel_txt.startswith("_runs/"):
        return "run_batch"
    if rel_txt.startswith("cross_disaster_comparison/"):
        return "cross_disaster"
    if is_event_dir(path):
        return "event_root"
    if path.name.startswith("_tmp"):
        return "tmp"
    return "module"


def pick_anchor_datetime(path: Path) -> tuple[dt.datetime, str]:
    name_dt = parse_name_datetime(path.name)
    if name_dt is not None:
        return name_dt, "name_timestamp"

    anchor_times: list[float] = []
    for filename in ANCHOR_FILE_NAMES:
        fpath = path / filename
        if fpath.exists():
            anchor_times.append(fpath.stat().st_mtime)
    for pattern in ANCHOR_FILE_GLOBS:
        for fpath in path.glob(pattern):
            if fpath.is_file():
                anchor_times.append(fpath.stat().st_mtime)

    if anchor_times:
        return dt.datetime.fromtimestamp(min(anchor_times)), "anchor_file_mtime"

    return dt.datetime.fromtimestamp(path.stat().st_mtime), "dir_mtime"


def collect_targets(root: Path) -> list[Path]:
    targets: list[Path] = []
    if root.name == "outputs":
        cross = root / "cross_disaster_comparison"
        if cross.exists():
            targets.extend(sorted([p for p in cross.iterdir() if p.is_dir()]))
        runs = root / "_runs"
        if runs.exists():
            for current_root, dirs, files in os.walk(runs):
                current = Path(current_root)
                rel_parts = current.relative_to(runs).parts
                depth = len(rel_parts)
                if depth > 3:
                    dirs[:] = []
                    continue
                if depth == 0:
                    continue
                has_primary_log = any(
                    fname in {"run.log", "pipeline.log", "status.json"}
                    or fname.endswith(".log")
                    or fname.startswith("_log")
                    for fname in files
                )
                has_logs_dir = (current / "logs").exists()
                has_ts = parse_name_datetime(current.name) is not None

                include = False
                if depth == 1:
                    include = (
                        has_ts
                        or current.name.startswith("_tmp")
                        or has_primary_log
                        or has_logs_dir
                        or current.name in {"centerfix", "dfg", "trackpath", "dfg_collection"}
                    )
                elif depth == 2:
                    include = (
                        has_ts
                        or current.name.startswith("_tmp")
                        or has_primary_log
                        or current.name.startswith("v")
                        or current.name.startswith("batch")
                    )
                elif depth == 3:
                    include = current.name.startswith("_tmp") or has_primary_log

                if include:
                    targets.append(current)
        for p in sorted(root.iterdir()):
            if not p.is_dir():
                continue
            if p.name in {"cross_disaster_comparison", "_runs"}:
                continue
            if p.name.startswith("."):
                continue
            if p.name.startswith("_") and p.name not in {"_legacy"}:
                continue
            if p.name == "_legacy":
                targets.extend(sorted([d for d in p.iterdir() if d.is_dir()]))
                continue
            if is_event_dir(p):
                continue
            if (p / "tables").exists() or (p / "figures").exists() or (p / "fits").exists() or has_anchor_files(p):
                targets.append(p)
    else:
        for p in sorted(root.iterdir()):
            if not p.is_dir():
                continue
            if p.name.startswith("."):
                continue
            if is_event_dir(p):
                continue
            if (p / "tables").exists() or (p / "figures").exists() or has_anchor_files(p):
                targets.append(p)

    unique: dict[str, Path] = {}
    for path in targets:
        unique[str(path)] = path
    return list(unique.values())


def build_records(roots: Iterable[Path]) -> list[ExperimentRecord]:
    records: list[ExperimentRecord] = []
    for root in roots:
        if not root.exists():
            continue
        for target in collect_targets(root):
            anchor_dt, source = pick_anchor_datetime(target)
            mtime = dt.datetime.fromtimestamp(target.stat().st_mtime)
            category = infer_category(target, root)
            key = normalize_key(target.name)
            records.append(
                ExperimentRecord(
                    datetime=anchor_dt,
                    source=source,
                    root=root.name,
                    category=category,
                    key=key,
                    path=target.as_posix(),
                    mtime=mtime,
                    has_log=int(has_anchor_files(target)),
                    has_tables=int((target / "tables").exists()),
                    has_figures=int((target / "figures").exists()),
                )
            )
    records.sort(key=lambda item: (item.datetime, item.path))
    return records


def write_records_csv(path: Path, records: list[ExperimentRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "datetime",
            "source",
            "root",
            "category",
            "key",
            "path",
            "mtime",
            "has_log",
            "has_tables",
            "has_figures",
        ])
        for row in records:
            writer.writerow([
                row.datetime.strftime("%Y-%m-%d %H:%M:%S"),
                row.source,
                row.root,
                row.category,
                row.key,
                row.path,
                row.mtime.strftime("%Y-%m-%d %H:%M:%S"),
                row.has_log,
                row.has_tables,
                row.has_figures,
            ])


def build_key_summary(records: list[ExperimentRecord]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str], list[ExperimentRecord]] = {}
    for row in records:
        grouped.setdefault((row.root, row.key), []).append(row)

    summary_rows: list[dict[str, str]] = []
    for (root, key), items in grouped.items():
        items_sorted = sorted(items, key=lambda item: item.datetime)
        summary_rows.append(
            {
                "root": root,
                "key": key,
                "category": items_sorted[0].category,
                "n_runs": str(len(items_sorted)),
                "first_datetime": items_sorted[0].datetime.strftime("%Y-%m-%d %H:%M:%S"),
                "last_datetime": items_sorted[-1].datetime.strftime("%Y-%m-%d %H:%M:%S"),
                "latest_path": items_sorted[-1].path,
            }
        )
    summary_rows.sort(key=lambda row: (row["root"], row["key"]))
    return summary_rows


def write_summary_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "root",
                "key",
                "category",
                "n_runs",
                "first_datetime",
                "last_datetime",
                "latest_path",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, records: list[ExperimentRecord], summary: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    by_date: dict[str, list[ExperimentRecord]] = {}
    for row in records:
        by_date.setdefault(row.datetime.strftime("%Y-%m-%d"), []).append(row)

    first_dt = records[0].datetime.strftime("%Y-%m-%d %H:%M:%S") if records else ""
    last_dt = records[-1].datetime.strftime("%Y-%m-%d %H:%M:%S") if records else ""

    with path.open("w", encoding="utf-8") as f:
        f.write("# 实验时序日志（全量目录，防重复版）\n\n")
        f.write(f"- 生成时间：{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- 覆盖实验条目：{len(records)}\n")
        f.write(f"- 覆盖实验键：{len(summary)}\n")
        f.write(f"- 时间范围：{first_dt} ~ {last_dt}\n")
        f.write("- 日期来源优先级：目录名时间戳 > 日志/元数据文件时间 > 目录时间\n\n")
        f.write("## 防重复建议\n\n")
        f.write("1. 新实验前先查 `experiment_timeline_key_summary_full.csv` 的 `key` 是否已存在。\n")
        f.write("2. 若已存在同 `key`，新结果目录必须带新时间戳或新参数后缀。\n")
        f.write("3. 复现实验请复用最近 `latest_path`，避免重复跑同参数。\n\n")

        f.write("## 重复运行最多的实验键（Top 20）\n\n")
        top20 = sorted(summary, key=lambda row: int(row["n_runs"]), reverse=True)[:20]
        f.write("|root|key|n_runs|first|last|latest_path|\n")
        f.write("|---|---|---:|---|---|---|\n")
        for row in top20:
            f.write(
                f"|{row['root']}|{row['key']}|{row['n_runs']}|{row['first_datetime']}|{row['last_datetime']}|`{row['latest_path']}`|\n"
            )
        f.write("\n")

        for day in sorted(by_date.keys()):
            f.write(f"## {day}\n")
            for row in by_date[day]:
                f.write(
                    f"- {row.datetime.strftime('%H:%M:%S')} | `{row.path}` | key=`{row.key}` | {row.category} | {row.source}\n"
                )
            f.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="汇总实验目录并按时序生成日志")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--roots", nargs="*", default=DEFAULT_ROOTS)
    parser.add_argument(
        "--out-csv",
        default="outputs/cross_disaster_comparison/experiment_timeline_full.csv",
    )
    parser.add_argument(
        "--out-summary-csv",
        default="outputs/cross_disaster_comparison/experiment_timeline_key_summary_full.csv",
    )
    parser.add_argument(
        "--out-md",
        default="Docs/experiment_timeline_full.md",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    roots = [repo_root / p for p in args.roots]
    records = build_records(roots)
    summary = build_key_summary(records)

    write_records_csv(repo_root / args.out_csv, records)
    write_summary_csv(repo_root / args.out_summary_csv, summary)
    write_markdown(repo_root / args.out_md, records, summary)

    print(f"records={len(records)}")
    print(f"keys={len(summary)}")
    if records:
        print(f"range={records[0].datetime} ~ {records[-1].datetime}")


if __name__ == "__main__":
    main()
