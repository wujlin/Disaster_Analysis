#!/usr/bin/env python3
"""
Route B 16 冻结口径 preflight 检查（跑前必过）。

检查项：
- slug 集合必须与 Route B 16 完全一致；
- 必填字段非空：slug, name, data_root, event_type, t0_pt, center_lat, center_lon, only_hour_pt；
- 主分析中 center_track_csv / center_track_storm_name 必须为空；
- 每个事件 data_root 存在，且 population 目录存在 hour=only_hour_pt 的窗口文件。
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


def _bootstrap_src() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


_bootstrap_src()

from disaster.population_io import parse_window_start_pt, resolve_subdir


ROUTE_B16_SLUGS: tuple[str, ...] = (
    "flooding_in_central_and_eastern_europe_sept_16_2024",
    "hurricane_beryl_across_quintana_roo_and_yucatan_mexico",
    "hurricane_beryl_across_southeastern_texas_us",
    "hurricane_beryl_pre_landfall_2024",
    "hurricane_john_across_southeastern_guerrero_mexico",
    "hurricane_john_southern_mexico_25_september_2024",
    "hurricane_milton_across_florida_us",
    "moldova_flooding_2024",
    "spain_flood",
    "the_earthquake_across_central_mexico",
    "the_flooding_across_bagmati_and_koshi_provinces_nepal",
    "the_flooding_across_eastern_bangladesh",
    "the_flooding_across_gujarat_india",
    "turkiye_earthquake_2023",
    "typhoon_yagi_across_northeastern_vietnam",
    "wildfires_in_boise_county_idaho_27_august_2024",
)


REQUIRED_COLUMNS: tuple[str, ...] = (
    "slug",
    "name",
    "data_root",
    "event_type",
    "t0_pt",
    "center_lat",
    "center_lon",
    "only_hour_pt",
)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    s = str(value).strip()
    return s == "" or s.lower() == "nan"


def run_preflight(catalog: Path, report_csv: Path, strict_slug_set: int = 1) -> None:
    if not catalog.exists():
        raise SystemExit(f"[fail] catalog 不存在：{catalog}")

    df = pd.read_csv(catalog)
    miss_cols = sorted(set(REQUIRED_COLUMNS) - set(df.columns))
    if miss_cols:
        raise SystemExit(f"[fail] catalog 缺少列：{miss_cols}")

    errors: list[str] = []

    got_slugs = set(df["slug"].astype(str))
    expect_slugs = set(ROUTE_B16_SLUGS)
    if int(strict_slug_set) == 1:
        missing = sorted(expect_slugs - got_slugs)
        extra = sorted(got_slugs - expect_slugs)
        if missing:
            errors.append(f"缺少 RouteB16 slug: {missing}")
        if extra:
            errors.append(f"存在非 RouteB16 slug: {extra}")
        if len(df) != len(ROUTE_B16_SLUGS):
            errors.append(f"事件行数不是16：{len(df)}")

    # 必填非空
    for col in REQUIRED_COLUMNS:
        bad = df[df[col].apply(_is_missing)]
        if not bad.empty:
            errors.append(f"列 {col} 存在空值：{sorted(bad['slug'].astype(str).unique().tolist())}")

    # 主分析禁用 track
    for col in ("center_track_csv", "center_track_storm_name"):
        if col in df.columns:
            bad = df[~df[col].apply(_is_missing)]
            if not bad.empty:
                errors.append(f"列 {col} 必须为空，发现非空：{sorted(bad['slug'].astype(str).unique().tolist())}")

    report_rows: list[dict] = []
    for row in df.to_dict(orient="records"):
        slug = str(row["slug"]).strip()
        data_root = Path(str(row["data_root"]).strip())
        only_hour = int(float(row["only_hour_pt"]))
        root_ok = data_root.exists()
        pop_ok = False
        n_hour_windows = 0
        first_hour_window_pt = ""
        last_hour_window_pt = ""
        message = "ok"

        if not root_ok:
            message = "data_root_missing"
            errors.append(f"{slug}: data_root 不存在：{data_root}")
        else:
            try:
                pop_dir = resolve_subdir(data_root, "population")
                pop_ok = pop_dir.exists()
                files = sorted(pop_dir.glob("*.csv"))
                hours = []
                for fp in files:
                    ts = pd.Timestamp(parse_window_start_pt(fp))
                    if int(ts.hour) == only_hour:
                        hours.append(ts)
                n_hour_windows = len(hours)
                if hours:
                    first_hour_window_pt = str(hours[0])
                    last_hour_window_pt = str(hours[-1])
                else:
                    message = f"no_hour_{only_hour}_windows"
                    errors.append(f"{slug}: population 存在但无 hour={only_hour} 窗口")
            except Exception as exc:
                message = f"population_check_error:{exc}"
                errors.append(f"{slug}: population 检查失败：{exc}")

        report_rows.append(
            {
                "slug": slug,
                "data_root": str(data_root),
                "root_exists": int(root_ok),
                "population_exists": int(pop_ok),
                "only_hour_pt": only_hour,
                "n_hour_windows": int(n_hour_windows),
                "first_hour_window_pt": first_hour_window_pt,
                "last_hour_window_pt": last_hour_window_pt,
                "message": message,
            }
        )

    report_df = pd.DataFrame(report_rows).sort_values("slug")
    report_csv.parent.mkdir(parents=True, exist_ok=True)
    report_df.to_csv(report_csv, index=False)

    if errors:
        print(f"[fail] preflight 未通过，问题数={len(errors)}")
        for item in errors:
            print(f" - {item}")
        print(f"[info] 详情见：{report_csv}")
        raise SystemExit(1)

    print("[ok] preflight 通过")
    print(f"[ok] report: {report_csv}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Route B 16 冻结口径 preflight 检查")
    parser.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog_routeB16_frozen.csv"))
    parser.add_argument(
        "--report-csv",
        type=Path,
        default=Path("outputs/cross_disaster_comparison/routeB16_frozen_preflight.csv"),
    )
    parser.add_argument("--strict-slug-set", type=int, default=1, choices=[0, 1])
    args = parser.parse_args()
    run_preflight(args.catalog, args.report_csv, args.strict_slug_set)


if __name__ == "__main__":
    main()

