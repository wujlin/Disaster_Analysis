#!/usr/bin/env python3
"""
Stretched exponential 拟合稳健性：β>1 是否稳定？

默认针对：
- distance_bin = "0-50km"
- 指标 = z_score_mean
- 仅用震后窗口（t >= 8h，默认排除 t=0 混合窗）

输出：
- outputs/population_relaxation/fits/beta_robustness_*.csv
- outputs/population_relaxation/figures/beta_robustness_*.pdf/png
"""

from __future__ import annotations

import argparse
import math
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
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as e:
        raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

    try:
        from scipy.optimize import curve_fit  # type: ignore
    except ModuleNotFoundError as e:
        raise SystemExit("缺少依赖：scipy。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

    from disaster import plot_style as ps

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ts-csv",
        type=Path,
        default=Path("outputs/population_relaxation/tables/population_relaxation_by_distance.csv"),
        help="按距离分箱聚合后的时间序列 CSV",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("outputs/population_relaxation"),
        help="输出根目录（会写入 fits/ 与 figures/）",
    )
    parser.add_argument("--distance-bin", type=str, default="0-50km", help="要测试的距离分箱")
    parser.add_argument(
        "--metric",
        type=str,
        default="z_score_mean",
        choices=["z_score_mean", "phi_mean"],
        help="拟合的指标（主分析建议 z_score_mean）",
    )
    parser.add_argument("--min-hours", type=float, default=8.0, help="最小 hours_since_quake（默认排除 t=0 混合窗）")
    parser.add_argument("--max-hours", type=float, default=None, help="最大 hours_since_quake（默认不限制）")
    parser.add_argument("--n-restarts", type=int, default=300, help="随机初值重启次数")
    parser.add_argument("--seed", type=int, default=7, help="随机种子")
    args = parser.parse_args()

    if not args.ts_csv.exists():
        raise SystemExit(f"未找到时间序列：{args.ts_csv}。请先运行 `python scripts/population_relaxation.py` 生成 tables。")

    out_fits = args.output_root / "fits"
    out_fig = args.output_root / "figures"
    _ensure_dir(out_fits)
    _ensure_dir(out_fig)

    ts = pd.read_csv(args.ts_csv, parse_dates=["window_start_pt"])
    ts = ts[ts["distance_bin"].astype(str) == str(args.distance_bin)].copy()
    ts = ts[ts["hours_since_quake"] >= float(args.min_hours)]
    if args.max_hours is not None:
        ts = ts[ts["hours_since_quake"] <= float(args.max_hours)]

    ts[args.metric] = pd.to_numeric(ts[args.metric], errors="coerce")
    ts = ts.dropna(subset=[args.metric]).sort_values("hours_since_quake", kind="stable")
    if len(ts) < 20:
        raise SystemExit(f"可用数据点不足（{len(ts)}）。请放宽时间范围或检查输入数据。")

    t = ts["hours_since_quake"].to_numpy(dtype=float)
    y = ts[args.metric].to_numpy(dtype=float)

    def stretched_exp(t_, tau, beta, a, c):
        return a * np.exp(-np.power(t_ / tau, beta)) + c

    # bounds 与主 pipeline 一致
    bounds = ([0.1, 0.1, -np.inf, -np.inf], [2000.0, 2.0, np.inf, np.inf])

    y0 = float(y[0])
    y_end = float(np.median(y[-max(5, len(y) // 20) :]))
    a_guess = y0 - y_end
    c_guess = y_end

    rng = np.random.default_rng(int(args.seed))
    rows: list[dict] = []
    for i in range(int(args.n_restarts)):
        tau0 = float(10 ** rng.uniform(math.log10(1.0), math.log10(1000.0)))
        beta0 = float(rng.uniform(0.1, 2.0))
        a0 = float(rng.normal(loc=a_guess, scale=max(0.5, abs(a_guess) + 0.5)))
        c0 = float(rng.normal(loc=c_guess, scale=0.5))
        p0 = [tau0, beta0, a0, c0]

        try:
            popt, _ = curve_fit(stretched_exp, t, y, p0=p0, bounds=bounds, maxfev=20000)
            yhat = stretched_exp(t, *popt)
            resid = y - yhat
            sse = float(np.sum(resid**2))
            rows.append(
                {
                    "trial": i,
                    "tau": float(popt[0]),
                    "beta": float(popt[1]),
                    "A": float(popt[2]),
                    "C": float(popt[3]),
                    "sse": sse,
                }
            )
        except Exception:
            continue

    if not rows:
        raise SystemExit("所有重启拟合都失败了；请检查 scipy/数据范围/初值设置。")

    df = pd.DataFrame(rows).sort_values("sse", kind="stable").reset_index(drop=True)
    best = df.iloc[0].to_dict()

    out_csv = out_fits / f"beta_robustness_stretched_exp_{args.metric}_{args.distance_bin}.csv"
    df.to_csv(out_csv, index=False)

    summary = {
        "distance_bin": str(args.distance_bin),
        "metric": str(args.metric),
        "min_hours": float(args.min_hours),
        "max_hours": float(args.max_hours) if args.max_hours is not None else None,
        "n_points": int(len(t)),
        "n_restarts": int(args.n_restarts),
        "n_success": int(len(df)),
        "success_rate": float(len(df)) / float(args.n_restarts),
        "best_tau": float(best["tau"]),
        "best_beta": float(best["beta"]),
        "best_C": float(best["C"]),
        "beta_median": float(df["beta"].median()),
        "beta_p25": float(df["beta"].quantile(0.25)),
        "beta_p75": float(df["beta"].quantile(0.75)),
        "beta_gt_1_rate": float((df["beta"] > 1.0).mean()),
    }
    summary_df = pd.DataFrame([summary])
    summary_path = out_fits / f"beta_robustness_summary_{args.metric}_{args.distance_bin}.csv"
    summary_df.to_csv(summary_path, index=False)

    # 1) β 分布直方图
    with ps.paper_style():
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        ax.hist(df["beta"].to_numpy(), bins=30, color=ps.OKABE_ITO["blue"], alpha=0.85)
        ax.axvline(1.0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.set_xlabel(r"Stretched exponential exponent $\beta$")
        ax.set_ylabel("Count (successful fits)")
        ax.set_title(f"Robustness of beta (>1?): {args.metric}, {args.distance_bin}")
        ps.despine(ax)
        fig.tight_layout()
        fig_path = out_fig / f"beta_robustness_hist_{args.metric}_{args.distance_bin}.pdf"
        ps.save_figure(fig, fig_path)
        ps.save_figure(fig, fig_path.with_suffix(".png"), dpi=200)
        plt.close(fig)

    # 2) 叠加：数据 + 最优拟合曲线
    tau_best = float(best["tau"])
    beta_best = float(best["beta"])
    a_best = float(best["A"])
    c_best = float(best["C"])
    y_fit = stretched_exp(t, tau_best, beta_best, a_best, c_best)

    with ps.paper_style():
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        ax.plot(t, y, marker="o", color=ps.OKABE_ITO["black"], label="data")
        ax.plot(t, y_fit, color=ps.OKABE_ITO["vermillion"], label=f"best fit (beta={beta_best:.2f})")
        ax.axhline(0, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.6)
        ax.set_xlabel("Hours since earthquake (PT windows)")
        ax.set_ylabel(args.metric)
        ax.set_title(f"Best stretched-exp fit: {args.metric}, {args.distance_bin}")
        ps.despine(ax)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=2, frameon=False)
        fig.subplots_adjust(bottom=0.28)
        fig_path = out_fig / f"beta_robustness_bestfit_{args.metric}_{args.distance_bin}.pdf"
        ps.save_figure(fig, fig_path)
        ps.save_figure(fig, fig_path.with_suffix(".png"), dpi=200)
        plt.close(fig)

    print(f"Done. Wrote: {out_csv}")
    print(f"Done. Wrote: {summary_path}")


if __name__ == "__main__":
    main()

