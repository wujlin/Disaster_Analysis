#!/usr/bin/env python3
"""
Route B 16 冻结口径 post-gate 检查（跑后必过）。

检查项：
- 每个事件的 center_by_window.csv 中 center_extrapolated 总和必须为 0；
- Dt_routeB_sample_flags.csv 中 route_b_selected 数量必须为期望值（默认 16）。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd


def _read_catalog_slugs(catalog: Path) -> list[str]:
    if not catalog.exists():
        raise SystemExit(f"[fail] catalog 不存在：{catalog}")
    df = pd.read_csv(catalog)
    if "slug" not in df.columns:
        raise SystemExit(f"[fail] catalog 缺少 slug 列：{catalog}")
    return [str(s).strip() for s in df["slug"].tolist() if str(s).strip()]


def _check_center_extrapolation(phi_root: Path, slugs: list[str]) -> pd.DataFrame:
    rows: list[dict] = []
    for slug in slugs:
        p = phi_root / slug / "phi_heatmap" / "tables" / "center_by_window.csv"
        if not p.exists():
            rows.append(
                {
                    "slug": slug,
                    "center_file_exists": 0,
                    "n_rows": 0,
                    "center_extrapolated_sum": -1,
                    "status": "missing_center_by_window",
                }
            )
            continue

        df = pd.read_csv(p)
        if "center_extrapolated" in df.columns:
            extra_sum = int(pd.to_numeric(df["center_extrapolated"], errors="coerce").fillna(0).sum())
        elif "center_mode" in df.columns:
            mode = df["center_mode"].astype(str).str.lower()
            extra_sum = int(mode.str.contains("extrapolated", regex=False).sum())
        else:
            extra_sum = 0

        rows.append(
            {
                "slug": slug,
                "center_file_exists": 1,
                "n_rows": int(len(df)),
                "center_extrapolated_sum": int(extra_sum),
                "status": ("ok" if extra_sum == 0 else "has_extrapolation"),
            }
        )
    return pd.DataFrame(rows).sort_values("slug")


def _check_route_b_selection(dt_out: Path) -> tuple[pd.DataFrame, dict]:
    p = dt_out / "tables" / "Dt_routeB_sample_flags.csv"
    if not p.exists():
        raise SystemExit(f"[fail] 缺少文件：{p}")
    df = pd.read_csv(p)
    if "route_b_selected" not in df.columns:
        raise SystemExit(f"[fail] 缺少列 route_b_selected：{p}")
    sel = df[df["route_b_selected"].fillna(False).astype(bool)].copy()
    meta = {
        "n_rows": int(len(df)),
        "n_selected": int(len(sel)),
        "selected_slugs": sorted(sel["slug"].astype(str).tolist()),
    }
    return df, meta


def run_postgate(
    catalog: Path,
    phi_root: Path,
    dt_out: Path,
    out_dir: Path,
    expected_selected: int,
) -> None:
    slugs = _read_catalog_slugs(catalog)
    center_df = _check_center_extrapolation(phi_root, slugs)
    _, rb_meta = _check_route_b_selection(dt_out)

    out_dir.mkdir(parents=True, exist_ok=True)
    center_report = out_dir / "center_extrapolation_gate.csv"
    center_df.to_csv(center_report, index=False)

    selected_set = set(rb_meta["selected_slugs"])
    catalog_set = set(slugs)
    missing_in_selected = sorted(catalog_set - selected_set)
    extra_in_selected = sorted(selected_set - catalog_set)

    gate = {
        "catalog": str(catalog),
        "phi_root": str(phi_root),
        "dt_out": str(dt_out),
        "expected_selected": int(expected_selected),
        "n_catalog_events": int(len(slugs)),
        "n_selected": int(rb_meta["n_selected"]),
        "missing_in_selected": missing_in_selected,
        "extra_in_selected": extra_in_selected,
        "n_extrapolation_events": int((center_df["center_extrapolated_sum"] > 0).sum()),
        "ok_center_extrapolation": bool((center_df["center_extrapolated_sum"] <= 0).all()),
        "ok_selected_count": bool(int(rb_meta["n_selected"]) == int(expected_selected)),
        "ok_selected_set": bool(not missing_in_selected and not extra_in_selected),
    }
    gate["ok_all"] = bool(gate["ok_center_extrapolation"] and gate["ok_selected_count"] and gate["ok_selected_set"])

    gate_json = out_dir / "postgate_summary.json"
    gate_json.write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")

    if not gate["ok_all"]:
        print("[fail] post-gate 未通过")
        print(json.dumps(gate, ensure_ascii=False, indent=2))
        print(f"[info] center report: {center_report}")
        print(f"[info] summary json : {gate_json}")
        raise SystemExit(1)

    print("[ok] post-gate 通过")
    print(f"[ok] center report: {center_report}")
    print(f"[ok] summary json : {gate_json}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Route B 16 冻结口径 post-gate 检查")
    parser.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog_routeB16_frozen.csv"))
    parser.add_argument("--phi-root", type=Path, required=True, help="cross_disaster_phi_heatmap 的 output-root")
    parser.add_argument("--dt-out", type=Path, required=True, help="dt_decay 的 out-dir")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("outputs/cross_disaster_comparison/routeB16_frozen_postgate"),
    )
    parser.add_argument("--expected-selected", type=int, default=16)
    args = parser.parse_args()
    run_postgate(args.catalog, args.phi_root, args.dt_out, args.out_dir, args.expected_selected)


if __name__ == "__main__":
    main()

