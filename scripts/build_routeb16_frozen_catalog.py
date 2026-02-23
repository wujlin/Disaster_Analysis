#!/usr/bin/env python3
"""
生成 Route B 16 事件的冻结 catalog（静态中心 + 固定 t0 + 仅 08:00 窗口）。

规则：
- 仅保留固定 16 个 slug。
- center_track_* 一律清空（主分析禁用动态中心/外推）。
- t0_pt 缺失时：使用首个 08:00 窗口所在日期的 16:00（first_day_1600）。
- center_lat/lon 缺失时：在最接近 t0_pt 的 08:00 窗口上按 |n_difference| 加权质心估计；
  若 n_difference 不可用，则退化到 n_crisis 加权质心。
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd


def _bootstrap_src() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


_bootstrap_src()

from disaster.population_io import load_population_file, parse_window_start_pt, resolve_subdir


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


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    s = str(value).strip()
    return s == "" or s.lower() == "nan"


def _to_float(value: object) -> float | None:
    if _is_missing(value):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _to_int(value: object, default: int = 8) -> int:
    if _is_missing(value):
        return int(default)
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _to_timestamp(value: object) -> pd.Timestamp | None:
    if _is_missing(value):
        return None
    ts = pd.to_datetime(str(value).strip(), errors="coerce")
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts)


def _list_windows(data_root: Path, hour_pt: int) -> list[tuple[pd.Timestamp, Path]]:
    pop_dir = resolve_subdir(data_root, "population")
    files = sorted(pop_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"population 目录无 CSV：{pop_dir}")
    out: list[tuple[pd.Timestamp, Path]] = []
    for fp in files:
        ts = pd.Timestamp(parse_window_start_pt(fp))
        if int(ts.hour) == int(hour_pt):
            out.append((ts, fp))
    out = sorted(out, key=lambda x: x[0])
    if not out:
        raise FileNotFoundError(f"未找到 hour={hour_pt} 的窗口：{pop_dir}")
    return out


def _weighted_centroid(lat: np.ndarray, lon: np.ndarray, w: np.ndarray) -> tuple[float, float] | None:
    mask = np.isfinite(lat) & np.isfinite(lon) & np.isfinite(w) & (w > 0)
    if not np.any(mask):
        return None
    ww = w[mask].astype(float)
    sw = float(np.sum(ww))
    if sw <= 0:
        return None
    return float(np.sum(lat[mask] * ww) / sw), float(np.sum(lon[mask] * ww) / sw)


def _infer_center_from_file(csv_path: Path) -> tuple[float, float, str]:
    df = load_population_file(csv_path)
    lat = pd.to_numeric(df["lat"], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(df["lon"], errors="coerce").to_numpy(dtype=float)

    diff = pd.to_numeric(df.get("n_difference", np.nan), errors="coerce").to_numpy(dtype=float)
    out = _weighted_centroid(lat, lon, np.abs(diff))
    if out is not None:
        return out[0], out[1], "auto_centroid_abs_n_difference"

    crisis = pd.to_numeric(df.get("n_crisis", np.nan), errors="coerce").to_numpy(dtype=float)
    out = _weighted_centroid(lat, lon, crisis)
    if out is not None:
        return out[0], out[1], "auto_centroid_n_crisis"

    raise SystemExit(f"无法估计中心点：{csv_path}")


def _first_day_1600(ts: pd.Timestamp) -> pd.Timestamp:
    day = pd.Timestamp(ts).normalize()
    return day + pd.Timedelta(hours=16)


def build_catalog(
    base_catalog: Path,
    out_catalog: Path,
    report_csv: Path,
) -> None:
    if not base_catalog.exists():
        raise FileNotFoundError(f"未找到 base catalog：{base_catalog}")
    base = pd.read_csv(base_catalog)
    if "slug" not in base.columns:
        raise SystemExit(f"catalog 缺少 slug 列：{base_catalog}")

    out_rows: list[dict] = []
    report_rows: list[dict] = []

    for slug in ROUTE_B16_SLUGS:
        sub = base[base["slug"].astype(str) == slug]
        if sub.empty:
            raise SystemExit(f"base catalog 缺少 Route B 事件：{slug}")
        if len(sub) > 1:
            raise SystemExit(f"base catalog 存在重复 slug：{slug}")
        row = sub.iloc[0].to_dict()

        data_root = Path(str(row["data_root"]).strip())
        only_hour = _to_int(row.get("only_hour_pt"), default=8)
        windows = _list_windows(data_root, only_hour)
        first_ts = windows[0][0]

        t0_raw = _to_timestamp(row.get("t0_pt"))
        if t0_raw is None:
            t0_pt = _first_day_1600(first_ts)
            t0_method = "frozen_first_day_1600"
        else:
            t0_pt = pd.Timestamp(t0_raw)
            t0_method = "catalog_provided"

        nearest_ts, nearest_fp = min(windows, key=lambda x: abs((x[0] - t0_pt).total_seconds()))

        center_lat = _to_float(row.get("center_lat"))
        center_lon = _to_float(row.get("center_lon"))
        if center_lat is None or center_lon is None:
            center_lat, center_lon, center_method = _infer_center_from_file(nearest_fp)
        else:
            center_method = "catalog_provided"

        outflow = _to_float(row.get("outflow_phi_threshold"))
        inflow = _to_float(row.get("inflow_phi_threshold"))
        t0_source_in = str(row.get("t0_source", "")).strip()
        center_source_in = str(row.get("center_source", "")).strip()
        exclude_reason = str(row.get("exclude_reason", "")).strip()
        t0_source = t0_source_in if t0_source_in and t0_method == "catalog_provided" else t0_method
        center_source = center_source_in if center_source_in and center_method == "catalog_provided" else center_method

        out_rows.append(
            {
                "slug": slug,
                "name": str(row.get("name", "")).strip(),
                "data_root": str(data_root),
                "event_type": str(row.get("event_type", "")).strip() or "unknown",
                "t0_pt": pd.Timestamp(t0_pt).strftime("%Y-%m-%d %H:%M:%S"),
                "center_lat": float(center_lat),
                "center_lon": float(center_lon),
                "only_hour_pt": int(only_hour),
                "outflow_phi_threshold": (0.9 if outflow is None else float(outflow)),
                "inflow_phi_threshold": (1.1 if inflow is None else float(inflow)),
                "t0_source": str(t0_source),
                "center_source": str(center_source),
                "exclude_reason": str(exclude_reason),
                "center_track_csv": "",
                "center_track_to_tz": "",
                "center_track_storm_name": "",
            }
        )

        report_rows.append(
            {
                "slug": slug,
                "data_root": str(data_root),
                "n_hour_windows": int(len(windows)),
                "first_window_pt": str(first_ts),
                "last_window_pt": str(windows[-1][0]),
                "t0_pt_frozen": str(t0_pt),
                "t0_method": t0_method,
                "center_lat_frozen": float(center_lat),
                "center_lon_frozen": float(center_lon),
                "center_method": center_method,
                "t0_source": str(t0_source),
                "center_source": str(center_source),
                "exclude_reason": str(exclude_reason),
                "center_source_window_pt": str(nearest_ts),
                "center_source_file": nearest_fp.name,
            }
        )

    out_df = pd.DataFrame(out_rows)
    report_df = pd.DataFrame(report_rows)

    out_catalog.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_catalog, index=False)
    report_csv.parent.mkdir(parents=True, exist_ok=True)
    report_df.to_csv(report_csv, index=False)

    print(f"[ok] wrote frozen catalog: {out_catalog} (n={len(out_df)})")
    print(f"[ok] wrote build report:   {report_csv}")


def main() -> None:
    parser = argparse.ArgumentParser(description="构建 Route B 16 冻结 catalog（静态中心 + 固定 t0）")
    parser.add_argument(
        "--base-catalog",
        type=Path,
        default=Path("Docs/cross_disaster_catalog_extended_mnt_existing_only.csv"),
    )
    parser.add_argument(
        "--out-catalog",
        type=Path,
        default=Path("Docs/cross_disaster_catalog_routeB16_frozen.csv"),
    )
    parser.add_argument(
        "--report-csv",
        type=Path,
        default=Path("Docs/cross_disaster_catalog_routeB16_frozen_build_report.csv"),
    )
    args = parser.parse_args()
    build_catalog(args.base_catalog, args.out_catalog, args.report_csv)


if __name__ == "__main__":
    main()
