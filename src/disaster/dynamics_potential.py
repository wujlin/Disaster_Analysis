from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise ModuleNotFoundError("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

try:
    from scipy.optimize import curve_fit, least_squares
    from scipy.stats import spearmanr, wilcoxon
except ModuleNotFoundError as e:
    raise ModuleNotFoundError("缺少依赖：scipy。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e


@dataclass(frozen=True)
class EventMeta:
    slug: str
    short_name: str
    disaster_type: str
    event_type: str
    t_peak_hours: float
    D_peak: float
    near_delta: float
    alpha: float


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
    s = str(slug).strip().lower()
    if not s:
        return ""
    if s == "turkiye_earthquake_2023":
        return "turkiye"
    if s.startswith("hurricane_beryl_across_southeastern_texas"):
        return "beryl_tx"
    if s.startswith("hurricane_milton_across_florida"):
        return "milton"
    if s.startswith("hurricane_helene_pre_landfall"):
        return "helene_pre"
    if s.startswith("hurricane_john_across_southeastern_guerrero"):
        return "john_gue"
    if s.startswith("hurricane_john_southern_mexico"):
        return "john_sm"
    if s.startswith("hurricane_beryl_across_quintana"):
        return "beryl_qr"
    if s.startswith("the_flooding_across_bagmati"):
        return "nepal_fld"
    if s.startswith("the_flooding_across_gujarat"):
        return "gujarat_fld"
    if s.startswith("the_flooding_across_eastern_bangladesh"):
        return "bangladesh_fld"
    if s.startswith("flooding_in_central_and_eastern_europe"):
        return "europe_fld"
    if s.startswith("spain_flood"):
        return "spain_fld"
    if s.startswith("the_earthquake_across_central_mexico"):
        return "mexico_eq"
    return s[:22]


def _load_event_meta(
    *,
    output_root: Path,
    dt_tables_dir: Path,
    selected_slugs: list[str] | None,
    use_route_b_selected: bool,
    route_b_min_n_mono: int,
) -> list[EventMeta]:
    p_summary = Path(dt_tables_dir) / "Dt_event_summary.csv"
    if not p_summary.exists():
        raise FileNotFoundError(f"未找到：{p_summary}")
    p_fit = Path(dt_tables_dir) / "Dt_powerlaw_fits.csv"
    if not p_fit.exists():
        raise FileNotFoundError(f"未找到：{p_fit}")
    p_flags = Path(dt_tables_dir) / "Dt_routeB_sample_flags.csv"

    summary = pd.read_csv(p_summary)
    fit = pd.read_csv(p_fit)
    for c in ["t_peak_hours", "D_peak", "near_delta_peak_windows_mean"]:
        summary[c] = pd.to_numeric(summary[c], errors="coerce")
    for c in ["alpha", "n_mono"]:
        fit[c] = pd.to_numeric(fit[c], errors="coerce")

    merged = summary.merge(
        fit[["slug", "alpha", "n_mono"]],
        on="slug",
        how="left",
    )

    route_b_selected_set: set[str] = set()
    if use_route_b_selected:
        if not p_flags.exists():
            raise FileNotFoundError(f"未找到 Route B 事件标记表：{p_flags}")
        f = pd.read_csv(p_flags)
        if "route_b_selected" not in f.columns:
            raise ValueError(f"{p_flags} 缺少 route_b_selected 列，无法保证口径一致。")
        f["route_b_selected"] = f["route_b_selected"].astype(bool)
        route_b_selected_set = set(f.loc[f["route_b_selected"], "slug"].astype(str).tolist())
        if not route_b_selected_set:
            raise ValueError(f"{p_flags} 中 route_b_selected 全为空或全 False，请检查上游筛选结果。")

    rows: list[EventMeta] = []
    chosen = {str(s).strip() for s in (selected_slugs or []) if str(s).strip()}
    for _, r in merged.iterrows():
        slug = str(r.get("slug", "")).strip()
        if not slug:
            continue
        phi_p = Path(output_root) / slug / "phi_heatmap" / "tables" / "phi_rt_long.csv"
        if not phi_p.exists():
            continue
        if chosen and slug not in chosen:
            continue
        if (not chosen) and use_route_b_selected and route_b_selected_set and (slug not in route_b_selected_set):
            continue

        t_peak = _safe_float(r.get("t_peak_hours"))
        D_peak = _safe_float(r.get("D_peak"))
        near_delta = _safe_float(r.get("near_delta_peak_windows_mean"))
        alpha = _safe_float(r.get("alpha"))
        if t_peak is None or D_peak is None or near_delta is None:
            continue
        rows.append(
            EventMeta(
                slug=slug,
                short_name=str(r.get("short_name") or _short_name(slug)),
                disaster_type=str(r.get("disaster_type") or ""),
                event_type=str(r.get("event_type") or ""),
                t_peak_hours=float(t_peak),
                D_peak=float(D_peak),
                near_delta=float(near_delta),
                alpha=float(alpha) if alpha is not None else float("nan"),
            )
        )
    rows = sorted(rows, key=lambda x: x.slug)
    return rows


def _load_phi_rt_long(output_root: Path, slug: str) -> pd.DataFrame:
    p = Path(output_root) / slug / "phi_heatmap" / "tables" / "phi_rt_long.csv"
    if not p.exists():
        raise FileNotFoundError(f"未找到：{p}")
    df = pd.read_csv(p)
    need = {"hours_since_quake", "r_bin_km", "phi_overlap", "n_tiles_overlap"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise ValueError(f"{p} 缺少列：{miss}")
    for c in ["hours_since_quake", "r_bin_km", "phi_overlap", "n_tiles_overlap"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["hours_since_quake", "r_bin_km", "phi_overlap", "n_tiles_overlap"]).copy()
    return df


def _median_step_hours(values: np.ndarray) -> float:
    h = np.asarray(values, dtype=float)
    h = h[np.isfinite(h)]
    if h.size < 2:
        return float("nan")
    h = np.sort(h)
    dh = np.diff(h)
    dh = dh[np.isfinite(dh) & (dh > 0)]
    if dh.size == 0:
        return float("nan")
    return float(np.median(dh))


def _prepare_phi(
    df: pd.DataFrame,
    *,
    r_max_km: float,
    min_tiles_overlap: int,
    daily_average_if_high_freq: bool,
    high_freq_thresh_h: float,
) -> tuple[pd.DataFrame, int, float]:
    sub = df.copy()
    sub = sub[(sub["r_bin_km"] <= float(r_max_km)) & (sub["n_tiles_overlap"] >= float(min_tiles_overlap))].copy()
    if sub.empty:
        return pd.DataFrame(columns=["hours_since_quake", "r_bin_km", "delta", "n_tiles_overlap"]), 0, float("nan")
    sub["delta"] = pd.to_numeric(sub["phi_overlap"], errors="coerce") - 1.0
    sub = sub.dropna(subset=["delta"]).copy()

    med_step = _median_step_hours(sub["hours_since_quake"].to_numpy(dtype=float))
    applied = 0
    if daily_average_if_high_freq and np.isfinite(med_step) and med_step < float(high_freq_thresh_h):
        applied = 1
        tmp = sub.copy()
        tmp["day_idx"] = np.floor(pd.to_numeric(tmp["hours_since_quake"], errors="coerce").to_numpy(dtype=float) / 24.0).astype(int)
        tmp = (
            tmp.groupby(["day_idx", "r_bin_km"], as_index=False, sort=True)
            .agg(
                hours_since_quake=("hours_since_quake", "mean"),
                delta=("delta", "mean"),
                n_tiles_overlap=("n_tiles_overlap", "mean"),
            )
            .sort_values(["hours_since_quake", "r_bin_km"], kind="stable")
            .reset_index(drop=True)
        )
        sub = tmp
    return sub[["hours_since_quake", "r_bin_km", "delta", "n_tiles_overlap"]].copy(), int(applied), float(med_step)


def _compute_D_timeseries(phi: pd.DataFrame) -> pd.DataFrame:
    if phi.empty:
        return pd.DataFrame(columns=["hours_since_quake", "D"])
    rows = []
    for t, g in phi.groupby("hours_since_quake", sort=True):
        arr = pd.to_numeric(g["delta"], errors="coerce").to_numpy(dtype=float)
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            continue
        rows.append({"hours_since_quake": float(t), "D": float(np.mean(np.abs(arr)))})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values("hours_since_quake", kind="stable").reset_index(drop=True)
    return out


def _resolve_t_peak_for_postfit(
    D_series: pd.DataFrame,
    *,
    preferred_t_peak: float | None,
    min_post_points: int,
) -> tuple[float, float, str]:
    """
    统一峰值时间选择：
    1) 先尝试外部传入的 preferred_t_peak（snap 到现有时间网格）；
    2) 若峰后点不足，回退到当前序列中“可留出足够峰后点”的最大 D 时刻；
    3) 仍不足则回退全局最大 D 时刻（会导致后续拟合不足，由上游诊断报错）。
    返回：(t_peak_use, D_peak_global, source)
    """
    ts = D_series.sort_values("hours_since_quake", kind="stable").copy()
    t = pd.to_numeric(ts["hours_since_quake"], errors="coerce").to_numpy(dtype=float)
    d = pd.to_numeric(ts["D"], errors="coerce").to_numpy(dtype=float)
    ok = np.isfinite(t) & np.isfinite(d)
    t = t[ok]
    d = d[ok]
    if t.size == 0:
        return float("nan"), float("nan"), "empty"

    D_peak_global = float(np.nanmax(d))
    n = int(t.size)
    min_post = int(max(1, min_post_points))
    max_peak_idx = n - min_post - 1  # 需确保 t > t_peak 至少 min_post 个时间点

    def _idx_from_preferred(tp: float | None) -> int | None:
        if tp is None or (not np.isfinite(float(tp))):
            return None
        return int(np.argmin(np.abs(t - float(tp))))

    idx_pref = _idx_from_preferred(preferred_t_peak)
    if idx_pref is not None and idx_pref <= max_peak_idx:
        return float(t[idx_pref]), D_peak_global, "preferred_snap"

    if max_peak_idx >= 0:
        idx_candidates = np.arange(0, max_peak_idx + 1, dtype=int)
        idx_best = int(idx_candidates[np.nanargmax(d[idx_candidates])])
        return float(t[idx_best]), D_peak_global, "fallback_local_peak"

    idx_global = int(np.nanargmax(d))
    return float(t[idx_global]), D_peak_global, "fallback_global_peak"


def _classify_bins(
    phi: pd.DataFrame,
    *,
    t_peak: float,
    D_series: pd.DataFrame,
    D_peak: float,
    peak_frac: float,
    near_zero_eps: float,
) -> pd.DataFrame:
    if phi.empty:
        return pd.DataFrame(columns=["r_bin_km", "bin_type", "peak_delta_mean", "delta0_signed", "delta0_abs"])

    peak_cut = float(peak_frac) * float(D_peak)
    peak_ts = D_series[pd.to_numeric(D_series["D"], errors="coerce") >= float(peak_cut)]["hours_since_quake"].to_numpy(dtype=float)
    peak_set = {round(float(x), 6) for x in peak_ts if np.isfinite(x)}

    rows: list[dict] = []
    for r_bin, g in phi.groupby("r_bin_km", sort=True):
        g = g.sort_values("hours_since_quake", kind="stable").copy()
        t = pd.to_numeric(g["hours_since_quake"], errors="coerce").to_numpy(dtype=float)
        d = pd.to_numeric(g["delta"], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(t) & np.isfinite(d)
        t = t[ok]
        d = d[ok]
        if t.size == 0:
            continue

        k = np.array([round(float(x), 6) in peak_set for x in t], dtype=bool)
        if np.sum(k) == 0:
            idx_near = int(np.argmin(np.abs(t - float(t_peak))))
            peak_delta_mean = float(d[idx_near])
        else:
            peak_delta_mean = float(np.mean(d[k]))

        idx0 = int(np.argmin(np.abs(t - float(t_peak))))
        delta0 = float(d[idx0])
        if peak_delta_mean < -float(near_zero_eps):
            bt = "EVAC"
        elif peak_delta_mean > float(near_zero_eps):
            bt = "INFL"
        else:
            bt = "NEUTRAL"
        rows.append(
            {
                "r_bin_km": float(r_bin),
                "bin_type": str(bt),
                "peak_delta_mean": float(peak_delta_mean),
                "delta0_signed": float(delta0),
                "delta0_abs": float(abs(delta0)),
            }
        )
    return pd.DataFrame(rows)


def _exp_model(t: np.ndarray, A: float, tau: float, C: float) -> np.ndarray:
    return A * np.exp(-np.asarray(t, dtype=float) / np.clip(float(tau), 1e-8, np.inf)) + C


def _exp_model_c0(t: np.ndarray, A: float, tau: float) -> np.ndarray:
    return A * np.exp(-np.asarray(t, dtype=float) / np.clip(float(tau), 1e-8, np.inf))


def _fit_exp_abs(t: np.ndarray, y: np.ndarray) -> dict:
    tt = np.asarray(t, dtype=float)
    yy = np.asarray(y, dtype=float)
    ok = np.isfinite(tt) & np.isfinite(yy) & (tt > 0) & (yy >= 0)
    tt = tt[ok]
    yy = yy[ok]
    if tt.size < 2:
        return {"ok": 0}

    A0 = float(max(yy[0] - yy[-1], 1e-3))
    tau0 = float(max(np.median(tt), 1.0))
    C0 = float(max(min(yy[-1], yy[0]), 0.0))
    # 1) full model (A, tau, C)
    if tt.size >= 4:
        try:
            popt, _ = curve_fit(
                _exp_model,
                tt,
                yy,
                p0=(A0, tau0, C0),
                bounds=([0.0, 1e-3, 0.0], [5.0, 1e5, 5.0]),
                maxfev=20000,
            )
            A, tau, C = float(popt[0]), float(popt[1]), float(popt[2])
            yh = _exp_model(tt, A, tau, C)
            sse = float(np.sum(np.square(yy - yh)))
            sst = float(np.sum(np.square(yy - float(np.mean(yy))))) if yy.size else float("nan")
            r2 = float(1.0 - sse / sst) if np.isfinite(sst) and sst > 0 else float("nan")
            return {
                "ok": 1,
                "A": A,
                "tau": tau,
                "C": C,
                "r2": r2,
                "n_points": int(tt.size),
                "sse": sse,
                "fit_method": "exp3",
            }
        except Exception:
            pass

    # 2) reduced model (A, tau), C fixed to 0
    if tt.size >= 3:
        try:
            popt, _ = curve_fit(
                _exp_model_c0,
                tt,
                yy,
                p0=(max(float(np.nanmax(yy)), 1e-4), tau0),
                bounds=([0.0, 1e-3], [5.0, 1e5]),
                maxfev=20000,
            )
            A, tau = float(popt[0]), float(popt[1])
            C = 0.0
            yh = _exp_model_c0(tt, A, tau)
            sse = float(np.sum(np.square(yy - yh)))
            sst = float(np.sum(np.square(yy - float(np.mean(yy))))) if yy.size else float("nan")
            r2 = float(1.0 - sse / sst) if np.isfinite(sst) and sst > 0 else float("nan")
            return {
                "ok": 1,
                "A": A,
                "tau": tau,
                "C": C,
                "r2": r2,
                "n_points": int(tt.size),
                "sse": sse,
                "fit_method": "exp2_c0",
            }
        except Exception:
            pass

    # 3) two-point closed-form tau with C=0 (last-resort to avoid dropping event)
    #    tau_ij = -(dt) / ln(yj/yi), valid only when yi>yj>0
    if tt.size >= 2:
        ord_idx = np.argsort(tt)
        t2 = tt[ord_idx]
        y2 = yy[ord_idx]
        taus = []
        for i in range(y2.size - 1):
            yi = float(y2[i])
            yj = float(y2[i + 1])
            dt = float(t2[i + 1] - t2[i])
            if yi > 0 and yj > 0 and yj < yi and dt > 0:
                val = -dt / np.log(yj / yi)
                if np.isfinite(val) and val > 1e-3:
                    taus.append(float(val))
        if taus:
            tau = float(np.median(np.asarray(taus, dtype=float)))
            A = float(np.median(y2 * np.exp(t2 / max(tau, 1e-6))))
            C = 0.0
            yh = _exp_model_c0(t2, A, tau)
            sse = float(np.sum(np.square(y2 - yh)))
            sst = float(np.sum(np.square(y2 - float(np.mean(y2))))) if y2.size else float("nan")
            r2 = float(1.0 - sse / sst) if np.isfinite(sst) and sst > 0 else float("nan")
            return {
                "ok": 1,
                "A": A,
                "tau": tau,
                "C": C,
                "r2": r2,
                "n_points": int(t2.size),
                "sse": sse,
                "fit_method": "exp2_closed_form",
            }
    return {"ok": 0}


def _monotone_segment(t: np.ndarray, y: np.ndarray, tol_up: float = 1.05) -> tuple[np.ndarray, np.ndarray]:
    tt = np.asarray(t, dtype=float)
    yy = np.asarray(y, dtype=float)
    ok = np.isfinite(tt) & np.isfinite(yy) & (tt > 0) & (yy > 0)
    tt = tt[ok]
    yy = yy[ok]
    if tt.size == 0:
        return tt, yy
    ord_idx = np.argsort(tt)
    tt = tt[ord_idx]
    yy = yy[ord_idx]
    keep = [0]
    for i in range(yy.size - 1):
        if yy[i + 1] <= yy[i] * float(tol_up):
            keep.append(i + 1)
        else:
            break
    k = np.array(keep, dtype=int)
    return tt[k], yy[k]


def _fit_powerlaw_alpha(t: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    tt = np.asarray(t, dtype=float)
    yy = np.asarray(y, dtype=float)
    ok = np.isfinite(tt) & np.isfinite(yy) & (tt > 0) & (yy > 0)
    tt = tt[ok]
    yy = yy[ok]
    if tt.size < 3:
        return float("nan"), float("nan")
    x = np.log(tt)
    z = np.log(yy)
    slope, intercept = np.polyfit(x, z, deg=1)
    zh = slope * x + intercept
    sse = float(np.sum(np.square(z - zh)))
    sst = float(np.sum(np.square(z - float(np.mean(z))))) if z.size else float("nan")
    r2 = float(1.0 - sse / sst) if np.isfinite(sst) and sst > 0 else float("nan")
    alpha = float(-slope)
    return alpha, r2


def _safe_spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, float, int]:
    xx = np.asarray(x, dtype=float)
    yy = np.asarray(y, dtype=float)
    ok = np.isfinite(xx) & np.isfinite(yy)
    xx = xx[ok]
    yy = yy[ok]
    n = int(xx.size)
    if n < 3:
        return float("nan"), float("nan"), n
    if float(np.nanstd(xx)) <= 1e-12 or float(np.nanstd(yy)) <= 1e-12:
        return float("nan"), float("nan"), n
    rho, p = spearmanr(xx, yy)
    return float(rho), float(p), n


def _ode_abs_solution(t: np.ndarray, delta0: float, k: float, gamma: float) -> np.ndarray:
    tt = np.asarray(t, dtype=float)
    d0 = float(abs(delta0))
    if not np.isfinite(d0):
        return np.full_like(tt, np.nan, dtype=float)
    k = float(k)
    gamma = float(gamma)
    if abs(k) < 1e-10:
        den = 1.0 + 2.0 * gamma * (d0**2) * np.clip(tt, 0.0, np.inf)
        den = np.maximum(den, 1e-9)
        return d0 / np.sqrt(den)
    e2 = np.exp(-2.0 * k * np.clip(tt, 0.0, np.inf))
    den = 1.0 + (gamma / k) * (d0**2) * (1.0 - e2)
    den = np.maximum(den, 1e-9)
    return d0 * np.exp(-k * np.clip(tt, 0.0, np.inf)) / np.sqrt(den)


def _bic(sse: float, n: int, k: int) -> float:
    if n <= 0 or k <= 0 or (not np.isfinite(sse)):
        return float("nan")
    sse = float(max(sse, 1e-12))
    return float(n * np.log(sse / float(n)) + float(k) * np.log(float(n)))


def _event_trajs_for_model(
    phi: pd.DataFrame,
    cls_df: pd.DataFrame,
    *,
    t_peak: float,
    min_post_points: int,
) -> list[dict]:
    out: list[dict] = []
    if phi.empty or cls_df.empty:
        return out
    cls = cls_df.set_index("r_bin_km")
    for r_bin, g in phi.groupby("r_bin_km", sort=True):
        if float(r_bin) not in cls.index:
            continue
        row = cls.loc[float(r_bin)]
        bt = str(row["bin_type"])
        if bt not in {"EVAC", "INFL"}:
            continue
        delta0 = float(row["delta0_signed"])
        sign = -1 if bt == "EVAC" else 1

        gg = g.sort_values("hours_since_quake", kind="stable").copy()
        t = pd.to_numeric(gg["hours_since_quake"], errors="coerce").to_numpy(dtype=float)
        d = pd.to_numeric(gg["delta"], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(t) & np.isfinite(d)
        t = t[ok]
        d = d[ok]
        post = t > float(t_peak)
        tp = t[post] - float(t_peak)
        yp = d[post]
        ok2 = np.isfinite(tp) & np.isfinite(yp) & (tp > 0)
        tp = tp[ok2]
        yp = yp[ok2]
        if tp.size < int(min_post_points):
            continue
        out.append(
            {
                "r_bin_km": float(r_bin),
                "bin_type": str(bt),
                "sign": int(sign),
                "delta0": float(delta0),
                "t": tp.astype(float),
                "y_abs": np.abs(yp).astype(float),
            }
        )
    return out


def _fit_langevin_models(
    trajs: list[dict],
    *,
    tau_guess_evac: float,
    tau_guess_infl: float,
) -> dict:
    if not trajs:
        return {"ok": 0}

    y_obs = np.concatenate([np.asarray(tr["y_abs"], dtype=float) for tr in trajs], axis=0)
    y_obs = y_obs[np.isfinite(y_obs)]
    if y_obs.size < 8:
        return {"ok": 0}

    tau_e = float(tau_guess_evac) if np.isfinite(tau_guess_evac) and tau_guess_evac > 0 else 48.0
    tau_i = float(tau_guess_infl) if np.isfinite(tau_guess_infl) and tau_guess_infl > 0 else 48.0
    k_minus0 = float(np.clip(1.0 / tau_e, 1e-3, 0.5))
    k_plus0 = float(np.clip(1.0 / tau_i, 1e-3, 0.5))
    k0 = float(np.clip(0.5 * (k_minus0 + k_plus0), 1e-3, 0.5))
    c0 = float(np.clip(np.nanpercentile(y_obs, 20), 0.0, 0.5))

    def unpack(theta: np.ndarray, mode: str) -> tuple[float, float, float, float]:
        if mode == "A":
            k, c = float(theta[0]), float(theta[1])
            return k, k, 0.0, c
        if mode == "B":
            km, kp, c = float(theta[0]), float(theta[1]), float(theta[2])
            return km, kp, 0.0, c
        if mode == "C":
            k, g, c = float(theta[0]), float(theta[1]), float(theta[2])
            return k, k, g, c
        km, kp, g, c = float(theta[0]), float(theta[1]), float(theta[2]), float(theta[3])
        return km, kp, g, c

    def residual(theta: np.ndarray, mode: str) -> np.ndarray:
        km, kp, gamma, c = unpack(theta, mode)
        res_list: list[np.ndarray] = []
        for tr in trajs:
            t = np.asarray(tr["t"], dtype=float)
            y = np.asarray(tr["y_abs"], dtype=float)
            d0 = float(tr["delta0"])
            k = km if int(tr["sign"]) < 0 else kp
            y_hat = _ode_abs_solution(t, d0, k, gamma) + float(c)
            res = y_hat - y
            res = res[np.isfinite(res)]
            if res.size:
                res_list.append(res)
        if not res_list:
            return np.array([1e6], dtype=float)
        return np.concatenate(res_list, axis=0)

    model_spec = {
        "A": {
            "x0": np.array([k0, c0], dtype=float),
            "lb": np.array([1e-5, 0.0], dtype=float),
            "ub": np.array([2.0, 1.0], dtype=float),
            "k_params": 2,
        },
        "B": {
            "x0": np.array([k_minus0, k_plus0, c0], dtype=float),
            "lb": np.array([1e-5, 1e-5, 0.0], dtype=float),
            "ub": np.array([2.0, 2.0, 1.0], dtype=float),
            "k_params": 3,
        },
        "C": {
            "x0": np.array([k0, 0.1, c0], dtype=float),
            "lb": np.array([1e-5, -10.0, 0.0], dtype=float),
            "ub": np.array([2.0, 10.0, 1.0], dtype=float),
            "k_params": 3,
        },
        "D": {
            "x0": np.array([k_minus0, k_plus0, 0.1, c0], dtype=float),
            "lb": np.array([1e-5, 1e-5, -10.0, 0.0], dtype=float),
            "ub": np.array([2.0, 2.0, 10.0, 1.0], dtype=float),
            "k_params": 4,
        },
    }

    out: dict[str, object] = {"ok": 1}
    n_obs = 0
    for m, spec in model_spec.items():
        try:
            ls = least_squares(
                lambda x: residual(x, m),
                x0=spec["x0"],
                bounds=(spec["lb"], spec["ub"]),
                max_nfev=30000,
                xtol=1e-8,
                ftol=1e-8,
                gtol=1e-8,
            )
            rr = residual(ls.x, m)
            sse = float(np.sum(np.square(rr)))
            n = int(rr.size)
            n_obs = max(n_obs, n)
            bic = _bic(sse=sse, n=n, k=int(spec["k_params"]))
            km, kp, g, c = unpack(ls.x, m)
            out[f"sse_{m}"] = float(sse)
            out[f"BIC_{m}"] = float(bic)
            out[f"km_{m}"] = float(km)
            out[f"kp_{m}"] = float(kp)
            out[f"gamma_{m}"] = float(g)
            out[f"c_{m}"] = float(c)
        except Exception:
            out[f"sse_{m}"] = float("nan")
            out[f"BIC_{m}"] = float("nan")
            out[f"km_{m}"] = float("nan")
            out[f"kp_{m}"] = float("nan")
            out[f"gamma_{m}"] = float("nan")
            out[f"c_{m}"] = float("nan")

    out["n_obs"] = int(n_obs)

    bics = {m: float(out.get(f"BIC_{m}", float("nan"))) for m in ["A", "B", "C", "D"]}
    finite = {m: b for m, b in bics.items() if np.isfinite(b)}
    if not finite:
        out["best_model"] = ""
        return out
    best_model = min(finite.keys(), key=lambda k: finite[k])
    out["best_model"] = str(best_model)

    km = float(out.get(f"km_{best_model}", float("nan")))
    kp = float(out.get(f"kp_{best_model}", float("nan")))
    gamma = float(out.get(f"gamma_{best_model}", float("nan")))
    c = float(out.get(f"c_{best_model}", float("nan")))
    sse = float(out.get(f"sse_{best_model}", float("nan")))
    sst = float(np.sum(np.square(y_obs - float(np.mean(y_obs))))) if y_obs.size else float("nan")
    r2 = float(1.0 - sse / sst) if np.isfinite(sst) and sst > 0 and np.isfinite(sse) else float("nan")
    out["k_minus"] = float(km)
    out["k_plus"] = float(kp)
    out["gamma"] = float(gamma)
    out["c"] = float(c)
    out["r2"] = float(r2)
    out["k_ratio"] = float(km / kp) if np.isfinite(km) and np.isfinite(kp) and kp != 0 else float("nan")
    return out


def _simulate_one_event(
    *,
    k_minus: float,
    k_plus: float,
    gamma: float,
    delta0_pool: np.ndarray,
    p_evac: float,
    rng: np.random.Generator,
    sigma: float,
    n_bins: int,
    n_near_bins: int,
    t_max_h: int,
    dt_h: float,
    sample_every_h: int,
    mono_tol_up: float,
) -> dict:
    if delta0_pool.size == 0:
        return {"ok": 0}
    n_bins = int(max(4, n_bins))
    n_near_bins = int(max(1, min(n_bins, n_near_bins)))

    d0_abs = rng.choice(delta0_pool, size=n_bins, replace=True)
    d0_abs = np.clip(np.asarray(d0_abs, dtype=float), 1e-4, 2.0)
    evac_flag = rng.random(n_bins) < float(np.clip(p_evac, 0.05, 0.95))
    sign = np.where(evac_flag, -1.0, 1.0)
    delta = sign * d0_abs
    k_vec = np.where(sign < 0, float(k_minus), float(k_plus)).astype(float)

    t_grid = np.arange(0.0, float(t_max_h) + 1e-9, float(dt_h), dtype=float)
    sample_every = int(max(1, round(float(sample_every_h) / float(dt_h))))
    sample_idx = np.arange(0, t_grid.size, sample_every, dtype=int)
    if sample_idx[-1] != t_grid.size - 1:
        sample_idx = np.append(sample_idx, t_grid.size - 1)

    D_list: list[float] = []
    delta_snapshots: list[np.ndarray] = []
    root_dt = np.sqrt(float(dt_h))
    sample_set = set(sample_idx.tolist())
    for i in range(t_grid.size):
        if i in sample_set:
            D_list.append(float(np.mean(np.abs(delta))))
            delta_snapshots.append(delta.copy())
        if i == t_grid.size - 1:
            break
        noise = float(sigma) * root_dt * rng.standard_normal(n_bins)
        drift = (-k_vec * delta - float(gamma) * np.power(delta, 3.0)) * float(dt_h)
        delta = delta + drift + noise
        delta = np.clip(delta, -5.0, 5.0)

    t_s = t_grid[sample_idx]
    D_s = np.asarray(D_list, dtype=float)
    if D_s.size < 4 or (not np.any(np.isfinite(D_s))):
        return {"ok": 0}

    ip = int(np.nanargmax(D_s))
    D_peak = float(D_s[ip])
    t_peak = float(t_s[ip])
    if not np.isfinite(D_peak) or D_peak <= 0:
        return {"ok": 0}
    near_delta = float(np.mean(np.asarray(delta_snapshots[ip][:n_near_bins], dtype=float)))

    post = np.where(t_s > t_peak)[0]
    if post.size < 3:
        return {"ok": 0}
    tp = (t_s[post] - t_peak).astype(float)
    yn = (D_s[post] / D_peak).astype(float)
    tp, yn = _monotone_segment(tp, yn, tol_up=float(mono_tol_up))
    alpha, r2 = _fit_powerlaw_alpha(tp, yn)
    if not np.isfinite(alpha):
        return {"ok": 0}
    return {
        "ok": 1,
        "alpha": float(alpha),
        "alpha_r2": float(r2),
        "delta_near": float(near_delta),
        "D_peak": float(D_peak),
        "t_peak_h": float(t_peak),
    }


def run(
    *,
    output_root: Path,
    dt_tables_dir: Path,
    out_dir: Path,
    slugs: list[str],
    use_route_b_selected: bool,
    route_b_min_n_mono: int,
    r_max_km: float,
    min_tiles_overlap: int,
    peak_frac: float,
    min_post_points: int,
    near_zero_eps: float,
    daily_average_if_high_freq: bool,
    high_freq_thresh_h: float,
    sim_sigma: float,
    sim_n_bins: int,
    sim_n_near_bins: int,
    sim_t_max_h: int,
    sim_dt_h: float,
    sim_sample_every_h: int,
    sim_events_per_cell: int,
    sim_ratio_min: float,
    sim_ratio_max: float,
    sim_ratio_n: int,
    sim_gamma_min: float,
    sim_gamma_max: float,
    sim_gamma_n: int,
    sim_validation_batches: int,
    seed: int,
    run_until_exp: int,
    exp2_require_all_events: bool,
) -> None:
    output_root = Path(output_root)
    out_dir = Path(out_dir)
    tabs = out_dir / "tables"
    figs = out_dir / "figures"
    _ensure_dir(tabs)
    _ensure_dir(figs)

    events = _load_event_meta(
        output_root=output_root,
        dt_tables_dir=dt_tables_dir,
        selected_slugs=slugs,
        use_route_b_selected=use_route_b_selected,
        route_b_min_n_mono=route_b_min_n_mono,
    )
    if not events:
        raise ValueError("没有可用事件（请检查 Dt 表或 --slugs 设置）。")

    run_until = int(np.clip(int(run_until_exp), 1, 4))

    # -------- 实验 1：逐 bin 弛豫时间 --------
    bin_rows: list[dict] = []
    event_diag_rows: list[dict] = []

    for em in events:
        raw = _load_phi_rt_long(output_root=output_root, slug=em.slug)
        phi, daily_applied, med_step = _prepare_phi(
            raw,
            r_max_km=float(r_max_km),
            min_tiles_overlap=int(min_tiles_overlap),
            daily_average_if_high_freq=bool(daily_average_if_high_freq),
            high_freq_thresh_h=float(high_freq_thresh_h),
        )
        if phi.empty:
            continue
        D_ts = _compute_D_timeseries(phi)
        if D_ts.empty:
            continue
        preferred_peak = float(em.t_peak_hours) if np.isfinite(em.t_peak_hours) else None
        t_peak_use, D_peak_global, t_peak_source = _resolve_t_peak_for_postfit(
            D_ts,
            preferred_t_peak=preferred_peak,
            min_post_points=int(min_post_points),
        )
        D_peak_use = float(D_peak_global) if np.isfinite(D_peak_global) else float(
            em.D_peak if np.isfinite(em.D_peak) and em.D_peak > 0 else np.nan
        )
        cls = _classify_bins(
            phi,
            t_peak=float(t_peak_use),
            D_series=D_ts,
            D_peak=float(D_peak_use),
            peak_frac=float(peak_frac),
            near_zero_eps=float(near_zero_eps),
        )
        if cls.empty:
            continue
        cls_map = cls.set_index("r_bin_km")
        for r_bin, g in phi.groupby("r_bin_km", sort=True):
            if float(r_bin) not in cls_map.index:
                continue
            meta = cls_map.loc[float(r_bin)]
            bt = str(meta["bin_type"])
            gg = g.sort_values("hours_since_quake", kind="stable").copy()
            t = pd.to_numeric(gg["hours_since_quake"], errors="coerce").to_numpy(dtype=float)
            d = pd.to_numeric(gg["delta"], errors="coerce").to_numpy(dtype=float)
            ok = np.isfinite(t) & np.isfinite(d)
            t = t[ok]
            d = d[ok]
            post = t > float(t_peak_use)
            tp = (t[post] - float(t_peak_use)).astype(float)
            yp = np.abs(d[post]).astype(float)
            fit = _fit_exp_abs(tp, yp)
            bin_rows.append(
                {
                    "slug": em.slug,
                    "short_name": em.short_name,
                    "disaster_type": em.disaster_type,
                    "event_type": em.event_type,
                    "t_peak_hours": float(t_peak_use),
                    "t_peak_source": str(t_peak_source),
                    "D_peak": float(D_peak_use),
                    "near_delta": float(em.near_delta),
                    "r_bin_km": float(r_bin),
                    "bin_type": bt,
                    "peak_delta_mean": float(meta["peak_delta_mean"]),
                    "delta0_signed": float(meta["delta0_signed"]),
                    "delta0_abs": float(meta["delta0_abs"]),
                    "tau": float(fit.get("tau", float("nan"))),
                    "A": float(fit.get("A", float("nan"))),
                    "C": float(fit.get("C", float("nan"))),
                    "r2": float(fit.get("r2", float("nan"))),
                    "n_points": int(fit.get("n_points", int(np.sum(np.isfinite(tp) & np.isfinite(yp) & (tp > 0) & (yp >= 0))))),
                    "fit_ok": int(fit.get("ok", 0)),
                    "tau_fit_method": str(fit.get("fit_method", "")),
                    "daily_avg_applied": int(daily_applied),
                    "median_step_hours_raw": float(med_step),
                }
            )

        event_diag_rows.append(
            {
                "slug": em.slug,
                "short_name": em.short_name,
                "n_bins_used": int(cls.shape[0]),
                "t_peak_source": str(t_peak_source),
                "t_peak_hours_used": float(t_peak_use),
                "daily_avg_applied": int(daily_applied),
                "median_step_hours_raw": float(med_step),
            }
        )

    bin_df = pd.DataFrame(bin_rows)
    if bin_df.empty:
        raise ValueError("实验1未产出可用 bin 拟合结果。")
    bin_df.to_csv(tabs / "bin_relaxation_times.csv", index=False)
    pd.DataFrame(event_diag_rows).to_csv(tabs / "event_preprocess_diagnostics.csv", index=False)

    asym_rows: list[dict] = []
    for slug, g in bin_df.groupby("slug", sort=True):
        ge = g[(g["bin_type"] == "EVAC") & pd.to_numeric(g["tau"], errors="coerce").notna()].copy()
        gi = g[(g["bin_type"] == "INFL") & pd.to_numeric(g["tau"], errors="coerce").notna()].copy()
        tau_e = float(np.nanmedian(pd.to_numeric(ge["tau"], errors="coerce").to_numpy(dtype=float))) if not ge.empty else float("nan")
        tau_i = float(np.nanmedian(pd.to_numeric(gi["tau"], errors="coerce").to_numpy(dtype=float))) if not gi.empty else float("nan")
        ratio = float(tau_i / tau_e) if np.isfinite(tau_i) and np.isfinite(tau_e) and tau_e > 0 else float("nan")
        meta = next((x for x in events if x.slug == str(slug)), None)
        asym_rows.append(
            {
                "slug": str(slug),
                "short_name": str(meta.short_name if meta else _short_name(str(slug))),
                "disaster_type": str(meta.disaster_type if meta else ""),
                "event_type": str(meta.event_type if meta else ""),
                "tau_median_evac": float(tau_e),
                "tau_median_infl": float(tau_i),
                "ratio": float(ratio),
                "n_evac_bins": int(ge.shape[0]),
                "n_infl_bins": int(gi.shape[0]),
                "near_delta": float(meta.near_delta if meta else float("nan")),
                "D_peak": float(meta.D_peak if meta else float("nan")),
            }
        )
    asym_df = pd.DataFrame(asym_rows)
    asym_df.to_csv(tabs / "asymmetry_summary.csv", index=False)

    both = asym_df[pd.to_numeric(asym_df["tau_median_evac"], errors="coerce").notna() & pd.to_numeric(asym_df["tau_median_infl"], errors="coerce").notna()].copy()
    ratio_arr = pd.to_numeric(both["ratio"], errors="coerce").to_numpy(dtype=float)
    ratio_arr = ratio_arr[np.isfinite(ratio_arr)]
    ratio_median = float(np.nanmedian(ratio_arr)) if ratio_arr.size else float("nan")
    ratio_gt1_frac = float(np.mean(ratio_arr > 1.0)) if ratio_arr.size else float("nan")
    rng_ci = np.random.default_rng(int(seed) + 7)
    ci_lo = float("nan")
    ci_hi = float("nan")
    if ratio_arr.size >= 2:
        med_samples = []
        for _ in range(1000):
            samp = rng_ci.choice(ratio_arr, size=ratio_arr.size, replace=True)
            med_samples.append(float(np.nanmedian(samp)))
        ci_lo = float(np.nanpercentile(np.asarray(med_samples, dtype=float), 2.5))
        ci_hi = float(np.nanpercentile(np.asarray(med_samples, dtype=float), 97.5))
    w_stat = float("nan")
    w_p = float("nan")
    if both.shape[0] >= 3:
        try:
            res_w = wilcoxon(
                pd.to_numeric(both["tau_median_infl"], errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(both["tau_median_evac"], errors="coerce").to_numpy(dtype=float),
                alternative="greater",
                zero_method="wilcox",
            )
            w_stat = float(res_w.statistic)
            w_p = float(res_w.pvalue)
        except Exception:
            pass
    asym_global = pd.DataFrame(
        [
            {
                "n_events_total": int(asym_df.shape[0]),
                "n_events_with_both_types": int(both.shape[0]),
                "ratio_median": float(ratio_median),
                "ratio_ci2p5": float(ci_lo),
                "ratio_ci97p5": float(ci_hi),
                "ratio_gt1_fraction": float(ratio_gt1_frac),
                "wilcoxon_stat_infl_gt_evac": float(w_stat),
                "wilcoxon_p_infl_gt_evac": float(w_p),
            }
        ]
    )
    asym_global.to_csv(tabs / "asymmetry_global_summary.csv", index=False)
    if run_until <= 1:
        meta = {
            "output_root": str(output_root),
            "dt_tables_dir": str(dt_tables_dir),
            "n_events": int(len(events)),
            "events": [e.slug for e in events],
            "use_route_b_selected": bool(use_route_b_selected),
            "run_until_exp": int(run_until),
            "seed": int(seed),
        }
        (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        readme = """# 动力学模型输出（阶段运行）

本次仅执行：
- 实验1：逐 bin 弛豫时间（`bin_relaxation_times.csv`, `asymmetry_summary.csv`）
"""
        (out_dir / "README.md").write_text(readme, encoding="utf-8")
        return

    # -------- 实验 2：非线性检验 --------
    nl_rows: list[dict] = []
    for subset in ["all", "EVAC", "INFL"]:
        if subset == "all":
            ss = bin_df.copy()
        else:
            ss = bin_df[bin_df["bin_type"].astype(str) == subset].copy()
        x = pd.to_numeric(ss["delta0_abs"], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(ss["tau"], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(x) & np.isfinite(y)
        x = x[ok]
        y = y[ok]
        rho = float("nan")
        p = float("nan")
        rho, p, n = _safe_spearman(x, y)
        nl_rows.append({"subset": subset, "n": int(n), "spearman_rho_tau_vs_abs_delta0": float(rho), "spearman_p": float(p)})

    # 事件级加权 tau 与 D_peak
    ev_rows = []
    for slug, g in bin_df.groupby("slug", sort=True):
        x = pd.to_numeric(g["delta0_abs"], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(g["tau"], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(x) & np.isfinite(y)
        x = x[ok]
        y = y[ok]
        if x.size == 0 or float(np.sum(x)) <= 0:
            continue
        w_tau = float(np.sum(x * y) / np.sum(x))
        meta = next((m for m in events if m.slug == str(slug)), None)
        ev_rows.append(
            {
                "slug": str(slug),
                "short_name": str(meta.short_name if meta else _short_name(str(slug))),
                "weighted_tau_by_abs_delta0": float(w_tau),
                "D_peak": float(meta.D_peak if meta else float("nan")),
                "near_delta": float(meta.near_delta if meta else float("nan")),
            }
        )
    ev_df = pd.DataFrame(ev_rows)
    if not ev_df.empty:
        x = pd.to_numeric(ev_df["weighted_tau_by_abs_delta0"], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(ev_df["D_peak"], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(x) & np.isfinite(y)
        x = x[ok]
        y = y[ok]
        rho = float("nan")
        p = float("nan")
        rho, p, n = _safe_spearman(x, y)
        nl_rows.append({"subset": "event_weighted_tau_vs_Dpeak", "n": int(n), "spearman_rho_tau_vs_abs_delta0": float(rho), "spearman_p": float(p)})
    nl_df = pd.DataFrame(nl_rows)
    nl_df.to_csv(tabs / "nonlinearity_test.csv", index=False)
    ev_df.to_csv(tabs / "nonlinearity_event_level.csv", index=False)

    # Route B 口径下，实验2事件级结果默认要求覆盖全部入样事件；否则直接报错，避免静默不一致
    all_events = sorted(bin_df["slug"].dropna().astype(str).unique().tolist())
    ev_events = sorted(ev_df["slug"].dropna().astype(str).unique().tolist()) if not ev_df.empty else []
    ev_set = set(ev_events)
    missing_exp2 = [s for s in all_events if s not in ev_set]
    diag_rows = []
    for s in missing_exp2:
        g = bin_df[bin_df["slug"].astype(str) == s].copy()
        x = pd.to_numeric(g["delta0_abs"], errors="coerce")
        y = pd.to_numeric(g["tau"], errors="coerce")
        ok = x.notna() & y.notna()
        diag_rows.append(
            {
                "slug": str(s),
                "n_rows": int(g.shape[0]),
                "n_valid_xy": int(ok.sum()),
                "sum_abs_delta0_valid": float(x[ok].sum()) if int(ok.sum()) > 0 else 0.0,
            }
        )
    pd.DataFrame(diag_rows).to_csv(tabs / "exp2_coverage_diagnostics.csv", index=False)
    if bool(exp2_require_all_events) and bool(use_route_b_selected) and missing_exp2:
        raise ValueError(
            "实验2事件级结果覆盖不足："
            f"expect={len(all_events)}, got={len(ev_events)}, missing={missing_exp2}。"
            f"详情见 {tabs / 'exp2_coverage_diagnostics.csv'}"
        )

    if run_until <= 2:
        meta = {
            "output_root": str(output_root),
            "dt_tables_dir": str(dt_tables_dir),
            "n_events": int(len(events)),
            "events": [e.slug for e in events],
            "use_route_b_selected": bool(use_route_b_selected),
            "run_until_exp": int(run_until),
            "exp2_require_all_events": bool(exp2_require_all_events),
            "seed": int(seed),
        }
        (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        readme = """# 动力学模型输出（阶段运行）

本次仅执行：
- 实验1：逐 bin 弛豫时间（`bin_relaxation_times.csv`, `asymmetry_summary.csv`）
- 实验2：非线性检验（`nonlinearity_test.csv`, `nonlinearity_event_level.csv`）
"""
        (out_dir / "README.md").write_text(readme, encoding="utf-8")
        return

    # -------- 实验 3：势模型拟合 --------
    fit_rows: list[dict] = []
    bic_long_rows: list[dict] = []
    for em in events:
        raw = _load_phi_rt_long(output_root=output_root, slug=em.slug)
        phi, _, _ = _prepare_phi(
            raw,
            r_max_km=float(r_max_km),
            min_tiles_overlap=int(min_tiles_overlap),
            daily_average_if_high_freq=bool(daily_average_if_high_freq),
            high_freq_thresh_h=float(high_freq_thresh_h),
        )
        if phi.empty:
            continue
        D_ts = _compute_D_timeseries(phi)
        if D_ts.empty:
            continue
        cls = _classify_bins(
            phi,
            t_peak=float(
                _resolve_t_peak_for_postfit(
                    D_ts,
                    preferred_t_peak=float(em.t_peak_hours) if np.isfinite(em.t_peak_hours) else None,
                    min_post_points=int(min_post_points),
                )[0]
            ),
            D_series=D_ts,
            D_peak=float(em.D_peak),
            peak_frac=float(peak_frac),
            near_zero_eps=float(near_zero_eps),
        )
        t_peak_for_model = _resolve_t_peak_for_postfit(
            D_ts,
            preferred_t_peak=float(em.t_peak_hours) if np.isfinite(em.t_peak_hours) else None,
            min_post_points=int(min_post_points),
        )[0]
        trajs = _event_trajs_for_model(phi, cls, t_peak=float(t_peak_for_model), min_post_points=int(min_post_points))
        if len(trajs) == 0:
            continue
        bsub = bin_df[bin_df["slug"].astype(str) == em.slug].copy()
        tau_guess_e = float(np.nanmedian(pd.to_numeric(bsub.loc[bsub["bin_type"] == "EVAC", "tau"], errors="coerce").to_numpy(dtype=float)))
        tau_guess_i = float(np.nanmedian(pd.to_numeric(bsub.loc[bsub["bin_type"] == "INFL", "tau"], errors="coerce").to_numpy(dtype=float)))
        fit = _fit_langevin_models(trajs, tau_guess_evac=tau_guess_e, tau_guess_infl=tau_guess_i)
        if int(fit.get("ok", 0)) != 1:
            continue
        for m in ["A", "B", "C", "D"]:
            bic_long_rows.append(
                {
                    "slug": em.slug,
                    "short_name": em.short_name,
                    "model": m,
                    "BIC": float(fit.get(f"BIC_{m}", float("nan"))),
                    "sse": float(fit.get(f"sse_{m}", float("nan"))),
                    "k_minus": float(fit.get(f"km_{m}", float("nan"))),
                    "k_plus": float(fit.get(f"kp_{m}", float("nan"))),
                    "gamma": float(fit.get(f"gamma_{m}", float("nan"))),
                    "c": float(fit.get(f"c_{m}", float("nan"))),
                }
            )
        fit_rows.append(
            {
                "slug": em.slug,
                "short_name": em.short_name,
                "disaster_type": em.disaster_type,
                "event_type": em.event_type,
                "n_bins": int(len(trajs)),
                "n_points": int(fit.get("n_obs", 0)),
                "k_minus": float(fit.get("k_minus", float("nan"))),
                "k_plus": float(fit.get("k_plus", float("nan"))),
                "k_ratio": float(fit.get("k_ratio", float("nan"))),
                "gamma": float(fit.get("gamma", float("nan"))),
                "c": float(fit.get("c", float("nan"))),
                "r2": float(fit.get("r2", float("nan"))),
                "BIC_A": float(fit.get("BIC_A", float("nan"))),
                "BIC_B": float(fit.get("BIC_B", float("nan"))),
                "BIC_C": float(fit.get("BIC_C", float("nan"))),
                "BIC_D": float(fit.get("BIC_D", float("nan"))),
                "best_model": str(fit.get("best_model", "")),
                "near_delta": float(em.near_delta),
                "D_peak": float(em.D_peak),
                "alpha": float(em.alpha),
            }
        )
    fit_df = pd.DataFrame(fit_rows)
    fit_df.to_csv(tabs / "langevin_fit_params.csv", index=False)
    pd.DataFrame(bic_long_rows).to_csv(tabs / "langevin_model_bic_long.csv", index=False)

    corr_rows: list[dict] = []
    if not fit_df.empty:
        for name, x_col, y_col in [
            ("k_ratio_vs_delta_near", "k_ratio", "near_delta"),
            ("gamma_vs_D_peak", "gamma", "D_peak"),
        ]:
            x = pd.to_numeric(fit_df[x_col], errors="coerce").to_numpy(dtype=float)
            y = pd.to_numeric(fit_df[y_col], errors="coerce").to_numpy(dtype=float)
            ok = np.isfinite(x) & np.isfinite(y)
            x = x[ok]
            y = y[ok]
            rho = float("nan")
            p = float("nan")
            rho, p, n = _safe_spearman(x, y)
            corr_rows.append({"test": name, "n": int(n), "spearman_rho": float(rho), "spearman_p": float(p)})
    corr_df = pd.DataFrame(corr_rows)
    corr_df.to_csv(tabs / "langevin_param_correlation.csv", index=False)

    # -------- 实验 4：Langevin Simulation --------
    rng = np.random.default_rng(int(seed))
    delta0_pool = pd.to_numeric(bin_df["delta0_abs"], errors="coerce").to_numpy(dtype=float)
    delta0_pool = delta0_pool[np.isfinite(delta0_pool) & (delta0_pool > 0)]
    if delta0_pool.size == 0:
        delta0_pool = np.array([0.05, 0.1, 0.2], dtype=float)
    p_evac = float(np.mean(bin_df["bin_type"].astype(str) == "EVAC")) if not bin_df.empty else 0.5
    p_evac = float(np.clip(p_evac, 0.05, 0.95))

    sim_rows: list[dict] = []
    k_plus_ref = float(np.nanmedian(pd.to_numeric(fit_df["k_plus"], errors="coerce").to_numpy(dtype=float))) if not fit_df.empty else 0.02
    if not np.isfinite(k_plus_ref) or k_plus_ref <= 0:
        k_plus_ref = 0.02

    ratio_grid = np.linspace(float(sim_ratio_min), float(sim_ratio_max), int(max(2, sim_ratio_n)), dtype=float)
    gamma_grid = np.linspace(float(sim_gamma_min), float(sim_gamma_max), int(max(2, sim_gamma_n)), dtype=float)
    for rr in ratio_grid:
        for gg in gamma_grid:
            alphas = []
            deltas = []
            dpeaks = []
            for _ in range(int(max(5, sim_events_per_cell))):
                m = _simulate_one_event(
                    k_minus=float(rr * k_plus_ref),
                    k_plus=float(k_plus_ref),
                    gamma=float(gg),
                    delta0_pool=delta0_pool,
                    p_evac=float(p_evac),
                    rng=rng,
                    sigma=float(sim_sigma),
                    n_bins=int(sim_n_bins),
                    n_near_bins=int(sim_n_near_bins),
                    t_max_h=int(sim_t_max_h),
                    dt_h=float(sim_dt_h),
                    sample_every_h=int(sim_sample_every_h),
                    mono_tol_up=1.05,
                )
                if int(m.get("ok", 0)) != 1:
                    continue
                alphas.append(float(m["alpha"]))
                deltas.append(float(m["delta_near"]))
                dpeaks.append(float(m["D_peak"]))
            alphas_arr = np.asarray(alphas, dtype=float)
            deltas_arr = np.asarray(deltas, dtype=float)
            dpeaks_arr = np.asarray(dpeaks, dtype=float)
            ok1 = np.isfinite(alphas_arr) & np.isfinite(deltas_arr)
            ok2 = np.isfinite(alphas_arr) & np.isfinite(dpeaks_arr)
            rho_ad = float("nan")
            p_ad = float("nan")
            rho_aD = float("nan")
            p_aD = float("nan")
            rho_ad, p_ad, _ = _safe_spearman(alphas_arr[ok1], deltas_arr[ok1])
            rho_aD, p_aD, _ = _safe_spearman(alphas_arr[ok2], dpeaks_arr[ok2])
            sim_rows.append(
                {
                    "k_ratio": float(rr),
                    "gamma": float(gg),
                    "n_valid": int(np.sum(ok1)),
                    "rho_alpha_delta_near": float(rho_ad),
                    "p_alpha_delta_near": float(p_ad),
                    "rho_alpha_D_peak": float(rho_aD),
                    "p_alpha_D_peak": float(p_aD),
                }
            )
    sim_grid_df = pd.DataFrame(sim_rows)
    sim_grid_df.to_csv(tabs / "simulation_phase_grid.csv", index=False)

    # 参数抽样验证：从实验3参数池中抽样，检验相关符号/量级
    val_rows: list[dict] = []
    synth_points: list[dict] = []
    real_points = []
    if not fit_df.empty:
        real_use = fit_df[pd.to_numeric(fit_df["alpha"], errors="coerce").notna() & pd.to_numeric(fit_df["near_delta"], errors="coerce").notna()].copy()
        if real_use.shape[0] >= 3:
            rrho1, rp1, _ = _safe_spearman(
                pd.to_numeric(real_use["alpha"], errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(real_use["near_delta"], errors="coerce").to_numpy(dtype=float),
            )
            rrho2, rp2, _ = _safe_spearman(
                pd.to_numeric(real_use["alpha"], errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(real_use["D_peak"], errors="coerce").to_numpy(dtype=float),
            )
            val_rows.append(
                {
                    "subset": "real_data",
                    "n_events": int(real_use.shape[0]),
                    "rho_alpha_delta_near": float(rrho1),
                    "p_alpha_delta_near": float(rp1),
                    "rho_alpha_D_peak": float(rrho2),
                    "p_alpha_D_peak": float(rp2),
                }
            )
            for _, r in real_use.iterrows():
                real_points.append({"alpha": float(r["alpha"]), "delta_near": float(r["near_delta"]), "source": "real", "slug": str(r["slug"])})

        pool = fit_df[pd.to_numeric(fit_df["k_minus"], errors="coerce").notna() & pd.to_numeric(fit_df["k_plus"], errors="coerce").notna() & pd.to_numeric(fit_df["gamma"], errors="coerce").notna()].copy()
        if not pool.empty:
            n_events_syn = int(max(6, real_use.shape[0] if real_use.shape[0] > 0 else 12))
            rho_ad_list = []
            rho_aD_list = []
            for b in range(int(max(10, sim_validation_batches))):
                m_rows = []
                draw_idx = rng.integers(0, pool.shape[0], size=n_events_syn)
                for idx in draw_idx:
                    pr = pool.iloc[int(idx)]
                    m = _simulate_one_event(
                        k_minus=float(pr["k_minus"]),
                        k_plus=float(pr["k_plus"]),
                        gamma=float(pr["gamma"]),
                        delta0_pool=delta0_pool,
                        p_evac=float(p_evac),
                        rng=rng,
                        sigma=float(sim_sigma),
                        n_bins=int(sim_n_bins),
                        n_near_bins=int(sim_n_near_bins),
                        t_max_h=int(sim_t_max_h),
                        dt_h=float(sim_dt_h),
                        sample_every_h=int(sim_sample_every_h),
                        mono_tol_up=1.05,
                    )
                    if int(m.get("ok", 0)) != 1:
                        continue
                    m_rows.append(m)
                if len(m_rows) < 3:
                    continue
                md = pd.DataFrame(m_rows)
                rho1, p1, _ = _safe_spearman(md["alpha"].to_numpy(dtype=float), md["delta_near"].to_numpy(dtype=float))
                rho2, p2, _ = _safe_spearman(md["alpha"].to_numpy(dtype=float), md["D_peak"].to_numpy(dtype=float))
                rho_ad_list.append(float(rho1))
                rho_aD_list.append(float(rho2))
                if b == 0:
                    for _, r in md.iterrows():
                        synth_points.append({"alpha": float(r["alpha"]), "delta_near": float(r["delta_near"]), "source": "synthetic", "slug": "sim"})
            if rho_ad_list:
                rho_ad_arr = np.asarray(rho_ad_list, dtype=float)
                rho_aD_arr = np.asarray(rho_aD_list, dtype=float)
                val_rows.append(
                    {
                        "subset": "synthetic_param_bootstrap",
                        "n_events": int(n_events_syn),
                        "n_batches": int(len(rho_ad_arr)),
                        "rho_alpha_delta_near_mean": float(np.nanmean(rho_ad_arr)),
                        "rho_alpha_delta_near_ci2p5": float(np.nanpercentile(rho_ad_arr, 2.5)),
                        "rho_alpha_delta_near_ci97p5": float(np.nanpercentile(rho_ad_arr, 97.5)),
                        "rho_alpha_D_peak_mean": float(np.nanmean(rho_aD_arr)),
                        "rho_alpha_D_peak_ci2p5": float(np.nanpercentile(rho_aD_arr, 2.5)),
                        "rho_alpha_D_peak_ci97p5": float(np.nanpercentile(rho_aD_arr, 97.5)),
                    }
                )
    val_df = pd.DataFrame(val_rows)
    val_df.to_csv(tabs / "simulation_validation.csv", index=False)
    pd.DataFrame(synth_points + real_points).to_csv(tabs / "synthetic_vs_real_points.csv", index=False)

    # -------- 绘图 --------
    try:
        from disaster import plot_style as ps  # type: ignore
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        meta = {
            "output_root": str(output_root),
            "dt_tables_dir": str(dt_tables_dir),
            "n_events": int(len(events)),
            "seed": int(seed),
        }
        (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    # Fig 1: tau_infl vs tau_evac
    if not both.empty:
        with ps.paper_style():
            fig, ax = plt.subplots(figsize=(5.4, 4.4))
            x = pd.to_numeric(both["tau_median_evac"], errors="coerce").to_numpy(dtype=float)
            y = pd.to_numeric(both["tau_median_infl"], errors="coerce").to_numpy(dtype=float)
            ok = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
            x = x[ok]
            y = y[ok]
            b2 = both.loc[ok].copy()
            ax.scatter(x, y, s=44, color=ps.OKABE_ITO["blue"], alpha=0.9, linewidths=0)
            for _, r in b2.iterrows():
                ax.text(float(r["tau_median_evac"]), float(r["tau_median_infl"]), str(r.get("short_name", "")), fontsize=7, ha="left", va="bottom")
            if x.size > 0:
                lo = float(min(np.min(x), np.min(y)))
                hi = float(max(np.max(x), np.max(y)))
                ax.plot([lo, hi], [lo, hi], color=ps.OKABE_ITO["gray"], ls="--", lw=1.2)
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_xlabel("τ_EVAC (hours)")
            ax.set_ylabel("τ_INFL (hours)")
            ax.set_title("Exp-1: Median relaxation time by event")
            ps.despine(ax)
            fig.tight_layout()
            ps.save_figure(fig, figs / "tau_infl_vs_evac_scatter.png", dpi=220)
            ps.save_figure(fig, figs / "tau_infl_vs_evac_scatter.pdf")
            plt.close(fig)

    # Fig 2: tau vs |delta0|
    bplot = bin_df[pd.to_numeric(bin_df["tau"], errors="coerce").notna() & pd.to_numeric(bin_df["delta0_abs"], errors="coerce").notna()].copy()
    if not bplot.empty:
        with ps.paper_style():
            fig, ax = plt.subplots(figsize=(5.6, 4.2))
            cmap = {"EVAC": ps.OKABE_ITO["vermillion"], "INFL": ps.OKABE_ITO["blue"], "NEUTRAL": ps.OKABE_ITO["gray"]}
            for bt, g in bplot.groupby("bin_type", sort=True):
                ax.scatter(
                    pd.to_numeric(g["delta0_abs"], errors="coerce").to_numpy(dtype=float),
                    pd.to_numeric(g["tau"], errors="coerce").to_numpy(dtype=float),
                    s=20,
                    alpha=0.6,
                    linewidths=0,
                    color=cmap.get(str(bt), ps.OKABE_ITO["gray"]),
                    label=str(bt),
                )
            ax.set_xlabel("|δ0| at peak")
            ax.set_ylabel("τ (hours)")
            ax.set_yscale("log")
            ax.set_title("Exp-2: τ vs |δ0|")
            ax.legend(frameon=False)
            ps.despine(ax)
            fig.tight_layout()
            ps.save_figure(fig, figs / "tau_vs_abs_delta0_scatter.png", dpi=220)
            ps.save_figure(fig, figs / "tau_vs_abs_delta0_scatter.pdf")
            plt.close(fig)

    # Fig 3a: k_ratio vs delta_near
    if not fit_df.empty:
        q = fit_df[pd.to_numeric(fit_df["k_ratio"], errors="coerce").notna() & pd.to_numeric(fit_df["near_delta"], errors="coerce").notna()].copy()
        if q.shape[0] >= 2:
            with ps.paper_style():
                fig, ax = plt.subplots(figsize=(5.6, 4.2))
                x = pd.to_numeric(q["near_delta"], errors="coerce").to_numpy(dtype=float)
                y = pd.to_numeric(q["k_ratio"], errors="coerce").to_numpy(dtype=float)
                ax.scatter(x, y, s=40, color=ps.OKABE_ITO["bluish_green"], alpha=0.9, linewidths=0)
                for _, r in q.iterrows():
                    ax.text(float(r["near_delta"]), float(r["k_ratio"]), str(r.get("short_name", "")), fontsize=7, ha="left", va="bottom")
                rho = float("nan")
                p = float("nan")
                rho, p, _ = _safe_spearman(x, y)
                ax.text(0.02, 0.98, f"Spearman ρ={rho:.3f}, p={p:.3f}", transform=ax.transAxes, ha="left", va="top", fontsize=9)
                ax.axhline(1.0, color=ps.OKABE_ITO["gray"], ls="--", lw=1.0, alpha=0.7)
                ax.set_xlabel("δ_near")
                ax.set_ylabel("k_minus / k_plus")
                ax.set_title("Exp-3: k asymmetry vs near-field direction")
                ps.despine(ax)
                fig.tight_layout()
                ps.save_figure(fig, figs / "k_ratio_vs_delta_near.png", dpi=220)
                ps.save_figure(fig, figs / "k_ratio_vs_delta_near.pdf")
                plt.close(fig)

        q2 = fit_df[pd.to_numeric(fit_df["gamma"], errors="coerce").notna() & pd.to_numeric(fit_df["D_peak"], errors="coerce").notna()].copy()
        if q2.shape[0] >= 2:
            with ps.paper_style():
                fig, ax = plt.subplots(figsize=(5.6, 4.2))
                x = pd.to_numeric(q2["D_peak"], errors="coerce").to_numpy(dtype=float)
                y = pd.to_numeric(q2["gamma"], errors="coerce").to_numpy(dtype=float)
                ax.scatter(x, y, s=40, color=ps.OKABE_ITO["reddish_purple"], alpha=0.9, linewidths=0)
                for _, r in q2.iterrows():
                    ax.text(float(r["D_peak"]), float(r["gamma"]), str(r.get("short_name", "")), fontsize=7, ha="left", va="bottom")
                rho = float("nan")
                p = float("nan")
                rho, p, _ = _safe_spearman(x, y)
                ax.text(0.02, 0.98, f"Spearman ρ={rho:.3f}, p={p:.3f}", transform=ax.transAxes, ha="left", va="top", fontsize=9)
                ax.set_xlabel("D_peak")
                ax.set_ylabel("γ")
                ax.set_title("Exp-3: nonlinearity vs perturbation amplitude")
                ps.despine(ax)
                fig.tight_layout()
                ps.save_figure(fig, figs / "gamma_vs_D_peak.png", dpi=220)
                ps.save_figure(fig, figs / "gamma_vs_D_peak.pdf")
                plt.close(fig)

    # Fig 4a: phase diagram
    if not sim_grid_df.empty:
        pivot = sim_grid_df.pivot_table(index="gamma", columns="k_ratio", values="rho_alpha_delta_near", aggfunc="mean")
        if not pivot.empty:
            with ps.paper_style():
                fig, ax = plt.subplots(figsize=(6.2, 4.7))
                z = pivot.to_numpy(dtype=float)
                x_vals = np.asarray(pivot.columns.to_list(), dtype=float)
                y_vals = np.asarray(pivot.index.to_list(), dtype=float)
                im = ax.imshow(
                    z,
                    origin="lower",
                    aspect="auto",
                    extent=[float(np.min(x_vals)), float(np.max(x_vals)), float(np.min(y_vals)), float(np.max(y_vals))],
                    cmap="RdBu_r",
                    vmin=-1.0,
                    vmax=1.0,
                )
                if not fit_df.empty:
                    ax.scatter(
                        pd.to_numeric(fit_df["k_ratio"], errors="coerce").to_numpy(dtype=float),
                        pd.to_numeric(fit_df["gamma"], errors="coerce").to_numpy(dtype=float),
                        s=28,
                        c="black",
                        marker="x",
                        alpha=0.8,
                    )
                ax.set_xlabel("k_minus / k_plus")
                ax.set_ylabel("γ")
                ax.set_title("Exp-4 phase diagram (color = ρ(α, δ_near))")
                cb = fig.colorbar(im, ax=ax, shrink=0.92)
                cb.set_label("ρ(α, δ_near)")
                ps.despine(ax)
                fig.tight_layout()
                ps.save_figure(fig, figs / "simulation_phase_diagram.png", dpi=220)
                ps.save_figure(fig, figs / "simulation_phase_diagram.pdf")
                plt.close(fig)

    # Fig 4b: synthetic vs real overlay
    ov = pd.DataFrame(synth_points + real_points)
    if not ov.empty:
        with ps.paper_style():
            fig, ax = plt.subplots(figsize=(5.8, 4.4))
            real = ov[ov["source"] == "real"].copy()
            syn = ov[ov["source"] == "synthetic"].copy()
            if not syn.empty:
                ax.scatter(
                    pd.to_numeric(syn["delta_near"], errors="coerce").to_numpy(dtype=float),
                    pd.to_numeric(syn["alpha"], errors="coerce").to_numpy(dtype=float),
                    s=20,
                    color=ps.OKABE_ITO["gray"],
                    alpha=0.35,
                    linewidths=0,
                    label="Synthetic",
                )
            if not real.empty:
                ax.scatter(
                    pd.to_numeric(real["delta_near"], errors="coerce").to_numpy(dtype=float),
                    pd.to_numeric(real["alpha"], errors="coerce").to_numpy(dtype=float),
                    s=44,
                    color=ps.OKABE_ITO["vermillion"],
                    alpha=0.9,
                    linewidths=0,
                    label="Real",
                )
            ax.axvline(0.0, color=ps.OKABE_ITO["gray"], lw=1.0, ls=":", alpha=0.6)
            ax.set_xlabel("δ_near")
            ax.set_ylabel("α")
            ax.set_title("Exp-4: synthetic vs real")
            ax.legend(frameon=False)
            ps.despine(ax)
            fig.tight_layout()
            ps.save_figure(fig, figs / "synthetic_vs_real_alpha_delta.png", dpi=220)
            ps.save_figure(fig, figs / "synthetic_vs_real_alpha_delta.pdf")
            plt.close(fig)

    meta = {
        "output_root": str(output_root),
        "dt_tables_dir": str(dt_tables_dir),
        "n_events": int(len(events)),
        "events": [e.slug for e in events],
        "use_route_b_selected": bool(use_route_b_selected),
        "run_until_exp": int(run_until),
        "exp2_require_all_events": bool(exp2_require_all_events),
        "r_max_km": float(r_max_km),
        "min_tiles_overlap": int(min_tiles_overlap),
        "peak_frac": float(peak_frac),
        "min_post_points": int(min_post_points),
        "near_zero_eps": float(near_zero_eps),
        "daily_average_if_high_freq": bool(daily_average_if_high_freq),
        "high_freq_thresh_h": float(high_freq_thresh_h),
        "sim_sigma": float(sim_sigma),
        "sim_n_bins": int(sim_n_bins),
        "sim_n_near_bins": int(sim_n_near_bins),
        "sim_t_max_h": int(sim_t_max_h),
        "sim_dt_h": float(sim_dt_h),
        "sim_sample_every_h": int(sim_sample_every_h),
        "sim_events_per_cell": int(sim_events_per_cell),
        "sim_ratio_min": float(sim_ratio_min),
        "sim_ratio_max": float(sim_ratio_max),
        "sim_ratio_n": int(sim_ratio_n),
        "sim_gamma_min": float(sim_gamma_min),
        "sim_gamma_max": float(sim_gamma_max),
        "sim_gamma_n": int(sim_gamma_n),
        "sim_validation_batches": int(sim_validation_batches),
        "seed": int(seed),
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# 动力学模型四实验输出

对应 `Opinion_PI.md` 的四个实验：
- 实验1：逐 bin 弛豫时间（`bin_relaxation_times.csv`, `asymmetry_summary.csv`）
- 实验2：非线性检验（`nonlinearity_test.csv`）
- 实验3：非对称非线性势拟合（`langevin_fit_params.csv`）
- 实验4：Langevin simulation（`simulation_phase_grid.csv`, `simulation_validation.csv`）

输入：
- `outputs/<slug>/phi_heatmap/tables/phi_rt_long.csv`
- `{Path(dt_tables_dir) / "Dt_event_summary.csv"}`
- `{Path(dt_tables_dir) / "Dt_powerlaw_fits.csv"}`
- `{Path(dt_tables_dir) / "Dt_routeB_sample_flags.csv"}`（若启用 Route B 样本筛选）

运行参数见 `metadata.json`。
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")


def cli_main() -> None:
    p = argparse.ArgumentParser(description="Opinion_PI 动力学模型四实验（bin弛豫/非线性/势拟合/仿真）")
    p.add_argument("--output-root", type=Path, default=Path("outputs"))
    p.add_argument("--dt-tables-dir", type=Path, default=Path("outputs/cross_disaster_comparison/Dt_decay/tables"))
    p.add_argument("--out-dir", type=Path, default=Path("outputs/cross_disaster_comparison/dynamics_potential"))
    p.add_argument("--slugs", type=str, nargs="*", default=[], help="可选：只跑指定 slugs；默认按 Route B 自动选")
    p.add_argument("--use-route-b-selected", type=int, default=1, help="1=只用 Dt_routeB_selected 事件；0=用全部可用事件")
    p.add_argument("--route-b-min-n-mono", type=int, default=3)

    p.add_argument("--r-max-km", type=float, default=200.0)
    p.add_argument("--min-tiles-overlap", type=int, default=3)
    p.add_argument("--peak-frac", type=float, default=0.5)
    p.add_argument("--min-post-points", type=int, default=4)
    p.add_argument("--near-zero-eps", type=float, default=1e-3)
    p.add_argument("--daily-average-if-high-freq", type=int, default=1, help="1=8h事件先按日均化再拟合")
    p.add_argument("--high-freq-thresh-h", type=float, default=16.0)

    p.add_argument("--sim-sigma", type=float, default=0.03)
    p.add_argument("--sim-n-bins", type=int, default=20)
    p.add_argument("--sim-n-near-bins", type=int, default=5)
    p.add_argument("--sim-t-max-h", type=int, default=200)
    p.add_argument("--sim-dt-h", type=float, default=1.0)
    p.add_argument("--sim-sample-every-h", type=int, default=8)
    p.add_argument("--sim-events-per-cell", type=int, default=80)
    p.add_argument("--sim-ratio-min", type=float, default=0.5)
    p.add_argument("--sim-ratio-max", type=float, default=2.5)
    p.add_argument("--sim-ratio-n", type=int, default=12)
    p.add_argument("--sim-gamma-min", type=float, default=-1.0)
    p.add_argument("--sim-gamma-max", type=float, default=2.0)
    p.add_argument("--sim-gamma-n", type=int, default=12)
    p.add_argument("--sim-validation-batches", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--run-until-exp", type=int, default=4, help="阶段执行：1/2/3/4，默认4（全跑）")
    p.add_argument("--exp2-require-all-events", type=int, default=1, help="1=实验2事件级必须覆盖全部Route B事件，否则报错")

    args = p.parse_args()
    run(
        output_root=Path(args.output_root),
        dt_tables_dir=Path(args.dt_tables_dir),
        out_dir=Path(args.out_dir),
        slugs=list(args.slugs or []),
        use_route_b_selected=bool(int(args.use_route_b_selected)),
        route_b_min_n_mono=int(args.route_b_min_n_mono),
        r_max_km=float(args.r_max_km),
        min_tiles_overlap=int(args.min_tiles_overlap),
        peak_frac=float(args.peak_frac),
        min_post_points=int(args.min_post_points),
        near_zero_eps=float(args.near_zero_eps),
        daily_average_if_high_freq=bool(int(args.daily_average_if_high_freq)),
        high_freq_thresh_h=float(args.high_freq_thresh_h),
        sim_sigma=float(args.sim_sigma),
        sim_n_bins=int(args.sim_n_bins),
        sim_n_near_bins=int(args.sim_n_near_bins),
        sim_t_max_h=int(args.sim_t_max_h),
        sim_dt_h=float(args.sim_dt_h),
        sim_sample_every_h=int(args.sim_sample_every_h),
        sim_events_per_cell=int(args.sim_events_per_cell),
        sim_ratio_min=float(args.sim_ratio_min),
        sim_ratio_max=float(args.sim_ratio_max),
        sim_ratio_n=int(args.sim_ratio_n),
        sim_gamma_min=float(args.sim_gamma_min),
        sim_gamma_max=float(args.sim_gamma_max),
        sim_gamma_n=int(args.sim_gamma_n),
        sim_validation_batches=int(args.sim_validation_batches),
        seed=int(args.seed),
        run_until_exp=int(args.run_until_exp),
        exp2_require_all_events=bool(int(args.exp2_require_all_events)),
    )


if __name__ == "__main__":
    cli_main()
