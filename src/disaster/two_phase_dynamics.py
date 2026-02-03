from __future__ import annotations

import argparse
import json
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
    summary_dir: Path

    phi_col: str = "phi_aggregate"
    distance_band_order: tuple[str, ...] = ("0-25km", "25-50km", "50-100km", "100-200km", "200km+")

    # classification: sign of mean(phi-1) in [0, early_hours]
    early_hours: float = 72.0
    neutral_eps: float = 0.02

    # peak search window (hours since quake, inclusive)
    peak_min_hours: float = 0.0
    peak_max_hours: float | None = None

    # fitting windows (hours since quake, inclusive)
    fit_min_hours: float = 0.0
    fit_max_hours: float | None = None

    min_points_growth: int = 5
    min_points_decay: int = 10
    min_signal_abs: float = 0.02  # max |phi-1| 小于该阈值则跳过拟合

    t_shift_hours: float = 1.0  # for power-law decay


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _out_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _aic_bic_from_sse(sse: float, *, n: int, k: int) -> tuple[float, float]:
    if n <= 0 or not np.isfinite(sse) or sse <= 0:
        return float("nan"), float("nan")
    n_f = float(n)
    aic = n_f * float(np.log(sse / n_f)) + 2.0 * float(k)
    bic = n_f * float(np.log(sse / n_f)) + float(k) * float(np.log(n_f))
    return float(aic), float(bic)


def _sse(y: np.ndarray, yhat: np.ndarray) -> float:
    r = y - yhat
    return float(np.sum(r * r))


def _r2(y: np.ndarray, yhat: np.ndarray) -> float:
    resid = y - yhat
    sse = float(np.sum(resid**2))
    sst = float(np.sum((y - float(np.mean(y))) ** 2))
    return float(1.0 - sse / sst) if sst > 0 else float("nan")


def _load_phi_by_band(
    *,
    output_root: Path,
    slug: str,
    phi_col: str,
    band_order: tuple[str, ...],
) -> pd.DataFrame:
    csv_path = output_root / slug / "population_redistribution" / "tables" / "redistribution_by_distance_band.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"未找到：{csv_path}")

    df = pd.read_csv(csv_path, parse_dates=["window_start_pt"])
    required = {"hours_since_quake", "distance_band", phi_col}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"输入缺少列：{missing}（来自 {csv_path}）")

    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df[phi_col] = pd.to_numeric(df[phi_col], errors="coerce")
    df["distance_band"] = df["distance_band"].astype(str)
    df = df.dropna(subset=["hours_since_quake", phi_col]).copy()
    df = df[df["distance_band"].isin(set(band_order))].copy()

    pivot = (
        df.pivot_table(index="hours_since_quake", columns="distance_band", values=phi_col, aggfunc="mean")
        .reindex(columns=list(band_order))
        .sort_index()
    )
    return pivot


def _classify_band(t: np.ndarray, phi: np.ndarray, *, early_hours: float, eps: float) -> tuple[str, float]:
    t = np.asarray(t, dtype=float)
    phi = np.asarray(phi, dtype=float)
    ok = np.isfinite(t) & np.isfinite(phi) & (t >= 0) & (t <= float(early_hours))
    if int(np.sum(ok)) == 0:
        return "unknown", float("nan")
    dev = phi[ok] - 1.0
    m = float(np.mean(dev))
    if m > float(eps):
        return "inflow", float(m)
    if m < -float(eps):
        return "outflow", float(m)
    return "neutral", float(m)


def _find_peak_time(t: np.ndarray, abs_dev: np.ndarray, *, t_min: float, t_max: float | None) -> tuple[float, float]:
    t = np.asarray(t, dtype=float)
    abs_dev = np.asarray(abs_dev, dtype=float)
    ok = np.isfinite(t) & np.isfinite(abs_dev) & (t >= float(t_min))
    if t_max is not None:
        ok &= t <= float(t_max)
    if int(np.sum(ok)) == 0:
        return float("nan"), float("nan")
    tt = t[ok]
    yy = abs_dev[ok]
    i = int(np.nanargmax(yy))
    return float(tt[i]), float(yy[i])


def _growth_model(t: np.ndarray, a: float, tau: float, *, y0: float) -> np.ndarray:
    # y(t) = A - (A - y0) * exp(-t/tau), ensures y(0)=y0
    return float(a) - (float(a) - float(y0)) * np.exp(-t / float(tau))


