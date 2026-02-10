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

try:
    from scipy.optimize import curve_fit
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：scipy。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e


@dataclass(frozen=True)
class EventRef:
    output_root: Path
    slug: str


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _safe_float(x: object) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except Exception:
        return None


def _short_name(slug: str) -> str:
    """
    生成用于图注/标注的短名（不追求完美，保证确定性和可读性）。
    """
    s = str(slug).strip().lower()
    if not s:
        return ""
    if s == "turkiye_earthquake_2023":
        return "turkiye"
    if s.startswith("park_fire_california"):
        return "park_fire2"
    if s.startswith("park_fire_2024"):
        return "park_fire1"
    if s.startswith("park_fire_"):
        return "park_fire"
    if s.startswith("moldova_"):
        return "moldova"
    if s.startswith("line_fire_"):
        return "line_fire"
    if s.startswith("wildfires_in_boise"):
        return "boise_fire"

    tokens = s.split("_")
    storm_name = ""
    if s.startswith("hurricane_") and len(tokens) >= 2:
        storm_name = tokens[1]
    elif s.startswith("typhoon_") and len(tokens) >= 2:
        storm_name = tokens[1]
    elif s.startswith("tropical_storm_") and len(tokens) >= 3:
        storm_name = tokens[2]

    # geographic hints (last match wins)
    geo_map = {
        "texas": "tx",
        "florida": "fl",
        "puerto": "pr",
        "rico": "pr",
        "quintana": "qr",
        "yucatan": "yuc",
        "mexico": "mx",
        "guerrero": "gue",
        "taiwan": "tw",
        "vietnam": "vn",
        "philippines": "ph",
        "nepal": "np",
        "bangladesh": "bd",
        "gujarat": "gj",
        "quito": "quito",
        "guinea": "gn",
        "nigeria": "ng",
        "moldova": "md",
        "colombia": "co",
        "california": "ca",
    }
    geo = ""
    for t in tokens:
        if t in geo_map:
            geo = geo_map[t]

    if storm_name:
        if "pre" in tokens and "landfall" in tokens:
            return f"{storm_name}_pre"
        if storm_name == "john":
            if "guerrero" in tokens:
                return "john_gue"
            if "southern" in tokens and "mexico" in tokens:
                return "john_sm"
        if storm_name == "beryl":
            if "texas" in tokens:
                return "beryl_tx"
            if "quintana" in tokens:
                return "beryl_qr"
        if storm_name == "yagi":
            if "vietnam" in tokens:
                return "yagi_vn"
            if "philippines" in tokens:
                return "yagi_ph"
        if storm_name == "kristine":
            return "kristine_ph"
        if storm_name == "enteng":
            return "enteng_ph"
        if storm_name == "debby":
            return "debby_pre"
        if storm_name == "krathon":
            return "krathon_tw"
        if storm_name == "helene":
            return "helene_pre"
        if storm_name == "milton":
            return "milton_fl"
        if storm_name == "ernesto":
            return "ernesto_pr"
        if geo:
            return f"{storm_name}_{geo}"
        return storm_name

    # floods / wildfires: try a stable keyword
    if s.startswith("the_flooding_across_") and "nepal" in tokens:
        return "nepal_fld"
    if s.startswith("the_flooding_across_") and "bangladesh" in tokens:
        return "bangladesh_fld"
    if s.startswith("the_flooding_across_") and "gujarat" in tokens:
        return "gujarat_fld"
    if s.startswith("the_wildfires_in_quito"):
        return "quito_fire"

    # fallback: keep it short but unique-ish
    return s[:22]


def _discover_events(output_root: Path) -> list[EventRef]:
    root = Path(output_root)
    if not root.exists():
        return []
    out: list[EventRef] = []
    for d in sorted(root.iterdir(), key=lambda x: x.name):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        p = d / "phi_heatmap" / "tables" / "phi_rt_long.csv"
        if p.exists():
            out.append(EventRef(output_root=root, slug=d.name))
    return out


def _parse_event_ref(s: str) -> EventRef:
    s = str(s).strip()
    if ":" not in s:
        raise SystemExit(f"--event 需要形如 <output_root>:<slug>，但收到：{s}")
    root_s, slug = s.split(":", 1)
    root = Path(root_s).expanduser()
    slug = str(slug).strip()
    if not slug:
        raise SystemExit(f"--event 的 slug 为空：{s}")
    return EventRef(output_root=root, slug=slug)


def _load_metadata(output_root: Path, slug: str) -> tuple[str, str]:
    meta_p = Path(output_root) / slug / "metadata.json"
    if meta_p.exists():
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            name = str(meta.get("name") or slug)
            event_type = str(meta.get("event_type") or slug.split("_", 1)[0])
            return name, event_type
        except Exception:
            pass
    return slug, slug.split("_", 1)[0]


