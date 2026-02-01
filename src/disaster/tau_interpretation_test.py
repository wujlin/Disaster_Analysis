from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    input_csv: Path
    output_dir: Path
    fit_min_hours: float = 0.0
    fit_max_hours: float | None = None
    recovery_threshold: float = 0.95
    distance_band_order: tuple[str, ...] = ("0-25km", "25-50km", "50-100km", "100-200km", "200km+")


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _relaxation_model(t: np.ndarray, y0: float, y_inf: float, tau: float) -> np.ndarray:
    return y_inf + (y0 - y_inf) * np.exp(-t / tau)


def _fit_relaxation_tau(t: np.ndarray, y: np.ndarray) -> dict:
    try:
        from scipy.optimize import curve_fit  # type: ignore
    except ModuleNotFoundError:
        curve_fit = None

    row = {
        "fit_ok": 0,
        "y0": float("nan"),
        "y_inf": float("nan"),
        "tau": float("nan"),
        "sse": float("nan"),
        "r2": float("nan"),
    }
    if curve_fit is None:
        return row

    mask = np.isfinite(t) & np.isfinite(y)
    t = t[mask].astype(float)
    y = y[mask].astype(float)
    if t.size < 6:
        return row

    t = t - float(np.min(t))
    y0_guess = float(y[0])
    y_inf_guess = float(y[-1])
    tau_guess = float(max(1.0, (float(np.max(t)) - float(np.min(t))) / 3.0))
    p0 = [y0_guess, y_inf_guess, tau_guess]
    bounds = ([0.0, -np.inf, 1.0], [np.inf, np.inf, 10000.0])

    try:
        popt, _ = curve_fit(_relaxation_model, t, y, p0=p0, bounds=bounds, maxfev=20000)
        y0, y_inf, tau = (float(popt[0]), float(popt[1]), float(popt[2]))
        y_hat = _relaxation_model(t, y0, y_inf, tau)
        resid = y - y_hat
        sse = float(np.sum(resid**2))
        sst = float(np.sum((y - float(np.mean(y))) ** 2))
        r2 = float(1.0 - sse / sst) if sst > 0 else float("nan")
        row.update({"fit_ok": 1, "y0": y0, "y_inf": y_inf, "tau": tau, "sse": sse, "r2": r2})
    except Exception:
        pass

    return row


def _first_time_geq(t: np.ndarray, y: np.ndarray, thr: float) -> float:
    mask = np.isfinite(t) & np.isfinite(y)
    t = t[mask].astype(float)
    y = y[mask].astype(float)
    if t.size == 0:
        return float("nan")
    idx = np.where(y >= float(thr))[0]
    if idx.size == 0:
        return float("nan")
    return float(t[int(idx[0])])


