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
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _out_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _load_event_metadata(output_root: Path, slug: str) -> dict:
    p = output_root / slug / "metadata.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _track_anchor_gap_hours(meta: dict) -> float | None:
    x = meta.get("track_anchor_to_t0_hours")
    try:
        if x is None:
            return None
        v = float(x)
        return v if np.isfinite(v) else None
    except Exception:
        return None


def _safe_float(x: object) -> float | None:
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() == "nan":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _r2(y: np.ndarray, yhat: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    yhat = np.asarray(yhat, dtype=float)
    ok = np.isfinite(y) & np.isfinite(yhat)
    if int(np.sum(ok)) < 2:
        return float("nan")
    yy = y[ok]
    yh = yhat[ok]
    sse = float(np.sum((yy - yh) ** 2))
    sst = float(np.sum((yy - float(np.mean(yy))) ** 2))
    return float(1.0 - sse / sst) if sst > 0 else float("nan")


def _load_population_redistribution_phi(
    *,
    output_root: Path,
    slug: str,
    phi_col: str,
    min_hours: float,
    max_hours: float | None,
) -> pd.DataFrame | None:
    csv_path = output_root / slug / "population_redistribution" / "tables" / "redistribution_by_distance_band.csv"
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path)
    required = {"hours_since_quake", "distance_band", phi_col}
    missing = sorted(required - set(df.columns))
    if missing:
        return None
    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df[phi_col] = pd.to_numeric(df[phi_col], errors="coerce")
    df = df.dropna(subset=["hours_since_quake", phi_col]).copy()
    df = df[df["hours_since_quake"] >= float(min_hours)].copy()
    if max_hours is not None:
        df = df[df["hours_since_quake"] <= float(max_hours)].copy()
    return df


def _load_phi_heatmap_long(
    *,
    output_root: Path,
    slug: str,
    phi_col: str,
    min_hours: float,
    max_hours: float | None,
) -> pd.DataFrame | None:
    csv_path = output_root / slug / "phi_heatmap" / "tables" / "phi_rt_long.csv"
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path)
    required = {"hours_since_quake", "r_bin_km", phi_col}
    missing = sorted(required - set(df.columns))
    if missing:
        return None
    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df["r_bin_km"] = pd.to_numeric(df["r_bin_km"], errors="coerce")
    df[phi_col] = pd.to_numeric(df[phi_col], errors="coerce")
    df = df.dropna(subset=["hours_since_quake", "r_bin_km", phi_col]).copy()
    df = df[df["hours_since_quake"] >= float(min_hours)].copy()
    if max_hours is not None:
        df = df[df["hours_since_quake"] <= float(max_hours)].copy()
    return df


