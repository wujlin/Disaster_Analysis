#!/usr/bin/env python3
"""
构建 Turkey Earthquake 2023 的 sample 原始数据集（用于 GitHub 同步/PI review）。

设计目标：
- 只复制少量原始 CSV（不改内容）
- 覆盖 t=0 窗口（2023-02-05 16:00 PT），并包含足够多的震后窗口用于拟合
- 生成 manifest.csv（文件大小 + sha256）方便校验

默认：population/ 2023-02-05 ~ 2023-02-09（PT 窗口：0000/0800/1600）
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


DEFAULT_TIMES = ("0000", "0800", "1600")


@dataclass(frozen=True)
class Window:
    day: date
    hhmm: str

    @property
    def window_start_pt(self) -> str:
        return f"{self.day.isoformat()} {self.hhmm[:2]}:00"

    @property
    def pattern(self) -> str:
        return f"*_{self.day.isoformat()}_{self.hhmm}.csv"


def _iter_days(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("end_date 必须 >= start_date")
    days: list[date] = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy_if_needed(src: Path, dst: Path, *, overwrite: bool) -> None:
    if dst.exists():
        if not overwrite:
            raise FileExistsError(f"目标已存在：{dst}（可加 --overwrite 覆盖）")
        dst.unlink()
    shutil.copy2(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("Data/Turkiye Turkey Earthquake Full Country Version Feb 8 2023"),
        help="原始数据根目录（包含 population/ 子目录）",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("datasets/turkiye_earthquake_2023_sample"),
        help="sample 数据集输出目录",
    )
    parser.add_argument("--start-date", type=str, default="2023-02-05", help="起始日期（PT，YYYY-MM-DD）")
    parser.add_argument("--end-date", type=str, default="2023-02-09", help="结束日期（PT，YYYY-MM-DD）")
    parser.add_argument(
        "--times",
        type=str,
        default=",".join(DEFAULT_TIMES),
        help="要包含的窗口起始时间（逗号分隔，例如 0000,0800,1600）",
    )
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的目标文件")
    args = parser.parse_args()

    source_root = Path(args.source_root)
    pop_src = source_root / "population"
    if not pop_src.exists():
        raise SystemExit(f"未找到 population/：{pop_src}")

    out_root = Path(args.output_root)
    pop_out = out_root / "raw" / "population"
    pop_out.mkdir(parents=True, exist_ok=True)

    try:
        start = date.fromisoformat(args.start_date)
        end = date.fromisoformat(args.end_date)
    except ValueError as e:
        raise SystemExit("日期格式错误：请使用 YYYY-MM-DD（例如 2023-02-05）") from e

    times = tuple(t.strip() for t in args.times.split(",") if t.strip())
    if not times:
        raise SystemExit("--times 不能为空")
    for t in times:
        if len(t) != 4 or not t.isdigit():
            raise SystemExit(f"非法 time：{t}（应为 4 位数字，如 1600）")

    windows = [Window(day=d, hhmm=t) for d in _iter_days(start, end) for t in times]
    if not windows:
        raise SystemExit("未生成任何窗口；请检查 start/end/times 参数")

    fieldnames = [
        "relpath",
        "dataset",
        "window_start_pt",
        "date_pt",
        "time_pt",
        "size_bytes",
        "sha256",
        "source_relpath",
    ]
    rows: list[dict[str, str]] = []

    for w in windows:
        matches = sorted(pop_src.glob(w.pattern))
        if len(matches) != 1:
            raise SystemExit(f"无法唯一匹配：{pop_src / w.pattern}（found={len(matches)}）")
        src_file = matches[0]
        dst_file = pop_out / src_file.name
        _copy_if_needed(src_file, dst_file, overwrite=bool(args.overwrite))

        relpath = dst_file.relative_to(out_root).as_posix()
        size_bytes = str(dst_file.stat().st_size)
        sha256 = _sha256_file(dst_file)
        source_relpath = src_file.relative_to(source_root).as_posix()

        rows.append(
            {
                "relpath": relpath,
                "dataset": "population",
                "window_start_pt": w.window_start_pt,
                "date_pt": w.day.isoformat(),
                "time_pt": w.hhmm,
                "size_bytes": size_bytes,
                "sha256": sha256,
                "source_relpath": source_relpath,
            }
        )

    manifest_path = out_root / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done. Copied {len(rows)} files -> {pop_out}")
    print(f"Done. Wrote manifest -> {manifest_path}")
    print("Tip: run sample pipeline with:")
    print("  python scripts/population_relaxation.py --data-root datasets/turkiye_earthquake_2023_sample/raw --output-dir outputs/population_relaxation_sample")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
