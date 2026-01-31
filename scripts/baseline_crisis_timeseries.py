#!/usr/bin/env python3
"""
P1：baseline / crisis 的绝对量时间序列（分距离带）

输出：
- figures/n_baseline_sum_by_distance.pdf/png
- figures/n_crisis_sum_by_distance.pdf/png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_src() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def main() -> None:
    _bootstrap_src()

    try:
        import numpy as np
        import pandas as pd
    except ModuleNotFoundError as e:
        raise SystemExit("缺少依赖：numpy/pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

    try:
        from disaster import plot_style as ps
    except ModuleNotFoundError as e:
        raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

    import matplotlib.pyplot as plt
    from disaster.bins import parse_km_bin

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ts-csv",
        type=Path,
        default=Path("outputs/population_relaxation/tables/population_relaxation_by_distance.csv"),
        help="按距离分箱聚合后的时间序列 CSV（由 scripts/population_relaxation.py 生成）",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("outputs/population_relaxation"),
        help="输出根目录（会写入 figures/）",
    )
    parser.add_argument("--min-hours", type=float, default=None, help="最小 hours_since_quake（默认不限制）")
    parser.add_argument("--max-hours", type=float, default=None, help="最大 hours_since_quake（默认不限制）")
    parser.add_argument("--include-t0", action="store_true", help="包含 t=0（默认包含；该开关仅用于与其他脚本一致）")
    parser.add_argument("--max-distance-km", type=float, default=None, help="仅保留 hi<=该值的距离 bin（默认不限制）")
    args = parser.parse_args()

    if not args.ts_csv.exists():
        raise SystemExit(f"未找到时间序列：{args.ts_csv}。请先运行 `python scripts/population_relaxation.py` 生成 tables。")

    out_fig = args.output_root / "figures"
    _ensure_dir(out_fig)

    ts = pd.read_csv(args.ts_csv, parse_dates=["window_start_pt"])
    ts["hours_since_quake"] = pd.to_numeric(ts["hours_since_quake"], errors="coerce")
    ts = ts[ts["hours_since_quake"].notna()].copy()

    if not args.include_t0:
        ts = ts[ts["hours_since_quake"] > 0].copy()
    if args.min_hours is not None:
        ts = ts[ts["hours_since_quake"] >= float(args.min_hours)].copy()
    if args.max_hours is not None:
        ts = ts[ts["hours_since_quake"] <= float(args.max_hours)].copy()

    required = ["distance_bin", "hours_since_quake", "n_baseline_sum", "n_crisis_sum"]
    missing = [c for c in required if c not in ts.columns]
    if missing:
        raise SystemExit(f"时间序列缺少列：{missing}。请先用最新代码重新生成 ts CSV。")

    ts["n_baseline_sum"] = pd.to_numeric(ts["n_baseline_sum"], errors="coerce")
    ts["n_crisis_sum"] = pd.to_numeric(ts["n_crisis_sum"], errors="coerce")

    ts["km_bin"] = ts["distance_bin"].astype(str).apply(parse_km_bin)
    ts["lo_km"] = ts["km_bin"].apply(lambda b: float(b.lo))
    ts["hi_km"] = ts["km_bin"].apply(lambda b: float(b.hi))
    if args.max_distance_km is not None:
        ts = ts[ts["hi_km"] <= float(args.max_distance_km)].copy()

    bins_sorted = (
        ts[["distance_bin", "lo_km", "hi_km"]]
        .drop_duplicates()
        .sort_values(["lo_km", "hi_km"], kind="stable")["distance_bin"]
        .astype(str)
        .tolist()
    )

    palette = [
        ps.OKABE_ITO["vermillion"],
        ps.OKABE_ITO["orange"],
        ps.OKABE_ITO["bluish_green"],
        ps.OKABE_ITO["sky_blue"],
        ps.OKABE_ITO["blue"],
        ps.OKABE_ITO["gray"],
        ps.OKABE_ITO["reddish_purple"],
        ps.OKABE_ITO["black"],
    ]
    color_map = {b: palette[i % len(palette)] for i, b in enumerate(bins_sorted)}

    def _plot_sum(y_col: str, title: str, out_name: str) -> Path:
        with ps.paper_style():
            fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
            for b in bins_sorted:
                sub = ts[ts["distance_bin"].astype(str) == b].sort_values("hours_since_quake", kind="stable").copy()
                x = sub["hours_since_quake"].to_numpy(dtype=float)
                y = pd.to_numeric(sub[y_col], errors="coerce").to_numpy(dtype=float)
                ax.plot(x, y, marker="o", color=color_map.get(b, ps.OKABE_ITO["gray"]), label=b)

            ax.axvline(0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
            ax.set_xlabel("Hours since earthquake (PT windows)")
            ax.set_ylabel(y_col)
            ax.set_title(title)
            ps.despine(ax)

            handles, labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3, frameon=False)
                fig.subplots_adjust(bottom=0.28)
            else:
                fig.tight_layout()

            out_pdf = out_fig / f"{out_name}.pdf"
            ps.save_figure(fig, out_pdf)
            ps.save_figure(fig, out_pdf.with_suffix(".png"), dpi=200)
            plt.close(fig)
            return out_pdf

    p0 = _plot_sum("n_baseline_sum", "n_baseline_sum(t) by distance", "n_baseline_sum_by_distance")
    p1 = _plot_sum("n_crisis_sum", "n_crisis_sum(t) by distance", "n_crisis_sum_by_distance")

    print(f"Done. Wrote: {p0}")
    print(f"Done. Wrote: {p1}")


if __name__ == "__main__":
    main()
