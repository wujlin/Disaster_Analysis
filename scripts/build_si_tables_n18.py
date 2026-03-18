#!/usr/bin/env python3
"""
构建 SI 配套表（N=18 口径）。

输出到：
outputs/cross_disaster_comparison/si_tables_n18/
  - table_S1_event_catalog_n18.csv
  - table_S2_parameter_sensitivity_summary.csv
  - table_S4_socioeconomic_short_summary.csv
  - caption_sample_size_helper.csv
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = ROOT / "outputs" / "cross_disaster_comparison"
OUT_DIR = OUT_ROOT / "si_tables_n18"

FLAGS_CSV = OUT_ROOT / "Dt_decay_unified_static_h8_gtfix_mtw5_mpp4" / "tables" / "Dt_routeB_sample_flags.csv"
CATALOG_CSV = ROOT / "Docs" / "cross_disaster_catalog_extended_partial_gt_round2_static_center.csv"

WIN_SENS_CSV = OUT_ROOT / "unified_static_h8_spearman_summary.csv"
RMAX_SENS_CSV = OUT_ROOT / "rmax_sensitivity_spearman_summary.csv"
RNEAR_SENS_CSV = OUT_ROOT / "rnear_sensitivity_spearman_summary.csv"

COV_DIR = OUT_ROOT / "external_covariates" / "tables"
BIV_CSV = COV_DIR / "bivariate_spearman.csv"
PART_DN_CSV = COV_DIR / "partial_spearman_delta_near_alpha.csv"


def build_table_s1(flags: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    keep = [
        "slug",
        "short_name",
        "disaster_type",
        "event_type",
        "D_peak",
        "alpha",
        "r2",
        "near_delta_peak_windows_mean",
        "D_inf",
        "n_time_windows",
        "n_mono",
        "t_peak_hours",
        "t_decay_start",
        "t_decay_end",
    ]
    sel = flags.loc[flags["route_b_selected"] == True, [c for c in keep if c in flags.columns]].copy()

    cat_keep = [
        "slug",
        "name",
        "event_type",
        "t0_pt",
        "center_lat",
        "center_lon",
        "t0_source",
        "center_source",
        "exclude_reason",
    ]
    cat = catalog[[c for c in cat_keep if c in catalog.columns]].copy()
    out = sel.merge(cat, on="slug", how="left", suffixes=("", "_catalog"))
    out = out.rename(columns={
        "near_delta_peak_windows_mean": "delta_near",
        "r2": "r2_event",
    })
    out = out.sort_values(["disaster_type", "alpha"], ascending=[True, False], kind="stable")
    return out


def build_table_s2() -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for path, block in [
        (WIN_SENS_CSV, "window_threshold_sensitivity"),
        (RMAX_SENS_CSV, "rmax_sensitivity"),
        (RNEAR_SENS_CSV, "rnear_sensitivity"),
    ]:
        if path.exists():
            df = pd.read_csv(path)
            df.insert(0, "sensitivity_block", block)
            parts.append(df)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def build_table_s4() -> pd.DataFrame:
    if not BIV_CSV.exists():
        return pd.DataFrame()
    b = pd.read_csv(BIV_CSV)
    rows = b[b["pair"].isin(["HDI vs delta_near", "GDP_per_capita_PPP vs delta_near"])].copy()
    rows.insert(0, "analysis", "bivariate")

    if PART_DN_CSV.exists():
        p = pd.read_csv(PART_DN_CSV)
        p_rows = p[p["pair"].isin([
            "delta_near vs alpha (raw)",
            "delta_near vs alpha | HDI",
            "delta_near vs alpha | GDP_per_capita_PPP",
        ])].copy()
        p_rows.insert(0, "analysis", "partial")
        rows = pd.concat([rows, p_rows], ignore_index=True)
    return rows


def build_caption_helper(flags: pd.DataFrame) -> pd.DataFrame:
    n_sel = int(flags["route_b_selected"].sum())
    n_sel_plot = int(flags["route_b_selected_plot"].sum())
    return pd.DataFrame([
        {
            "panel": "Fig1a",
            "n_events": n_sel,
            "n_events_plot": n_sel_plot,
            "note": "Global map uses route_b_selected",
        },
        {
            "panel": "Fig1c",
            "n_events": n_sel_plot,
            "n_events_plot": n_sel_plot,
            "note": "log-log normalized decay",
        },
        {
            "panel": "Fig1d",
            "n_events": n_sel_plot,
            "n_events_plot": n_sel_plot,
            "note": "alpha vs delta_near scatter",
        },
    ])


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    flags = pd.read_csv(FLAGS_CSV)
    catalog = pd.read_csv(CATALOG_CSV)

    table_s1 = build_table_s1(flags, catalog)
    table_s1.to_csv(OUT_DIR / "table_S1_event_catalog_n18.csv", index=False)

    table_s2 = build_table_s2()
    if not table_s2.empty:
        table_s2.to_csv(OUT_DIR / "table_S2_parameter_sensitivity_summary.csv", index=False)

    table_s4 = build_table_s4()
    if not table_s4.empty:
        table_s4.to_csv(OUT_DIR / "table_S4_socioeconomic_short_summary.csv", index=False)

    cap = build_caption_helper(flags)
    cap.to_csv(OUT_DIR / "caption_sample_size_helper.csv", index=False)

    print(f"[ok] wrote SI tables to {OUT_DIR}")
    print(f"  S1 rows: {len(table_s1)}")
    if not table_s2.empty:
        print(f"  S2 rows: {len(table_s2)}")
    if not table_s4.empty:
        print(f"  S4 rows: {len(table_s4)}")


if __name__ == "__main__":
    main()
