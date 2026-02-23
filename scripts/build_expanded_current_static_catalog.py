#!/usr/bin/env python3
"""
构建 expanded_current 的静态中心 catalog：
- 保留输入 catalog 的 slug/name/data_root/event_type/t0/center 等字段；
- 强制清空 center_track_*，避免主分析混入动态中心与外推。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def run(*, catalog_in: Path, catalog_out: Path, report_out: Path) -> None:
    if not catalog_in.exists():
        raise SystemExit(f"[fail] 输入 catalog 不存在: {catalog_in}")
    df = pd.read_csv(catalog_in)
    if "slug" not in df.columns:
        raise SystemExit(f"[fail] 输入 catalog 缺少 slug: {catalog_in}")

    for col in ("center_track_csv", "center_track_to_tz", "center_track_storm_name"):
        if col not in df.columns:
            df[col] = ""
        df[col] = ""
    for col in ("t0_source", "center_source", "exclude_reason"):
        if col not in df.columns:
            df[col] = ""

    catalog_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(catalog_out, index=False)

    rep = df[["slug", "center_track_csv", "center_track_to_tz", "center_track_storm_name"]].copy()
    rep["all_track_fields_empty"] = (
        rep["center_track_csv"].fillna("").astype(str).str.strip().eq("")
        & rep["center_track_to_tz"].fillna("").astype(str).str.strip().eq("")
        & rep["center_track_storm_name"].fillna("").astype(str).str.strip().eq("")
    )
    rep.to_csv(report_out, index=False)

    print(f"[ok] wrote static expanded catalog: {catalog_out} (n={len(df)})")
    print(f"[ok] wrote report: {report_out}")


def main() -> None:
    p = argparse.ArgumentParser(description="构建 expanded_current 静态中心 catalog")
    p.add_argument("--catalog-in", type=Path, default=Path("Docs/cross_disaster_catalog_extended_mnt_existing_only.csv"))
    p.add_argument("--catalog-out", type=Path, default=Path("Docs/cross_disaster_catalog_expanded_current_static.csv"))
    p.add_argument(
        "--report-out",
        type=Path,
        default=Path("Docs/cross_disaster_catalog_expanded_current_static_report.csv"),
    )
    args = p.parse_args()
    run(catalog_in=args.catalog_in, catalog_out=args.catalog_out, report_out=args.report_out)


if __name__ == "__main__":
    main()
