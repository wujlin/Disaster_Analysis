from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`。") from e

from disaster.dt_decay import (
    _compute_dt_timeseries,
    _fit_powerlaw_loglog,
    _load_phi_rt_long,
    _monotone_decay_segment,
    _pick_peak,
)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _fit_powerlaw_loglog_wls(t: np.ndarray, y: np.ndarray, weights: np.ndarray) -> tuple[float, float, float]:
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    w = np.asarray(weights, dtype=float)
    ok = np.isfinite(t) & np.isfinite(y) & np.isfinite(w) & (t > 0) & (y > 0) & (w > 0)
    tt = t[ok]
    yy = y[ok]
    ww = w[ok]
    if tt.size < 3:
        return float("nan"), float("nan"), float("nan")

    x = np.log(tt)
    ly = np.log(yy)
    sw = np.sqrt(ww)
    X = np.column_stack([np.ones_like(x), x])
    Xw = X * sw[:, None]
    yw = ly * sw
    beta, *_ = np.linalg.lstsq(Xw, yw, rcond=None)
    intercept = float(beta[0])
    slope = float(beta[1])
    pred = intercept + slope * x

    # weighted R^2 in log space
    y_bar = float(np.sum(ww * ly) / np.sum(ww))
    ss_res = float(np.sum(ww * (ly - pred) ** 2))
    ss_tot = float(np.sum(ww * (ly - y_bar) ** 2))
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")
    alpha = float(-slope)
    return alpha, intercept, r2


def run(
    *,
    output_root: Path,
    dt_flags_csv: Path,
    out_dir: Path,
    fit_min_tprime_hours: float,
    mono_tol_up: float,
    r_max_km: float,
    near_r_km: float,
    min_tiles_overlap: int,
    min_r_bins: int,
    min_near_bins: int,
    peak_min_hours: float | None,
    peak_max_hours: float | None,
) -> None:
    if not dt_flags_csv.exists():
        raise FileNotFoundError(f"未找到 Dt flags：{dt_flags_csv}")

    flags = pd.read_csv(dt_flags_csv)
    if "slug" not in flags.columns or "route_b_selected" not in flags.columns:
        raise SystemExit(f"{dt_flags_csv} 缺少 slug/route_b_selected 列")
    slugs = sorted(flags.loc[flags["route_b_selected"].fillna(False).astype(bool), "slug"].astype(str).tolist())
    if not slugs:
        raise SystemExit(f"{dt_flags_csv} 中 route_b_selected 为空")

    tables = out_dir / "tables"
    _ensure_dir(tables)

    rows: list[dict] = []
    for slug in slugs:
        try:
            df = _load_phi_rt_long(output_root, slug)
        except Exception:
            rows.append(
                {
                    "slug": slug,
                    "alpha_mono": float("nan"),
                    "n_mono": 0,
                    "alpha_full": float("nan"),
                    "n_full": 0,
                    "alpha_full_wls": float("nan"),
                    "r2_mono": float("nan"),
                    "r2_full": float("nan"),
                    "r2_full_wls": float("nan"),
                    "status": "missing_phi_rt_long",
                }
            )
            continue

        ts = _compute_dt_timeseries(
            df,
            r_max_km=float(r_max_km),
            near_r_km=float(near_r_km),
            min_tiles_overlap=int(min_tiles_overlap),
            min_r_bins=int(min_r_bins),
            min_near_bins=int(min_near_bins),
        )
        if ts.empty:
            rows.append(
                {
                    "slug": slug,
                    "alpha_mono": float("nan"),
                    "n_mono": 0,
                    "alpha_full": float("nan"),
                    "n_full": 0,
                    "alpha_full_wls": float("nan"),
                    "r2_mono": float("nan"),
                    "r2_full": float("nan"),
                    "r2_full_wls": float("nan"),
                    "status": "empty_timeseries",
                }
            )
            continue

        t_peak, D_peak = _pick_peak(ts, peak_min_hours=peak_min_hours, peak_max_hours=peak_max_hours)
        post = ts[pd.to_numeric(ts["hours_since_quake"], errors="coerce") > float(t_peak)].copy()
        post = post.sort_values("hours_since_quake", kind="stable").reset_index(drop=True)
        post["t_prime_h"] = pd.to_numeric(post["hours_since_quake"], errors="coerce") - float(t_peak)
        post["D_norm"] = pd.to_numeric(post["D"], errors="coerce") / float(D_peak) if np.isfinite(float(D_peak)) and float(D_peak) > 0 else np.nan
        post = post[pd.to_numeric(post["t_prime_h"], errors="coerce") >= float(fit_min_tprime_hours)].copy()

        t_full = pd.to_numeric(post["t_prime_h"], errors="coerce").to_numpy(dtype=float)
        y_full = pd.to_numeric(post["D_norm"], errors="coerce").to_numpy(dtype=float)

        alpha_full, _, r2_full = _fit_powerlaw_loglog(t_full, y_full)
        w = np.zeros_like(t_full, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            w = 1.0 / t_full
        alpha_full_wls, _, r2_full_wls = _fit_powerlaw_loglog_wls(t_full, y_full, w)

        mono = _monotone_decay_segment(post[["t_prime_h", "D_norm"]].copy(), tol_up=float(mono_tol_up)) if not post.empty else pd.DataFrame()
        t_mono = pd.to_numeric(mono["t_prime_h"], errors="coerce").to_numpy(dtype=float) if not mono.empty else np.array([], dtype=float)
        y_mono = pd.to_numeric(mono["D_norm"], errors="coerce").to_numpy(dtype=float) if not mono.empty else np.array([], dtype=float)
        alpha_mono, _, r2_mono = _fit_powerlaw_loglog(t_mono, y_mono)

        rows.append(
            {
                "slug": slug,
                "alpha_mono": float(alpha_mono),
                "n_mono": int(mono.shape[0]) if mono is not None else 0,
                "alpha_full": float(alpha_full),
                "n_full": int(post.shape[0]),
                "alpha_full_wls": float(alpha_full_wls),
                "r2_mono": float(r2_mono),
                "r2_full": float(r2_full),
                "r2_full_wls": float(r2_full_wls),
                "status": "ok",
            }
        )

    out = pd.DataFrame(rows).sort_values("slug", kind="stable")
    out_csv = tables / "alpha_truncation_comparison.csv"
    out.to_csv(out_csv, index=False)

    # summary
    valid = out[out["status"] == "ok"].copy()
    x_m = pd.to_numeric(valid["alpha_mono"], errors="coerce").to_numpy(dtype=float)
    x_f = pd.to_numeric(valid["alpha_full"], errors="coerce").to_numpy(dtype=float)
    x_w = pd.to_numeric(valid["alpha_full_wls"], errors="coerce").to_numpy(dtype=float)

    def _pearson(a: np.ndarray, b: np.ndarray) -> tuple[float, int]:
        ok = np.isfinite(a) & np.isfinite(b)
        aa = a[ok]
        bb = b[ok]
        if aa.size < 3:
            return float("nan"), int(aa.size)
        return float(np.corrcoef(aa, bb)[0, 1]), int(aa.size)

    r_mf, n_mf = _pearson(x_m, x_f)
    r_mw, n_mw = _pearson(x_m, x_w)

    diff_mf = np.abs(x_m - x_f)
    diff_mw = np.abs(x_m - x_w)
    sign_flip_mf = int(np.sum(np.isfinite(x_m) & np.isfinite(x_f) & (np.sign(x_m) != np.sign(x_f))))
    sign_flip_mw = int(np.sum(np.isfinite(x_m) & np.isfinite(x_w) & (np.sign(x_m) != np.sign(x_w))))

    summary = pd.DataFrame(
        [
            {
                "n_events_total": int(len(slugs)),
                "n_events_ok": int((out["status"] == "ok").sum()),
                "pearson_alpha_mono_vs_full": float(r_mf),
                "pearson_alpha_mono_vs_full_n": int(n_mf),
                "pearson_alpha_mono_vs_full_wls": float(r_mw),
                "pearson_alpha_mono_vs_full_wls_n": int(n_mw),
                "sign_flip_mono_vs_full": int(sign_flip_mf),
                "sign_flip_mono_vs_full_wls": int(sign_flip_mw),
                "max_abs_diff_mono_vs_full": float(np.nanmax(diff_mf)) if np.any(np.isfinite(diff_mf)) else float("nan"),
                "max_abs_diff_mono_vs_full_wls": float(np.nanmax(diff_mw)) if np.any(np.isfinite(diff_mw)) else float("nan"),
                "fit_min_tprime_hours": float(fit_min_tprime_hours),
                "mono_tol_up": float(mono_tol_up),
            }
        ]
    )
    summary_csv = tables / "alpha_truncation_comparison_summary.csv"
    summary.to_csv(summary_csv, index=False)

    meta = {
        "output_root": str(output_root),
        "dt_flags_csv": str(dt_flags_csv),
        "n_selected_slugs": int(len(slugs)),
        "fit_min_tprime_hours": float(fit_min_tprime_hours),
        "mono_tol_up": float(mono_tol_up),
        "r_max_km": float(r_max_km),
        "near_r_km": float(near_r_km),
        "min_tiles_overlap": int(min_tiles_overlap),
        "min_r_bins": int(min_r_bins),
        "min_near_bins": int(min_near_bins),
        "peak_min_hours": (float(peak_min_hours) if peak_min_hours is not None else None),
        "peak_max_hours": (float(peak_max_hours) if peak_max_hours is not None else None),
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[ok] wrote: {out_csv}")
    print(f"[ok] wrote: {summary_csv}")


def cli_main() -> None:
    p = argparse.ArgumentParser(description="比较 alpha_mono vs alpha_full vs alpha_full_wls（Route B）")
    p.add_argument("--output-root", type=Path, default=Path("outputs"))
    p.add_argument("--dt-flags-csv", type=Path, default=Path("outputs/cross_disaster_comparison/Dt_decay/tables/Dt_routeB_sample_flags.csv"))
    p.add_argument("--out-dir", type=Path, default=Path("outputs/cross_disaster_comparison/Dt_decay_truncation_compare"))
    p.add_argument("--fit-min-tprime-hours", type=float, default=24.0)
    p.add_argument("--mono-tol-up", type=float, default=1.05)
    p.add_argument("--r-max-km", type=float, default=200.0)
    p.add_argument("--near-r-km", type=float, default=50.0)
    p.add_argument("--min-tiles-overlap", type=int, default=3)
    p.add_argument("--min-r-bins", type=int, default=5)
    p.add_argument("--min-near-bins", type=int, default=2)
    p.add_argument("--peak-min-hours", type=float, default=None)
    p.add_argument("--peak-max-hours", type=float, default=None)
    args = p.parse_args()

    run(
        output_root=Path(args.output_root),
        dt_flags_csv=Path(args.dt_flags_csv),
        out_dir=Path(args.out_dir),
        fit_min_tprime_hours=float(args.fit_min_tprime_hours),
        mono_tol_up=float(args.mono_tol_up),
        r_max_km=float(args.r_max_km),
        near_r_km=float(args.near_r_km),
        min_tiles_overlap=int(args.min_tiles_overlap),
        min_r_bins=int(args.min_r_bins),
        min_near_bins=int(args.min_near_bins),
        peak_min_hours=(float(args.peak_min_hours) if args.peak_min_hours is not None else None),
        peak_max_hours=(float(args.peak_max_hours) if args.peak_max_hours is not None else None),
    )


if __name__ == "__main__":
    cli_main()
