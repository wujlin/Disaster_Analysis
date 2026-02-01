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
    distance_band_order: tuple[str, ...] = ("0-25km", "25-50km", "50-100km", "100-200km", "200km+")
    distance_band_center_km: tuple[float, ...] = (12.5, 37.5, 75.0, 150.0, 300.0)
    plot_times_hours: tuple[float, ...] = (16.0, 40.0, 88.0, 160.0, 832.0)
    phi_vmin: float = 0.6
    phi_vmax: float = 1.6


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _nearest(values: np.ndarray, target: float) -> float:
    if values.size == 0:
        return float("nan")
    idx = int(np.argmin(np.abs(values - float(target))))
    return float(values[idx])


def _relaxation_model(t: np.ndarray, phi_0: float, phi_inf: float, tau: float) -> np.ndarray:
    return phi_inf + (phi_0 - phi_inf) * np.exp(-t / tau)


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
    required = {"hours_since_quake", "distance_band", "phi_aggregate"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"输入缺少列：{missing}（来自 {cfg.input_csv}）")

    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df["phi_aggregate"] = pd.to_numeric(df["phi_aggregate"], errors="coerce")
    df = df[df["hours_since_quake"].notna() & df["phi_aggregate"].notna()].copy()

    # 统一 band 顺序
    df["distance_band"] = df["distance_band"].astype(str)
    df = df[df["distance_band"].isin(set(cfg.distance_band_order))].copy()

    # φ(r,t) 矩阵（hours x bands）
    pivot = (
        df.pivot_table(index="hours_since_quake", columns="distance_band", values="phi_aggregate", aggfunc="mean")
        .reindex(columns=list(cfg.distance_band_order))
        .sort_index()
    )
    phi_rt = pivot.copy()
    out_matrix = out.tables / "phi_rt_matrix.csv"
    phi_rt.reset_index().to_csv(out_matrix, index=False)

    # B.2.1：φ(r) 多时间点曲线（取 nearest 窗口）
    times = phi_rt.index.to_numpy(dtype=float)
    picked_times = [(_nearest(times, t), float(t)) for t in cfg.plot_times_hours]
    picked_times = [(pt, t) for pt, t in picked_times if np.isfinite(pt)]

    r_centers = np.array(cfg.distance_band_center_km, dtype=float)

    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        for pt, t_req in picked_times:
            if pt not in phi_rt.index:
                continue
            y = phi_rt.loc[pt, list(cfg.distance_band_order)].to_numpy(dtype=float)
            ax.plot(r_centers, y, marker="o", label=f"{int(round(pt))}h (req {int(round(t_req))}h)")
        ax.axhline(1.0, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.7)
        ax.set_xlabel("Distance to epicenter r (km, band center)")
        ax.set_ylabel(r"$\phi_{agg}(r,t)=\sum n_{crisis}/\sum n_{baseline}$")
        ax.set_title(r"$\phi(r)$ at selected times (08:00 windows)")
        ax.legend(frameon=False, ncol=2)
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "phi_vs_r_multitime.png")
        plt.close(fig)

        # B.2.2：φ(t) 多距离带曲线
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        for band in cfg.distance_band_order:
            if band not in phi_rt.columns:
                continue
            ax.plot(phi_rt.index.to_numpy(dtype=float), phi_rt[band].to_numpy(dtype=float), marker="o", label=band)
        ax.axvline(0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.axhline(1.0, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.7)
        ax.set_xlabel("Hours since earthquake (PT, 08:00 windows)")
        ax.set_ylabel(r"$\phi_{agg}$")
        ax.set_title(r"$\phi(t)$ by distance band (08:00 windows)")
        ax.legend(frameon=False, ncol=3)
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "phi_vs_t_multiband.png")
        plt.close(fig)

        # B.2.3：φ(r,t) 热力图
        z = phi_rt.to_numpy(dtype=float)
        fig, ax = plt.subplots(figsize=(ps.FIGSIZE_FULL[0], ps.FIGSIZE_FULL[1] * 0.9))
        im = ax.imshow(z.T, aspect="auto", cmap="RdBu_r", vmin=float(cfg.phi_vmin), vmax=float(cfg.phi_vmax))
        ax.set_yticks(np.arange(len(cfg.distance_band_order), dtype=float))
        ax.set_yticklabels(list(cfg.distance_band_order))
        xs = phi_rt.index.to_numpy(dtype=float)
        if xs.size:
            step = max(1, int(xs.size / 8))
            xt = np.arange(0, xs.size, step)
            ax.set_xticks(xt)
        ax.set_xticklabels([f"{int(xs[j])}" for j in xt], rotation=0)
        ax.set_xlabel("Hours since earthquake (08:00 windows)")
        ax.set_ylabel("Distance band")
        ax.set_title(r"$\phi(r,t)$ heatmap")
        cb = fig.colorbar(im, ax=ax, shrink=0.9)
        cb.set_label(r"$\phi_{agg}$")
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "phi_rt_heatmap.png")
        plt.close(fig)

    # B.4：指数恢复拟合（每个距离带）
    try:
        from scipy.optimize import curve_fit  # type: ignore
    except ModuleNotFoundError:
        curve_fit = None

    fit_rows: list[dict] = []
    tau_rows: list[dict] = []

    for band, r_km in zip(cfg.distance_band_order, cfg.distance_band_center_km, strict=False):
        if band not in phi_rt.columns:
            continue
        series = phi_rt[band].dropna()
        t_all = series.index.to_numpy(dtype=float)
        y_all = series.to_numpy(dtype=float)

        mask = t_all >= float(cfg.fit_min_hours)
        if cfg.fit_max_hours is not None:
            mask &= t_all <= float(cfg.fit_max_hours)
        t = t_all[mask]
        y = y_all[mask]

        row = {
            "distance_band": band,
            "distance_center_km": float(r_km),
            "n_points": int(len(t)),
            "t_min": float(np.min(t)) if len(t) else float("nan"),
            "t_max": float(np.max(t)) if len(t) else float("nan"),
            "phi_0": float("nan"),
            "phi_inf": float("nan"),
            "tau": float("nan"),
            "sse": float("nan"),
            "r2": float("nan"),
            "fit_ok": 0,
        }

        if curve_fit is None or len(t) < 6:
            fit_rows.append(row)
            tau_rows.append({"distance_band": band, "distance_center_km": float(r_km), "tau": float("nan")})
            continue

        phi_0_guess = float(y[0])
        phi_inf_guess = float(y[-1])
        tau_guess = float(max(1.0, (np.max(t) - np.min(t)) / 3.0))
        p0 = [phi_0_guess, phi_inf_guess, tau_guess]
        bounds = ([0.0, 0.0, 1.0], [3.0, 3.0, 10000.0])

        try:
            popt, _ = curve_fit(_relaxation_model, t, y, p0=p0, bounds=bounds, maxfev=20000)
            phi_0, phi_inf, tau = (float(popt[0]), float(popt[1]), float(popt[2]))
            y_hat = _relaxation_model(t, phi_0, phi_inf, tau)
            resid = y - y_hat
            sse = float(np.sum(resid**2))
            sst = float(np.sum((y - float(np.mean(y))) ** 2))
            r2 = float(1.0 - sse / sst) if sst > 0 else float("nan")
            row.update({"phi_0": phi_0, "phi_inf": phi_inf, "tau": tau, "sse": sse, "r2": r2, "fit_ok": 1})
        except Exception:
            pass

        fit_rows.append(row)
        tau_rows.append({"distance_band": band, "distance_center_km": float(r_km), "tau": float(row["tau"])})

    fit_df = pd.DataFrame(fit_rows)
    tau_df = pd.DataFrame(tau_rows)
    out_fit = out.tables / "relaxation_fit_by_band.csv"
    out_tau = out.tables / "tau_vs_distance.csv"
    fit_df.to_csv(out_fit, index=False)
    tau_df.to_csv(out_tau, index=False)

    # τ(r) 图
    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        x = tau_df["distance_center_km"].to_numpy(dtype=float)
        y = tau_df["tau"].to_numpy(dtype=float)
        mask = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
        ax.scatter(x[mask], y[mask], s=70, color=ps.OKABE_ITO["vermillion"], alpha=0.85, linewidths=0)
        for band, r_km, tau in tau_df.itertuples(index=False):
            if np.isfinite(r_km) and np.isfinite(tau) and r_km > 0 and tau > 0:
                ax.text(float(r_km), float(tau), str(band), fontsize=8, ha="left", va="bottom")
        if int(np.sum(mask)) >= 1:
            ax.set_xscale("log")
            ax.set_yscale("log")
        else:
            ax.text(0.02, 0.98, "No valid $\\tau$ (fit failed / insufficient points)", transform=ax.transAxes, ha="left", va="top")
        ax.set_xlabel("Distance r (km, band center)")
        ax.set_ylabel(r"$\tau(r)$ (hours)")
        ax.set_title(r"Exponential recovery fit: $\tau(r)$")
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "tau_vs_distance.png")
        plt.close(fig)

    readme = f"""# Physical Model: $\\phi(r,t)$ (Task B)

本目录对应 `Opinion_PI.md` 的 **Task B**：
把 `outputs/population_redistribution/tables/redistribution_by_distance_band.csv` 里的 $\\phi_{{agg}}(r,t)$ 转成可视化 + 指数恢复拟合，提取 $\\tau(r)$。

## 输入

- `{cfg.input_csv}`

## 主要输出

- `tables/phi_rt_matrix.csv`：$\\phi(r,t)$ 矩阵（rows=hours_since_quake, cols=distance bands）
- `figures/phi_vs_r_multitime.*`：$\\phi(r)$ 多时间点曲线
- `figures/phi_vs_t_multiband.*`：$\\phi(t)$ 多距离带曲线
- `figures/phi_rt_heatmap.*`：$\\phi(r,t)$ 热力图
- `tables/relaxation_fit_by_band.csv`：指数恢复拟合参数（$\\phi_0,\\phi_\\infty,\\tau$）
- `tables/tau_vs_distance.csv`：$\\tau(r)$
- `figures/tau_vs_distance.*`：$\\tau(r)$ 图（log-log）

## 拟合窗口

- t >= {float(cfg.fit_min_hours)}h
"""
    if cfg.fit_max_hours is not None:
        readme += f"- t <= {float(cfg.fit_max_hours)}h\n"
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_matrix}")
    print(f"Done. Wrote: {out_fit}")
    print(f"Done. Wrote: {out_tau}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=Path("outputs/population_redistribution/tables/redistribution_by_distance_band.csv"),
        help="输入 CSV（来自 population_redistribution）",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/physical_model"), help="输出目录")
    parser.add_argument("--fit-min-hours", type=float, default=0.0, help="拟合使用的最小时间（小时）")
    parser.add_argument("--fit-max-hours", type=float, default=None, help="拟合使用的最大时间（小时，可选）")
    parser.add_argument(
        "--plot-times-hours",
        type=float,
        nargs="*",
        default=[16.0, 40.0, 88.0, 160.0, 832.0],
        help="用于 φ(r) 曲线的时间点（会取 nearest window）",
    )
    parser.add_argument("--phi-vmin", type=float, default=0.6, help="热力图 vmin")
    parser.add_argument("--phi-vmax", type=float, default=1.6, help="热力图 vmax")
    args = parser.parse_args()

    cfg = Config(
        input_csv=args.input_csv,
        output_dir=args.output_dir,
        fit_min_hours=float(args.fit_min_hours),
        fit_max_hours=float(args.fit_max_hours) if args.fit_max_hours is not None else None,
        plot_times_hours=tuple(float(x) for x in args.plot_times_hours),
        phi_vmin=float(args.phi_vmin),
        phi_vmax=float(args.phi_vmax),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()
