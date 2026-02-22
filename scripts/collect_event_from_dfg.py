#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "datasets" / "dfg_catalog.json"
DFG_DOWNLOADER = REPO_ROOT / "scripts" / "dfg_downloader.py"
DEFAULT_COLLECTIONS = [
    "Facebook Population During Crisis",
    "Movement Between Places During Crisis",
    "Network Coverage Maps",
    "Business Activity Trends During Crisis",
]
TS_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})_(\d{4})\.csv$")


def _sanitize_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


def _load_catalog(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"未找到 catalog：{path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"catalog 格式错误（应为 list）：{path}")
    return data


def _match_event(
    catalog: list[dict[str, Any]],
    event_name: str,
    match_mode: str,
) -> list[dict[str, Any]]:
    q = event_name.strip().lower()
    if match_mode == "exact":
        rows = [r for r in catalog if str(r.get("display_name", "")).strip().lower() == q]
    else:
        rows = [r for r in catalog if q in str(r.get("display_name", "")).lower()]
    if not rows:
        raise ValueError(f"catalog 中未找到事件：{event_name}（match_mode={match_mode}）")
    return rows


def _run_cmd(cmd: list[str]) -> None:
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)
    if res.returncode != 0:
        raise RuntimeError(f"命令执行失败（exit={res.returncode}）：{' '.join(cmd)}")


def _parse_csv_dt(path: Path) -> datetime | None:
    m = TS_RE.search(path.name)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H%M")
    except ValueError:
        return None


@dataclass
class CollectionLocalStats:
    dataset_id: str
    display_name: str
    collection_title: str
    date_range_start: str
    date_range_end: str
    raw_dir: Path
    csv_count: int
    dt_min: str | None
    dt_max: str | None
    hour_hist: dict[str, int]


def _build_local_stats(row: dict[str, Any]) -> CollectionLocalStats:
    event_safe = _sanitize_name(str(row.get("display_name", "")))
    col_safe = _sanitize_name(str(row.get("collection_title", "")))
    raw_dir = REPO_ROOT / "datasets" / event_safe / col_safe / "raw"
    csv_files = sorted(raw_dir.glob("*.csv")) if raw_dir.exists() else []
    dts = [d for d in (_parse_csv_dt(p) for p in csv_files) if d is not None]
    hour_hist = Counter(f"{d.hour:02d}" for d in dts)
    return CollectionLocalStats(
        dataset_id=str(row.get("dataset_id", "")),
        display_name=str(row.get("display_name", "")),
        collection_title=str(row.get("collection_title", "")),
        date_range_start=str(row.get("date_range_start", "")),
        date_range_end=str(row.get("date_range_end", "")),
        raw_dir=raw_dir,
        csv_count=len(csv_files),
        dt_min=min(dts).strftime("%Y-%m-%d %H:%M") if dts else None,
        dt_max=max(dts).strftime("%Y-%m-%d %H:%M") if dts else None,
        hour_hist=dict(sorted(hour_hist.items())),
    )


