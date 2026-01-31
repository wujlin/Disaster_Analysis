#!/usr/bin/env python3
"""
机制分区（regime differentiation）：
- 对每个距离带做多模型竞争（exp / stretched-exp / power-law / log）
- 用 BIC 选择最优模型，并输出“距离 → 模型类型”的分区图
- （可选）做参数化 bootstrap，输出“模型胜率”以检验分区是否稳健

注意：log 模型是经验候选，用于避免“漏掉慢变化形态导致误判”；它在 t→∞ 下不收敛到常数，
因此更适合作为竞争/诊断工具，而不是“新稳态”机制模型。
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


def _metric_cfg(metric: str):
    from disaster.relaxation_fit import FitConfig

    metric = str(metric).strip().lower()
    if metric in {"z", "z_score", "zscore"}:
        return FitConfig(y_col="z_score_mean", y_std_col="z_score_std", y_n_col="z_score_count")
    if metric in {"phi"}:
        return FitConfig(y_col="phi_mean", y_std_col="phi_std", y_n_col="phi_count")
    if metric in {"percent_change", "pct"}:
        return FitConfig(y_col="percent_change_mean", y_std_col="percent_change_std", y_n_col="percent_change_count")
    if metric in {"n_difference", "ndiff"}:
        return FitConfig(y_col="n_difference_mean", y_std_col="n_difference_std", y_n_col="n_difference_count")
    raise SystemExit(f"未知 metric：{metric}（可选：z_score/phi/percent_change/n_difference）")


def main() -> None:
    _bootstrap_src()

    try:
        import numpy as np
        import pandas as pd
    except ModuleNotFoundError as e:
        raise SystemExit("缺少依赖：numpy/pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
    except ModuleNotFoundError as e:
        raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

    from disaster import plot_style as ps
    from disaster.bins import parse_km_bin
    from disaster.relaxation_fit import FitConfig, fit_relaxation_models_table

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
        help="输出根目录（会写入 fits/ figures/ tables/）",
    )
    parser.add_argument(
        "--metric",
        type=str,
        default="z_score",
        help="要做分区的指标：z_score / phi / percent_change / n_difference",
    )
    parser.add_argument("--min-hours", type=float, default=0.0, help="最小 hours_since_quake（默认 0）")
    parser.add_argument("--max-hours", type=float, default=None, help="最大 hours_since_quake（默认不限制）")
    parser.add_argument("--min-points", type=int, default=10, help="每个距离带拟合所需最小点数（默认 10）")
    parser.add_argument("--include-t0", action="store_true", help="包含 t=0（默认排除混合窗 t=0）")
    parser.add_argument("--n-bootstrap", type=int, default=0, help="bootstrap 重采样次数（默认 0=不做）")
    parser.add_argument("--seed", type=int, default=7, help="bootstrap 随机种子")
    parser.add_argument(
        "--open-ended-right-km",
        type=float,
        default=None,
        help="将 '1000km+' 这类开区间 bin 绘制到该右端（不指定则在 regime map 中跳过开区间 bin）",
    )
    args = parser.parse_args()

    if not args.ts_csv.exists():
        raise SystemExit(f"未找到时间序列：{args.ts_csv}。请先运行 `python scripts/population_relaxation.py` 生成 tables。")

    out_fits = args.output_root / "fits"
    out_fig = args.output_root / "figures"
    out_tbl = args.output_root / "tables"
    _ensure_dir(out_fits)
    _ensure_dir(out_fig)
    _ensure_dir(out_tbl)

    cfg: FitConfig = _metric_cfg(args.metric)
    cfg = FitConfig(
        y_col=cfg.y_col,
        y_std_col=cfg.y_std_col,
        y_n_col=cfg.y_n_col,
        min_points=int(args.min_points),
        exclude_t0=not bool(args.include_t0),
        seed=int(args.seed),
    )

    ts = pd.read_csv(args.ts_csv, parse_dates=["window_start_pt"])
    ts["hours_since_quake"] = pd.to_numeric(ts["hours_since_quake"], errors="coerce")
    ts = ts[ts["hours_since_quake"].notna()].copy()
    ts = ts[ts["hours_since_quake"] >= float(args.min_hours)]
    if args.max_hours is not None:
        ts = ts[ts["hours_since_quake"] <= float(args.max_hours)]

    fit_df = fit_relaxation_models_table(ts, cfg=cfg)
    if fit_df.empty:
        raise SystemExit("拟合结果为空：可能是点数不足、指标列缺失，或缺少 scipy。")

    metric_tag = str(args.metric).strip().lower()
    all_models_csv = out_fits / f"regime_fit_{metric_tag}_all_models.csv"
    best_csv = out_fits / f"regime_fit_{metric_tag}_best_bic.csv"
    fit_df.to_csv(all_models_csv, index=False)

    best = fit_df.loc[fit_df.groupby("distance_bin")["bic"].idxmin()].copy()
    best.insert(1, "best_by", "bic")

    # 距离排序 + 边界检测
    best["km_bin"] = best["distance_bin"].astype(str).apply(parse_km_bin)
    best["lo_km"] = best["km_bin"].apply(lambda b: float(b.lo))
    best["hi_km"] = best["km_bin"].apply(lambda b: float(b.hi))
    best["is_open_ended"] = best["km_bin"].apply(lambda b: bool(b.is_open_ended))
    best = best.sort_values(["lo_km", "hi_km"], kind="stable").reset_index(drop=True)
    best.to_csv(best_csv, index=False)

    boundaries: list[dict] = []
    for i in range(1, len(best)):
        prev = best.iloc[i - 1]
        cur = best.iloc[i]
        if str(prev["model"]) != str(cur["model"]):
            boundaries.append(
                {
                    "boundary_km": float(cur["lo_km"]),
                    "left_bin": str(prev["distance_bin"]),
                    "left_model": str(prev["model"]),
                    "right_bin": str(cur["distance_bin"]),
                    "right_model": str(cur["model"]),
                }
            )
    boundaries_df = pd.DataFrame(boundaries)
    boundaries_path = out_tbl / f"regime_boundaries_{metric_tag}.csv"
    boundaries_df.to_csv(boundaries_path, index=False)

    # 1) Regime map（距离条带）
    model_color = {
        "exponential": ps.OKABE_ITO["blue"],
        "stretched_exp": ps.OKABE_ITO["vermillion"],
        "power_law": ps.OKABE_ITO["gray"],
        "log": ps.OKABE_ITO["bluish_green"],
    }
    model_order = ["exponential", "stretched_exp", "power_law", "log"]
    model_label = {
        "exponential": "exp",
        "stretched_exp": "stretched-exp",
        "power_law": "power-law",
        "log": "log",
    }

    map_df = best.copy()
    if args.open_ended_right_km is None:
        map_df = map_df[~map_df["is_open_ended"]].copy()
    else:
        map_df.loc[map_df["is_open_ended"], "hi_km"] = float(args.open_ended_right_km)

    with ps.paper_style():
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        for _, row in map_df.iterrows():
            lo = float(row["lo_km"])
            hi = float(row["hi_km"])
            m = str(row["model"])
            if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
                continue
            ax.add_patch(Rectangle((lo, 0.0), hi - lo, 1.0, facecolor=model_color.get(m, ps.OKABE_ITO["black"]), linewidth=0))

        for _, b in boundaries_df.iterrows():
            x = float(b["boundary_km"])
            if np.isfinite(x):
                ax.axvline(x, color=ps.OKABE_ITO["black"], linestyle=":", linewidth=1.0, alpha=0.65)

        ax.set_ylim(0.0, 1.0)
        ax.set_yticks([])
        ax.set_xlabel(r"Distance to epicenter $r$ (km)")
        ax.set_title(f"Regime map by BIC-selected model ({metric_tag})")
        ps.despine(ax)

        handles = []
        for m in model_order:
            if (map_df["model"].astype(str) == m).any():
                handles.append(Rectangle((0, 0), 1, 1, facecolor=model_color[m], label=model_label[m]))
        if handles:
            ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=len(handles), frameon=False)
            fig.subplots_adjust(bottom=0.28)
        else:
            fig.tight_layout()

        fig_path = out_fig / f"regime_map_{metric_tag}.pdf"
        ps.save_figure(fig, fig_path)
        ps.save_figure(fig, fig_path.with_suffix(".png"), dpi=200)
        plt.close(fig)

    # 2) Bootstrap：模型胜率热力图
    n_boot = int(args.n_bootstrap)
    if n_boot > 0:
        rng = np.random.default_rng(int(args.seed))
        win_rows: list[dict] = []
        for dist_bin, sub in ts.groupby("distance_bin", sort=False, observed=True):
            sub = sub.copy()
            sub[cfg.y_col] = pd.to_numeric(sub[cfg.y_col], errors="coerce")
            sub["hours_since_quake"] = pd.to_numeric(sub["hours_since_quake"], errors="coerce")
            if cfg.y_std_col is not None and cfg.y_n_col is not None:
                sub[cfg.y_std_col] = pd.to_numeric(sub[cfg.y_std_col], errors="coerce")
                sub[cfg.y_n_col] = pd.to_numeric(sub[cfg.y_n_col], errors="coerce")

            # 有效点筛选交给 fit_relaxation_models_table，但 bootstrap 需要先做一次 mask
            fit_base = fit_relaxation_models_table(sub, cfg=cfg)
            if fit_base.empty:
                continue
            base_best = fit_base.loc[fit_base["bic"].idxmin()].to_dict()

            wins = {m: 0 for m in model_order}
            n_success = 0
            for _ in range(n_boot):
                sub_star = sub.copy()
                sigma = None
                if cfg.y_std_col is not None and cfg.y_n_col is not None:
                    std = pd.to_numeric(sub_star[cfg.y_std_col], errors="coerce").to_numpy(dtype=float)
                    n = pd.to_numeric(sub_star[cfg.y_n_col], errors="coerce").to_numpy(dtype=float)
                    se = std / np.sqrt(np.where(n > 0, n, np.nan))
                    sigma = np.where(np.isfinite(se), np.maximum(se, float(cfg.min_sigma)), np.nan)
                else:
                    sigma = None

                y = pd.to_numeric(sub_star[cfg.y_col], errors="coerce").to_numpy(dtype=float)
                if sigma is None:
                    # 没有 SE 的情况下，bootstrap 退化为对观测加一个很小噪声（主要用于 sanity check）
                    y_star = y + rng.normal(scale=1e-6, size=len(y))
                else:
                    eps = rng.normal(size=len(y))
                    y_star = y + sigma * eps
                sub_star[cfg.y_col] = y_star

                fit_star = fit_relaxation_models_table(sub_star, cfg=cfg)
                if fit_star.empty:
                    continue
                best_row = fit_star.loc[fit_star["bic"].idxmin()]
                wins[str(best_row["model"])] = wins.get(str(best_row["model"]), 0) + 1
                n_success += 1

            row = {
                "distance_bin": str(dist_bin),
                "base_best_model": str(base_best["model"]),
                "n_bootstrap": int(n_boot),
                "n_success": int(n_success),
                "success_rate": float(n_success) / float(n_boot),
            }
            for m in model_order:
                row[f"win_rate_{m}"] = float(wins.get(m, 0)) / float(n_success) if n_success > 0 else float("nan")
            win_rows.append(row)

        win_df = pd.DataFrame(win_rows)
        win_df["km_bin"] = win_df["distance_bin"].astype(str).apply(parse_km_bin)
        win_df["lo_km"] = win_df["km_bin"].apply(lambda b: float(b.lo))
        win_df["hi_km"] = win_df["km_bin"].apply(lambda b: float(b.hi))
        win_df = win_df.sort_values(["lo_km", "hi_km"], kind="stable").reset_index(drop=True)

        win_csv = out_fits / f"regime_bootstrap_winrates_{metric_tag}.csv"
        win_df.to_csv(win_csv, index=False)

        heat_bins = win_df["distance_bin"].astype(str).tolist()
        heat = np.vstack([win_df[f"win_rate_{m}"].to_numpy(dtype=float) for m in model_order])

        with ps.paper_style():
            fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
            im = ax.imshow(heat, aspect="auto", vmin=0.0, vmax=1.0, cmap="viridis")
            ax.set_yticks(range(len(model_order)))
            ax.set_yticklabels([model_label[m] for m in model_order])
            ax.set_xticks(range(len(heat_bins)))
            ax.set_xticklabels(heat_bins, rotation=45, ha="right")
            ax.set_xlabel("Distance bin")
            ax.set_title(f"Bootstrap win rates (n={n_boot}, {metric_tag})")
            ps.despine(ax)
            cb = fig.colorbar(im, ax=ax, shrink=0.88)
            cb.set_label("Win rate")
            fig.tight_layout()
            fig_path = out_fig / f"regime_bootstrap_winrates_{metric_tag}.pdf"
            ps.save_figure(fig, fig_path)
            ps.save_figure(fig, fig_path.with_suffix(".png"), dpi=200)
            plt.close(fig)

    print(f"Done. Wrote: {all_models_csv}")
    print(f"Done. Wrote: {best_csv}")
    print(f"Done. Wrote: {boundaries_path}")


if __name__ == "__main__":
    main()