def run_phase0_signal_scan(
    *,
    catalog: Path,
    output_root: Path,
    out_dir: Path,
    phi_col: str,
    source: str,
    min_hours: float,
    max_hours: float | None,
) -> pd.DataFrame:
    specs = load_catalog(catalog)
    out = _out_dirs(out_dir)
    _ensure_dir(out.root)
    _ensure_dir(out.figures)
    _ensure_dir(out.tables)

    rows: list[dict] = []
    for spec in specs:
        if source == "population_redistribution":
            df = _load_population_redistribution_phi(
                output_root=output_root, slug=spec.slug, phi_col=phi_col, min_hours=float(min_hours), max_hours=max_hours
            )
            key_cols = {"distance_band": "distance_band"}
        elif source == "phi_heatmap":
            df = _load_phi_heatmap_long(
                output_root=output_root, slug=spec.slug, phi_col=phi_col, min_hours=float(min_hours), max_hours=max_hours
            )
            key_cols = {"distance_band": "r_bin_km"}
        else:
            raise SystemExit(f"不支持的 source：{source}（仅支持 population_redistribution / phi_heatmap）")

        if df is None or df.empty:
            rows.append(
                {
                    "slug": spec.slug,
                    "name": spec.name,
                    "event_type": spec.event_type,
                    "source": source,
                    "phi_col": phi_col,
                    "S": float("nan"),
                    "arg_key": float("nan") if source == "phi_heatmap" else "",
                    "t_at_S": float("nan"),
                    "phi_at_S": float("nan"),
                    "min_phi": float("nan"),
                    "max_phi": float("nan"),
                    "n_points": 0,
                }
            )
            continue

        phi = pd.to_numeric(df[phi_col], errors="coerce").to_numpy(dtype=float)
        abs_dev = np.abs(phi - 1.0)
        i = int(np.nanargmax(abs_dev)) if abs_dev.size else 0
        s = float(abs_dev[i]) if abs_dev.size else float("nan")
        t = float(df.iloc[i]["hours_since_quake"]) if "hours_since_quake" in df.columns else float("nan")
        phi_at = float(phi[i]) if abs_dev.size else float("nan")
        k = df.iloc[i][list(key_cols.values())[0]]
        rows.append(
            {
                "slug": spec.slug,
                "name": spec.name,
                "event_type": spec.event_type,
                "source": source,
                "phi_col": phi_col,
                "S": float(s),
                "arg_key": float(k) if source == "phi_heatmap" else str(k),
                "t_at_S": float(t),
                "phi_at_S": float(phi_at),
                "min_phi": float(np.nanmin(phi)) if phi.size else float("nan"),
                "max_phi": float(np.nanmax(phi)) if phi.size else float("nan"),
                "n_points": int(df.shape[0]),
            }
        )

    out_df = pd.DataFrame(rows)
    out_df = out_df.sort_values(["S"], ascending=[False], kind="stable")
    out_df.to_csv(out.tables / "phase0_signal_strength.csv", index=False)
    (out.root / "metadata.json").write_text(
        json.dumps(
            {
                "catalog": str(catalog),
                "output_root": str(output_root),
                "phi_col": phi_col,
                "source": source,
                "min_hours": float(min_hours),
                "max_hours": float(max_hours) if max_hours is not None else None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return out_df


def _radial_profile_from_phi_long(
    df_long: pd.DataFrame,
    *,
    time_min: float,
    time_max: float,
    phi_col: str,
    min_tiles: int = 0,
    r_bin_col: str = "r_bin_km",
    detrend_far_rmin_km: float | None = None,
    detrend_far_rmax_km: float | None = None,
    min_coverage_frac: float | None = None,
) -> pd.DataFrame:
    df = df_long.copy()
    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df[r_bin_col] = pd.to_numeric(df[r_bin_col], errors="coerce")
    df[phi_col] = pd.to_numeric(df[phi_col], errors="coerce")
    df = df.dropna(subset=["hours_since_quake", r_bin_col, phi_col]).copy()
    df = df[(df["hours_since_quake"] >= float(time_min)) & (df["hours_since_quake"] <= float(time_max))].copy()
    if df.empty:
        return pd.DataFrame()

    phi_use_col = str(phi_col)
    if detrend_far_rmin_km is not None and np.isfinite(float(detrend_far_rmin_km)):
        rmin = float(detrend_far_rmin_km)
        rmax = float(detrend_far_rmax_km) if detrend_far_rmax_km is not None and np.isfinite(float(detrend_far_rmax_km)) else float("inf")
        far = df[(df[r_bin_col] >= rmin) & (df[r_bin_col] <= rmax)].copy()
        if not far.empty:
            far_phi = (
                far.groupby("hours_since_quake", observed=True)[phi_col]
                .median()
                .reset_index()
                .rename(columns={phi_col: "phi_far"})
            )
            df = df.merge(far_phi, on="hours_since_quake", how="left")
            df["phi_detrended"] = pd.to_numeric(df[phi_col], errors="coerce") / pd.to_numeric(df["phi_far"], errors="coerce")
            df = df.replace([np.inf, -np.inf], np.nan)
            df = df.dropna(subset=["phi_detrended"]).copy()
            phi_use_col = "phi_detrended"

    r_bins = np.sort(df[r_bin_col].unique().astype(float))
    if r_bins.size >= 2:
        dr = float(np.median(np.diff(r_bins)))
    else:
        dr = 10.0

    agg_ops: dict[str, tuple[str, str]] = {"phi_mean": (phi_use_col, "mean")}
    if "n_tiles" in df.columns:
        df["n_tiles"] = pd.to_numeric(df["n_tiles"], errors="coerce")
        agg_ops["n_tiles_mean"] = ("n_tiles", "mean")
    if "n_tiles_overlap" in df.columns:
        df["n_tiles_overlap"] = pd.to_numeric(df["n_tiles_overlap"], errors="coerce")
        agg_ops["n_tiles_overlap_mean"] = ("n_tiles_overlap", "mean")
    if "path_coverage_frac" in df.columns:
        df["path_coverage_frac"] = pd.to_numeric(df["path_coverage_frac"], errors="coerce")
        agg_ops["path_coverage_frac_mean"] = ("path_coverage_frac", "mean")

    g = df.groupby(r_bin_col, sort=True, observed=True).agg(**agg_ops).reset_index()
    g = g.rename(columns={r_bin_col: "r_bin_km"})
    g["r_center_km"] = pd.to_numeric(g["r_bin_km"], errors="coerce") + dr / 2.0
    g["abs_dev"] = (pd.to_numeric(g["phi_mean"], errors="coerce") - 1.0).abs()
    if int(min_tiles) > 0 and "n_tiles_mean" in g.columns:
        g = g[pd.to_numeric(g["n_tiles_mean"], errors="coerce") >= float(min_tiles)].copy()
    if min_coverage_frac is not None and "path_coverage_frac_mean" in g.columns:
        g = g[pd.to_numeric(g["path_coverage_frac_mean"], errors="coerce") >= float(min_coverage_frac)].copy()
    return g.sort_values("r_center_km", kind="stable")


def _fit_powerlaw_alpha(profile: pd.DataFrame, *, r_min: float, r_max: float, y_min: float) -> dict:
    if profile.empty:
        return {"fit_ok": 0}
    r = pd.to_numeric(profile["r_center_km"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(profile["abs_dev"], errors="coerce").to_numpy(dtype=float)
    ok = np.isfinite(r) & np.isfinite(y) & (r > 0) & (y > float(y_min)) & (r >= float(r_min)) & (r <= float(r_max))
    if int(np.sum(ok)) < 3:
        return {"fit_ok": 0}
    rr = r[ok]
    yy = y[ok]
    x = np.log(rr)
    z = np.log(yy)
    slope, intercept = np.polyfit(x, z, deg=1)
    alpha = -float(slope)
    zhat = slope * x + intercept
    r2 = _r2(z, zhat)
    return {
        "fit_ok": 1,
        "alpha": float(alpha),
        "slope": float(slope),
        "intercept": float(intercept),
        "r2_loglog": float(r2),
        "n_points_fit": int(rr.size),
        "r_min_fit": float(np.min(rr)),
        "r_max_fit": float(np.max(rr)),
        "y_min_fit": float(np.min(yy)),
        "y_max_fit": float(np.max(yy)),
    }


def run_phase1_powerlaw(
    *,
    catalog: Path,
    output_root: Path,
    out_dir: Path,
    phi_col: str,
    phase0_csv: Path | None,
    strong_signal_threshold: float,
    time_min: float,
    time_max: float,
    r_min: float,
    r_max: float,
    y_min: float,
    min_tiles: int = 0,
    min_windows: int = 0,
    max_track_anchor_gap_hours: float | None = None,
    detrend_far_rmin_km: float | None = None,
    detrend_far_rmax_km: float | None = None,
    min_coverage_frac: float | None = None,
) -> pd.DataFrame:
    specs = load_catalog(catalog)
    out = _out_dirs(out_dir)
    _ensure_dir(out.root)
    _ensure_dir(out.figures)
    _ensure_dir(out.tables)

    strong_slugs: set[str] | None = None
    if phase0_csv is not None and phase0_csv.exists():
        s0 = pd.read_csv(phase0_csv)
        if "slug" in s0.columns and "S" in s0.columns:
            s0["S"] = pd.to_numeric(s0["S"], errors="coerce")
            strong_slugs = set(s0[s0["S"] >= float(strong_signal_threshold)]["slug"].astype(str).tolist())

    rows: list[dict] = []
    for spec in specs:
        if strong_slugs is not None and spec.slug not in strong_slugs:
            continue

        meta = _load_event_metadata(Path(output_root), spec.slug)
        gap_h = _track_anchor_gap_hours(meta)
        if max_track_anchor_gap_hours is not None and gap_h is not None and abs(float(gap_h)) > float(max_track_anchor_gap_hours):
            rows.append(
                {
                    "slug": spec.slug,
                    "name": spec.name,
                    "event_type": spec.event_type,
                    "fit_ok": 0,
                    "alpha": float("nan"),
                    "r2_loglog": float("nan"),
                    "n_points_fit": 0,
                    "n_windows_in_range": 0,
                    "track_anchor_to_t0_hours": float(gap_h),
                    "note": "t0_misaligned_vs_track_anchor",
                }
            )
            continue

        phi_long = _load_phi_heatmap_long(
            output_root=output_root, slug=spec.slug, phi_col=phi_col, min_hours=float(time_min), max_hours=float(time_max)
        )
        if phi_long is None or phi_long.empty:
            rows.append(
                {
                    "slug": spec.slug,
                    "name": spec.name,
                    "event_type": spec.event_type,
                    "fit_ok": 0,
                    "alpha": float("nan"),
                    "r2_loglog": float("nan"),
                    "n_points_fit": 0,
                    "n_windows_in_range": 0,
                    "track_anchor_to_t0_hours": float(gap_h) if gap_h is not None else float("nan"),
                    "note": "missing_phi_heatmap",
                }
            )
            continue

        n_windows = int(pd.to_numeric(phi_long["hours_since_quake"], errors="coerce").dropna().nunique())
        if int(min_windows) > 0 and int(n_windows) < int(min_windows):
            rows.append(
                {
                    "slug": spec.slug,
                    "name": spec.name,
                    "event_type": spec.event_type,
                    "time_min_hours": float(time_min),
                    "time_max_hours": float(time_max),
                    "fit_ok": 0,
                    "alpha": float("nan"),
                    "r2_loglog": float("nan"),
                    "n_points_fit": 0,
                    "n_windows_in_range": int(n_windows),
                    "track_anchor_to_t0_hours": float(gap_h) if gap_h is not None else float("nan"),
                    "note": "too_few_time_windows",
                }
            )
            continue

        prof = _radial_profile_from_phi_long(
            phi_long,
            time_min=float(time_min),
            time_max=float(time_max),
            phi_col=phi_col,
            min_tiles=int(min_tiles),
            detrend_far_rmin_km=float(detrend_far_rmin_km) if detrend_far_rmin_km is not None else None,
            detrend_far_rmax_km=float(detrend_far_rmax_km) if detrend_far_rmax_km is not None else None,
            min_coverage_frac=float(min_coverage_frac) if min_coverage_frac is not None else None,
        )
        fit = _fit_powerlaw_alpha(prof, r_min=float(r_min), r_max=float(r_max), y_min=float(y_min))
        rows.append(
            {
                "slug": spec.slug,
                "name": spec.name,
                "event_type": spec.event_type,
                "time_min_hours": float(time_min),
                "time_max_hours": float(time_max),
                "fit_ok": int(fit.get("fit_ok", 0)),
                "alpha": float(fit.get("alpha", float("nan"))),
                "r2_loglog": float(fit.get("r2_loglog", float("nan"))),
                "n_points_fit": int(fit.get("n_points_fit", 0)),
                "n_windows_in_range": int(n_windows),
                "track_anchor_to_t0_hours": float(gap_h) if gap_h is not None else float("nan"),
                "r_min_fit": float(fit.get("r_min_fit", float("nan"))),
                "r_max_fit": float(fit.get("r_max_fit", float("nan"))),
                "y_min_fit": float(fit.get("y_min_fit", float("nan"))),
                "y_max_fit": float(fit.get("y_max_fit", float("nan"))),
            }
        )

        # per-disaster artifacts
        per_dir = output_root / spec.slug / "universality_scaling" / "phase1_powerlaw"
        per = _out_dirs(per_dir)
        _ensure_dir(per.root)
        _ensure_dir(per.figures)
        _ensure_dir(per.tables)
        prof.to_csv(per.tables / "radial_profile.csv", index=False)
        pd.DataFrame([{**fit, "time_min_hours": float(time_min), "time_max_hours": float(time_max)}]).to_csv(
            per.tables / "powerlaw_fit.csv", index=False
        )

        try:
            from disaster import plot_style as ps  # type: ignore
            import matplotlib.pyplot as plt

            with ps.paper_style():
                fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
                rr = pd.to_numeric(prof["r_center_km"], errors="coerce").to_numpy(dtype=float)
                yy = pd.to_numeric(prof["abs_dev"], errors="coerce").to_numpy(dtype=float)
                ok = np.isfinite(rr) & np.isfinite(yy) & (rr > 0) & (yy > 0)
                ax.scatter(rr[ok], yy[ok], s=18, alpha=0.85, color=ps.OKABE_ITO["gray"], linewidths=0)

                if int(fit.get("fit_ok", 0)) == 1:
                    alpha = float(fit["alpha"])
                    c = float(np.exp(float(fit["intercept"])))
                    rline = np.geomspace(max(1e-6, float(fit["r_min_fit"])), float(fit["r_max_fit"]), 50)
                    yline = c * np.power(rline, -alpha)
                    ax.plot(rline, yline, color=ps.OKABE_ITO["vermillion"], linewidth=2.0, label=f"alpha={alpha:.3f}")
                    ax.legend(frameon=False)

                ax.set_xscale("log")
                ax.set_yscale("log")
                ax.set_xlabel("Distance r (km)")
                ax.set_ylabel("abs(phi_mean(r) - 1) (time-avg)")
                ax.set_title(f"{spec.slug}: power-law fit, t in [{time_min},{time_max}]h")
                ps.despine(ax)
                fig.tight_layout()
                save_png_and_pdf(ps, fig, per.figures / "powerlaw_fit_loglog.png")
                plt.close(fig)
        except ModuleNotFoundError:
            pass

    out_df = pd.DataFrame(rows)
    out_df.to_csv(out.tables / "phase1_powerlaw_fit.csv", index=False)

    # alpha summary
    al = out_df[out_df["fit_ok"] == 1]["alpha"].to_numpy(dtype=float) if not out_df.empty else np.array([], dtype=float)
    alpha_mean = float(np.nanmean(al)) if al.size else float("nan")
    alpha_std = float(np.nanstd(al)) if al.size else float("nan")
    alpha_cv = float(alpha_std / alpha_mean) if np.isfinite(alpha_mean) and alpha_mean != 0 else float("nan")
    summary = pd.DataFrame(
        [
            {
                "n_fit_ok": int(np.sum(out_df["fit_ok"].to_numpy(dtype=int))) if "fit_ok" in out_df.columns else 0,
                "alpha_mean": alpha_mean,
                "alpha_std": alpha_std,
                "alpha_cv": alpha_cv,
                "strong_signal_threshold": float(strong_signal_threshold),
                "time_min_hours": float(time_min),
                "time_max_hours": float(time_max),
                "r_min": float(r_min),
                "r_max": float(r_max),
                "y_min": float(y_min),
                "min_tiles": int(min_tiles),
                "min_windows": int(min_windows),
                "max_track_anchor_gap_hours": float(max_track_anchor_gap_hours) if max_track_anchor_gap_hours is not None else float("nan"),
                "detrend_far_rmin_km": float(detrend_far_rmin_km) if detrend_far_rmin_km is not None else float("nan"),
                "detrend_far_rmax_km": float(detrend_far_rmax_km) if detrend_far_rmax_km is not None else float("nan"),
                "min_coverage_frac": float(min_coverage_frac) if min_coverage_frac is not None else float("nan"),
            }
        ]
    )
    summary.to_csv(out.tables / "phase1_alpha_summary.csv", index=False)
    return out_df


def _half_distance_r0(r: np.ndarray, y: np.ndarray) -> float:
    """
    r0：从峰值位置向外，首次达到 y <= 0.5*y_max 的距离（线性插值）。
    若找不到则返回 NaN。
    """
    r = np.asarray(r, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(r) & np.isfinite(y) & (r > 0) & (y >= 0)
    r = r[ok]
    y = y[ok]
    if r.size < 3:
        return float("nan")

    i_max = int(np.nanargmax(y))
    y_max = float(y[i_max])
    if not np.isfinite(y_max) or y_max <= 0:
        return float("nan")
    target = 0.5 * y_max

    for i in range(i_max + 1, r.size):
        if y[i] <= target:
            r0, y0 = float(r[i - 1]), float(y[i - 1])
            r1, y1 = float(r[i]), float(y[i])
            if y1 == y0:
                return float(r1)
            # linear interpolation in y
            frac = (target - y0) / (y1 - y0)
            return float(r0 + frac * (r1 - r0))
    return float("nan")


def run_phase2_collapse(
    *,
    catalog: Path,
    output_root: Path,
    out_dir: Path,
    phi_col: str,
    phase0_csv: Path | None,
    strong_signal_threshold: float,
    time_min: float,
    time_max: float,
    x_min: float,
    x_max: float,
    x_grid_n: int,
    overlap_tol: float,
    min_tiles: int = 0,
    min_windows: int = 0,
    max_track_anchor_gap_hours: float | None = None,
    detrend_far_rmin_km: float | None = None,
    detrend_far_rmax_km: float | None = None,
    min_coverage_frac: float | None = None,
) -> pd.DataFrame:
    specs = load_catalog(catalog)
    out = _out_dirs(out_dir)
    _ensure_dir(out.root)
    _ensure_dir(out.figures)
    _ensure_dir(out.tables)

    strong_slugs: set[str] | None = None
    if phase0_csv is not None and phase0_csv.exists():
        s0 = pd.read_csv(phase0_csv)
        if "slug" in s0.columns and "S" in s0.columns:
            s0["S"] = pd.to_numeric(s0["S"], errors="coerce")
            strong_slugs = set(s0[s0["S"] >= float(strong_signal_threshold)]["slug"].astype(str).tolist())

    curve_rows: list[dict] = []
    r0_rows: list[dict] = []
    interp_rows: list[np.ndarray] = []
    interp_slugs: list[str] = []

    x_grid = np.geomspace(float(x_min), float(x_max), int(x_grid_n))

    for spec in specs:
        if strong_slugs is not None and spec.slug not in strong_slugs:
            continue

        meta = _load_event_metadata(Path(output_root), spec.slug)
        gap_h = _track_anchor_gap_hours(meta)
        if max_track_anchor_gap_hours is not None and gap_h is not None and abs(float(gap_h)) > float(max_track_anchor_gap_hours):
            r0_rows.append(
                {
                    "slug": spec.slug,
                    "name": spec.name,
                    "event_type": spec.event_type,
                    "r0_km": float("nan"),
                    "y_max": float("nan"),
                    "n_windows_in_range": 0,
                    "track_anchor_to_t0_hours": float(gap_h),
                    "note": "t0_misaligned_vs_track_anchor",
                }
            )
            continue

        phi_long = _load_phi_heatmap_long(
            output_root=output_root, slug=spec.slug, phi_col=phi_col, min_hours=float(time_min), max_hours=float(time_max)
        )
        if phi_long is None or phi_long.empty:
            r0_rows.append(
                {
                    "slug": spec.slug,
                    "name": spec.name,
                    "event_type": spec.event_type,
                    "r0_km": float("nan"),
                    "y_max": float("nan"),
                    "n_windows_in_range": 0,
                    "track_anchor_to_t0_hours": float(gap_h) if gap_h is not None else float("nan"),
                    "note": "missing_phi_heatmap",
                }
            )
            continue

        n_windows = int(pd.to_numeric(phi_long["hours_since_quake"], errors="coerce").dropna().nunique())
        if int(min_windows) > 0 and int(n_windows) < int(min_windows):
            r0_rows.append(
                {
                    "slug": spec.slug,
                    "name": spec.name,
                    "event_type": spec.event_type,
                    "r0_km": float("nan"),
                    "y_max": float("nan"),
                    "n_windows_in_range": int(n_windows),
                    "track_anchor_to_t0_hours": float(gap_h) if gap_h is not None else float("nan"),
                    "note": "too_few_time_windows",
                }
            )
            continue

        prof = _radial_profile_from_phi_long(
            phi_long,
            time_min=float(time_min),
            time_max=float(time_max),
            phi_col=phi_col,
            min_tiles=int(min_tiles),
            detrend_far_rmin_km=float(detrend_far_rmin_km) if detrend_far_rmin_km is not None else None,
            detrend_far_rmax_km=float(detrend_far_rmax_km) if detrend_far_rmax_km is not None else None,
            min_coverage_frac=float(min_coverage_frac) if min_coverage_frac is not None else None,
        )
        r = pd.to_numeric(prof["r_center_km"], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(prof["abs_dev"], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(r) & np.isfinite(y) & (r > 0) & (y >= 0)
        r = r[ok]
        y = y[ok]
        if r.size < 3:
            r0_rows.append(
                {
                    "slug": spec.slug,
                    "name": spec.name,
                    "event_type": spec.event_type,
                    "r0_km": float("nan"),
                    "y_max": float("nan"),
                    "n_windows_in_range": int(n_windows),
                    "track_anchor_to_t0_hours": float(gap_h) if gap_h is not None else float("nan"),
                    "note": "too_few_r_bins",
                }
            )
            continue

        y_max = float(np.nanmax(y))
        r0 = _half_distance_r0(r, y)
        r0_rows.append(
            {
                "slug": spec.slug,
                "name": spec.name,
                "event_type": spec.event_type,
                "r0_km": float(r0),
                "y_max": float(y_max),
                "n_windows_in_range": int(n_windows),
                "track_anchor_to_t0_hours": float(gap_h) if gap_h is not None else float("nan"),
                "note": "",
            }
        )

        if not np.isfinite(r0) or r0 <= 0 or not np.isfinite(y_max) or y_max <= 0:
            continue

        x = r / float(r0)
        y_scaled = y / float(y_max)

        for xx, yy in zip(x.tolist(), y_scaled.tolist(), strict=False):
            curve_rows.append({"slug": spec.slug, "event_type": spec.event_type, "x": float(xx), "y": float(yy)})

        # interpolation for overlap metric
        order = np.argsort(x)
        xs = x[order]
        ys = y_scaled[order]
        # np.interp requires ascending and finite
        y_on_grid = np.interp(x_grid, xs, ys, left=np.nan, right=np.nan)
        interp_rows.append(y_on_grid)
        interp_slugs.append(spec.slug)

        per_dir = output_root / spec.slug / "universality_scaling" / "phase2_collapse"
        per = _out_dirs(per_dir)
        _ensure_dir(per.root)
        _ensure_dir(per.figures)
        _ensure_dir(per.tables)
        prof.to_csv(per.tables / "radial_profile.csv", index=False)
        pd.DataFrame([{"r0_km": float(r0), "y_max": float(y_max), "time_min_hours": float(time_min), "time_max_hours": float(time_max)}]).to_csv(
            per.tables / "r0_definition.csv", index=False
        )

    curve_df = pd.DataFrame(curve_rows)
    curve_df.to_csv(out.tables / "phase2_collapse_curves.csv", index=False)
    r0_df = pd.DataFrame(r0_rows)
    r0_df.to_csv(out.tables / "phase2_r0_by_disaster.csv", index=False)

    overlap_fraction = float("nan")
    n_used = 0
    if interp_rows:
        mat = np.vstack(interp_rows)
        n_used = int(mat.shape[0])
        # spread across disasters at each x
        spread = np.nanmax(mat, axis=0) - np.nanmin(mat, axis=0)
        ok = np.isfinite(spread)
        if int(np.sum(ok)) > 0:
            overlap_fraction = float(np.mean(spread[ok] <= float(overlap_tol)))

    pd.DataFrame(
        [
            {
                "n_disasters_used": int(n_used),
                "x_min": float(x_min),
                "x_max": float(x_max),
                "x_grid_n": int(x_grid_n),
                "overlap_tol": float(overlap_tol),
                "overlap_fraction": float(overlap_fraction),
                "time_min_hours": float(time_min),
                "time_max_hours": float(time_max),
                "strong_signal_threshold": float(strong_signal_threshold),
                "min_tiles": int(min_tiles),
                "min_windows": int(min_windows),
                "max_track_anchor_gap_hours": float(max_track_anchor_gap_hours) if max_track_anchor_gap_hours is not None else float("nan"),
                "detrend_far_rmin_km": float(detrend_far_rmin_km) if detrend_far_rmin_km is not None else float("nan"),
                "detrend_far_rmax_km": float(detrend_far_rmax_km) if detrend_far_rmax_km is not None else float("nan"),
                "min_coverage_frac": float(min_coverage_frac) if min_coverage_frac is not None else float("nan"),
            }
        ]
    ).to_csv(out.tables / "phase2_overlap_metric.csv", index=False)

    # plot collapse
    try:
        from disaster import plot_style as ps  # type: ignore
        import matplotlib.pyplot as plt

        with ps.paper_style():
            fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
            if not curve_df.empty:
                for slug, sub in curve_df.groupby("slug", sort=False):
                    ax.plot(sub["x"].to_numpy(dtype=float), sub["y"].to_numpy(dtype=float), linewidth=1.6, alpha=0.8, label=str(slug))
            ax.set_xscale("log")
            ax.set_xlabel("r / r0")
            ax.set_ylabel("abs(phi_mean(r)-1) / max_r abs(phi_mean(r)-1)")
            ax.set_title(f"Collapse attempt (t in [{time_min},{time_max}]h), overlap={overlap_fraction:.2f}")
            ps.despine(ax)
            if not curve_df.empty:
                ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=2, frameon=False, fontsize=8)
            fig.subplots_adjust(bottom=0.28)
            save_png_and_pdf(ps, fig, out.figures / "phase2_collapse_plot.png")
            plt.close(fig)
    except ModuleNotFoundError:
        pass

    return curve_df


def cli_main() -> None:
    p = argparse.ArgumentParser(description="灾后人口响应的普适性检验：Phase0(信号扫描)/Phase1(幂律)/Phase2(坍缩)")
    p.add_argument("--phase", type=str, required=True, choices=["phase0", "phase1", "phase2"])
    p.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog.csv"))
    p.add_argument("--output-root", type=Path, default=Path("outputs"))
    p.add_argument("--out-dir", type=Path, default=Path("outputs/_tmp_universality_scaling"))
    p.add_argument("--phi-col", type=str, default="phi_aggregate")

    # phase0
    p.add_argument("--source", type=str, default="population_redistribution", choices=["population_redistribution", "phi_heatmap"])
    p.add_argument("--min-hours", type=float, default=0.0)
    p.add_argument("--max-hours", type=float, default=None)

    # select strong signals
    p.add_argument("--phase0-csv", type=Path, default=None, help="phase0 输出表（用于筛选强信号灾害）")
    p.add_argument("--strong-signal-threshold", type=float, default=0.1)

    # phase1/2 time window
    p.add_argument("--time-min", type=float, default=24.0)
    p.add_argument("--time-max", type=float, default=72.0)

    # phase1 fit range
    p.add_argument("--r-min", type=float, default=10.0)
    p.add_argument("--r-max", type=float, default=500.0)
    p.add_argument("--y-min", type=float, default=1e-4)

    # phase2 overlap settings
    p.add_argument("--x-min", type=float, default=0.5)
    p.add_argument("--x-max", type=float, default=3.0)
    p.add_argument("--x-grid-n", type=int, default=80)
    p.add_argument("--overlap-tol", type=float, default=0.2)
    p.add_argument("--min-tiles", type=int, default=0, help="仅对 source=phi_heatmap 生效：剖面聚合时要求每个 r_bin 的平均 n_tiles >= min_tiles")
    p.add_argument("--min-windows", type=int, default=0, help="Phase1/2：在 [time_min,time_max] 内要求每个灾害至少有多少个时间窗口（0=不限制）")
    p.add_argument("--max-track-anchor-gap-hours", type=float, default=None, help="Phase1/2：若 metadata.json 含 track_anchor_to_t0_hours，则要求 |gap|<=该阈值（None=不限制）")
    p.add_argument("--detrend-far-rmin-km", type=float, default=None, help="Phase1/2：可选远场去趋势：far-field r>=该阈值用于估计 phi_far(t)")
    p.add_argument("--detrend-far-rmax-km", type=float, default=None, help="Phase1/2：可选远场去趋势：far-field r<=该阈值（默认无上限）")
    p.add_argument("--min-coverage-frac", type=float, default=None, help="Phase1/2：若存在 path_coverage_frac，则要求 r_bin 的平均覆盖率 >= 该阈值（None=不限制）")

    args = p.parse_args()

    out_dir = Path(args.out_dir)
    if args.phase == "phase0":
        run_phase0_signal_scan(
            catalog=Path(args.catalog),
            output_root=Path(args.output_root),
            out_dir=out_dir,
            phi_col=str(args.phi_col),
            source=str(args.source),
            min_hours=float(args.min_hours),
            max_hours=(float(args.max_hours) if args.max_hours is not None else None),
        )
        return

    phase0_csv = Path(args.phase0_csv) if args.phase0_csv is not None else (out_dir / "tables" / "phase0_signal_strength.csv")

    if args.phase == "phase1":
        run_phase1_powerlaw(
            catalog=Path(args.catalog),
            output_root=Path(args.output_root),
            out_dir=out_dir,
            phi_col=str(args.phi_col),
            phase0_csv=phase0_csv,
            strong_signal_threshold=float(args.strong_signal_threshold),
            time_min=float(args.time_min),
            time_max=float(args.time_max),
            r_min=float(args.r_min),
            r_max=float(args.r_max),
            y_min=float(args.y_min),
            min_tiles=int(args.min_tiles),
            min_windows=int(args.min_windows),
            max_track_anchor_gap_hours=(float(args.max_track_anchor_gap_hours) if args.max_track_anchor_gap_hours is not None else None),
            detrend_far_rmin_km=(float(args.detrend_far_rmin_km) if args.detrend_far_rmin_km is not None else None),
            detrend_far_rmax_km=(float(args.detrend_far_rmax_km) if args.detrend_far_rmax_km is not None else None),
            min_coverage_frac=(float(args.min_coverage_frac) if args.min_coverage_frac is not None else None),
        )
        return

    if args.phase == "phase2":
        run_phase2_collapse(
            catalog=Path(args.catalog),
            output_root=Path(args.output_root),
            out_dir=out_dir,
            phi_col=str(args.phi_col),
            phase0_csv=phase0_csv,
            strong_signal_threshold=float(args.strong_signal_threshold),
            time_min=float(args.time_min),
            time_max=float(args.time_max),
            x_min=float(args.x_min),
            x_max=float(args.x_max),
            x_grid_n=int(args.x_grid_n),
            overlap_tol=float(args.overlap_tol),
            min_tiles=int(args.min_tiles),
            min_windows=int(args.min_windows),
            max_track_anchor_gap_hours=(float(args.max_track_anchor_gap_hours) if args.max_track_anchor_gap_hours is not None else None),
            detrend_far_rmin_km=(float(args.detrend_far_rmin_km) if args.detrend_far_rmin_km is not None else None),
            detrend_far_rmax_km=(float(args.detrend_far_rmax_km) if args.detrend_far_rmax_km is not None else None),
            min_coverage_frac=(float(args.min_coverage_frac) if args.min_coverage_frac is not None else None),
        )
        return


def cli_entry() -> None:
    cli_main()


if __name__ == "__main__":
    cli_main()
