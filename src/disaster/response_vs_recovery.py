from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.cross_disaster_phi_tau import load_catalog
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    catalog: Path
    output_root: Path
    output_dir: Path
    epicenter_radius_km: float = 25.0
    response_max_hours: float | None = None
    min_tau_r2: float | None = None


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _load_phi_band(output_root: Path, slug: str, *, band: str = "0-25km") -> pd.DataFrame:
    p = output_root / slug / "population_redistribution" / "tables" / "redistribution_by_distance_band.csv"
    if not p.exists():
        raise FileNotFoundError(f"未找到：{p}（请先生成 population_redistribution 输出）")
    df = pd.read_csv(p, parse_dates=["window_start_pt"])
    need = {"hours_since_quake", "distance_band", "phi_aggregate"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise SystemExit(f"{p} 缺少列：{miss}")
    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df["phi_aggregate"] = pd.to_numeric(df["phi_aggregate"], errors="coerce")
    df["distance_band"] = df["distance_band"].astype(str)
    df = df[df["distance_band"] == str(band)].copy()
    return df.dropna(subset=["hours_since_quake", "phi_aggregate"]).sort_values("hours_since_quake", kind="stable")


def _phi_max(df: pd.DataFrame, *, max_hours: float | None) -> tuple[float, float]:
    sub = df[df["hours_since_quake"] >= 0].copy()
    if max_hours is not None:
        sub = sub[sub["hours_since_quake"] <= float(max_hours)].copy()
    if sub.empty:
        return float("nan"), float("nan")
    idx = int(pd.to_numeric(sub["phi_aggregate"], errors="coerce").idxmax())
    phi_max = float(sub.loc[idx, "phi_aggregate"])
    t_at_max = float(sub.loc[idx, "hours_since_quake"])
    return phi_max, t_at_max


def _load_tau_tiles(output_root: Path, slug: str) -> pd.DataFrame:
    p = output_root / slug / "tau_continuous_fit" / "tables" / "tile_level_tau.csv"
    if not p.exists():
        raise FileNotFoundError(f"未找到：{p}（请先生成 tau_continuous_fit 输出）")
    df = pd.read_csv(p)
    need = {"distance_km", "tau_hours", "tau_r2"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise SystemExit(f"{p} 缺少列：{miss}")
    df["distance_km"] = pd.to_numeric(df["distance_km"], errors="coerce")
    df["tau_hours"] = pd.to_numeric(df["tau_hours"], errors="coerce")
    df["tau_r2"] = pd.to_numeric(df["tau_r2"], errors="coerce")
    return df.dropna(subset=["distance_km", "tau_hours"]).copy()


def _summarize_tau(df: pd.DataFrame, *, r_max: float, min_r2: float | None) -> dict:
    sub = df[df["distance_km"] < float(r_max)].copy()
    if min_r2 is not None:
        sub = sub[pd.to_numeric(sub["tau_r2"], errors="coerce") >= float(min_r2)].copy()
    tau = pd.to_numeric(sub["tau_hours"], errors="coerce").to_numpy(dtype=float)
    tau = tau[np.isfinite(tau) & (tau > 0)]
    if tau.size == 0:
        return {"n_tiles_tau": 0, "tau_median_hours": float("nan"), "tau_mean_hours": float("nan")}
    return {
        "n_tiles_tau": int(tau.size),
        "tau_median_hours": float(np.nanmedian(tau)),
        "tau_mean_hours": float(np.nanmean(tau)),
    }


def _pearsonr(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    if x.size < 2:
        return float("nan")
    x = x - float(np.mean(x))
    y = y - float(np.mean(y))
    denom = float(np.sqrt(np.sum(x**2) * np.sum(y**2)))
    if denom <= 0:
        return float("nan")
    return float(np.sum(x * y) / denom)


def _spearmanr(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    if x.size < 2:
        return float("nan")
    rx = pd.Series(x).rank(method="average").to_numpy(dtype=float)
    ry = pd.Series(y).rank(method="average").to_numpy(dtype=float)
    return _pearsonr(rx, ry)


def run(cfg: Config) -> None:
    specs = load_catalog(cfg.catalog)
    _ensure_dir(cfg.output_dir)
    _ensure_dir(cfg.output_dir / "tables")
    _ensure_dir(cfg.output_dir / "figures")

    rows: list[dict] = []
    for spec in specs:
        phi_df = _load_phi_band(cfg.output_root, spec.slug, band="0-25km")
        phi_max, t_at_max = _phi_max(phi_df, max_hours=cfg.response_max_hours)
        response_intensity = float(phi_max - 1.0) if np.isfinite(phi_max) else float("nan")

        tau_df = _load_tau_tiles(cfg.output_root, spec.slug)
        tau_sum = _summarize_tau(tau_df, r_max=float(cfg.epicenter_radius_km), min_r2=cfg.min_tau_r2)
        tau_median_hours = float(tau_sum["tau_median_hours"])
        tau_mean_hours = float(tau_sum["tau_mean_hours"])
        tau_days = float(tau_median_hours / 24.0) if np.isfinite(tau_median_hours) else float("nan")
        recovery_speed = float(1.0 / tau_days) if np.isfinite(tau_days) and tau_days > 0 else float("nan")

        rows.append(
            {
                "slug": spec.slug,
                "name": spec.name,
                "event_type": spec.event_type,
                "epicenter_radius_km": float(cfg.epicenter_radius_km),
                "response_max_hours": float(cfg.response_max_hours) if cfg.response_max_hours is not None else float("nan"),
                "phi_max_0_25": float(phi_max),
                "phi_max_hours": float(t_at_max),
                "response_intensity": float(response_intensity),
                "min_tau_r2": float(cfg.min_tau_r2) if cfg.min_tau_r2 is not None else float("nan"),
                "tau_median_hours_0_25": float(tau_median_hours),
                "tau_mean_hours_0_25": float(tau_mean_hours),
                "tau_median_days_0_25": float(tau_days),
                "recovery_speed_per_day": float(recovery_speed),
                "n_tiles_tau_0_25": int(tau_sum["n_tiles_tau"]),
            }
        )

    out_df = pd.DataFrame(rows)
    out_csv = cfg.output_dir / "tables" / "response_vs_recovery_by_disaster.csv"
    out_df.to_csv(out_csv, index=False)

    x = pd.to_numeric(out_df["response_intensity"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(out_df["recovery_speed_per_day"], errors="coerce").to_numpy(dtype=float)
    pearson_r = _pearsonr(x, y)
    spearman_rho = _spearmanr(x, y)
    n_used = int(np.sum(np.isfinite(x) & np.isfinite(y)))

    corr_df = pd.DataFrame(
        [
            {
                "n": int(n_used),
                "pearson_r": float(pearson_r),
                "spearman_rho": float(spearman_rho),
            }
        ]
    )
    out_corr = cfg.output_dir / "tables" / "correlation_summary.csv"
    corr_df.to_csv(out_corr, index=False)

    # plot
    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        mask = np.isfinite(x) & np.isfinite(y)
        ax.scatter(x[mask], y[mask], s=90, color=ps.OKABE_ITO["blue"], alpha=0.85, linewidths=0)

        for _, r in out_df.iterrows():
            xi = float(pd.to_numeric(r["response_intensity"], errors="coerce"))
            yi = float(pd.to_numeric(r["recovery_speed_per_day"], errors="coerce"))
            if not (np.isfinite(xi) and np.isfinite(yi)):
                continue
            ax.text(xi, yi, str(r["slug"]), fontsize=8, ha="left", va="bottom")

        # 简单线性趋势线（仅用于视觉）
        if n_used >= 2:
            xx = x[mask]
            yy = y[mask]
            A = np.vstack([np.ones_like(xx), xx]).T
            beta, *_ = np.linalg.lstsq(A, yy, rcond=None)
            b0, b1 = float(beta[0]), float(beta[1])
            xs = np.linspace(float(np.min(xx)), float(np.max(xx)), 50)
            ys = b0 + b1 * xs
            ax.plot(xs, ys, color=ps.OKABE_ITO["vermillion"], linewidth=2.0, alpha=0.8, label="OLS trend")
            ax.legend(frameon=False)

        ax.axvline(0.0, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.6)
        ax.set_xlabel(r"response_intensity = $\max_t \phi_{0-25}(t) - 1$")
        ax.set_ylabel(r"recovery_speed = $1/\tau_{0-25}$ (1/day)")
        ax.set_title(f"Response intensity vs recovery speed (n={n_used}, Pearson r={pearson_r:.3f})")
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, cfg.output_dir / "figures" / "response_vs_recovery_scatter.png")
        plt.close(fig)

    readme = f"""# Response Intensity vs Recovery Speed

检验问题（简化版）：

- response_intensity = φ_max(0–25km) - 1
- recovery_speed = 1 / τ(0–25km)

## 计算口径

### response_intensity（来自 population_redistribution）

- 输入：`outputs/<slug>/population_redistribution/tables/redistribution_by_distance_band.csv`
- 取距离带：`0-25km`
- φ(t)=`phi_aggregate`（n_crisis_sum / n_baseline_sum）
- φ_max：取 t>=0 且 t<=response_max_hours（若指定）范围内的最大值

### τ(0–25km)（来自 tau_continuous_fit）

- 输入：`outputs/<slug>/tau_continuous_fit/tables/tile_level_tau.csv`
- 筛选：distance_km < {float(cfg.epicenter_radius_km)}
- τ：取 tile-level τ 的 **median**（可选用 min_tau_r2 过滤）

## 输出

- `tables/response_vs_recovery_by_disaster.csv`
- `tables/correlation_summary.csv`
- `figures/response_vs_recovery_scatter.*`
"""
    (cfg.output_dir / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_csv}")
    print(f"Done. Wrote: {out_corr}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog.csv"), help="灾难配置表（CSV）")
    parser.add_argument("--output-root", type=Path, default=Path("outputs"), help="outputs 根目录")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/cross_disaster_comparison/response_vs_recovery"),
        help="输出目录",
    )
    parser.add_argument("--epicenter-radius-km", type=float, default=25.0, help="震中半径（km，默认 25）")
    parser.add_argument("--response-max-hours", type=float, default=None, help="计算 φ_max 时的最大小时数（默认不限制）")
    parser.add_argument("--min-tau-r2", type=float, default=None, help="tile-level τ 的最小 R2 过滤阈值（默认不滤）")
    args = parser.parse_args()

    cfg = Config(
        catalog=args.catalog,
        output_root=args.output_root,
        output_dir=args.output_dir,
        epicenter_radius_km=float(args.epicenter_radius_km),
        response_max_hours=float(args.response_max_hours) if args.response_max_hours is not None else None,
        min_tau_r2=float(args.min_tau_r2) if args.min_tau_r2 is not None else None,
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()