def _load_phi_rt_long(output_root: Path, slug: str) -> pd.DataFrame:
    p = Path(output_root) / slug / "phi_heatmap" / "tables" / "phi_rt_long.csv"
    if not p.exists():
        raise FileNotFoundError(f"未找到：{p}")
    df = pd.read_csv(p)
    need = {"hours_since_quake", "r_bin_km", "phi_overlap", "n_tiles_overlap"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise SystemExit(f"{p} 缺少列：{miss}")
    for c in ["hours_since_quake", "r_bin_km", "phi_overlap", "n_tiles_overlap"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["hours_since_quake", "r_bin_km", "phi_overlap", "n_tiles_overlap"]).copy()
    return df


def _compute_dt_timeseries(
    df: pd.DataFrame,
    *,
    r_max_km: float,
    near_r_km: float,
    min_tiles_overlap: int,
    min_r_bins: int,
    min_near_bins: int,
) -> pd.DataFrame:
    sub = df.copy()
    sub = sub[(sub["r_bin_km"] <= float(r_max_km)) & (sub["n_tiles_overlap"] >= float(min_tiles_overlap))].copy()
    if sub.empty:
        return pd.DataFrame(columns=["hours_since_quake", "D", "near_delta", "n_r_bins"])
    sub["delta"] = sub["phi_overlap"] - 1.0

    rows: list[dict] = []
    for t, g in sub.groupby("hours_since_quake", sort=True):
        if g.shape[0] < int(min_r_bins):
            continue
        D = float(np.mean(np.abs(pd.to_numeric(g["delta"], errors="coerce").to_numpy(dtype=float))))
        near = g[g["r_bin_km"] <= float(near_r_km)]["delta"].to_numpy(dtype=float)
        near = near[np.isfinite(near)]
        near_delta = float(np.mean(near)) if near.size >= int(min_near_bins) else float("nan")
        rows.append({"hours_since_quake": float(t), "D": float(D), "near_delta": float(near_delta), "n_r_bins": int(g.shape[0])})

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("hours_since_quake", kind="stable").reset_index(drop=True)
    return out


def _pick_peak(ts: pd.DataFrame, *, peak_min_hours: float | None, peak_max_hours: float | None) -> tuple[float, float]:
    if ts.empty:
        return float("nan"), float("nan")
    sub = ts.copy()
    if peak_min_hours is not None:
        sub = sub[pd.to_numeric(sub["hours_since_quake"], errors="coerce") >= float(peak_min_hours)].copy()
    if peak_max_hours is not None:
        sub = sub[pd.to_numeric(sub["hours_since_quake"], errors="coerce") <= float(peak_max_hours)].copy()
    if sub.empty:
        sub = ts.copy()
    i = int(pd.to_numeric(sub["D"], errors="coerce").idxmax())
    row = ts.loc[i]
    return float(row["hours_since_quake"]), float(row["D"])


def _classify_event(
    ts: pd.DataFrame,
    *,
    D_peak: float,
    D_peak_min: float,
    min_time_windows: int,
    peak_frac: float,
    near_thresh: float,
) -> tuple[str, float]:
    """
    返回：(event_type, near_delta_mean_over_peak_windows)
    event_type ∈ {EVAC, INFL, LOW_SIGNAL, EXCLUDED_SHORT, NEUTRAL}
    """
    if ts.empty:
        return "EXCLUDED_SHORT", float("nan")
    if int(ts.shape[0]) < int(min_time_windows):
        return "EXCLUDED_SHORT", float("nan")
    if not np.isfinite(float(D_peak)) or float(D_peak) < float(D_peak_min):
        return "LOW_SIGNAL", float("nan")

    cut = float(peak_frac) * float(D_peak)
    peak_w = ts[pd.to_numeric(ts["D"], errors="coerce") >= float(cut)].copy()
    near = pd.to_numeric(peak_w["near_delta"], errors="coerce").to_numpy(dtype=float)
    near = near[np.isfinite(near)]
    near_mean = float(np.mean(near)) if near.size else float("nan")

    if np.isfinite(near_mean) and near_mean < -float(near_thresh):
        return "EVAC", float(near_mean)
    if np.isfinite(near_mean) and near_mean > float(near_thresh):
        return "INFL", float(near_mean)
    return "NEUTRAL", float(near_mean)


def _monotone_decay_segment(
    post: pd.DataFrame,
    *,
    tol_up: float,
) -> pd.DataFrame:
    """
    给定 post-peak 序列（按 t' 升序），返回“首次反弹即截断”的单调衰减段。
    允许小幅波动：D_{i+1} <= D_i * tol_up 视为继续。
    """
    if post.empty:
        return post.copy()
    post = post.sort_values("t_prime_h", kind="stable").reset_index(drop=True)
    keep_idx = [0]
    for i in range(post.shape[0] - 1):
        di = float(post.loc[i, "D_norm"])
        dj = float(post.loc[i + 1, "D_norm"])
        if not (np.isfinite(di) and np.isfinite(dj)):
            break
        if dj <= di * float(tol_up):
            keep_idx.append(i + 1)
            continue
        break
    return post.loc[keep_idx].copy().reset_index(drop=True)


def _fit_powerlaw_loglog(t: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """
    拟合 y = A * t^{-alpha} 的 log-log OLS；返回 (alpha, logA, r2)。
    """
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(t) & np.isfinite(y) & (t > 0) & (y > 0)
    t1 = t[ok]
    y1 = y[ok]
    if t1.size < 3:
        return float("nan"), float("nan"), float("nan")
    x = np.log(t1)
    yy = np.log(y1)
    slope, intercept = np.polyfit(x, yy, deg=1)
    yy_hat = slope * x + intercept
    ss_res = float(np.sum(np.square(yy - yy_hat)))
    ss_tot = float(np.sum(np.square(yy - float(np.mean(yy))))) if yy.size else float("nan")
    r2 = float(1.0 - ss_res / ss_tot) if np.isfinite(ss_tot) and ss_tot > 0 else float("nan")
    alpha = float(-slope)
    logA = float(intercept)
    return alpha, logA, r2


def _bic_from_sse(*, sse: float, n: int, k: int) -> float:
    if n <= 0 or k <= 0 or not np.isfinite(sse):
        return float("nan")
    sse = float(max(sse, 1e-12))
    return float(n * np.log(sse / float(n)) + float(k) * np.log(float(n)))


def _fit_models_bic(
    t: np.ndarray,
    y: np.ndarray,
) -> dict:
    """
    在 real space 上拟合三模型，并返回 BIC 与参数。
    """
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(t) & np.isfinite(y) & (t > 0) & (y > 0)
    tt = t[ok]
    yy = y[ok]
    if tt.size < 3:
        return {"ok": 0}

    def f_powerlaw(t_in: np.ndarray, A: float, alpha: float) -> np.ndarray:
        return A * np.power(np.asarray(t_in, dtype=float), -alpha)

    def f_exp(t_in: np.ndarray, A: float, tau: float) -> np.ndarray:
        return A * np.exp(-np.asarray(t_in, dtype=float) / tau)

    def f_strexp(t_in: np.ndarray, A: float, tau: float, beta: float) -> np.ndarray:
        return A * np.exp(-np.power(np.asarray(t_in, dtype=float) / tau, beta))

    # initial guesses
    A0 = float(np.nanmax(yy)) if yy.size else 1.0
    A0 = float(np.clip(A0, 0.1, 5.0))
    t_med = float(np.nanmedian(tt)) if tt.size else 48.0
    t_med = float(t_med) if np.isfinite(t_med) and t_med > 0 else 48.0
    alpha0 = 0.5
    tau0 = float(np.clip(t_med, 1.0, 2000.0))
    beta0 = 1.0

    out: dict[str, object] = {"ok": 1, "n_pts": int(tt.size)}

    # power-law
    try:
        popt, _ = curve_fit(
            f_powerlaw,
            tt,
            yy,
            p0=(A0, alpha0),
            bounds=([0.0, -1.0], [5.0, 3.0]),
            maxfev=20000,
        )
        A_p, alpha_p = float(popt[0]), float(popt[1])
        y_hat = f_powerlaw(tt, A_p, alpha_p)
        sse = float(np.sum(np.square(yy - y_hat)))
        out.update({"BIC_power": _bic_from_sse(sse=sse, n=int(tt.size), k=2), "A_power": A_p, "alpha_power": alpha_p})
    except Exception:
        out.update({"BIC_power": float("nan"), "A_power": float("nan"), "alpha_power": float("nan")})

    # exponential
    try:
        popt, _ = curve_fit(
            f_exp,
            tt,
            yy,
            p0=(A0, tau0),
            bounds=([0.0, 1.0], [5.0, 2000.0]),
            maxfev=20000,
        )
        A_e, tau_e = float(popt[0]), float(popt[1])
        y_hat = f_exp(tt, A_e, tau_e)
        sse = float(np.sum(np.square(yy - y_hat)))
        out.update({"BIC_exp": _bic_from_sse(sse=sse, n=int(tt.size), k=2), "A_exp": A_e, "tau_exp": tau_e})
    except Exception:
        out.update({"BIC_exp": float("nan"), "A_exp": float("nan"), "tau_exp": float("nan")})

    # stretched exponential
    try:
        popt, _ = curve_fit(
            f_strexp,
            tt,
            yy,
            p0=(A0, tau0, beta0),
            bounds=([0.0, 1.0, 0.01], [5.0, 2000.0, 3.0]),
            maxfev=40000,
        )
        A_s, tau_s, beta_s = float(popt[0]), float(popt[1]), float(popt[2])
        y_hat = f_strexp(tt, A_s, tau_s, beta_s)
        sse = float(np.sum(np.square(yy - y_hat)))
        out.update(
            {"BIC_strexp": _bic_from_sse(sse=sse, n=int(tt.size), k=3), "A_strexp": A_s, "tau_strexp": tau_s, "beta_strexp": beta_s}
        )
    except Exception:
        out.update({"BIC_strexp": float("nan"), "A_strexp": float("nan"), "tau_strexp": float("nan"), "beta_strexp": float("nan")})

    return out


def _tau50(t_prime_h: np.ndarray, y: np.ndarray) -> tuple[float, int]:
    t_prime_h = np.asarray(t_prime_h, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(t_prime_h) & np.isfinite(y) & (t_prime_h > 0)
    t1 = t_prime_h[ok]
    y1 = y[ok]
    if t1.size == 0:
        return float("nan"), 0
    idx = np.where(y1 <= 0.5)[0]
    if idx.size:
        return float(t1[int(idx[0])]), 0
    return float(np.max(t1)), 1


def run(
    *,
    output_root: Path,
    out_dir: Path,
    slugs: list[str],
    exclude_slugs: list[str],
    r_max_km: float,
    near_r_km: float,
    min_tiles_overlap: int,
    min_r_bins: int,
    min_near_bins: int,
    peak_min_hours: float | None,
    peak_max_hours: float | None,
    D_peak_min: float,
    min_time_windows: int,
    peak_frac: float,
    near_thresh: float,
    mono_tol_up: float,
) -> None:
    output_root = Path(output_root)
    out_dir = Path(out_dir)
    tabs = out_dir / "tables"
    figs = out_dir / "figures"
    _ensure_dir(tabs)
    _ensure_dir(figs)

    refs = {r.slug: r for r in _discover_events(output_root)}
    want = [str(s).strip() for s in (slugs or []) if str(s).strip()]
    if want and len(want) == 1 and want[0].lower() == "all":
        want = []
    if not want:
        want = sorted(refs.keys())
    exclude = {str(s).strip() for s in (exclude_slugs or []) if str(s).strip()}
    if exclude:
        want = [s for s in want if s not in exclude]

    all_rows: list[dict] = []
    summary_rows: list[dict] = []
    fit_rows: list[dict] = []
    bic_rows: list[dict] = []
    collapse_rows: list[dict] = []

    for slug in want:
        if slug not in refs:
            continue
        ref = refs[slug]
        name, disaster_type = _load_metadata(ref.output_root, slug)
        df = _load_phi_rt_long(ref.output_root, slug)

        ts = _compute_dt_timeseries(
            df,
            r_max_km=float(r_max_km),
            near_r_km=float(near_r_km),
            min_tiles_overlap=int(min_tiles_overlap),
            min_r_bins=int(min_r_bins),
            min_near_bins=int(min_near_bins),
        )

        t_peak, D_peak = _pick_peak(ts, peak_min_hours=peak_min_hours, peak_max_hours=peak_max_hours)
        event_type, near_mean = _classify_event(
            ts,
            D_peak=float(D_peak),
            D_peak_min=float(D_peak_min),
            min_time_windows=int(min_time_windows),
            peak_frac=float(peak_frac),
            near_thresh=float(near_thresh),
        )

        # per-time rows
        if not ts.empty and np.isfinite(float(D_peak)) and float(D_peak) > 0:
            ts2 = ts.copy()
            ts2["t_hours"] = pd.to_numeric(ts2["hours_since_quake"], errors="coerce")
            ts2["D_peak"] = float(D_peak)
            ts2["t_peak_hours"] = float(t_peak)
            ts2["D_norm"] = ts2["D"].to_numpy(dtype=float) / float(D_peak)
            ts2["short_name"] = _short_name(slug)
            ts2["slug"] = str(slug)
            ts2["name"] = str(name)
            ts2["disaster_type"] = str(disaster_type)
            ts2["event_type"] = str(event_type)
            for r in ts2.to_dict(orient="records"):
                all_rows.append(r)

        # summary row
        summary_rows.append(
            {
                "slug": str(slug),
                "short_name": _short_name(slug),
                "name": str(name),
                "disaster_type": str(disaster_type),
                "output_root": str(ref.output_root),
                "n_time_windows": int(ts.shape[0]),
                "t_peak_hours": float(t_peak),
                "D_peak": float(D_peak),
                "event_type": str(event_type),
                "near_delta_peak_windows_mean": float(near_mean),
            }
        )

        # post-peak arrays for fits
        if ts.empty or not np.isfinite(float(t_peak)) or not np.isfinite(float(D_peak)) or float(D_peak) <= 0:
            continue
        if event_type in {"EXCLUDED_SHORT"}:
            continue

        post = ts.copy()
        post = post[pd.to_numeric(post["hours_since_quake"], errors="coerce") > float(t_peak)].copy()
        post = post.sort_values("hours_since_quake", kind="stable").reset_index(drop=True)
        post["t_prime_h"] = pd.to_numeric(post["hours_since_quake"], errors="coerce") - float(t_peak)
        post["D_norm"] = pd.to_numeric(post["D"], errors="coerce") / float(D_peak)

        # Task 2: monotone segment fit（即使 post 为空也写一行，便于全表对齐）
        mono = _monotone_decay_segment(post[["t_prime_h", "D_norm"]].copy(), tol_up=float(mono_tol_up)) if not post.empty else pd.DataFrame()
        alpha, logA, r2 = _fit_powerlaw_loglog(
            pd.to_numeric(mono["t_prime_h"], errors="coerce").to_numpy(dtype=float) if not mono.empty else np.array([], dtype=float),
            pd.to_numeric(mono["D_norm"], errors="coerce").to_numpy(dtype=float) if not mono.empty else np.array([], dtype=float),
        )
        fit_rows.append(
            {
                "slug": str(slug),
                "short_name": _short_name(slug),
                "disaster_type": str(disaster_type),
                "event_type": str(event_type),
                "D_peak": float(D_peak),
                "t_peak_hours": float(t_peak),
                "n_mono": int(mono.shape[0]) if mono is not None else 0,
                "n_total_post": int(post.shape[0]),
                "alpha": float(alpha),
                "logA": float(logA),
                "r2": float(r2),
                "t_decay_start": float(pd.to_numeric(mono["t_prime_h"], errors="coerce").min()) if mono is not None and not mono.empty else float("nan"),
                "t_decay_end": float(pd.to_numeric(mono["t_prime_h"], errors="coerce").max()) if mono is not None and not mono.empty else float("nan"),
            }
        )

        # Task 3: BIC compare on full post-peak
        bic = (
            _fit_models_bic(
                pd.to_numeric(post["t_prime_h"], errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(post["D_norm"], errors="coerce").to_numpy(dtype=float),
            )
            if not post.empty
            else {"ok": 0, "n_pts": 0}
        )
        Bp = float(bic.get("BIC_power", float("nan")))
        Be = float(bic.get("BIC_exp", float("nan")))
        Bs = float(bic.get("BIC_strexp", float("nan")))
        finite = [x for x in [Bp, Be, Bs] if np.isfinite(float(x))]
        best = float(min(finite)) if finite else float("nan")
        best_model = ""
        if np.isfinite(best):
            if np.isfinite(Bp) and abs(Bp - best) < 1e-9:
                best_model = "power_law"
            elif np.isfinite(Be) and abs(Be - best) < 1e-9:
                best_model = "exponential"
            elif np.isfinite(Bs) and abs(Bs - best) < 1e-9:
                best_model = "stretched_exp"
        bic_rows.append(
            {
                "slug": str(slug),
                "short_name": _short_name(slug),
                "disaster_type": str(disaster_type),
                "event_type": str(event_type),
                "n_pts": int(bic.get("n_pts", int(post.shape[0]))),
                "best_model": str(best_model),
                "BIC_power": float(Bp),
                "BIC_exp": float(Be),
                "BIC_strexp": float(Bs),
                "dBIC_power": float(Bp - best) if np.isfinite(Bp) and np.isfinite(best) else float("nan"),
                "dBIC_exp": float(Be - best) if np.isfinite(Be) and np.isfinite(best) else float("nan"),
                "dBIC_strexp": float(Bs - best) if np.isfinite(Bs) and np.isfinite(best) else float("nan"),
                "alpha_power": float(bic.get("alpha_power", float("nan"))),
                "tau_exp": float(bic.get("tau_exp", float("nan"))),
                "tau_strexp": float(bic.get("tau_strexp", float("nan"))),
                "beta_strexp": float(bic.get("beta_strexp", float("nan"))),
            }
        )

        # Task 4: tau_50 for collapse（无 post 时写 NaN）
        tau50, lower_bound = (
            _tau50(
                pd.to_numeric(post["t_prime_h"], errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(post["D_norm"], errors="coerce").to_numpy(dtype=float),
            )
            if not post.empty
            else (float("nan"), 0)
        )
        collapse_rows.append(
            {
                "slug": str(slug),
                "short_name": _short_name(slug),
                "disaster_type": str(disaster_type),
                "event_type": str(event_type),
                "t_peak_hours": float(t_peak),
                "D_peak": float(D_peak),
                "tau50_h": float(tau50),
                "tau50_lower_bound": int(lower_bound),
            }
        )

    # tables
    dt_df = pd.DataFrame(all_rows)
    summary_df = pd.DataFrame(summary_rows)
    fits_df = pd.DataFrame(fit_rows)
    bic_df = pd.DataFrame(bic_rows)
    collapse_df = pd.DataFrame(collapse_rows)

    dt_df.to_csv(tabs / "Dt_all_events.csv", index=False)
    summary_df.to_csv(tabs / "Dt_event_summary.csv", index=False)
    fits_df.to_csv(tabs / "Dt_powerlaw_fits.csv", index=False)
    bic_df.to_csv(tabs / "Dt_model_bic.csv", index=False)
    collapse_df.to_csv(tabs / "Dt_tau50.csv", index=False)

    # collapse quality table
    bins = [(0.0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, 2.5), (2.5, 3.0)]
    q_rows: list[dict] = []
    if not dt_df.empty and not collapse_df.empty:
        # build post-peak normalized time for each event
        dt_post = dt_df.copy()
        dt_post = dt_post[pd.to_numeric(dt_post["hours_since_quake"], errors="coerce") > pd.to_numeric(dt_post["t_peak_hours"], errors="coerce")].copy()
        dt_post["t_prime_h"] = pd.to_numeric(dt_post["hours_since_quake"], errors="coerce") - pd.to_numeric(dt_post["t_peak_hours"], errors="coerce")
        dt_post = dt_post.merge(collapse_df[["slug", "tau50_h", "tau50_lower_bound"]], on="slug", how="left")
        dt_post["t_tilde"] = pd.to_numeric(dt_post["t_prime_h"], errors="coerce") / pd.to_numeric(dt_post["tau50_h"], errors="coerce")
        dt_post["D_norm"] = pd.to_numeric(dt_post["D_norm"], errors="coerce")

        def _group_quality(group_name: str, want_types: set[str] | None) -> None:
            g = dt_post.copy()
            if want_types is not None:
                g = g[g["event_type"].astype(str).isin(want_types)].copy()
            for lo, hi in bins:
                vals: list[float] = []
                for slug, sub in g.groupby("slug", sort=False):
                    x = pd.to_numeric(sub["t_tilde"], errors="coerce").to_numpy(dtype=float)
                    y = pd.to_numeric(sub["D_norm"], errors="coerce").to_numpy(dtype=float)
                    m = np.isfinite(x) & np.isfinite(y) & (x >= lo) & (x < hi)
                    if np.sum(m) == 0:
                        continue
                    vals.append(float(np.mean(y[m])))
                vals_arr = np.asarray(vals, dtype=float)
                n = int(np.sum(np.isfinite(vals_arr)))
                mean = float(np.nanmean(vals_arr)) if n else float("nan")
                std = float(np.nanstd(vals_arr, ddof=1)) if n >= 2 else float("nan")
                cv = float(std / mean) if np.isfinite(std) and np.isfinite(mean) and mean != 0 else float("nan")
                if n < 3:
                    quality = "insufficient"
                    cv = float("nan")
                elif np.isfinite(cv):
                    if cv < 0.3:
                        quality = "good"
                    elif cv < 0.5:
                        quality = "medium"
                    else:
                        quality = "bad"
                else:
                    quality = ""
                q_rows.append(
                    {
                        "group": group_name,
                        "bin_lo": float(lo),
                        "bin_hi": float(hi),
                        "n_events": int(n),
                        "mean_Dnorm": float(mean),
                        "std_Dnorm": float(std),
                        "cv": float(cv),
                        "quality": str(quality),
                    }
                )

        _group_quality("all", None)
        _group_quality("EVAC", {"EVAC"})
        _group_quality("INFL", {"INFL"})

    q_df = pd.DataFrame(q_rows)
    q_df.to_csv(tabs / "Dt_collapse_quality.csv", index=False)

    # figures (optional)
    try:
        from disaster import plot_style as ps  # type: ignore
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        meta = {
            "output_root": str(output_root),
            "n_events": int(len(want)),
            "r_max_km": float(r_max_km),
            "near_r_km": float(near_r_km),
            "min_tiles_overlap": int(min_tiles_overlap),
            "min_r_bins": int(min_r_bins),
            "min_near_bins": int(min_near_bins),
        }
        (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    # palette: EVAC red, INFL blue, others gray
    color_map = {"EVAC": ps.OKABE_ITO["vermillion"], "INFL": ps.OKABE_ITO["blue"], "LOW_SIGNAL": ps.OKABE_ITO["gray"], "NEUTRAL": ps.OKABE_ITO["gray"]}

    # Fig 1: all events decay (log-log) + power-law fit on mono segment (if available)
    if not dt_df.empty:
        # compute t' for plotting
        d = dt_df.copy()
        d = d[pd.to_numeric(d["hours_since_quake"], errors="coerce") > pd.to_numeric(d["t_peak_hours"], errors="coerce")].copy()
        d["t_prime_h"] = pd.to_numeric(d["hours_since_quake"], errors="coerce") - pd.to_numeric(d["t_peak_hours"], errors="coerce")
        d = d[(pd.to_numeric(d["t_prime_h"], errors="coerce") > 0) & (pd.to_numeric(d["D_norm"], errors="coerce") > 0)].copy()

        with ps.paper_style():
            fig, ax = plt.subplots(figsize=(6.6, 4.2))
            for slug, sub in d.groupby("slug", sort=False):
                sub = sub.sort_values("t_prime_h", kind="stable")
                et = str(sub["event_type"].iloc[0])
                c = color_map.get(et, ps.OKABE_ITO["gray"])
                x = pd.to_numeric(sub["t_prime_h"], errors="coerce").to_numpy(dtype=float)
                y = pd.to_numeric(sub["D_norm"], errors="coerce").to_numpy(dtype=float)
                ok = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
                x = x[ok]
                y = y[ok]
                if x.size < 3:
                    continue
                ax.plot(x, y, color=c, alpha=0.55, lw=1.6)

            # overlay mono-fit lines (light)
            if not fits_df.empty:
                for _, r in fits_df.iterrows():
                    alpha = _safe_float(r.get("alpha"))
                    logA = _safe_float(r.get("logA"))
                    t0 = _safe_float(r.get("t_decay_start"))
                    t1 = _safe_float(r.get("t_decay_end"))
                    slug = str(r.get("slug", ""))
                    if alpha is None or logA is None or t0 is None or t1 is None:
                        continue
                    et = str(r.get("event_type", ""))
                    c = color_map.get(et, ps.OKABE_ITO["gray"])
                    xx = np.geomspace(max(t0, 1e-3), max(t1, t0 * 1.01), 80)
                    yy = np.exp(float(logA)) * np.power(xx, -float(alpha))
                    ax.plot(xx, yy, color=c, alpha=0.25, lw=2.2)

            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_xlabel("t' = t - t_peak (hours)")
            ax.set_ylabel("D(t') / D_peak")
            ax.set_title("Dt decay (all events, r<=200km)")
            ps.despine(ax)
            fig.tight_layout()
            ps.save_figure(fig, figs / "Dt_decay_all_events_loglog.png", dpi=220)
            ps.save_figure(fig, figs / "Dt_decay_all_events_loglog.pdf")
            plt.close(fig)

    # Fig 2: alpha comparison (EVAC vs INFL) + alpha vs D_peak
    if not fits_df.empty:
        fd = fits_df.copy()
        fd["alpha"] = pd.to_numeric(fd["alpha"], errors="coerce")
        fd["D_peak"] = pd.to_numeric(fd["D_peak"], errors="coerce")
        fd = fd.dropna(subset=["alpha", "D_peak"]).copy()
        if not fd.empty:
            with ps.paper_style():
                fig, axes = plt.subplots(1, 2, figsize=(6.8, 3.1), constrained_layout=True)
                ax0, ax1 = axes[0], axes[1]

                # box + strip
                order = ["EVAC", "INFL", "NEUTRAL", "LOW_SIGNAL"]
                plot_df = fd[fd["event_type"].astype(str).isin({"EVAC", "INFL"})].copy()
                labels = [t for t in order if t in set(plot_df["event_type"].astype(str).unique().tolist())]
                data = [plot_df[plot_df["event_type"] == t]["alpha"].to_numpy(dtype=float) for t in labels]
                ax0.boxplot(data, labels=labels, showfliers=False)
                for i, t in enumerate(labels, start=1):
                    y = plot_df[plot_df["event_type"] == t]["alpha"].to_numpy(dtype=float)
                    x = np.random.default_rng(0).normal(loc=i, scale=0.06, size=y.size)
                    ax0.scatter(x, y, s=22, alpha=0.8, color=color_map.get(t, "black"), linewidths=0)
                ax0.set_ylabel("alpha (monotone decay)")
                ax0.set_title("alpha by type")
                ps.despine(ax0)

                # scatter alpha vs D_peak
                for _, r in plot_df.iterrows():
                    et = str(r.get("event_type"))
                    c = color_map.get(et, ps.OKABE_ITO["gray"])
                    ax1.scatter(float(r["D_peak"]), float(r["alpha"]), s=28, color=c, alpha=0.85, linewidths=0)
                    ax1.text(float(r["D_peak"]), float(r["alpha"]), str(r.get("short_name", "")), fontsize=7, ha="left", va="bottom", alpha=0.85)
                ax1.set_xlabel("D_peak")
                ax1.set_ylabel("alpha")
                ax1.set_title("alpha vs D_peak")
                ps.despine(ax1)

                ps.save_figure(fig, figs / "Dt_alpha_comparison.png", dpi=220)
                ps.save_figure(fig, figs / "Dt_alpha_comparison.pdf")
                plt.close(fig)

    # Fig 3: collapse plots
    if not dt_df.empty and not collapse_df.empty:
        dt_post = dt_df.copy()
        dt_post = dt_post[pd.to_numeric(dt_post["hours_since_quake"], errors="coerce") > pd.to_numeric(dt_post["t_peak_hours"], errors="coerce")].copy()
        dt_post["t_prime_h"] = pd.to_numeric(dt_post["hours_since_quake"], errors="coerce") - pd.to_numeric(dt_post["t_peak_hours"], errors="coerce")
        dt_post = dt_post.merge(collapse_df[["slug", "tau50_h", "tau50_lower_bound"]], on="slug", how="left")
        dt_post["t_tilde"] = pd.to_numeric(dt_post["t_prime_h"], errors="coerce") / pd.to_numeric(dt_post["tau50_h"], errors="coerce")
        dt_post = dt_post[(pd.to_numeric(dt_post["t_tilde"], errors="coerce") >= 0) & (pd.to_numeric(dt_post["t_tilde"], errors="coerce") <= 3.2)].copy()

        def _plot_collapse(df_in: pd.DataFrame, out_name: str, title: str) -> None:
            if df_in.empty:
                return
            with ps.paper_style():
                fig, ax = plt.subplots(figsize=(6.4, 3.9))
                for slug, sub in df_in.groupby("slug", sort=False):
                    et = str(sub["event_type"].iloc[0])
                    c = color_map.get(et, ps.OKABE_ITO["gray"])
                    x = pd.to_numeric(sub["t_tilde"], errors="coerce").to_numpy(dtype=float)
                    y = pd.to_numeric(sub["D_norm"], errors="coerce").to_numpy(dtype=float)
                    ok = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
                    x = x[ok]
                    y = y[ok]
                    if x.size < 2:
                        continue
                    ax.scatter(x, y, s=10, alpha=0.35, color=c, linewidths=0, rasterized=True)
                ax.set_xscale("linear")
                ax.set_yscale("log")
                ax.set_xlabel("t' / tau50")
                ax.set_ylabel("D(t') / D_peak")
                ax.set_title(title)
                ps.despine(ax)
                fig.tight_layout()
                ps.save_figure(fig, figs / f"{out_name}.png", dpi=220)
                ps.save_figure(fig, figs / f"{out_name}.pdf")
                plt.close(fig)

        _plot_collapse(dt_post, "Dt_collapse_all", "Collapse: all events")
        _plot_collapse(dt_post[dt_post["event_type"].astype(str).isin({"EVAC", "INFL"})], "Dt_collapse_by_type", "Collapse: EVAC/INFL")

    # Fig 4: panels of D(t) absolute (linear) + peak + mono segment highlight
    if not dt_df.empty:
        # build per-event mono segments in original time coordinates
        mono_map: dict[str, tuple[float, float]] = {}
        if not fits_df.empty:
            for _, r in fits_df.iterrows():
                slug = str(r.get("slug", ""))
                t_peak_h = _safe_float(r.get("t_peak_hours"))
                t0 = _safe_float(r.get("t_decay_start"))
                t1 = _safe_float(r.get("t_decay_end"))
                if not slug or t_peak_h is None or t0 is None or t1 is None:
                    continue
                mono_map[slug] = (float(t_peak_h + t0), float(t_peak_h + t1))

        panel_df = dt_df.copy()
        panel_df["hours_since_quake"] = pd.to_numeric(panel_df["hours_since_quake"], errors="coerce")
        panel_df["D"] = pd.to_numeric(panel_df["D"], errors="coerce")
        panel_df = panel_df.dropna(subset=["hours_since_quake", "D"]).copy()
        slugs_order = summary_df.sort_values(["D_peak"], ascending=False, kind="stable")["slug"].astype(str).tolist() if not summary_df.empty else sorted(panel_df["slug"].astype(str).unique().tolist())

        n = len(slugs_order)
        ncols = 6
        nrows = int(np.ceil(n / ncols)) if n else 1
        with ps.paper_style():
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(3.1 * ncols, 2.0 * nrows), squeeze=False)
            for i, slug in enumerate(slugs_order):
                ax = axes[i // ncols][i % ncols]
                sub = panel_df[panel_df["slug"] == slug].sort_values("hours_since_quake", kind="stable")
                x = sub["hours_since_quake"].to_numpy(dtype=float)
                y = sub["D"].to_numpy(dtype=float)
                et = str(sub["event_type"].iloc[0]) if not sub.empty else ""
                c = color_map.get(et, ps.OKABE_ITO["gray"])
                ax.plot(x, y, color=c, lw=1.7, marker="o", ms=3.2, alpha=0.9)
                # peak marker
                try:
                    t_peak = float(sub["t_peak_hours"].iloc[0])
                    D_peak = float(sub["D_peak"].iloc[0])
                    ax.scatter([t_peak], [D_peak], s=28, color="black", zorder=5)
                except Exception:
                    pass
                # mono segment highlight
                if slug in mono_map:
                    a, b = mono_map[slug]
                    ax.axvspan(a, b, color=c, alpha=0.12, lw=0)
                ax.set_title(str(sub["short_name"].iloc[0]) if not sub.empty else slug, fontsize=9)
                ax.set_xlabel("t (h)")
                ax.set_ylabel("D")
                ps.despine(ax)
            for j in range(n, nrows * ncols):
                axes[j // ncols][j % ncols].axis("off")
            fig.tight_layout()
            ps.save_figure(fig, figs / "Dt_timeseries_panels.png", dpi=220)
            ps.save_figure(fig, figs / "Dt_timeseries_panels.pdf")
            plt.close(fig)

    meta = {
        "output_root": str(output_root),
        "n_events": int(len(want)),
        "r_max_km": float(r_max_km),
        "near_r_km": float(near_r_km),
        "min_tiles_overlap": int(min_tiles_overlap),
        "min_r_bins": int(min_r_bins),
        "min_near_bins": int(min_near_bins),
        "peak_min_hours": (float(peak_min_hours) if peak_min_hours is not None else None),
        "peak_max_hours": (float(peak_max_hours) if peak_max_hours is not None else None),
        "D_peak_min": float(D_peak_min),
        "min_time_windows": int(min_time_windows),
        "peak_frac": float(peak_frac),
        "near_thresh": float(near_thresh),
        "mono_tol_up": float(mono_tol_up),
        "slugs": want,
        "exclude_slugs": sorted(exclude),
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def cli_main() -> None:
    p = argparse.ArgumentParser(description="SVD-free: 计算 D(t) 并做衰减拟合/模型比较/坍缩与可视化")
    p.add_argument("--output-root", type=Path, default=Path("outputs"), help="输入根目录：包含 <slug>/phi_heatmap/tables/phi_rt_long.csv")
    p.add_argument("--out-dir", type=Path, default=Path("outputs/cross_disaster_comparison/Dt_decay"))
    p.add_argument("--slugs", type=str, nargs="*", default=[], help="可选：只跑指定 slugs（空或 all=自动发现）")
    p.add_argument("--exclude-slugs", type=str, nargs="*", default=[], help="可选：剔除指定 slugs")

    p.add_argument("--r-max-km", type=float, default=200.0)
    p.add_argument("--near-r-km", type=float, default=50.0)
    p.add_argument("--min-tiles-overlap", type=int, default=3)
    p.add_argument("--min-r-bins", type=int, default=5)
    p.add_argument("--min-near-bins", type=int, default=2)

    p.add_argument("--peak-min-hours", type=float, default=None, help="peak 搜索的最小 t（小时）。默认不限制（允许灾前 peak）。")
    p.add_argument("--peak-max-hours", type=float, default=None)
    p.add_argument("--D-peak-min", type=float, default=0.03)
    p.add_argument("--min-time-windows", type=int, default=5)
    p.add_argument("--peak-frac", type=float, default=0.5)
    p.add_argument("--near-thresh", type=float, default=0.02)

    p.add_argument("--mono-tol-up", type=float, default=1.05, help="单调衰减段允许的上升比例（默认 1.05=5%）")

    args = p.parse_args()

    run(
        output_root=Path(args.output_root),
        out_dir=Path(args.out_dir),
        slugs=list(args.slugs or []),
        exclude_slugs=list(args.exclude_slugs or []),
        r_max_km=float(args.r_max_km),
        near_r_km=float(args.near_r_km),
        min_tiles_overlap=int(args.min_tiles_overlap),
        min_r_bins=int(args.min_r_bins),
        min_near_bins=int(args.min_near_bins),
        peak_min_hours=args.peak_min_hours,
        peak_max_hours=(float(args.peak_max_hours) if args.peak_max_hours is not None else None),
        D_peak_min=float(args.D_peak_min),
        min_time_windows=int(args.min_time_windows),
        peak_frac=float(args.peak_frac),
        near_thresh=float(args.near_thresh),
        mono_tol_up=float(args.mono_tol_up),
    )


if __name__ == "__main__":
    cli_main()