def run(cfg: Config) -> None:
    if not cfg.input_csv.exists():
        raise FileNotFoundError(f"未找到输入：{cfg.input_csv}")

    out = _output_dirs(cfg.output_dir)
    _ensure_dir(out.root)
    _ensure_dir(out.figures)
    _ensure_dir(out.tables)

    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    df = pd.read_csv(cfg.input_csv, parse_dates=["window_start_pt"])
    required = {"hours_since_quake", "distance_band", "phi_aggregate", "n_tiles_overlap", "crisis_mean_overlap"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"输入缺少列：{missing}（请用最新版 scripts/population_redistribution.py 重新生成）")

    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df["phi_aggregate"] = pd.to_numeric(df["phi_aggregate"], errors="coerce")
    df["n_tiles_overlap"] = pd.to_numeric(df["n_tiles_overlap"], errors="coerce")
    df["crisis_mean_overlap"] = pd.to_numeric(df["crisis_mean_overlap"], errors="coerce")
    df["distance_band"] = df["distance_band"].astype(str)
    df = df[df["distance_band"].isin(set(cfg.distance_band_order))].copy()

    pre = df[df["hours_since_quake"] < 0].copy()
    if pre.empty:
        raise SystemExit("未找到 hours_since_quake < 0 的震前窗口，无法做“相对震前”归一化。")

    pre_ref = (
        pre.groupby("distance_band", observed=True)
        .agg(
            pre_phi=("phi_aggregate", "mean"),
            pre_n_tiles_overlap=("n_tiles_overlap", "mean"),
            pre_crisis_mean_overlap=("crisis_mean_overlap", "mean"),
        )
        .reindex(list(cfg.distance_band_order))
    )
    pre_ref = pre_ref.reset_index()

    df = df.merge(pre_ref, on="distance_band", how="left")
    df["tile_count_ratio"] = np.where(
        pd.to_numeric(df["pre_n_tiles_overlap"], errors="coerce") > 0,
        df["n_tiles_overlap"] / df["pre_n_tiles_overlap"],
        np.nan,
    )
    df["crisis_mean_ratio"] = np.where(
        pd.to_numeric(df["pre_crisis_mean_overlap"], errors="coerce") > 0,
        df["crisis_mean_overlap"] / df["pre_crisis_mean_overlap"],
        np.nan,
    )

    df = df[df["hours_since_quake"].notna()].copy()
    df = df.sort_values(["hours_since_quake", "distance_band"], kind="stable")

    # 时序矩阵（便于外部复用）
    pivot_phi = (
        df.pivot_table(index="hours_since_quake", columns="distance_band", values="phi_aggregate", aggfunc="mean")
        .reindex(columns=list(cfg.distance_band_order))
        .sort_index()
    )
    pivot_tile_ratio = (
        df.pivot_table(index="hours_since_quake", columns="distance_band", values="tile_count_ratio", aggfunc="mean")
        .reindex(columns=list(cfg.distance_band_order))
        .sort_index()
    )
    pivot_mean_ratio = (
        df.pivot_table(index="hours_since_quake", columns="distance_band", values="crisis_mean_ratio", aggfunc="mean")
        .reindex(columns=list(cfg.distance_band_order))
        .sort_index()
    )

    out_phi = out.tables / "phi_aggregate_rt_matrix.csv"
    out_tile = out.tables / "tile_count_ratio_rt_matrix.csv"
    out_mean = out.tables / "crisis_mean_ratio_rt_matrix.csv"
    pivot_phi.reset_index().to_csv(out_phi, index=False)
    pivot_tile_ratio.reset_index().to_csv(out_tile, index=False)
    pivot_mean_ratio.reset_index().to_csv(out_mean, index=False)

    # 机制检验：哪个带的“tile 可见性”或“平均强度”恢复更快？
    rows: list[dict] = []
    for band in cfg.distance_band_order:
        if band not in pivot_phi.columns:
            continue
        t_all = pivot_phi.index.to_numpy(dtype=float)
        phi_all = pivot_phi[band].to_numpy(dtype=float)
        tile_all = pivot_tile_ratio[band].to_numpy(dtype=float)
        mean_all = pivot_mean_ratio[band].to_numpy(dtype=float)

        post_mask = t_all >= 0
        t_post = t_all[post_mask]
        phi_post = phi_all[post_mask]
        tile_post = tile_all[post_mask]
        mean_post = mean_all[post_mask]

        # 拟合窗口
        fit_mask = t_post >= float(cfg.fit_min_hours)
        if cfg.fit_max_hours is not None:
            fit_mask &= t_post <= float(cfg.fit_max_hours)

        t_fit = t_post[fit_mask]
        phi_fit = phi_post[fit_mask]
        tile_fit = tile_post[fit_mask]
        mean_fit = mean_post[fit_mask]

        # min & recover time（只用于 post）
        def _min_and_time(t: np.ndarray, y: np.ndarray) -> tuple[float, float]:
            m = np.isfinite(t) & np.isfinite(y)
            if not np.any(m):
                return float("nan"), float("nan")
            tt = t[m].astype(float)
            yy = y[m].astype(float)
            i = int(np.argmin(yy))
            return float(yy[i]), float(tt[i])

        tile_min, tile_tmin = _min_and_time(t_post, tile_post)
        mean_min, mean_tmin = _min_and_time(t_post, mean_post)

        tile_t95 = _first_time_geq(t_post, tile_post, float(cfg.recovery_threshold))
        tile_t100 = _first_time_geq(t_post, tile_post, 1.0)
        mean_t95 = _first_time_geq(t_post, mean_post, float(cfg.recovery_threshold))
        mean_t100 = _first_time_geq(t_post, mean_post, 1.0)

        phi_fit_row = _fit_relaxation_tau(t_fit, phi_fit)
        tile_fit_row = _fit_relaxation_tau(t_fit, tile_fit)
        mean_fit_row = _fit_relaxation_tau(t_fit, mean_fit)

        rows.append(
            {
                "distance_band": band,
                "recovery_threshold": float(cfg.recovery_threshold),
                "fit_min_hours": float(cfg.fit_min_hours),
                "fit_max_hours": float(cfg.fit_max_hours) if cfg.fit_max_hours is not None else float("nan"),
                "tile_ratio_min": float(tile_min),
                "tile_ratio_t_at_min": float(tile_tmin),
                "tile_ratio_t_geq_thr": float(tile_t95),
                "tile_ratio_t_geq_1": float(tile_t100),
                "crisis_mean_ratio_min": float(mean_min),
                "crisis_mean_ratio_t_at_min": float(mean_tmin),
                "crisis_mean_ratio_t_geq_thr": float(mean_t95),
                "crisis_mean_ratio_t_geq_1": float(mean_t100),
                "tau_phi_hours": float(phi_fit_row["tau"]),
                "tau_phi_r2": float(phi_fit_row["r2"]),
                "tau_phi_fit_ok": int(phi_fit_row["fit_ok"]),
                "tau_tile_hours": float(tile_fit_row["tau"]),
                "tau_tile_r2": float(tile_fit_row["r2"]),
                "tau_tile_fit_ok": int(tile_fit_row["fit_ok"]),
                "tau_crisis_mean_hours": float(mean_fit_row["tau"]),
                "tau_crisis_mean_r2": float(mean_fit_row["r2"]),
                "tau_crisis_mean_fit_ok": int(mean_fit_row["fit_ok"]),
            }
        )

    out_table = out.tables / "tau_interpretation_hypothesis_test.csv"
    out_df = pd.DataFrame(rows)
    out_df.to_csv(out_table, index=False)

    # figures
    with ps.paper_style():
        import matplotlib.pyplot as plt

        def _plot_ratio(pivot: pd.DataFrame, *, ylabel: str, title: str, out_name: str) -> None:
            fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
            for band in cfg.distance_band_order:
                if band not in pivot.columns:
                    continue
                ax.plot(pivot.index.to_numpy(dtype=float), pivot[band].to_numpy(dtype=float), marker="o", label=band)
            ax.axvline(0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
            ax.axhline(1.0, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.7)
            ax.axhline(float(cfg.recovery_threshold), color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.0, alpha=0.6)
            ax.set_xlabel("Hours since earthquake (PT, 08:00 windows)")
            ax.set_ylabel(ylabel)
            ax.set_title(title)
            ax.legend(frameon=False, ncol=3)
            ps.despine(ax)
            fig.tight_layout()
            save_png_and_pdf(ps, fig, out.figures / out_name)
            plt.close(fig)

        _plot_ratio(
            pivot_tile_ratio,
            ylabel=r"tile_count_ratio = n_tiles_overlap / pre_n_tiles_overlap",
            title="Reachable tile proxy (overlap tiles) by distance band (normalized to pre)",
            out_name="tile_count_ratio_timeseries.png",
        )
        _plot_ratio(
            pivot_mean_ratio,
            ylabel=r"crisis_mean_ratio = crisis_mean_overlap / pre_crisis_mean_overlap",
            title="Mean n_crisis per tile (overlap tiles) by distance band (normalized to pre)",
            out_name="crisis_mean_ratio_timeseries.png",
        )

    readme = f"""# τ(r) 物理解释 - 最简假设检验（无需外部数据）

目标：解释为何 `50-100km` 距离带在 $\\tau(r)$ 拟合中“恢复最快”，并区分三类机制假说：

- A（损毁梯度）：平均 n_crisis 回升更快
- B（通达性/可达范围）：可见 tile 数回升更快
- C（吸引力）：平均 n_crisis 回升更快（与 A 在本检验里同口径）

## 输入

- `{cfg.input_csv}`

## 关键口径

- 可达 tile 代理：`n_tiles_overlap`（baseline 与 crisis 同时非空的 tile 数，避免“新 tiles”造成口径漂移）
- 归一化：相对震前窗口均值（hours_since_quake < 0）
- tile_count_ratio(t) = n_tiles_overlap(t) / pre_n_tiles_overlap
- crisis_mean_ratio(t) = crisis_mean_overlap(t) / pre_crisis_mean_overlap
- recovery_threshold = {float(cfg.recovery_threshold)}
- 拟合窗口：t ∈ [{float(cfg.fit_min_hours)}, {float(cfg.fit_max_hours) if cfg.fit_max_hours is not None else "inf"}] hours

## 产物

- `tables/tau_interpretation_hypothesis_test.csv`：每个距离带的最小值、达到阈值时间、以及指数拟合 τ（若 scipy 可用）
- `tables/tile_count_ratio_rt_matrix.csv`：tile_count_ratio(r,t)
- `tables/crisis_mean_ratio_rt_matrix.csv`：crisis_mean_ratio(r,t)
- `figures/tile_count_ratio_timeseries.*`
- `figures/crisis_mean_ratio_timeseries.*`
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_table}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=Path("outputs/population_redistribution/tables/redistribution_by_distance_band.csv"),
        help="population_redistribution 输出的距离带汇总表",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/tau_interpretation_test"),
        help="输出目录",
    )
    parser.add_argument("--fit-min-hours", type=float, default=0.0, help="拟合窗口下界（默认 t>=0）")
    parser.add_argument("--fit-max-hours", type=float, default=None, help="拟合窗口上界（默认不限制）")
    parser.add_argument("--recovery-threshold", type=float, default=0.95, help="判定“恢复”的阈值（相对震前归一化）")
    args = parser.parse_args()

    cfg = Config(
        input_csv=args.input_csv,
        output_dir=args.output_dir,
        fit_min_hours=float(args.fit_min_hours),
        fit_max_hours=float(args.fit_max_hours) if args.fit_max_hours is not None else None,
        recovery_threshold=float(args.recovery_threshold),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()