def _fit_growth_saturating_exp(t: np.ndarray, y: np.ndarray) -> dict:
    """
    对增长段拟合饱和增长：
      y(t) = A - (A - y0) exp(-t/tau_in)
    其中 y0 固定为 t=0（段起点）的观测值，拟合参数为 (A, tau_in)。
    """
    try:
        from scipy.optimize import curve_fit  # type: ignore
    except ModuleNotFoundError as e:
        raise SystemExit("缺少依赖：scipy（拟合需要）。请先安装 scipy。") from e

    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(t) & np.isfinite(y) & (t >= 0) & (y >= 0)
    t = t[ok]
    y = y[ok]
    if t.size < 2:
        return {"fit_ok": 0}

    y0 = float(y[0])
    y_max = float(np.max(y))
    t_span = float(np.max(t) - np.min(t))

    a0 = max(y_max, y0 + 1e-6)
    tau0 = max(1.0, t_span / 3.0)
    tau_hi = max(2000.0, 3.0 * float(np.max(t)))

    try:
        popt, _ = curve_fit(
            lambda tt, a, tau: _growth_model(tt, a, tau, y0=float(y0)),
            t,
            y,
            p0=[a0, tau0],
            bounds=([y_max, 0.1], [np.inf, tau_hi]),
            maxfev=20000,
        )
        a, tau = float(popt[0]), float(popt[1])
        yhat = _growth_model(t, a, tau, y0=float(y0))
        sse = _sse(y, yhat)
        r2 = _r2(y, yhat)
        aic, bic = _aic_bic_from_sse(sse, n=int(t.size), k=2)
        return {
            "fit_ok": 1,
            "y0": float(y0),
            "A": float(a),
            "tau_in_hours": float(tau),
            "sse": float(sse),
            "r2": float(r2),
            "aic": float(aic),
            "bic": float(bic),
        }
    except Exception:
        return {"fit_ok": 0}


def _exp_decay(t: np.ndarray, a: float, tau: float) -> np.ndarray:
    return float(a) * np.exp(-t / float(tau))


def _power_decay(t: np.ndarray, a: float, beta: float, *, t_shift: float) -> np.ndarray:
    return float(a) * np.power(t + float(t_shift), -float(beta))


def _fit_decay_models(t: np.ndarray, y: np.ndarray, *, t_shift: float) -> dict[str, dict]:
    try:
        from scipy.optimize import curve_fit  # type: ignore
    except ModuleNotFoundError as e:
        raise SystemExit("缺少依赖：scipy（拟合需要）。请先安装 scipy。") from e

    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(t) & np.isfinite(y) & (t >= 0) & (y >= 0)
    t = t[ok]
    y = y[ok]
    if t.size < 2:
        return {}

    a0 = float(max(1e-6, y[0]))
    tau0 = float(max(1.0, (float(np.max(t)) - float(np.min(t))) / 3.0))
    tau_hi = float(max(2000.0, 3.0 * float(np.max(t))))

    out: dict[str, dict] = {}

    try:
        popt, _ = curve_fit(
            lambda tt, a, tau: _exp_decay(tt, a, tau),
            t,
            y,
            p0=[a0, tau0],
            bounds=([0.0, 0.1], [np.inf, tau_hi]),
            maxfev=20000,
        )
        a, tau = float(popt[0]), float(popt[1])
        yhat = _exp_decay(t, a, tau)
        sse = _sse(y, yhat)
        r2 = _r2(y, yhat)
        aic, bic = _aic_bic_from_sse(sse, n=int(t.size), k=2)
        out["exponential"] = {
            "fit_ok": 1,
            "A": a,
            "tau_out_hours": tau,
            "sse": sse,
            "r2": r2,
            "aic": aic,
            "bic": bic,
        }
    except Exception:
        out["exponential"] = {"fit_ok": 0}

    try:
        popt, _ = curve_fit(
            lambda tt, a, beta: _power_decay(tt, a, beta, t_shift=float(t_shift)),
            t,
            y,
            p0=[a0, 0.5],
            bounds=([0.0, 0.01], [np.inf, 5.0]),
            maxfev=20000,
        )
        a, beta = float(popt[0]), float(popt[1])
        yhat = _power_decay(t, a, beta, t_shift=float(t_shift))
        sse = _sse(y, yhat)
        r2 = _r2(y, yhat)
        aic, bic = _aic_bic_from_sse(sse, n=int(t.size), k=2)
        out["power_law"] = {
            "fit_ok": 1,
            "A": a,
            "beta": beta,
            "t_shift_hours": float(t_shift),
            "sse": sse,
            "r2": r2,
            "aic": aic,
            "bic": bic,
        }
    except Exception:
        out["power_law"] = {"fit_ok": 0}

    return out


