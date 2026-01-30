#!/usr/bin/env python3
"""
Population relaxation：拟合后分析（τ(r)、新稳态偏移 C、log-log 可视化）

输入：
- outputs/population_relaxation/fits/population_relaxation_fit_best_bic.csv

输出（写回同一 outputs 根目录下的 figures/tables）：
- figures/tau_vs_distance_loglog.pdf/png
- figures/offset_C_vs_distance.pdf/png
- tables/population_relaxation_postfit_summary.csv
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
        import pandas as pd
    except ModuleNotFoundError as e:
        raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as e:
        raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

    from disaster.bins import km_bin_midpoint, parse_km_bin
    from disaster import plot_style as ps

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fits-csv",
        type=Path,
        default=Path("outputs/population_relaxation/fits/population_relaxation_fit_best_bic.csv"),
        help="BIC 最优拟合结果 CSV",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("outputs/population_relaxation"),
        help="输出根目录（会写入 figures/ 与 tables/）",
    )
    parser.add_argument(
        "--open-ended-mid-km",
        type=float,
        default=None,
        help="对 '1000km+' 这类开区间 bin 指定一个用于画图的代表距离（不指定则该 bin 在 log-log 图中跳过）",
    )
    args = parser.parse_args()

    if not args.fits_csv.exists():
        raise SystemExit(f"未找到拟合结果：{args.fits_csv}。请先运行 `python scripts/population_relaxation.py` 生成 fits。")

    out_fig = args.output_root / "figures"
    out_tbl = args.output_root / "tables"
    _ensure_dir(out_fig)
    _ensure_dir(out_tbl)

    df = pd.read_csv(args.fits_csv)

    for col in ["tau", "beta", "alpha", "A", "C", "bic", "aic", "sse"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    bins = df["distance_bin"].astype(str).apply(parse_km_bin)
    df["lo_km"] = [b.lo for b in bins]
    df["hi_km"] = [b.hi for b in bins]
    df["is_open_ended"] = [b.is_open_ended for b in bins]
    df["mid_km"] = df["distance_bin"].astype(str).apply(lambda s: km_bin_midpoint(s, open_ended_mid_km=args.open_ended_mid_km))

    df = df.sort_values(["lo_km", "hi_km"], kind="stable").reset_index(drop=True)
    df.to_csv(out_tbl / "population_relaxation_postfit_summary.csv", index=False)

    model_color = {
        "exponential": ps.OKABE_ITO["blue"],
        "stretched_exp": ps.OKABE_ITO["vermillion"],
        "power_law": ps.OKABE_ITO["gray"],
    }

    # τ(r)：仅对有 tau 的模型作图（并默认跳过开区间 bin）
    tau_df = df[df["tau"].notna() & df["mid_km"].notna()].copy()
    if args.open_ended_mid_km is None:
        tau_df = tau_df[~tau_df["is_open_ended"]]

    with ps.paper_style():
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        for model, sub in tau_df.groupby("model", sort=False):
            sub = sub.sort_values("mid_km")
            color = model_color.get(str(model), ps.OKABE_ITO["black"])
            ax.plot(sub["mid_km"], sub["tau"], marker="o", color=color, label=str(model))

        if not tau_df.empty:
            fastest_idx = tau_df["tau"].idxmin()
            fastest = tau_df.loc[fastest_idx]
            ax.scatter(
                [fastest["mid_km"]],
                [fastest["tau"]],
                s=90,
                facecolors="none",
                edgecolors=ps.OKABE_ITO["orange"],
                linewidths=2.0,
                zorder=6,
            )
            ax.annotate(
                f"fastest\n{fastest['distance_bin']}",
                (fastest["mid_km"], fastest["tau"]),
                xytext=(10, 10),
                textcoords="offset points",
                ha="left",
                va="bottom",
            )

        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel(r"Distance to epicenter $r$ (km)")
        ax.set_ylabel(r"Relaxation timescale $\tau$ (hours)")
        ax.set_title(r"$\tau(r)$ from BIC-selected fits")
        ps.despine(ax)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3, frameon=False)
        fig.subplots_adjust(bottom=0.28)
        ps.save_figure(fig, out_fig / "tau_vs_distance_loglog.pdf")
        ps.save_figure(fig, out_fig / "tau_vs_distance_loglog.png", dpi=200)
        plt.close(fig)

    # C(r)：新稳态偏移（offset）
    c_df = df[df["C"].notna() & df["mid_km"].notna()].copy()
    if args.open_ended_mid_km is None:
        c_df = c_df[~c_df["is_open_ended"]]

    with ps.paper_style():
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        ax.plot(c_df["mid_km"], c_df["C"], marker="o", color=ps.OKABE_ITO["bluish_green"])
        ax.axhline(0, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.6)
        ax.set_xscale("log")
        ax.set_xlabel(r"Distance to epicenter $r$ (km)")
        ax.set_ylabel(r"Fitted offset $C$")
        ax.set_title(r"New steady-state offset $C(r)$")
        ps.despine(ax)
        fig.tight_layout()
        ps.save_figure(fig, out_fig / "offset_C_vs_distance.pdf")
        ps.save_figure(fig, out_fig / "offset_C_vs_distance.png", dpi=200)
        plt.close(fig)

    print(f"Done. Wrote figures to: {out_fig}")
    print(f"Done. Wrote tables to: {out_tbl}")


if __name__ == "__main__":
    main()