def _write_csv_report(path: Path, stats: list[CollectionLocalStats]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "dataset_id",
        "display_name",
        "collection_title",
        "date_range_start",
        "date_range_end",
        "raw_dir",
        "csv_count",
        "dt_min",
        "dt_max",
        "hour_hist",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for s in stats:
            writer.writerow(
                {
                    "dataset_id": s.dataset_id,
                    "display_name": s.display_name,
                    "collection_title": s.collection_title,
                    "date_range_start": s.date_range_start,
                    "date_range_end": s.date_range_end,
                    "raw_dir": str(s.raw_dir),
                    "csv_count": s.csv_count,
                    "dt_min": s.dt_min or "",
                    "dt_max": s.dt_max or "",
                    "hour_hist": json.dumps(s.hour_hist, ensure_ascii=False),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="按事件名从 DFG 批量采集并做本地完整性校验（严格模式，无 silent fallback）"
    )
    parser.add_argument("--event-display-name", required=True, help="事件 display_name（建议精确匹配）")
    parser.add_argument("--match-mode", choices=["exact", "contains"], default="exact")
    parser.add_argument("--refresh-catalog", type=int, default=0, help="1=先执行 dfg_downloader.py catalog")
    parser.add_argument("--download", type=int, default=1, help="1=执行下载，0=仅做本地检查")
    parser.add_argument("--max-dates", type=int, default=100)
    parser.add_argument("--format", default="csv", choices=["csv", "geotiff", "geojson", "all"])
    parser.add_argument("--strict-collections", type=int, default=1, help="1=缺少必需 collection 直接报错")
    parser.add_argument(
        "--required-collections",
        default="|".join(DEFAULT_COLLECTIONS),
        help="必需 collection，以 | 分隔",
    )
    parser.add_argument(
        "--min-population-windows",
        type=int,
        default=0,
        help="若 >0，则要求 Population csv_count >= 该阈值",
    )
    parser.add_argument("--out-dir", default="outputs/_runs/dfg_collection")
    args = parser.parse_args()

    if args.refresh_catalog == 1:
        _run_cmd([sys.executable, str(DFG_DOWNLOADER), "catalog"])

    catalog = _load_catalog(CATALOG_PATH)
    selected = _match_event(catalog, args.event_display_name, args.match_mode)
    selected = sorted(selected, key=lambda x: str(x.get("collection_title", "")))

    print(f"[collect_event_from_dfg] event={args.event_display_name}")
    print(f"[collect_event_from_dfg] matched datasets={len(selected)}")
    for row in selected:
        print(
            f"  - {row.get('dataset_id')} | {row.get('collection_title')} "
            f"| {row.get('date_range_start')} ~ {row.get('date_range_end')}"
        )

    if args.download == 1:
        for row in selected:
            _run_cmd(
                [
                    sys.executable,
                    str(DFG_DOWNLOADER),
                    "download",
                    "--dataset-id",
                    str(row.get("dataset_id", "")),
                    "--max-dates",
                    str(args.max_dates),
                    "--format",
                    args.format,
                    "--yes",
                ]
            )

    stats = [_build_local_stats(row) for row in selected]
    required = [s.strip() for s in str(args.required_collections).split("|") if s.strip()]
    present_collections = {s.collection_title for s in stats}

    if args.strict_collections == 1:
        missing = [c for c in required if c not in present_collections]
        if missing:
            raise ValueError(f"缺少必需 collection：{missing}，present={sorted(present_collections)}")

    if args.min_population_windows > 0:
        pop = [s for s in stats if s.collection_title == "Facebook Population During Crisis"]
        if not pop:
            raise ValueError("未找到 Population collection，无法检查窗口数")
        if pop[0].csv_count < args.min_population_windows:
            raise ValueError(
                "Population 窗口不足："
                f"{pop[0].csv_count} < {args.min_population_windows} "
                f"(event={args.event_display_name})"
            )

    out_dir = REPO_ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    event_safe = _sanitize_name(args.event_display_name)
    json_out = out_dir / f"{event_safe}_collection_report.json"
    csv_out = out_dir / f"{event_safe}_collection_report.csv"

    report = {
        "event_display_name": args.event_display_name,
        "match_mode": args.match_mode,
        "refresh_catalog": int(args.refresh_catalog),
        "download": int(args.download),
        "max_dates": int(args.max_dates),
        "format": args.format,
        "strict_collections": int(args.strict_collections),
        "required_collections": required,
        "min_population_windows": int(args.min_population_windows),
        "datasets": [
            {
                "dataset_id": s.dataset_id,
                "collection_title": s.collection_title,
                "date_range_start": s.date_range_start,
                "date_range_end": s.date_range_end,
                "raw_dir": str(s.raw_dir),
                "csv_count": s.csv_count,
                "dt_min": s.dt_min,
                "dt_max": s.dt_max,
                "hour_hist": s.hour_hist,
            }
            for s in stats
        ],
    }
    json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_csv_report(csv_out, stats)

    print(f"[collect_event_from_dfg] wrote: {json_out}")
    print(f"[collect_event_from_dfg] wrote: {csv_out}")


if __name__ == "__main__":
    main()

