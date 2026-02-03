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
    fit_mode: str = "from_peak"  # from_peak | from_t0
    fit_min_hours: float = 0.0
    fit_max_hours: float | None = None

    # power-law uses (t + t_shift)^(-beta) to avoid singular at t=0
    t_shift_hours: float = 1.0

    min_points: int = 10
    min_signal_abs: float = 0.02  # |phi-1| max 小于该阈值则判为“无显著扰动”

    distance_band_order: tuple[str, ...] = ("0-25km", "25-50km", "50-100km", "100-200km", "200km+")
    distance_band_center_km: tuple[float, ...] = (12.5, 37.5, 75.0, 150.0, 300.0)


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _out_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _safe_corr(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    if np.sum(ok) < 2:
        return float("nan")
    x = x[ok]
    y = y[ok]
    if float(np.nanstd(x)) == 0.0 or float(np.nanstd(y)) == 0.0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def _sse(y: np.ndarray, yhat: np.ndarray) -> float:
    r = y - yhat
    return float(np.sum(r * r))


def _r2(y: np.ndarray, yhat: np.ndarray) -> float:
    resid = y - yhat
    sse = float(np.sum(resid**2))
    sst = float(np.sum((y - float(np.mean(y))) ** 2))
    return float(1.0 - sse / sst) if sst > 0 else float("nan")


def _aic_bic_from_sse(sse: float, *, n: int, k: int) -> tuple[float, float]:
    # Gaussian likelihood with unknown sigma: AIC/BIC ∝ n*log(SSE/n) + penalty
    if n <= 0 or not np.isfinite(sse) or sse <= 0:
        return float("nan"), float("nan")
    n_f = float(n)
    aic = n_f * float(np.log(sse / n_f)) + 2.0 * float(k)
    bic = n_f * float(np.log(sse / n_f)) + float(k) * float(np.log(n_f))
    return float(aic), float(bic)


def _exp_decay(t: np.ndarray, a: float, tau: float) -> np.ndarray:
    return float(a) * np.exp(-t / float(tau))


def _power_decay(t: np.ndarray, a: float, beta: float, *, t_shift: float) -> np.ndarray:
    return float(a) * np.power(t + float(t_shift), -float(beta))


def _fit_decay_models(
    t: np.ndarray,
    y: np.ndarray,
    *,
    t_shift: float,
) -> dict:
    """
    对 y(t)（非负）拟合：
    - exponential: y = A * exp(-t/tau)
    - power_law:  y = A * (t + t_shift)^(-beta)
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
        return {}

    # initial guesses
    a0 = float(max(1e-6, y[0]))
    tau0 = float(max(1.0, (float(np.max(t)) - float(np.min(t))) / 3.0))
    tau_hi = float(max(2000.0, 3.0 * float(np.max(t))))

    out: dict[str, dict] = {}

    # exponential (A>=0, tau>0)
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
            "tau_hours": tau,
            "sse": sse,
            "r2": r2,
            "aic": aic,
            "bic": bic,
        }
    except Exception:
        out["exponential"] = {"fit_ok": 0}

    # power-law (A>=0, beta>0)
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


def _load_phi_rt_from_outputs(
    *,
    output_root: Path,
    slug: str,
    phi_col: str,
    band_order: tuple[str, ...],
) -> pd.DataFrame:
    """
    从 outputs/<slug>/population_redistribution/tables/redistribution_by_distance_band.csv
    读取并构造 phi(r,t) 矩阵（index=hours_since_quake, columns=distance_band）。
    """

    csv_path = output_root / slug / "population_redistribution" / "tables" / "redistribution_by_distance_band.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"未找到：{csv_path}")

    df = pd.read_csv(csv_path)
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


def _fit_one_disaster(
    *,
    slug: str,
    name: str,
    event_type: str,
    phi_rt: pd.DataFrame,
    cfg: Config,
    out_dir: Path,
) -> tuple[pd.DataFrame, dict[str, dict[str, pd.DataFrame]]]:
    """
    返回：
    - fit_df：每个 band 的拟合参数
    - curves：用于坍缩/画图的原始曲线（abs_dev 与 t_rel）
    """

    bands = list(cfg.distance_band_order)
    centers = {b: float(r) for b, r in zip(cfg.distance_band_order, cfg.distance_band_center_km, strict=False)}

    rows: list[dict] = []
    curves: dict[str, dict[str, pd.DataFrame]] = {"abs_dev": {}, "signed_dev": {}}

    times_all = phi_rt.index.to_numpy(dtype=float)
    for band in bands:
        if band not in phi_rt.columns:
            continue

        y_phi = pd.to_numeric(phi_rt[band], errors="coerce").to_numpy(dtype=float)
        t = times_all.copy()
        ok = np.isfinite(t) & np.isfinite(y_phi)
        t = t[ok]
        phi = y_phi[ok]

        # fit window
        win = t >= float(cfg.fit_min_hours)
        if cfg.fit_max_hours is not None:
            win &= t <= float(cfg.fit_max_hours)
        t = t[win]
        phi = phi[win]

        if t.size == 0:
            rows.append(
                {
                    "slug": slug,
                    "name": name,
                    "event_type": event_type,
                    "distance_band": band,
                    "distance_center_km": centers.get(band, float("nan")),
                    "fit_mode": cfg.fit_mode,
                    "t_start_hours": float("nan"),
                    "t_end_hours": float("nan"),
                    "t_peak_hours": float("nan"),
                    "n_points_total": 0,
                    "max_abs_dev": float("nan"),
                    "low_signal": 1,
                    "exp_fit_ok": 0,
                    "exp_tau_hours": float("nan"),
                    "exp_tau_days": float("nan"),
                    "exp_A": float("nan"),
                    "exp_r2": float("nan"),
                    "exp_bic": float("nan"),
                    "pl_fit_ok": 0,
                    "pl_beta": float("nan"),
                    "pl_A": float("nan"),
                    "pl_r2": float("nan"),
                    "pl_bic": float("nan"),
                    "best_model_by_bic": "",
                }
            )
            continue

        signed_dev = phi - 1.0
        abs_dev = np.abs(signed_dev)
        max_abs = float(np.nanmax(abs_dev)) if abs_dev.size else float("nan")
        low_signal = int(np.isfinite(max_abs) and max_abs < float(cfg.min_signal_abs))

        # peak time in window (for from_peak)
        i_peak = int(np.nanargmax(abs_dev)) if abs_dev.size else 0
        t_peak = float(t[i_peak]) if t.size else float("nan")

        if cfg.fit_mode == "from_peak":
            t0 = float(t_peak)
        elif cfg.fit_mode == "from_t0":
            t0 = float(np.nanmin(t))
        else:
            raise SystemExit(f"不支持的 fit_mode：{cfg.fit_mode}（仅支持 from_peak/from_t0）")

        # decay time axis
        t_rel = t - float(t0)
        keep = np.isfinite(t_rel) & (t_rel >= 0) & np.isfinite(abs_dev)
        t_rel = t_rel[keep]
        abs_y = abs_dev[keep]
        sign_y = signed_dev[keep]

        curves["abs_dev"][band] = pd.DataFrame({"t_rel_hours": t_rel, "abs_dev": abs_y})
        curves["signed_dev"][band] = pd.DataFrame({"t_rel_hours": t_rel, "signed_dev": sign_y})

        row = {
            "slug": slug,
            "name": name,
            "event_type": event_type,
            "distance_band": band,
            "distance_center_km": centers.get(band, float("nan")),
            "fit_mode": cfg.fit_mode,
            "t_start_hours": float(t0),
            "t_end_hours": float(np.nanmax(t)) if t.size else float("nan"),
            "t_peak_hours": float(t_peak),
            "n_points_total": int(abs_y.size),
            "max_abs_dev": float(max_abs),
            "low_signal": int(low_signal),
        }

        if low_signal or abs_y.size < int(cfg.min_points):
            rows.append(
                {
                    **row,
                    "exp_fit_ok": 0,
                    "exp_tau_hours": float("nan"),
                    "exp_tau_days": float("nan"),
                    "exp_A": float("nan"),
                    "exp_r2": float("nan"),
                    "exp_bic": float("nan"),
                    "pl_fit_ok": 0,
                    "pl_beta": float("nan"),
                    "pl_A": float("nan"),
                    "pl_r2": float("nan"),
                    "pl_bic": float("nan"),
                    "best_model_by_bic": "",
                }
            )
            continue

        fits = _fit_decay_models(t_rel, abs_y, t_shift=float(cfg.t_shift_hours))

        exp = fits.get("exponential", {})
        pl = fits.get("power_law", {})

        exp_ok = int(exp.get("fit_ok", 0))
        pl_ok = int(pl.get("fit_ok", 0))

        exp_tau = float(exp.get("tau_hours", float("nan"))) if exp_ok else float("nan")
        pl_beta = float(pl.get("beta", float("nan"))) if pl_ok else float("nan")

        exp_bic = float(exp.get("bic", float("nan"))) if exp_ok else float("nan")
        pl_bic = float(pl.get("bic", float("nan"))) if pl_ok else float("nan")

        best = ""
        if exp_ok and pl_ok and np.isfinite(exp_bic) and np.isfinite(pl_bic):
            best = "exponential" if exp_bic <= pl_bic else "power_law"
        elif exp_ok:
            best = "exponential"
        elif pl_ok:
            best = "power_law"

        rows.append(
            {
                **row,
                "exp_fit_ok": exp_ok,
                "exp_tau_hours": float(exp_tau),
                "exp_tau_days": float(exp_tau / 24.0) if np.isfinite(exp_tau) else float("nan"),
                "exp_A": float(exp.get("A", float("nan"))),
                "exp_r2": float(exp.get("r2", float("nan"))),
                "exp_bic": float(exp_bic),
                "pl_fit_ok": pl_ok,
                "pl_beta": float(pl_beta),
                "pl_A": float(pl.get("A", float("nan"))),
                "pl_r2": float(pl.get("r2", float("nan"))),
                "pl_bic": float(pl_bic),
                "best_model_by_bic": str(best),
            }
        )

    fit_df = pd.DataFrame(rows)
    fit_df = fit_df.sort_values(["distance_center_km"], kind="stable")

    out = _out_dirs(out_dir)
    _ensure_dir(out.root)
    _ensure_dir(out.figures)
    _ensure_dir(out.tables)

    fit_df.to_csv(out.tables / "recovery_fit_by_band.csv", index=False)
    (out.root / "metadata.json").write_text(
        json.dumps(
            {
                "slug": slug,
                "name": name,
                "event_type": event_type,
                "phi_col": cfg.phi_col,
                "fit_mode": cfg.fit_mode,
                "fit_min_hours": float(cfg.fit_min_hours),
                "fit_max_hours": float(cfg.fit_max_hours) if cfg.fit_max_hours is not None else None,
                "t_shift_hours": float(cfg.t_shift_hours),
                "min_points": int(cfg.min_points),
                "min_signal_abs": float(cfg.min_signal_abs),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return fit_df, curves


def _plot_tau_vs_r(all_fit: pd.DataFrame, cfg: Config, *, out_path: Path) -> None:
    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    df = all_fit.copy()
    df["distance_center_km"] = pd.to_numeric(df["distance_center_km"], errors="coerce")
    df["exp_tau_hours"] = pd.to_numeric(df["exp_tau_hours"], errors="coerce")
    df = df[df["exp_fit_ok"] == 1].copy()
    df = df.dropna(subset=["distance_center_km", "exp_tau_hours"]).copy()
    df = df[(df["distance_center_km"] > 0) & (df["exp_tau_hours"] > 0)].copy()
    if df.empty:
        return

    # color by event_type (Okabe–Ito subset)
    color_map = {
        "earthquake": ps.OKABE_ITO["vermillion"],
        "hurricane": ps.OKABE_ITO["blue"],
        "flood": ps.OKABE_ITO["bluish_green"],
        "wildfire": ps.OKABE_ITO["orange"],
    }

    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        for et, sub in df.groupby("event_type", sort=False):
            c = color_map.get(str(et), ps.OKABE_ITO["gray"])
            ax.scatter(
                sub["distance_center_km"].to_numpy(dtype=float),
                (sub["exp_tau_hours"].to_numpy(dtype=float) / 24.0),
                s=55,
                alpha=0.85,
                color=c,
                label=str(et),
                linewidths=0,
            )
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Distance r (km, band center)")
        ax.set_ylabel(r"$\tau(r)$ (days)")
        ax.set_title(r"Exponential decay fit on $|\phi-1|$: $\tau(r)$ across disasters")
        ps.despine(ax)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), ncol=4, frameon=False)
        fig.subplots_adjust(bottom=0.25)
        save_png_and_pdf(ps, fig, out_path)
        plt.close(fig)


def _plot_beta_vs_r(all_fit: pd.DataFrame, cfg: Config, *, out_path: Path) -> None:
    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    df = all_fit.copy()
    df["distance_center_km"] = pd.to_numeric(df["distance_center_km"], errors="coerce")
    df["pl_beta"] = pd.to_numeric(df["pl_beta"], errors="coerce")
    df = df[df["pl_fit_ok"] == 1].copy()
    df = df.dropna(subset=["distance_center_km", "pl_beta"]).copy()
    df = df[(df["distance_center_km"] > 0) & (df["pl_beta"] > 0)].copy()
    if df.empty:
        return

    color_map = {
        "earthquake": ps.OKABE_ITO["vermillion"],
        "hurricane": ps.OKABE_ITO["blue"],
        "flood": ps.OKABE_ITO["bluish_green"],
        "wildfire": ps.OKABE_ITO["orange"],
    }

    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        for et, sub in df.groupby("event_type", sort=False):
            c = color_map.get(str(et), ps.OKABE_ITO["gray"])
            ax.scatter(
                sub["distance_center_km"].to_numpy(dtype=float),
                sub["pl_beta"].to_numpy(dtype=float),
                s=55,
                alpha=0.85,
                color=c,
                label=str(et),
                linewidths=0,
            )
        ax.set_xscale("log")
        ax.set_xlabel("Distance r (km, band center)")
        ax.set_ylabel(r"Power-law exponent $\beta$")
        ax.set_title(r"Power-law decay fit on $|\phi-1|$: $\beta(r)$ across disasters")
        ps.despine(ax)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), ncol=4, frameon=False)
        fig.subplots_adjust(bottom=0.25)
        save_png_and_pdf(ps, fig, out_path)
        plt.close(fig)


def _plot_collapse_one_disaster(
    *,
    slug: str,
    fit_df: pd.DataFrame,
    curves_abs: dict[str, pd.DataFrame],
    cfg: Config,
    out_path: Path,
) -> None:
    """
    对单个灾害：用 τ(r) 做时间重标度，画 y_norm=|phi-1|/y0 vs t_rel/tau。
    """

    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    df = fit_df.copy()
    df = df[df["exp_fit_ok"] == 1].copy()
    df["exp_tau_hours"] = pd.to_numeric(df["exp_tau_hours"], errors="coerce")
    df = df.dropna(subset=["distance_band", "exp_tau_hours"]).copy()
    df = df[np.isfinite(df["exp_tau_hours"].to_numpy(dtype=float)) & (df["exp_tau_hours"].to_numpy(dtype=float) > 0)].copy()
    if df.empty:
        return

    band_order = [b for b in cfg.distance_band_order if b in set(df["distance_band"].astype(str))]
    colors = [
        ps.OKABE_ITO["vermillion"],
        ps.OKABE_ITO["orange"],
        ps.OKABE_ITO["bluish_green"],
        ps.OKABE_ITO["sky_blue"],
        ps.OKABE_ITO["blue"],
    ]

    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        for i, band in enumerate(band_order):
            tau = float(df.loc[df["distance_band"].astype(str) == str(band), "exp_tau_hours"].iloc[0])
            curve = curves_abs.get(str(band))
            if curve is None or curve.empty:
                continue
            t_rel = pd.to_numeric(curve["t_rel_hours"], errors="coerce").to_numpy(dtype=float)
            y = pd.to_numeric(curve["abs_dev"], errors="coerce").to_numpy(dtype=float)
            ok = np.isfinite(t_rel) & np.isfinite(y) & (y >= 0)
            t_rel = t_rel[ok]
            y = y[ok]
            if t_rel.size < 2:
                continue
            y0 = float(y[0])
            if not np.isfinite(y0) or y0 <= 0:
                continue
            x = t_rel / tau
            y_norm = y / y0
            ax.plot(x, y_norm, marker="o", markersize=3.8, linewidth=1.8, color=colors[i % len(colors)], label=f"{band} (τ={tau/24:.1f}d)")

        # reference: exp(-x)
        x_ref = np.linspace(0.0, 6.0, 200)
        ax.plot(x_ref, np.exp(-x_ref), color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.2, alpha=0.8, label=r"$e^{-\tilde{t}}$")

        ax.set_xlabel(r"Rescaled time $\tilde{t}=t/\tau(r)$")
        ax.set_ylabel(r"$|\phi-1|/|\phi-1|_{t_0}$")
        ax.set_title(f"Time rescaling collapse (exponential τ): {slug}")
        ps.despine(ax)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.23), ncol=2, frameon=False)
        fig.subplots_adjust(bottom=0.28)
        save_png_and_pdf(ps, fig, out_path)
        plt.close(fig)


def _plot_collapse_cross_disaster(
    *,
    all_fit: pd.DataFrame,
    curves_by_slug: dict[str, dict[str, pd.DataFrame]],
    cfg: Config,
    out_path: Path,
) -> None:
    """
    跨灾害坍缩：对每个距离带，叠加不同灾害的 y_norm vs t_rel/tau。
    """

    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    df = all_fit.copy()
    df = df[df["exp_fit_ok"] == 1].copy()
    df["exp_tau_hours"] = pd.to_numeric(df["exp_tau_hours"], errors="coerce")
    df = df.dropna(subset=["slug", "distance_band", "exp_tau_hours"]).copy()
    df = df[np.isfinite(df["exp_tau_hours"].to_numpy(dtype=float)) & (df["exp_tau_hours"].to_numpy(dtype=float) > 0)].copy()
    if df.empty:
        return

    # color by disaster (stable order)
    slugs = sorted(set(df["slug"].astype(str)))
    palette = [
        ps.OKABE_ITO["blue"],
        ps.OKABE_ITO["vermillion"],
        ps.OKABE_ITO["bluish_green"],
        ps.OKABE_ITO["orange"],
        ps.OKABE_ITO["sky_blue"],
        ps.OKABE_ITO["reddish_purple"],
    ]
    color_by_slug = {s: palette[i % len(palette)] for i, s in enumerate(slugs)}

    bands = list(cfg.distance_band_order)
    n_panels = len(bands)

    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, n_panels, figsize=(ps.FIGSIZE_FULL[0] * 2.2, ps.FIGSIZE_FULL[1] * 0.9), sharey=True)
        if n_panels == 1:
            axes = [axes]

        for ax, band in zip(axes, bands, strict=False):
            sub = df[df["distance_band"].astype(str) == str(band)].copy()
            if sub.empty:
                ax.set_title(str(band))
                continue
            for row in sub.itertuples(index=False):
                slug = str(row.slug)
                tau = float(row.exp_tau_hours)
                curve = curves_by_slug.get(slug, {}).get(str(band))
                if curve is None or curve.empty:
                    continue
                t_rel = pd.to_numeric(curve["t_rel_hours"], errors="coerce").to_numpy(dtype=float)
                y = pd.to_numeric(curve["abs_dev"], errors="coerce").to_numpy(dtype=float)
                ok = np.isfinite(t_rel) & np.isfinite(y) & (y >= 0)
                t_rel = t_rel[ok]
                y = y[ok]
                if t_rel.size < 2:
                    continue
                y0 = float(y[0])
                if not np.isfinite(y0) or y0 <= 0:
                    continue
                x = t_rel / tau
                y_norm = y / y0
                ax.plot(x, y_norm, marker="o", markersize=2.8, linewidth=1.4, color=color_by_slug.get(slug, ps.OKABE_ITO["gray"]), alpha=0.85)
            ax.plot([0, 6], [1, np.exp(-6)], color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.6)
            ax.set_title(str(band))
            ax.set_xlabel(r"$t/\tau$")
            ps.despine(ax)

        axes[0].set_ylabel(r"$|\phi-1|/|\phi-1|_{t_0}$")

        # legend (one per slug)
        handles = []
        labels = []
        for s in slugs:
            handles.append(plt.Line2D([0], [0], color=color_by_slug[s], lw=2))
            labels.append(s)
        fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=min(4, len(labels)), frameon=False)
        fig.subplots_adjust(bottom=0.22)
        save_png_and_pdf(ps, fig, out_path)
        plt.close(fig)


def run(cfg: Config) -> None:
    specs = load_catalog(cfg.catalog)
    out_sum = _out_dirs(cfg.summary_dir)
    _ensure_dir(out_sum.root)
    _ensure_dir(out_sum.figures)
    _ensure_dir(out_sum.tables)

    all_rows: list[pd.DataFrame] = []
    corr_rows: list[dict] = []
    curves_by_slug: dict[str, dict[str, pd.DataFrame]] = {}

    for spec in specs:
        try:
            phi_rt = _load_phi_rt_from_outputs(
                output_root=cfg.output_root,
                slug=spec.slug,
                phi_col=str(cfg.phi_col),
                band_order=cfg.distance_band_order,
            )
        except Exception as e:
            print(f"[recovery_dynamics] skip {spec.slug}: {type(e).__name__}: {e}")
            continue

        per_dir = cfg.output_root / spec.slug / "recovery_dynamics"
        fit_df, curves = _fit_one_disaster(
            slug=spec.slug,
            name=spec.name,
            event_type=spec.event_type,
            phi_rt=phi_rt,
            cfg=cfg,
            out_dir=per_dir,
        )
        all_rows.append(fit_df)
        curves_by_slug[spec.slug] = curves["abs_dev"]

        # per-disaster collapse
        _plot_collapse_one_disaster(
            slug=spec.slug,
            fit_df=fit_df,
            curves_abs=curves["abs_dev"],
            cfg=cfg,
            out_path=per_dir / "figures" / "collapse_by_tau.png",
        )

        # correlation tau vs r, beta vs r (within disaster)
        sub_tau = fit_df[fit_df["exp_fit_ok"] == 1].copy()
        sub_tau["distance_center_km"] = pd.to_numeric(sub_tau["distance_center_km"], errors="coerce")
        sub_tau["exp_tau_hours"] = pd.to_numeric(sub_tau["exp_tau_hours"], errors="coerce")
        corr_tau = _safe_corr(np.log(sub_tau["distance_center_km"].to_numpy(dtype=float)), np.log(sub_tau["exp_tau_hours"].to_numpy(dtype=float)))

        sub_beta = fit_df[fit_df["pl_fit_ok"] == 1].copy()
        sub_beta["distance_center_km"] = pd.to_numeric(sub_beta["distance_center_km"], errors="coerce")
        sub_beta["pl_beta"] = pd.to_numeric(sub_beta["pl_beta"], errors="coerce")
        corr_beta = _safe_corr(np.log(sub_beta["distance_center_km"].to_numpy(dtype=float)), sub_beta["pl_beta"].to_numpy(dtype=float))

        corr_rows.append(
            {
                "slug": spec.slug,
                "name": spec.name,
                "event_type": spec.event_type,
                "corr_log_tau_vs_log_r": float(corr_tau),
                "corr_beta_vs_log_r": float(corr_beta),
                "n_tau_points": int(sub_tau.dropna(subset=["distance_center_km", "exp_tau_hours"]).shape[0]),
                "n_beta_points": int(sub_beta.dropna(subset=["distance_center_km", "pl_beta"]).shape[0]),
            }
        )

    if not all_rows:
        raise SystemExit("未生成任何拟合结果（检查 outputs/<slug>/population_redistribution 是否存在）")

    all_fit = pd.concat(all_rows, ignore_index=True)
    all_fit.to_csv(out_sum.tables / "recovery_fit_all_disasters.csv", index=False)
    pd.DataFrame(corr_rows).to_csv(out_sum.tables / "correlation_summary.csv", index=False)

    # cross-disaster plots
    _plot_tau_vs_r(all_fit, cfg, out_path=out_sum.figures / "tau_vs_distance_cross_disaster.png")
    _plot_beta_vs_r(all_fit, cfg, out_path=out_sum.figures / "beta_vs_distance_cross_disaster.png")
    _plot_collapse_cross_disaster(
        all_fit=all_fit,
        curves_by_slug=curves_by_slug,
        cfg=cfg,
        out_path=out_sum.figures / "collapse_by_tau_cross_disaster.png",
    )


def cli_main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog.csv"))
    p.add_argument("--output-root", type=Path, default=Path("outputs"))
    p.add_argument("--summary-dir", type=Path, default=Path("outputs/_tmp_cross_recovery_dynamics"))
    p.add_argument("--phi-col", type=str, default="phi_aggregate")
    p.add_argument("--fit-mode", type=str, choices=["from_peak", "from_t0"], default="from_peak")
    p.add_argument("--fit-min-hours", type=float, default=0.0)
    p.add_argument("--fit-max-hours", type=float, default=None)
    p.add_argument("--t-shift-hours", type=float, default=1.0)
    p.add_argument("--min-points", type=int, default=10)
    p.add_argument("--min-signal-abs", type=float, default=0.02)
    args = p.parse_args()

    cfg = Config(
        catalog=Path(args.catalog),
        output_root=Path(args.output_root),
        summary_dir=Path(args.summary_dir),
        phi_col=str(args.phi_col),
        fit_mode=str(args.fit_mode),
        fit_min_hours=float(args.fit_min_hours),
        fit_max_hours=float(args.fit_max_hours) if args.fit_max_hours is not None else None,
        t_shift_hours=float(args.t_shift_hours),
        min_points=int(args.min_points),
        min_signal_abs=float(args.min_signal_abs),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()