def _plot_phi_timeseries(
    *,
    phi_rt: pd.DataFrame,
    cfg: Config,
    peak_by_band: dict[str, float],
    out_path: Path,
    title: str,
) -> None:
    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    import matplotlib.pyplot as plt

    bands = list(cfg.distance_band_order)
    times = phi_rt.index.to_numpy(dtype=float)

    with ps.paper_style():
        fig, axes = plt.subplots(len(bands), 1, figsize=(ps.FIGSIZE_FULL[0], 1.8 * len(bands)), sharex=True)
        if len(bands) == 1:
            axes = [axes]

        for ax, band in zip(axes, bands, strict=False):
            if band not in phi_rt.columns:
                continue
            phi = pd.to_numeric(phi_rt[band], errors="coerce").to_numpy(dtype=float)
            t = times.copy()
            ok = np.isfinite(t) & np.isfinite(phi)
            t = t[ok]
            phi = phi[ok]

            # plot line
            ax.plot(t, phi, color=ps.OKABE_ITO["gray"], linewidth=1.2, alpha=0.8)

            # color points by sign of phi-1
            mask_pos = phi >= 1.0
            ax.scatter(t[mask_pos], phi[mask_pos], s=18, color=ps.OKABE_ITO["vermillion"], alpha=0.9, linewidths=0)
            ax.scatter(t[~mask_pos], phi[~mask_pos], s=18, color=ps.OKABE_ITO["blue"], alpha=0.9, linewidths=0)

            # reference lines
            ax.axvline(0.0, color=ps.OKABE_ITO["black"], linestyle=":", linewidth=1.0, alpha=0.7)
            ax.axhline(1.0, color=ps.OKABE_ITO["black"], linestyle="--", linewidth=1.0, alpha=0.5)

            t_peak = float(peak_by_band.get(band, float("nan")))
            if np.isfinite(t_peak):
                ax.axvline(t_peak, color=ps.OKABE_ITO["orange"], linestyle="--", linewidth=1.2, alpha=0.85)

            ax.set_ylabel(band)
            ps.despine(ax)

        axes[-1].set_xlabel("Hours since disaster (PT windows)")
        fig.suptitle(title, y=0.995)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out_path)
        plt.close(fig)


