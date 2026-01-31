#!/usr/bin/env python3
"""
P0：z_score vs φ 对比图（分距离带）

目的：在同一张图上对比 z_score_mean(t) 与 phi_mean(t)，辅助诊断：
z_score 的长期漂移是否同时出现在 φ 上（从而判断漂移是否可能来自 baseline/标准化口径）。
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
    parser.add_argument("--include-t0", action="store_true", help="包含 t=0（默认排除）")
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

    required = [
        "distance_bin",
        "hours_since_quake",
        "z_score_mean",
        "z_score_std",
        "z_score_count",
        "phi_mean",
        "phi_std",
        "phi_count",
    ]
    missing = [c for c in required if c not in ts.columns]
    if missing:
        raise SystemExit(f"时间序列缺少列：{missing}。请先用最新代码重新生成 ts CSV。")

    # 距离排序
    bins = ts["distance_bin"].astype(str).dropna().unique().tolist()
    bins_sorted = sorted(bins, key=lambda s: (float(parse_km_bin(s).lo), float(parse_km_bin(s).hi)))

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

    def _plot_panel(ax, y_col: str, y_std_col: str, y_n_col: str, title: str) -> None:
        for b in bins_sorted:
            sub = ts[ts["distance_bin"].astype(str) == b].copy()
            if sub.empty:
                continue
            sub = sub.sort_values("hours_since_quake", kind="stable")
            x = pd.to_numeric(sub["hours_since_quake"], errors="coerce").to_numpy(dtype=float)
            y = pd.to_numeric(sub[y_col], errors="coerce").to_numpy(dtype=float)
            std = pd.to_numeric(sub[y_std_col], errors="coerce").to_numpy(dtype=float)
            n = pd.to_numeric(sub[y_n_col], errors="coerce").to_numpy(dtype=float)
            se = std / np.sqrt(np.where(n > 0, n, np.nan))
            color = color_map.get(b, ps.OKABE_ITO["gray"])
            ax.plot(x, y, marker="o", color=color, label=b)
            ax.fill_between(x, y - se, y + se, color=color, alpha=0.18, linewidth=0)

        ax.axvline(0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.axhline(0, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.6)
        ax.set_ylabel(y_col)
        ax.set_title(title)
        ps.despine(ax)

    with ps.paper_style():
        fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(ps.FIGSIZE_FULL[0], ps.FIGSIZE_FULL[1] * 1.35), sharex=True)
        ax0, ax1 = axes

        _plot_panel(
            ax0,
            y_col="z_score_mean",
            y_std_col="z_score_std",
            y_n_col="z_score_count",
            title="z_score_mean(t) by distance",
        )
        _plot_panel(
            ax1,
            y_col="phi_mean",
            y_std_col="phi_std",
            y_n_col="phi_count",
            title="phi_mean(t) by distance",
        )
        ax1.set_xlabel("Hours since earthquake (PT windows)")

        handles, labels = ax0.get_legend_handles_labels()
        if handles:
            ax1.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=3, frameon=False)
            fig.subplots_adjust(bottom=0.32, hspace=0.28)
        else:
            fig.tight_layout()

        out_pdf = out_fig / "zscore_vs_phi_by_distance.pdf"
        ps.save_figure(fig, out_pdf)
        ps.save_figure(fig, out_pdf.with_suffix(".png"), dpi=200)
        plt.close(fig)

    print(f"Done. Wrote: {out_pdf}")


if __name__ == "__main__":
    main()