def run(cfg: Config) -> None:
    specs = load_catalog(cfg.catalog)

    out_summary = _out_dirs(cfg.summary_dir)
    _ensure_dir(out_summary.root)
    _ensure_dir(out_summary.figures)
    _ensure_dir(out_summary.tables)

    all_rows: list[dict] = []

    for spec in specs:
        slug = spec.slug
        name = spec.name
        event_type = spec.event_type

        phi_rt = _load_phi_by_band(output_root=cfg.output_root, slug=slug, phi_col=cfg.phi_col, band_order=cfg.distance_band_order)

        # keep full for plotting; for fitting apply fit window below
        times_all = phi_rt.index.to_numpy(dtype=float)

        band_rows: list[dict] = []
        peak_by_band: dict[str, float] = {}

        for band in cfg.distance_band_order:
            if band not in phi_rt.columns:
                continue

            phi_all = pd.to_numeric(phi_rt[band], errors="coerce").to_numpy(dtype=float)
            ok = np.isfinite(times_all) & np.isfinite(phi_all)
            t = times_all[ok].astype(float)
            phi = phi_all[ok].astype(float)

            # fitting window
            win = (t >= float(cfg.fit_min_hours)) & (t <= float(cfg.fit_max_hours) if cfg.fit_max_hours is not None else True)
            t_fit = t[win]
            phi_fit = phi[win]

            signed_dev = phi_fit - 1.0
            abs_dev = np.abs(signed_dev)
            max_abs = float(np.nanmax(abs_dev)) if abs_dev.size else float("nan")

            cls, mean_dev_early = _classify_band(t_fit, phi_fit, early_hours=float(cfg.early_hours), eps=float(cfg.neutral_eps))

            # peak in the (peak window) based on abs_dev
            t_peak, peak_abs = _find_peak_time(
                t_fit,
                abs_dev,
                t_min=float(cfg.peak_min_hours),
                t_max=float(cfg.peak_max_hours) if cfg.peak_max_hours is not None else None,
            )
            peak_by_band[band] = float(t_peak) if np.isfinite(t_peak) else float("nan")

            phi_at_peak = float("nan")
            if np.isfinite(t_peak):
                # nearest point (times are discrete)
                i = int(np.argmin(np.abs(t_fit - float(t_peak))))
                phi_at_peak = float(phi_fit[i]) if i < phi_fit.size else float("nan")

            row = {
                "slug": slug,
                "name": name,
                "event_type": event_type,
                "distance_band": band,
                "fit_min_hours": float(cfg.fit_min_hours),
                "fit_max_hours": float(cfg.fit_max_hours) if cfg.fit_max_hours is not None else float("nan"),
                "peak_min_hours": float(cfg.peak_min_hours),
                "peak_max_hours": float(cfg.peak_max_hours) if cfg.peak_max_hours is not None else float("nan"),
                "early_hours": float(cfg.early_hours),
                "class": cls,
                "mean_dev_0_early": float(mean_dev_early),
                "n_points_total": int(t_fit.size),
                "max_abs_dev": float(max_abs),
                "t_peak_hours": float(t_peak),
                "phi_at_peak": float(phi_at_peak),
                "abs_dev_at_peak": float(peak_abs),
            }

            # two-phase fitting on y=|phi-1|
            if (not np.isfinite(t_peak)) or (not np.isfinite(max_abs)) or (max_abs < float(cfg.min_signal_abs)):
                band_rows.append(
                    {
                        **row,
                        "growth_fit_ok": 0,
                        "growth_tau_in_hours": float("nan"),
                        "growth_A": float("nan"),
                        "growth_r2": float("nan"),
                        "growth_bic": float("nan"),
                        "decay_fit_ok": 0,
                        "decay_best_model": "",
                        "decay_exp_tau_out_hours": float("nan"),
                        "decay_pl_beta": float("nan"),
                        "decay_r2": float("nan"),
                        "decay_bic": float("nan"),
                        "n_points_growth": 0,
                        "n_points_decay": 0,
                    }
                )
                continue

            # growth: [t0, t_peak]
            gmask = (t_fit >= float(cfg.fit_min_hours)) & (t_fit <= float(t_peak))
            tg = t_fit[gmask]
            yg = abs_dev[gmask]
            # shift start to 0
            if tg.size > 0:
                tg_rel = tg - float(np.min(tg))
            else:
                tg_rel = tg

            growth = {"fit_ok": 0}
            if tg_rel.size >= int(cfg.min_points_growth):
                growth = _fit_growth_saturating_exp(tg_rel, yg)

            # decay: [t_peak, t_end]
            dmask = t_fit >= float(t_peak)
            td = t_fit[dmask]
            yd = abs_dev[dmask]
            td_rel = td - float(t_peak)

            decay_best = ""
            decay_fit_ok = 0
            decay_r2 = float("nan")
            decay_bic = float("nan")
            decay_exp_tau = float("nan")
            decay_pl_beta = float("nan")

            if td_rel.size >= int(cfg.min_points_decay):
                fits = _fit_decay_models(td_rel, yd, t_shift=float(cfg.t_shift_hours))
                exp = fits.get("exponential", {})
                pl = fits.get("power_law", {})
                exp_ok = int(exp.get("fit_ok", 0))
                pl_ok = int(pl.get("fit_ok", 0))

                candidates: list[tuple[str, float]] = []
                if exp_ok == 1 and np.isfinite(float(exp.get("bic", float("nan")))):
                    candidates.append(("exponential", float(exp["bic"])))
                if pl_ok == 1 and np.isfinite(float(pl.get("bic", float("nan")))):
                    candidates.append(("power_law", float(pl["bic"])))

                if candidates:
                    decay_best = min(candidates, key=lambda x: x[1])[0]
                    decay_fit_ok = 1
                    if decay_best == "exponential":
                        decay_exp_tau = float(exp.get("tau_out_hours", float("nan")))
                        decay_r2 = float(exp.get("r2", float("nan")))
                        decay_bic = float(exp.get("bic", float("nan")))
                    else:
                        decay_pl_beta = float(pl.get("beta", float("nan")))
                        decay_r2 = float(pl.get("r2", float("nan")))
                        decay_bic = float(pl.get("bic", float("nan")))

            band_rows.append(
                {
                    **row,
                    "growth_fit_ok": int(growth.get("fit_ok", 0)),
                    "growth_tau_in_hours": float(growth.get("tau_in_hours", float("nan"))),
                    "growth_A": float(growth.get("A", float("nan"))),
                    "growth_r2": float(growth.get("r2", float("nan"))),
                    "growth_bic": float(growth.get("bic", float("nan"))),
                    "decay_fit_ok": int(decay_fit_ok),
                    "decay_best_model": str(decay_best),
                    "decay_exp_tau_out_hours": float(decay_exp_tau),
                    "decay_pl_beta": float(decay_pl_beta),
                    "decay_r2": float(decay_r2),
                    "decay_bic": float(decay_bic),
                    "n_points_growth": int(tg_rel.size),
                    "n_points_decay": int(td_rel.size),
                }
            )

        # write per-disaster outputs
        out_dir = cfg.output_root / slug / "two_phase_dynamics"
        out = _out_dirs(out_dir)
        _ensure_dir(out.root)
        _ensure_dir(out.figures)
        _ensure_dir(out.tables)

        fit_df = pd.DataFrame(band_rows)
        fit_df.to_csv(out.tables / "two_phase_fit.csv", index=False)

        phase_df = fit_df[
            [
                "distance_band",
                "class",
                "mean_dev_0_early",
                "t_peak_hours",
                "phi_at_peak",
                "abs_dev_at_peak",
                "n_points_total",
                "max_abs_dev",
            ]
        ].copy()
        phase_df.to_csv(out.tables / "phase_classification.csv", index=False)

        (out.root / "metadata.json").write_text(
            json.dumps(
                {
                    "slug": slug,
                    "name": name,
                    "event_type": event_type,
                    "phi_col": cfg.phi_col,
                    "fit_min_hours": float(cfg.fit_min_hours),
                    "fit_max_hours": float(cfg.fit_max_hours) if cfg.fit_max_hours is not None else None,
                    "peak_min_hours": float(cfg.peak_min_hours),
                    "peak_max_hours": float(cfg.peak_max_hours) if cfg.peak_max_hours is not None else None,
                    "early_hours": float(cfg.early_hours),
                    "neutral_eps": float(cfg.neutral_eps),
                    "min_points_growth": int(cfg.min_points_growth),
                    "min_points_decay": int(cfg.min_points_decay),
                    "min_signal_abs": float(cfg.min_signal_abs),
                    "t_shift_hours": float(cfg.t_shift_hours),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        _plot_phi_timeseries(
            phi_rt=phi_rt,
            cfg=cfg,
            peak_by_band=peak_by_band,
            out_path=out.figures / "phi_timeseries_by_band.png",
            title=f"{slug}: {name} | {cfg.phi_col} by distance band",
        )

        all_rows.extend(band_rows)

    all_df = pd.DataFrame(all_rows)
    all_df.to_csv(out_summary.tables / "two_phase_fit_all_disasters.csv", index=False)


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="分阶段动力学：增长期(τ_in)+恢复期(τ_out/β) 的两段拟合（基于 φ=phi_aggregate）")
    p.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog.csv"))
    p.add_argument("--output-root", type=Path, default=Path("outputs"))
    p.add_argument("--summary-dir", type=Path, default=Path("outputs/_tmp_two_phase_dynamics"))
    p.add_argument("--phi-col", type=str, default="phi_aggregate")

    p.add_argument("--early-hours", type=float, default=72.0)
    p.add_argument("--neutral-eps", type=float, default=0.02)

    p.add_argument("--peak-min-hours", type=float, default=0.0)
    p.add_argument("--peak-max-hours", type=float, default=None)

    p.add_argument("--fit-min-hours", type=float, default=0.0)
    p.add_argument("--fit-max-hours", type=float, default=None)

    p.add_argument("--min-points-growth", type=int, default=5)
    p.add_argument("--min-points-decay", type=int, default=10)
    p.add_argument("--min-signal-abs", type=float, default=0.02)
    p.add_argument("--t-shift-hours", type=float, default=1.0)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_argparser().parse_args(argv)
    cfg = Config(
        catalog=Path(args.catalog),
        output_root=Path(args.output_root),
        summary_dir=Path(args.summary_dir),
        phi_col=str(args.phi_col),
        early_hours=float(args.early_hours),
        neutral_eps=float(args.neutral_eps),
        peak_min_hours=float(args.peak_min_hours),
        peak_max_hours=(float(args.peak_max_hours) if args.peak_max_hours is not None else None),
        fit_min_hours=float(args.fit_min_hours),
        fit_max_hours=(float(args.fit_max_hours) if args.fit_max_hours is not None else None),
        min_points_growth=int(args.min_points_growth),
        min_points_decay=int(args.min_points_decay),
        min_signal_abs=float(args.min_signal_abs),
        t_shift_hours=float(args.t_shift_hours),
    )
    run(cfg)


if __name__ == "__main__":
    main()

