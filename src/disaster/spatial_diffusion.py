from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise ModuleNotFoundError("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

try:
    import matplotlib.pyplot as plt
except ModuleNotFoundError as e:
    raise ModuleNotFoundError("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

try:
    from scipy.optimize import minimize
    from scipy.special import j0, jn_zeros
    from scipy.stats import pearsonr, spearmanr
except ModuleNotFoundError as e:
    raise ModuleNotFoundError("缺少依赖：scipy。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from .plot_style import OKABE_ITO, FIGSIZE_FULL, apply_paper_style, save_figure


@dataclass(frozen=True)
class EventMeta:
    slug: str
    short_name: str
    disaster_type: str
    event_type: str
    t_peak_hours: float
    D_peak: float
    delta_near: float
    alpha: float


@dataclass
class EventData:
    meta: EventMeta
    phi: pd.DataFrame
    profile: pd.DataFrame
    post: pd.DataFrame
    D_emp: pd.DataFrame
    t_snap: float
    t_snap_abs_diff_h: float
    median_step_hours_raw: float
    daily_avg_applied: int


@dataclass
class ProfileModel:
    meta: EventMeta
    roots: np.ndarray
    coeffs: np.ndarray
    r_grid: np.ndarray
    basis_matrix: np.ndarray


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _safe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except Exception:
        return None


def _to_bool_series(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s.copy()
    return s.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y"})


def _short_name(slug: str) -> str:
    s = str(slug).strip().lower()
    if not s:
        return ""
    mapping = {
        "turkiye_earthquake_2023": "turkiye",
        "hurricane_beryl_across_southeastern_texas_us": "beryl_tx",
        "hurricane_beryl_across_quintana_roo_and_yucatan_mexico": "beryl_qr",
        "hurricane_beryl_pre_landfall_2024": "beryl_pre",
        "hurricane_john_across_southeastern_guerrero_mexico": "john_gue",
        "hurricane_john_southern_mexico_25_september_2024": "john_sm",
        "hurricane_milton_across_florida_us": "milton_fl",
        "the_earthquake_across_central_mexico": "mexico_eq",
        "spain_flood": "spain_fld",
        "wildfires_in_boise_county_idaho_27_august_2024": "boise_fire",
        "typhoon_yagi_across_northeastern_vietnam": "yagi_vn",
        "the_flooding_across_bagmati_and_koshi_provinces_nepal": "nepal_fld",
        "the_flooding_across_gujarat_india": "gujarat_fld",
        "the_flooding_across_eastern_bangladesh": "bangladesh_fld",
        "flooding_in_central_and_eastern_europe_sept_16_2024": "flooding_eu",
        "moldova_flooding_2024": "moldova_fld",
    }
    return mapping.get(s, s[:24])


def _load_route_b_events(
    *,
    dt_tables_dir: Path,
    use_route_b_selected: bool,
) -> list[EventMeta]:
    flags_path = Path(dt_tables_dir) / "Dt_routeB_sample_flags.csv"
    if not flags_path.exists():
        raise FileNotFoundError(f"未找到 Route B 样本表：{flags_path}")
    df = pd.read_csv(flags_path)
    required_cols = [
        "slug",
        "short_name",
        "disaster_type",
        "event_type",
        "t_peak_hours",
        "D_peak",
        "near_delta_peak_windows_mean",
        "alpha",
    ]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        raise ValueError(f"{flags_path} 缺少列：{missing_cols}")

    if use_route_b_selected:
        if "route_b_selected" not in df.columns:
            raise ValueError(f"{flags_path} 缺少 route_b_selected 列，无法保证口径一致。")
        selected_mask = _to_bool_series(df["route_b_selected"])
        df = df.loc[selected_mask].copy()
        if df.empty:
            raise ValueError(f"{flags_path} 中 route_b_selected 为空，无法继续。")

    events: list[EventMeta] = []
    errors: list[str] = []
    for _, row in df.iterrows():
        slug = str(row.get("slug", "")).strip()
        if not slug:
            continue
        t_peak = _safe_float(row.get("t_peak_hours"))
        D_peak = _safe_float(row.get("D_peak"))
        delta_near = _safe_float(row.get("near_delta_peak_windows_mean"))
        alpha = _safe_float(row.get("alpha"))
        if t_peak is None or D_peak is None or delta_near is None or alpha is None:
            errors.append(slug)
            continue
        events.append(
            EventMeta(
                slug=slug,
                short_name=str(row.get("short_name") or _short_name(slug)),
                disaster_type=str(row.get("disaster_type") or ""),
                event_type=str(row.get("event_type") or ""),
                t_peak_hours=float(t_peak),
                D_peak=float(D_peak),
                delta_near=float(delta_near),
                alpha=float(alpha),
            )
        )

    if errors:
        raise ValueError(f"以下事件在 Route B 样本表中缺少必要数值列：{sorted(errors)}")
    if not events:
        raise ValueError("未加载到任何事件。")
    return sorted(events, key=lambda e: e.slug)


def _load_phi_rt_long(output_root: Path, slug: str) -> pd.DataFrame:
    path = Path(output_root) / slug / "phi_heatmap" / "tables" / "phi_rt_long.csv"
    if not path.exists():
        raise FileNotFoundError(f"未找到：{path}")
    df = pd.read_csv(path)
    need = {"hours_since_quake", "r_bin_km", "phi_overlap", "n_tiles_overlap"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise ValueError(f"{path} 缺少列：{miss}")
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
    if sub.empty:
        return pd.DataFrame(columns=["hours_since_quake", "r_bin_km", "delta", "n_tiles_overlap"]), 0, float("nan")

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


def _compute_D_timeseries(post_df: pd.DataFrame) -> pd.DataFrame:
    if post_df.empty:
        return pd.DataFrame(columns=["hours_since_peak", "D"])
    rows: list[dict[str, float]] = []
    for t, grp in post_df.groupby("hours_since_peak", sort=True):
        arr = pd.to_numeric(grp["delta"], errors="coerce").to_numpy(dtype=float)
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            continue
        rows.append({"hours_since_peak": float(t), "D": float(np.mean(np.abs(arr)))})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("hours_since_peak", kind="stable").reset_index(drop=True)


def _extract_event_data(
    *,
    meta: EventMeta,
    output_root: Path,
    r_max_km: float,
    min_tiles_overlap: int,
    daily_average_if_high_freq: bool,
    high_freq_thresh_h: float,
) -> EventData:
    raw = _load_phi_rt_long(output_root, meta.slug)
    phi, daily_applied, med_step = _prepare_phi(
        raw,
        r_max_km=r_max_km,
        min_tiles_overlap=min_tiles_overlap,
        daily_average_if_high_freq=daily_average_if_high_freq,
        high_freq_thresh_h=high_freq_thresh_h,
    )
    if phi.empty:
        raise ValueError(f"{meta.slug} 过滤后无可用 phi 数据。")

    hours = phi["hours_since_quake"].to_numpy(dtype=float)
    i_snap = int(np.nanargmin(np.abs(hours - float(meta.t_peak_hours))))
    t_snap = float(hours[i_snap])
    profile = (
        phi[phi["hours_since_quake"] == t_snap][["r_bin_km", "delta", "n_tiles_overlap"]]
        .copy()
        .sort_values("r_bin_km", kind="stable")
        .reset_index(drop=True)
    )
    if profile["r_bin_km"].nunique() < 3:
        raise ValueError(f"{meta.slug} 的峰值剖面有效 r_bin 少于 3。")

    post = phi[phi["hours_since_quake"] > float(meta.t_peak_hours)][["hours_since_quake", "r_bin_km", "delta", "n_tiles_overlap"]].copy()
    post["hours_since_peak"] = post["hours_since_quake"] - float(meta.t_peak_hours)
    post = post.sort_values(["hours_since_peak", "r_bin_km"], kind="stable").reset_index(drop=True)
    if post.empty:
        raise ValueError(f"{meta.slug} 在 t_peak 之后无数据，无法进行后峰分析。")

    D_emp = _compute_D_timeseries(post)
    if D_emp.empty:
        raise ValueError(f"{meta.slug} 无法构造 D(t) 后峰序列。")

    return EventData(
        meta=meta,
        phi=phi,
        profile=profile,
        post=post,
        D_emp=D_emp,
        t_snap=t_snap,
        t_snap_abs_diff_h=float(abs(t_snap - float(meta.t_peak_hours))),
        median_step_hours_raw=float(med_step),
        daily_avg_applied=int(daily_applied),
    )


def _bessel_basis(r: np.ndarray, root: float, R_max: float) -> np.ndarray:
    if abs(float(root)) < 1e-12:
        return np.ones_like(r, dtype=float)
    return j0(float(root) * r / float(R_max))


def _bessel_decomposition(
    *,
    r_bins: np.ndarray,
    delta_vals: np.ndarray,
    R_max: float,
    n_modes: int,
    n_grid: int = 200,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if n_modes < 2:
        raise ValueError("n_modes 至少为 2。")
    r = np.asarray(r_bins, dtype=float)
    d = np.asarray(delta_vals, dtype=float)
    ok = np.isfinite(r) & np.isfinite(d)
    r = r[ok]
    d = d[ok]
    if r.size < 3:
        raise ValueError("贝塞尔分解需要至少 3 个有效 r 点。")
    order = np.argsort(r)
    r = r[order]
    d = d[order]

    r_grid = np.linspace(0.0, float(R_max), int(n_grid))
    d_grid = np.interp(r_grid, r, d, left=float(d[0]), right=float(d[-1]))

    roots_nonzero = jn_zeros(0, int(n_modes) - 1)
    roots = np.concatenate([np.array([0.0]), roots_nonzero.astype(float)])
    coeffs = np.zeros_like(roots, dtype=float)

    w = r_grid
    basis0 = np.ones_like(r_grid, dtype=float)
    num0 = np.trapezoid(d_grid * basis0 * w, r_grid)
    den0 = np.trapezoid((basis0**2) * w, r_grid)
    if abs(float(den0)) < 1e-12:
        raise ValueError("贝塞尔分解失败：n=0 分母过小。")
    coeffs[0] = float(num0 / den0)

    for i in range(1, roots.size):
        b = _bessel_basis(r_grid, float(roots[i]), float(R_max))
        num = np.trapezoid(d_grid * b * w, r_grid)
        den = np.trapezoid((b**2) * w, r_grid)
        if abs(float(den)) < 1e-12:
            raise ValueError(f"贝塞尔分解失败：mode={i} 分母过小。")
        coeffs[i] = float(num / den)

    basis_matrix = np.vstack([_bessel_basis(r_grid, float(z), float(R_max)) for z in roots])
    return roots, coeffs, r_grid, basis_matrix


def _compute_shape_metrics(r_bins: np.ndarray, delta_vals: np.ndarray) -> dict[str, float]:
    r = np.asarray(r_bins, dtype=float)
    d = np.asarray(delta_vals, dtype=float)
    ok = np.isfinite(r) & np.isfinite(d)
    r = r[ok]
    d = d[ok]
    order = np.argsort(r)
    r = r[order]
    d = d[order]
    if r.size < 3:
        raise ValueError("shape 指标需要至少 3 个 r 点。")

    abs_area = float(np.trapezoid(np.abs(d), r))
    pos_area = float(np.trapezoid(np.maximum(d, 0.0), r))
    pos_frac = float(pos_area / abs_area) if abs_area > 1e-12 else float("nan")
    r_centroid = float(np.trapezoid(r * np.abs(d), r) / abs_area) if abs_area > 1e-12 else float("nan")

    d_mean = float(np.mean(d))
    d_std = float(np.std(d, ddof=0))
    spatial_cv = float(d_std / abs(d_mean)) if abs(d_mean) > 1e-12 else float("nan")

    slope = float(np.polyfit(r, d, 1)[0]) if r.size >= 2 else float("nan")
    signs = np.sign(d)
    nz = signs[np.abs(signs) > 0]
    sign_changes = float(np.sum(nz[1:] * nz[:-1] < 0)) if nz.size >= 2 else 0.0
    delta_range = float(np.max(d) - np.min(d))
    d0 = float(np.interp(0.0, r, d, left=float(d[0]), right=float(d[-1])))
    d100 = float(np.interp(100.0, r, d, left=float(d[0]), right=float(d[-1])))
    gradient_0_100 = float(d0 - d100)

    return {
        "pos_frac": pos_frac,
        "r_centroid": r_centroid,
        "spatial_cv": spatial_cv,
        "radial_slope": slope,
        "sign_changes": sign_changes,
        "delta_range": delta_range,
        "gradient_0_100": gradient_0_100,
    }


def _spearman_pair(x: np.ndarray, y: np.ndarray) -> tuple[float, float, int]:
    xx = np.asarray(x, dtype=float)
    yy = np.asarray(y, dtype=float)
    ok = np.isfinite(xx) & np.isfinite(yy)
    n = int(np.sum(ok))
    if n < 3:
        return float("nan"), float("nan"), n
    rho, p = spearmanr(xx[ok], yy[ok], nan_policy="omit")
    return float(rho), float(p), n


def _partial_spearman(x: np.ndarray, y: np.ndarray, controls: np.ndarray) -> tuple[float, float, int]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    controls = np.asarray(controls, dtype=float)
    if controls.ndim == 1:
        controls = controls.reshape(-1, 1)
    ok = np.isfinite(x) & np.isfinite(y) & np.all(np.isfinite(controls), axis=1)
    if np.sum(ok) < controls.shape[1] + 3:
        return float("nan"), float("nan"), int(np.sum(ok))
    x = x[ok]
    y = y[ok]
    z = controls[ok, :]

    rank_x = pd.Series(x).rank(method="average").to_numpy(dtype=float)
    rank_y = pd.Series(y).rank(method="average").to_numpy(dtype=float)
    rank_z = np.column_stack([pd.Series(z[:, i]).rank(method="average").to_numpy(dtype=float) for i in range(z.shape[1])])

    X = np.column_stack([np.ones(rank_x.shape[0], dtype=float), rank_z])
    bx, *_ = np.linalg.lstsq(X, rank_x, rcond=None)
    by, *_ = np.linalg.lstsq(X, rank_y, rcond=None)
    rx = rank_x - X @ bx
    ry = rank_y - X @ by

    if np.std(rx) < 1e-12 or np.std(ry) < 1e-12:
        return float("nan"), float("nan"), int(rank_x.shape[0])
    r, p = pearsonr(rx, ry)
    return float(r), float(p), int(rank_x.shape[0])


def predict_D_from_profile(
    c_n: np.ndarray,
    zeros: np.ndarray,
    k: float,
    Ds: float,
    t_array: np.ndarray,
    R_max: float = 200.0,
    n_r_eval: int = 200,
) -> np.ndarray:
    c = np.asarray(c_n, dtype=float)
    z = np.asarray(zeros, dtype=float)
    t = np.asarray(t_array, dtype=float)
    if c.size != z.size:
        raise ValueError("predict_D_from_profile: c_n 与 zeros 长度不一致。")
    if c.size == 0:
        raise ValueError("predict_D_from_profile: 空系数。")

    r_eval = np.linspace(0.0, float(R_max), int(n_r_eval))
    basis = np.vstack([_bessel_basis(r_eval, float(root), float(R_max)) for root in z])
    lambdas = float(k) + float(Ds) * (z / float(R_max)) ** 2
    decays = np.exp(-np.outer(t, lambdas))
    delta_rt = decays @ (c[:, None] * basis)
    D_vals = np.mean(np.abs(delta_rt), axis=1)
    return D_vals


def _fit_alpha_from_D_detail(
    D_array: np.ndarray,
    t_array: np.ndarray,
    *,
    t_start: float,
    t_end: float,
) -> tuple[float, float, int]:
    D = np.asarray(D_array, dtype=float)
    t = np.asarray(t_array, dtype=float)
    ok = np.isfinite(D) & np.isfinite(t) & (t > 0) & (D > 0) & (t >= float(t_start)) & (t <= float(t_end))
    if int(np.sum(ok)) < 3:
        return float("nan"), float("nan"), int(np.sum(ok))
    lx = np.log(t[ok])
    ly = np.log(D[ok])
    slope, intercept = np.polyfit(lx, ly, 1)
    yhat = slope * lx + intercept
    ss_res = float(np.sum((ly - yhat) ** 2))
    ss_tot = float(np.sum((ly - np.mean(ly)) ** 2))
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 1e-12 else float("nan")
    alpha = float(-slope)
    return alpha, r2, int(np.sum(ok))


def fit_alpha_from_D(
    D_array: np.ndarray,
    t_array: np.ndarray,
    t_start: float = 24.0,
    t_end: float = 120.0,
) -> float:
    alpha, _, _ = _fit_alpha_from_D_detail(D_array, t_array, t_start=t_start, t_end=t_end)
    return float(alpha)


def _predict_D_from_model(model: ProfileModel, *, k: float, Ds: float, t_array: np.ndarray) -> np.ndarray:
    z = model.roots
    c = model.coeffs
    t = np.asarray(t_array, dtype=float)
    lambdas = float(k) + float(Ds) * (z / float(model.r_grid[-1])) ** 2
    decays = np.exp(-np.outer(t, lambdas))
    delta_rt = decays @ (c[:, None] * model.basis_matrix)
    D_vals = np.mean(np.abs(delta_rt), axis=1)
    return D_vals


def _estimate_global_params_grid(
    models: list[ProfileModel],
    *,
    k_grid: np.ndarray,
    ds_grid: np.ndarray,
    t_eval: np.ndarray,
    t_start: float,
    t_end: float,
) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    alpha_emp = np.array([m.meta.alpha for m in models], dtype=float)
    delta_near = np.array([m.meta.delta_near for m in models], dtype=float)
    D_peak = np.array([m.meta.D_peak for m in models], dtype=float)

    for k in k_grid:
        for ds in ds_grid:
            pred = []
            valid = True
            for m in models:
                Dp = _predict_D_from_model(m, k=float(k), Ds=float(ds), t_array=t_eval)
                alpha_pred = fit_alpha_from_D(Dp, t_eval, t_start=float(t_start), t_end=float(t_end))
                if not np.isfinite(alpha_pred):
                    valid = False
                    break
                pred.append(float(alpha_pred))
            if not valid:
                continue
            alpha_pred_arr = np.array(pred, dtype=float)
            rho_s, p_s, n_s = _spearman_pair(alpha_pred_arr, alpha_emp)
            rho_p, p_p = pearsonr(alpha_pred_arr, alpha_emp)
            mae = float(np.mean(np.abs(alpha_pred_arr - alpha_emp)))
            rho_dn, p_dn, _ = _spearman_pair(alpha_pred_arr, delta_near)
            rho_dp, p_dp, _ = _spearman_pair(alpha_pred_arr, D_peak)
            rows.append(
                {
                    "k": float(k),
                    "Ds": float(ds),
                    "spearman_rho_alpha_emp": float(rho_s),
                    "spearman_p_alpha_emp": float(p_s),
                    "pearson_r_alpha_emp": float(rho_p),
                    "pearson_p_alpha_emp": float(p_p),
                    "mae_alpha": float(mae),
                    "n_events": int(n_s),
                    "spearman_rho_alpha_pred_vs_delta_near": float(rho_dn),
                    "spearman_p_alpha_pred_vs_delta_near": float(p_dn),
                    "spearman_rho_alpha_pred_vs_D_peak": float(rho_dp),
                    "spearman_p_alpha_pred_vs_D_peak": float(p_dp),
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("参数网格搜索未得到任何可用组合。")
    return out


def _estimate_global_params_least_squares(
    models: list[ProfileModel],
    *,
    t_eval: np.ndarray,
    t_start: float,
    t_end: float,
    k_min: float,
    k_max: float,
    ds_min: float,
    ds_max: float,
    k_init: float,
    ds_init: float,
) -> dict[str, float]:
    alpha_emp = np.array([m.meta.alpha for m in models], dtype=float)
    delta_near = np.array([m.meta.delta_near for m in models], dtype=float)
    D_peak = np.array([m.meta.D_peak for m in models], dtype=float)

    def _alpha_pred(k: float, ds: float) -> np.ndarray:
        out = []
        for m in models:
            Dp = _predict_D_from_model(m, k=float(k), Ds=float(ds), t_array=t_eval)
            a = fit_alpha_from_D(Dp, t_eval, t_start=float(t_start), t_end=float(t_end))
            out.append(float(a))
        return np.array(out, dtype=float)

    def objective(log_params: np.ndarray) -> float:
        k = float(np.exp(log_params[0]))
        ds = float(np.exp(log_params[1]))
        ap = _alpha_pred(k, ds)
        if not np.all(np.isfinite(ap)):
            return 1e6
        return float(np.mean((ap - alpha_emp) ** 2))

    x0 = np.log([max(k_min, min(k_init, k_max)), max(ds_min, min(ds_init, ds_max))])
    bounds = [(float(np.log(k_min)), float(np.log(k_max))), (float(np.log(ds_min)), float(np.log(ds_max)))]
    res = minimize(objective, x0=x0, method="L-BFGS-B", bounds=bounds)
    x_opt = res.x if np.all(np.isfinite(res.x)) else x0
    k_opt = float(np.exp(x_opt[0]))
    ds_opt = float(np.exp(x_opt[1]))

    alpha_pred = _alpha_pred(k_opt, ds_opt)
    rho_s, p_s, n_s = _spearman_pair(alpha_pred, alpha_emp)
    rho_p, p_p = pearsonr(alpha_pred, alpha_emp)
    mae = float(np.mean(np.abs(alpha_pred - alpha_emp)))
    rho_dn, p_dn, _ = _spearman_pair(alpha_pred, delta_near)
    rho_dp, p_dp, _ = _spearman_pair(alpha_pred, D_peak)
    return {
        "criterion": "min_sse_opt",
        "k": float(k_opt),
        "Ds": float(ds_opt),
        "spearman_rho_alpha_emp": float(rho_s),
        "spearman_p_alpha_emp": float(p_s),
        "pearson_r_alpha_emp": float(rho_p),
        "pearson_p_alpha_emp": float(p_p),
        "mae_alpha": float(mae),
        "n_events": int(n_s),
        "spearman_rho_alpha_pred_vs_delta_near": float(rho_dn),
        "spearman_p_alpha_pred_vs_delta_near": float(p_dn),
        "spearman_rho_alpha_pred_vs_D_peak": float(rho_dp),
        "spearman_p_alpha_pred_vs_D_peak": float(p_dp),
        "optimizer_success": int(bool(res.success)),
        "optimizer_fun": float(res.fun),
    }


def _pick_best_rows(param_grid: pd.DataFrame) -> pd.DataFrame:
    if param_grid.empty:
        raise ValueError("空参数网格。")
    idx_s = int(param_grid["spearman_rho_alpha_emp"].astype(float).idxmax())
    idx_p = int(param_grid["pearson_r_alpha_emp"].astype(float).idxmax())
    idx_m = int(param_grid["mae_alpha"].astype(float).idxmin())
    rows = []
    for criterion, idx in [("max_spearman", idx_s), ("max_pearson", idx_p), ("min_mae", idx_m)]:
        row = param_grid.loc[idx].to_dict()
        row["criterion"] = criterion
        rows.append(row)
    return pd.DataFrame(rows)


def _loo_cross_validation(
    models: list[ProfileModel],
    *,
    k_grid: np.ndarray,
    ds_grid: np.ndarray,
    t_eval: np.ndarray,
    t_start: float,
    t_end: float,
) -> pd.DataFrame:
    if len(models) < 4:
        raise ValueError("LOO 至少需要 4 个事件。")
    rows: list[dict[str, float | str]] = []
    for i, hold in enumerate(models):
        train = [m for j, m in enumerate(models) if j != i]
        grid_train = _estimate_global_params_grid(
            train,
            k_grid=k_grid,
            ds_grid=ds_grid,
            t_eval=t_eval,
            t_start=t_start,
            t_end=t_end,
        )
        best_idx = int(grid_train["spearman_rho_alpha_emp"].astype(float).idxmax())
        best = grid_train.loc[best_idx]
        k_best = float(best["k"])
        ds_best = float(best["Ds"])
        D_pred = _predict_D_from_model(hold, k=k_best, Ds=ds_best, t_array=t_eval)
        alpha_pred = fit_alpha_from_D(D_pred, t_eval, t_start=t_start, t_end=t_end)
        rows.append(
            {
                "slug": hold.meta.slug,
                "short_name": hold.meta.short_name,
                "alpha_emp": float(hold.meta.alpha),
                "alpha_pred_loo": float(alpha_pred),
                "abs_error": float(abs(alpha_pred - hold.meta.alpha)),
                "k_best_train": k_best,
                "Ds_best_train": ds_best,
            }
        )
    out = pd.DataFrame(rows)
    rho, p, n = _spearman_pair(out["alpha_pred_loo"].to_numpy(dtype=float), out["alpha_emp"].to_numpy(dtype=float))
    out["loo_spearman_rho"] = float(rho)
    out["loo_spearman_p"] = float(p)
    out["loo_n_events"] = int(n)
    return out


def _bootstrap_simulation(
    models: list[ProfileModel],
    *,
    k: float,
    Ds: float,
    t_eval: np.ndarray,
    t_start: float,
    t_end: float,
    n_iter: int,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(int(seed))
    n = len(models)
    rows: list[dict[str, float | int]] = []
    for i in range(int(n_iter)):
        idx = rng.integers(low=0, high=n, size=n)
        alpha_pred_list = []
        delta_near_list = []
        for j in idx:
            m = models[int(j)]
            amp = float(rng.uniform(0.8, 1.2))
            noise = rng.normal(loc=0.0, scale=0.02 * (np.std(m.coeffs) + 1e-6), size=m.coeffs.size)
            c_mod = m.coeffs * amp + noise
            D_pred = predict_D_from_profile(
                c_mod,
                m.roots,
                float(k),
                float(Ds),
                t_eval,
                R_max=float(m.r_grid[-1]),
                n_r_eval=int(m.r_grid.size),
            )
            a = fit_alpha_from_D(D_pred, t_eval, t_start=t_start, t_end=t_end)
            if not np.isfinite(a):
                continue
            alpha_pred_list.append(float(a))
            delta_near_list.append(float(m.meta.delta_near * amp + rng.normal(0.0, 0.01)))
        if len(alpha_pred_list) < 4:
            continue
        rho, p, n_eff = _spearman_pair(np.array(alpha_pred_list, dtype=float), np.array(delta_near_list, dtype=float))
        rows.append({"iter": i, "rho_alpha_pred_vs_delta_near": float(rho), "p_value": float(p), "n_eff": int(n_eff)})
    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("bootstrap_simulation 未生成有效样本。")
    return out


def _counterfactual_shuffle(
    models: list[ProfileModel],
    *,
    k: float,
    Ds: float,
    t_eval: np.ndarray,
    t_start: float,
    t_end: float,
    n_iter: int,
    seed: int,
) -> dict[str, float]:
    rng = np.random.default_rng(int(seed))
    n = len(models)
    near = np.array([m.meta.delta_near for m in models], dtype=float)
    rho_list: list[float] = []
    for _ in range(int(n_iter)):
        perm = rng.permutation(n)
        alpha_pred = []
        for idx_model in perm:
            m = models[int(idx_model)]
            D_pred = _predict_D_from_model(m, k=k, Ds=Ds, t_array=t_eval)
            a = fit_alpha_from_D(D_pred, t_eval, t_start=t_start, t_end=t_end)
            alpha_pred.append(float(a))
        rho, _, _ = _spearman_pair(np.array(alpha_pred, dtype=float), near)
        if np.isfinite(rho):
            rho_list.append(float(rho))
    if not rho_list:
        raise ValueError("counterfactual_shuffle 未得到有效 rho。")
    arr = np.array(rho_list, dtype=float)
    return {
        "rho_mean": float(np.mean(arr)),
        "rho_ci_low": float(np.quantile(arr, 0.025)),
        "rho_ci_high": float(np.quantile(arr, 0.975)),
        "n_iter": int(arr.size),
    }


def _counterfactual_no_diffusion(
    models: list[ProfileModel],
    *,
    k: float,
    t_eval: np.ndarray,
    t_start: float,
    t_end: float,
) -> dict[str, float]:
    alpha_pred = []
    near = []
    for m in models:
        D_pred = _predict_D_from_model(m, k=float(k), Ds=0.0, t_array=t_eval)
        a = fit_alpha_from_D(D_pred, t_eval, t_start=t_start, t_end=t_end)
        alpha_pred.append(float(a))
        near.append(float(m.meta.delta_near))
    rho, p, n = _spearman_pair(np.array(alpha_pred, dtype=float), np.array(near, dtype=float))
    return {"rho": float(rho), "p_value": float(p), "n_events": int(n)}


def _counterfactual_uniform_profile(
    models: list[ProfileModel],
    *,
    k: float,
    Ds: float,
    t_eval: np.ndarray,
    t_start: float,
    t_end: float,
) -> dict[str, float]:
    alpha_pred = []
    near = []
    for m in models:
        c = np.zeros_like(m.coeffs)
        c[0] = m.coeffs[0]
        D_pred = predict_D_from_profile(
            c,
            m.roots,
            float(k),
            float(Ds),
            t_eval,
            R_max=float(m.r_grid[-1]),
            n_r_eval=int(m.r_grid.size),
        )
        a = fit_alpha_from_D(D_pred, t_eval, t_start=t_start, t_end=t_end)
        alpha_pred.append(float(a))
        near.append(float(m.meta.delta_near))
    rho, p, n = _spearman_pair(np.array(alpha_pred, dtype=float), np.array(near, dtype=float))
    return {"rho": float(rho), "p_value": float(p), "n_events": int(n)}


def _write_readme(out_dir: Path) -> None:
    text = """# 空间扩散-弛豫实验输出（Direction C）

输入：
- `outputs/<slug>/phi_heatmap/tables/phi_rt_long.csv`
- `outputs/cross_disaster_comparison/Dt_decay/tables/Dt_routeB_sample_flags.csv`

实验分层：
- Exp0：数据准备（峰值剖面 + 后峰轨迹）
- Exp1：profile 形状指标 + 贝塞尔模态分解 + 相关/偏相关
- Exp2：解析工具（合成 profile 的 D(t) 与 α）
- Exp3：真实 profile 的 PDE 预测与参数搜索
- Exp4：bootstrap 与反事实验证
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def _plot_profile_gallery(shape_df: pd.DataFrame, out_path: Path) -> None:
    if shape_df.empty:
        return
    apply_paper_style()
    order = shape_df.sort_values("delta_near", kind="stable")["slug"].tolist()
    fig, axes = plt.subplots(2, 8, figsize=(16, 5.2), sharex=True, sharey=True)
    ax_list = axes.ravel().tolist()
    for i, slug in enumerate(order[:16]):
        ax = ax_list[i]
        sub = shape_df.loc[shape_df["slug"] == slug].sort_values("r_bin_km", kind="stable")
        color = OKABE_ITO["vermillion"] if float(sub["delta_near"].iloc[0]) < 0 else OKABE_ITO["blue"]
        ax.plot(sub["r_bin_km"], sub["delta_at_peak"], color=color, lw=2.0)
        ax.axhline(0.0, color=OKABE_ITO["gray"], lw=1.0, ls="--")
        ax.set_title(str(sub["short_name"].iloc[0]), fontsize=9)
    for j in range(len(order), len(ax_list)):
        ax_list[j].axis("off")
    fig.supxlabel("r (km)")
    fig.supylabel("δ(r, t_peak)")
    fig.tight_layout()
    save_figure(fig, out_path)
    plt.close(fig)


def _plot_synthetic_decay(df: pd.DataFrame, out_path: Path) -> None:
    if df.empty:
        return
    apply_paper_style()
    fig, ax = plt.subplots(figsize=FIGSIZE_FULL)
    color_map = {"EVAC": OKABE_ITO["vermillion"], "INFL": OKABE_ITO["blue"], "MIXED": OKABE_ITO["gray"]}
    for key, grp in df.groupby("profile_label", sort=True):
        cls = str(grp["profile_class"].iloc[0])
        ax.plot(grp["t_hours"], grp["D"], lw=2.0, color=color_map.get(cls, OKABE_ITO["gray"]), label=str(key))
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("t' (hours)")
    ax.set_ylabel("D(t')")
    ax.set_title("Synthetic profile decay")
    ax.legend(ncol=2, frameon=False, fontsize=8)
    fig.tight_layout()
    save_figure(fig, out_path)
    plt.close(fig)


def _plot_mode_decay(roots: np.ndarray, *, k: float, Ds: float, R_max: float, out_path: Path) -> None:
    apply_paper_style()
    n = np.arange(roots.size)
    lam = float(k) + float(Ds) * (roots / float(R_max)) ** 2
    fig, ax = plt.subplots(figsize=FIGSIZE_FULL)
    ax.plot(n, lam, marker="o", lw=2.0, color=OKABE_ITO["bluish_green"])
    ax.set_xlabel("mode n")
    ax.set_ylabel("λ_n (1/h)")
    ax.set_title("Mode decay rates")
    fig.tight_layout()
    save_figure(fig, out_path)
    plt.close(fig)


def _plot_param_heatmap(
    param_grid: pd.DataFrame,
    *,
    k_values: np.ndarray,
    ds_values: np.ndarray,
    out_path: Path,
) -> None:
    apply_paper_style()
    k_sorted = np.array(sorted(np.unique(k_values)), dtype=float)
    ds_sorted = np.array(sorted(np.unique(ds_values)), dtype=float)
    n_k, n_ds = k_sorted.size, ds_sorted.size

    def make_matrix(col: str) -> np.ndarray:
        mat = np.full((n_k, n_ds), np.nan, dtype=float)
        k_to_i = {float(v): i for i, v in enumerate(k_sorted)}
        ds_to_j = {float(v): j for j, v in enumerate(ds_sorted)}
        for _, row in param_grid.iterrows():
            i = k_to_i.get(float(row["k"]))
            j = ds_to_j.get(float(row["Ds"]))
            if i is not None and j is not None:
                mat[i, j] = float(row[col])
        return mat

    m_s = make_matrix("spearman_rho_alpha_emp")
    m_mae = make_matrix("mae_alpha")
    m_dn = make_matrix("spearman_rho_alpha_pred_vs_delta_near")

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2), sharex=True, sharey=True)
    mats = [m_s, m_mae, m_dn]
    titles = ["Spearman(α_pred, α_emp)", "MAE(α)", "Spearman(α_pred, δ_near)"]
    cmaps = ["RdBu_r", "viridis", "RdBu_r"]
    for ax, m, ttl, cmap in zip(axes, mats, titles, cmaps):
        im = ax.imshow(
            m,
            origin="lower",
            aspect="auto",
            extent=[np.log10(ds_sorted.min()), np.log10(ds_sorted.max()), np.log10(k_sorted.min()), np.log10(k_sorted.max())],
            cmap=cmap,
        )
        ax.set_title(ttl)
        ax.set_xlabel("log10(Ds)")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    axes[0].set_ylabel("log10(k)")
    fig.tight_layout()
    save_figure(fig, out_path)
    plt.close(fig)


def _plot_alpha_scatter(df: pd.DataFrame, out_path: Path) -> None:
    if df.empty:
        return
    apply_paper_style()
    fig, ax = plt.subplots(figsize=FIGSIZE_FULL)
    x = df["alpha_emp"].to_numpy(dtype=float)
    y = df["alpha_pred"].to_numpy(dtype=float)
    ax.scatter(x, y, c=OKABE_ITO["blue"], s=45, alpha=0.9)
    lo = float(min(np.nanmin(x), np.nanmin(y)))
    hi = float(max(np.nanmax(x), np.nanmax(y)))
    ax.plot([lo, hi], [lo, hi], ls="--", lw=1.2, color=OKABE_ITO["gray"])
    rho_s, p_s, n = _spearman_pair(x, y)
    ax.set_xlabel("α empirical")
    ax.set_ylabel("α predicted")
    ax.set_title(f"α prediction (Spearman ρ={rho_s:.3f}, p={p_s:.3g}, n={n})")
    fig.tight_layout()
    save_figure(fig, out_path)
    plt.close(fig)


def _plot_D_comparison_gallery(
    *,
    event_data: dict[str, EventData],
    models_by_slug: dict[str, ProfileModel],
    k: float,
    Ds: float,
    out_path: Path,
) -> None:
    ranked = sorted(event_data.values(), key=lambda e: e.meta.delta_near)
    if len(ranked) < 4:
        return
    chosen = [ranked[0], ranked[1], ranked[-2], ranked[-1]]
    apply_paper_style()
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharex=False, sharey=False)
    for ax, ev in zip(axes.ravel(), chosen):
        d_emp = ev.D_emp.copy()
        t = d_emp["hours_since_peak"].to_numpy(dtype=float)
        y_emp = d_emp["D"].to_numpy(dtype=float)
        model = models_by_slug[ev.meta.slug]
        y_pred = _predict_D_from_model(model, k=k, Ds=Ds, t_array=t)
        if np.isfinite(y_emp[0]) and y_emp[0] > 1e-12:
            y_emp_n = y_emp / y_emp[0]
            y_pred_n = y_pred / y_pred[0]
        else:
            y_emp_n = y_emp
            y_pred_n = y_pred
        ax.plot(t, y_emp_n, color=OKABE_ITO["black"], lw=2.0, label="Empirical")
        ax.plot(t, y_pred_n, color=OKABE_ITO["vermillion"], lw=2.0, ls="--", label="PDE predicted")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_title(f"{ev.meta.short_name} (δ_near={ev.meta.delta_near:.3f})", fontsize=10)
        ax.set_xlabel("t' (hours)")
        ax.set_ylabel("D(t') / D(0+)")
        ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    save_figure(fig, out_path)
    plt.close(fig)


def _run_exp0(
    *,
    events: list[EventMeta],
    output_root: Path,
    tables_dir: Path,
    r_max_km: float,
    min_tiles_overlap: int,
    daily_average_if_high_freq: bool,
    high_freq_thresh_h: float,
) -> tuple[dict[str, EventData], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    event_data: dict[str, EventData] = {}
    radial_rows: list[dict[str, Any]] = []
    post_rows: list[dict[str, Any]] = []
    diag_rows: list[dict[str, Any]] = []

    for meta in events:
        e = _extract_event_data(
            meta=meta,
            output_root=output_root,
            r_max_km=r_max_km,
            min_tiles_overlap=min_tiles_overlap,
            daily_average_if_high_freq=daily_average_if_high_freq,
            high_freq_thresh_h=high_freq_thresh_h,
        )
        event_data[meta.slug] = e
        for _, row in e.profile.iterrows():
            radial_rows.append(
                {
                    "slug": meta.slug,
                    "short_name": meta.short_name,
                    "disaster_type": meta.disaster_type,
                    "event_type": meta.event_type,
                    "r_bin_km": float(row["r_bin_km"]),
                    "delta_at_peak": float(row["delta"]),
                    "n_tiles": float(row["n_tiles_overlap"]),
                    "t_snap": float(e.t_snap),
                    "t_peak_hours": float(meta.t_peak_hours),
                    "t_snap_abs_diff_h": float(e.t_snap_abs_diff_h),
                    "delta_near": float(meta.delta_near),
                    "D_peak": float(meta.D_peak),
                    "alpha": float(meta.alpha),
                }
            )
        for _, row in e.post.iterrows():
            post_rows.append(
                {
                    "slug": meta.slug,
                    "r_bin_km": float(row["r_bin_km"]),
                    "hours_since_peak": float(row["hours_since_peak"]),
                    "delta": float(row["delta"]),
                    "n_tiles": float(row["n_tiles_overlap"]),
                }
            )
        diag_rows.append(
            {
                "slug": meta.slug,
                "short_name": meta.short_name,
                "t_peak_hours": float(meta.t_peak_hours),
                "t_snap": float(e.t_snap),
                "t_snap_abs_diff_h": float(e.t_snap_abs_diff_h),
                "n_profile_bins": int(e.profile["r_bin_km"].nunique()),
                "n_post_rows": int(len(e.post)),
                "median_step_hours_raw": float(e.median_step_hours_raw),
                "daily_avg_applied": int(e.daily_avg_applied),
            }
        )

    if len(event_data) != len(events):
        missing = sorted(set(e.slug for e in events) - set(event_data.keys()))
        raise ValueError(f"Exp0 事件覆盖不足：expect={len(events)} got={len(event_data)} missing={missing}")

    radial_df = pd.DataFrame(radial_rows).sort_values(["slug", "r_bin_km"], kind="stable").reset_index(drop=True)
    post_df = pd.DataFrame(post_rows).sort_values(["slug", "hours_since_peak", "r_bin_km"], kind="stable").reset_index(drop=True)
    diag_df = pd.DataFrame(diag_rows).sort_values(["slug"], kind="stable").reset_index(drop=True)

    radial_df.to_csv(tables_dir / "radial_profiles_at_peak.csv", index=False)
    post_df.to_csv(tables_dir / "post_peak_trajectories.csv", index=False)
    diag_df.to_csv(tables_dir / "event_preprocess_diagnostics.csv", index=False)
    return event_data, radial_df, post_df, diag_df


def _run_exp1(
    *,
    event_data: dict[str, EventData],
    tables_dir: Path,
    figures_dir: Path,
    r_max_km: float,
    n_bessel_modes: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metrics_rows: list[dict[str, Any]] = []
    bessel_rows: list[dict[str, Any]] = []
    gallery_rows: list[dict[str, Any]] = []

    for slug, ev in event_data.items():
        r = ev.profile["r_bin_km"].to_numpy(dtype=float)
        d = ev.profile["delta"].to_numpy(dtype=float)
        metrics = _compute_shape_metrics(r, d)
        roots, coeffs, r_grid, basis = _bessel_decomposition(
            r_bins=r,
            delta_vals=d,
            R_max=float(r_max_km),
            n_modes=int(n_bessel_modes),
            n_grid=200,
        )
        energies = coeffs**2
        e_total = float(np.sum(energies))
        e_low = float(np.sum(energies[:2])) if energies.size >= 2 else float(np.sum(energies))
        e_low_frac = float(e_low / e_total) if e_total > 1e-12 else float("nan")
        e_high_frac = float(1.0 - e_low_frac) if np.isfinite(e_low_frac) else float("nan")

        row = {
            "slug": slug,
            "short_name": ev.meta.short_name,
            "disaster_type": ev.meta.disaster_type,
            "event_type": ev.meta.event_type,
            "alpha": float(ev.meta.alpha),
            "delta_near": float(ev.meta.delta_near),
            "D_peak": float(ev.meta.D_peak),
            "t_peak_hours": float(ev.meta.t_peak_hours),
            "t_snap": float(ev.t_snap),
            "t_snap_abs_diff_h": float(ev.t_snap_abs_diff_h),
            "n_profile_bins": int(ev.profile["r_bin_km"].nunique()),
            **metrics,
            "E_low_frac": e_low_frac,
            "E_high_frac": e_high_frac,
            "c0": float(coeffs[0]),
            "c1": float(coeffs[1]) if coeffs.size > 1 else float("nan"),
            "c2": float(coeffs[2]) if coeffs.size > 2 else float("nan"),
        }
        metrics_rows.append(row)

        brow = {
            "slug": slug,
            "short_name": ev.meta.short_name,
            "alpha": float(ev.meta.alpha),
            "delta_near": float(ev.meta.delta_near),
            "D_peak": float(ev.meta.D_peak),
            "E_total": e_total,
            "E_low_frac": e_low_frac,
            "E_high_frac": e_high_frac,
        }
        for i, c in enumerate(coeffs):
            brow[f"c_{i}"] = float(c)
            brow[f"E_{i}"] = float(energies[i])
            brow[f"root_{i}"] = float(roots[i])
        bessel_rows.append(brow)

        for _, row_r in ev.profile.iterrows():
            gallery_rows.append(
                {
                    "slug": slug,
                    "short_name": ev.meta.short_name,
                    "delta_near": float(ev.meta.delta_near),
                    "r_bin_km": float(row_r["r_bin_km"]),
                    "delta_at_peak": float(row_r["delta"]),
                }
            )

        ev_model = ProfileModel(meta=ev.meta, roots=roots, coeffs=coeffs, r_grid=r_grid, basis_matrix=basis)
        event_data[slug].__dict__["_profile_model"] = ev_model

    metrics_df = pd.DataFrame(metrics_rows).sort_values(["slug"], kind="stable").reset_index(drop=True)
    bessel_df = pd.DataFrame(bessel_rows).sort_values(["slug"], kind="stable").reset_index(drop=True)
    gallery_df = pd.DataFrame(gallery_rows).sort_values(["slug", "r_bin_km"], kind="stable").reset_index(drop=True)

    metrics_df.to_csv(tables_dir / "profile_shape_metrics.csv", index=False)
    bessel_df.to_csv(tables_dir / "bessel_coefficients.csv", index=False)

    corr_rows: list[dict[str, Any]] = []
    metric_cols = [
        "pos_frac",
        "r_centroid",
        "spatial_cv",
        "radial_slope",
        "sign_changes",
        "delta_range",
        "gradient_0_100",
        "E_low_frac",
        "E_high_frac",
        "c0",
        "c1",
        "c2",
    ]
    targets = ["alpha", "delta_near", "D_peak"]
    for m in metric_cols:
        x = metrics_df[m].to_numpy(dtype=float)
        for t in targets:
            y = metrics_df[t].to_numpy(dtype=float)
            rho, p, n = _spearman_pair(x, y)
            corr_rows.append({"metric": m, "target": t, "n": int(n), "spearman_rho": float(rho), "spearman_p": float(p)})
    corr_df = pd.DataFrame(corr_rows)
    corr_df.to_csv(tables_dir / "shape_alpha_correlations.csv", index=False)

    partial_rows: list[dict[str, Any]] = []
    r1, p1, n1 = _partial_spearman(
        metrics_df["pos_frac"].to_numpy(dtype=float),
        metrics_df["alpha"].to_numpy(dtype=float),
        metrics_df[["delta_near"]].to_numpy(dtype=float),
    )
    partial_rows.append(
        {
            "x_metric": "pos_frac",
            "y_target": "alpha",
            "controls": "delta_near",
            "n": int(n1),
            "partial_spearman_r": float(r1),
            "p_value": float(p1),
        }
    )
    r2, p2, n2 = _partial_spearman(
        metrics_df["E_high_frac"].to_numpy(dtype=float),
        metrics_df["alpha"].to_numpy(dtype=float),
        metrics_df[["D_peak"]].to_numpy(dtype=float),
    )
    partial_rows.append(
        {
            "x_metric": "E_high_frac",
            "y_target": "alpha",
            "controls": "D_peak",
            "n": int(n2),
            "partial_spearman_r": float(r2),
            "p_value": float(p2),
        }
    )
    partial_df = pd.DataFrame(partial_rows)
    partial_df.to_csv(tables_dir / "shape_alpha_partial_correlations.csv", index=False)

    _plot_profile_gallery(gallery_df, figures_dir / "profile_gallery.png")
    return metrics_df, bessel_df


def _run_exp2(
    *,
    tables_dir: Path,
    figures_dir: Path,
    r_max_km: float,
    n_bessel_modes: int,
    t_start: float,
    t_end: float,
    k_synth: float,
    ds_synth: float,
) -> None:
    r = np.linspace(0.0, float(r_max_km), 201)
    synth_defs = [
        ("evac_core", "EVAC", -0.35 * np.exp(-(r / 35.0) ** 2)),
        ("evac_spread", "EVAC", -0.25 * np.exp(-(r / 60.0) ** 2) - 0.05 * np.exp(-((r - 120.0) / 35.0) ** 2)),
        ("infl_uniform", "INFL", 0.20 * np.exp(-(r / 95.0) ** 2)),
        ("infl_core", "INFL", 0.30 * np.exp(-(r / 45.0) ** 2)),
        ("mixed_ring", "MIXED", -0.20 * np.exp(-(r / 30.0) ** 2) + 0.16 * np.exp(-((r - 120.0) / 28.0) ** 2)),
        ("mixed_weak", "MIXED", -0.12 * np.exp(-(r / 50.0) ** 2) + 0.10 * np.exp(-((r - 145.0) / 35.0) ** 2)),
    ]
    t_eval = np.arange(0.0, 241.0, 8.0, dtype=float)
    rows_curve: list[dict[str, Any]] = []
    rows_pred: list[dict[str, Any]] = []
    roots_ref: np.ndarray | None = None

    for label, cls, delta in synth_defs:
        roots, coeffs, _, _ = _bessel_decomposition(
            r_bins=r,
            delta_vals=delta,
            R_max=float(r_max_km),
            n_modes=int(n_bessel_modes),
            n_grid=200,
        )
        roots_ref = roots
        D_vals = predict_D_from_profile(coeffs, roots, float(k_synth), float(ds_synth), t_eval, R_max=float(r_max_km), n_r_eval=240)
        alpha, r2, n_fit = _fit_alpha_from_D_detail(D_vals, t_eval, t_start=float(t_start), t_end=float(t_end))
        delta_near = float(np.mean(delta[r <= 50.0]))
        rows_pred.append(
            {
                "profile_label": label,
                "profile_class": cls,
                "k": float(k_synth),
                "Ds": float(ds_synth),
                "alpha_predicted": float(alpha),
                "fit_r2": float(r2),
                "n_fit": int(n_fit),
                "delta_near": delta_near,
                "c0": float(coeffs[0]),
                "E_low_frac": float(np.sum(coeffs[:2] ** 2) / np.sum(coeffs**2)),
            }
        )
        for t, d in zip(t_eval, D_vals):
            rows_curve.append({"profile_label": label, "profile_class": cls, "t_hours": float(t), "D": float(d)})

    pred_df = pd.DataFrame(rows_pred).sort_values(["profile_class", "profile_label"], kind="stable").reset_index(drop=True)
    curve_df = pd.DataFrame(rows_curve).sort_values(["profile_label", "t_hours"], kind="stable").reset_index(drop=True)
    pred_df.to_csv(tables_dir / "analytic_predictions_synthetic.csv", index=False)
    curve_df.to_csv(tables_dir / "synthetic_D_curves.csv", index=False)

    _plot_synthetic_decay(curve_df, figures_dir / "synthetic_D_decay_comparison.png")
    if roots_ref is not None:
        _plot_mode_decay(roots_ref, k=float(k_synth), Ds=float(ds_synth), R_max=float(r_max_km), out_path=figures_dir / "mode_decay_schematic.png")


def _run_exp3(
    *,
    event_data: dict[str, EventData],
    tables_dir: Path,
    figures_dir: Path,
    r_max_km: float,
    k_grid_n: int,
    ds_grid_n: int,
    k_min: float,
    k_max: float,
    ds_min: float,
    ds_max: float,
    t_start: float,
    t_end: float,
) -> tuple[float, float, pd.DataFrame]:
    models: list[ProfileModel] = []
    for slug in sorted(event_data):
        ev = event_data[slug]
        model = ev.__dict__.get("_profile_model")
        if model is None:
            raise ValueError(f"{slug} 缺少 profile model（请先运行 Exp1）。")
        models.append(model)

    t_eval = np.arange(0.0, max(240.0, float(t_end) + 8.0), 8.0, dtype=float)
    k_grid = np.logspace(np.log10(float(k_min)), np.log10(float(k_max)), int(k_grid_n))
    ds_grid = np.logspace(np.log10(float(ds_min)), np.log10(float(ds_max)), int(ds_grid_n))

    param_grid = _estimate_global_params_grid(
        models,
        k_grid=k_grid,
        ds_grid=ds_grid,
        t_eval=t_eval,
        t_start=float(t_start),
        t_end=float(t_end),
    )
    param_grid.to_csv(tables_dir / "pde_param_grid.csv", index=False)

    best_df = _pick_best_rows(param_grid)
    best_s = best_df.loc[best_df["criterion"] == "max_spearman"].iloc[0]
    opt_row = _estimate_global_params_least_squares(
        models,
        t_eval=t_eval,
        t_start=float(t_start),
        t_end=float(t_end),
        k_min=float(k_min),
        k_max=float(k_max),
        ds_min=float(ds_min),
        ds_max=float(ds_max),
        k_init=float(best_s["k"]),
        ds_init=float(best_s["Ds"]),
    )
    best_df = pd.concat([best_df, pd.DataFrame([opt_row])], ignore_index=True)
    best_df.to_csv(tables_dir / "pde_optimal_params.csv", index=False)
    best_s = best_df.loc[best_df["criterion"] == "max_spearman"].iloc[0]
    k_best = float(best_s["k"])
    ds_best = float(best_s["Ds"])

    pred_rows: list[dict[str, Any]] = []
    for m in models:
        D_pred = _predict_D_from_model(m, k=k_best, Ds=ds_best, t_array=t_eval)
        alpha_pred, fit_r2, n_fit = _fit_alpha_from_D_detail(D_pred, t_eval, t_start=float(t_start), t_end=float(t_end))
        pred_rows.append(
            {
                "slug": m.meta.slug,
                "short_name": m.meta.short_name,
                "disaster_type": m.meta.disaster_type,
                "event_type": m.meta.event_type,
                "alpha_emp": float(m.meta.alpha),
                "alpha_pred": float(alpha_pred),
                "residual": float(alpha_pred - m.meta.alpha),
                "abs_error": float(abs(alpha_pred - m.meta.alpha)),
                "delta_near": float(m.meta.delta_near),
                "D_peak": float(m.meta.D_peak),
                "k_best": k_best,
                "Ds_best": ds_best,
                "fit_r2": float(fit_r2),
                "n_fit": int(n_fit),
            }
        )
    pred_df = pd.DataFrame(pred_rows).sort_values(["slug"], kind="stable").reset_index(drop=True)
    pred_df.to_csv(tables_dir / "pde_alpha_predictions.csv", index=False)

    loo_df = _loo_cross_validation(
        models,
        k_grid=k_grid,
        ds_grid=ds_grid,
        t_eval=t_eval,
        t_start=float(t_start),
        t_end=float(t_end),
    )
    loo_df.to_csv(tables_dir / "pde_loo_results.csv", index=False)

    _plot_param_heatmap(param_grid, k_values=k_grid, ds_values=ds_grid, out_path=figures_dir / "pde_param_heatmap.png")
    _plot_alpha_scatter(pred_df, figures_dir / "pde_alpha_scatter.png")

    models_map = {m.meta.slug: m for m in models}
    _plot_D_comparison_gallery(
        event_data=event_data,
        models_by_slug=models_map,
        k=k_best,
        Ds=ds_best,
        out_path=figures_dir / "pde_D_comparison_gallery.png",
    )
    return k_best, ds_best, pred_df


def _run_exp4(
    *,
    event_data: dict[str, EventData],
    pred_df: pd.DataFrame,
    tables_dir: Path,
    k_best: float,
    ds_best: float,
    t_start: float,
    t_end: float,
    n_bootstrap: int,
    seed: int,
) -> None:
    models: list[ProfileModel] = [event_data[s].__dict__["_profile_model"] for s in sorted(event_data)]
    t_eval = np.arange(0.0, max(240.0, float(t_end) + 8.0), 8.0, dtype=float)

    boot_df = _bootstrap_simulation(
        models,
        k=float(k_best),
        Ds=float(ds_best),
        t_eval=t_eval,
        t_start=float(t_start),
        t_end=float(t_end),
        n_iter=int(n_bootstrap),
        seed=int(seed),
    )
    boot_df.to_csv(tables_dir / "simulation_bootstrap.csv", index=False)

    shuffled = _counterfactual_shuffle(
        models,
        k=float(k_best),
        Ds=float(ds_best),
        t_eval=t_eval,
        t_start=float(t_start),
        t_end=float(t_end),
        n_iter=max(200, int(n_bootstrap)),
        seed=int(seed) + 17,
    )
    no_diff = _counterfactual_no_diffusion(
        models,
        k=float(k_best),
        t_eval=t_eval,
        t_start=float(t_start),
        t_end=float(t_end),
    )
    uniform = _counterfactual_uniform_profile(
        models,
        k=float(k_best),
        Ds=float(ds_best),
        t_eval=t_eval,
        t_start=float(t_start),
        t_end=float(t_end),
    )

    rho_emp, p_emp, n_emp = _spearman_pair(pred_df["alpha_emp"].to_numpy(dtype=float), pred_df["delta_near"].to_numpy(dtype=float))
    rho_model, p_model, n_model = _spearman_pair(pred_df["alpha_pred"].to_numpy(dtype=float), pred_df["delta_near"].to_numpy(dtype=float))
    rho_boot = boot_df["rho_alpha_pred_vs_delta_near"].to_numpy(dtype=float)

    cf_rows = [
        {"scenario": "observed_empirical", "rho": float(rho_emp), "p_value": float(p_emp), "n_events": int(n_emp), "note": "α_emp vs δ_near"},
        {"scenario": "pde_predicted", "rho": float(rho_model), "p_value": float(p_model), "n_events": int(n_model), "note": "α_pred vs δ_near"},
        {
            "scenario": "bootstrap_profile_perturbation",
            "rho": float(np.mean(rho_boot)),
            "p_value": float("nan"),
            "n_events": int(len(models)),
            "note": f"95%CI=[{np.quantile(rho_boot,0.025):.3f},{np.quantile(rho_boot,0.975):.3f}]",
        },
        {
            "scenario": "counterfactual_shuffle_profiles",
            "rho": float(shuffled["rho_mean"]),
            "p_value": float("nan"),
            "n_events": int(len(models)),
            "note": f"95%CI=[{shuffled['rho_ci_low']:.3f},{shuffled['rho_ci_high']:.3f}], n_iter={int(shuffled['n_iter'])}",
        },
        {
            "scenario": "counterfactual_no_diffusion_Ds0",
            "rho": float(no_diff["rho"]),
            "p_value": float(no_diff["p_value"]),
            "n_events": int(no_diff["n_events"]),
            "note": "Ds=0",
        },
        {
            "scenario": "counterfactual_uniform_profile_only_c0",
            "rho": float(uniform["rho"]),
            "p_value": float(uniform["p_value"]),
            "n_events": int(uniform["n_events"]),
            "note": "仅保留 c0",
        },
    ]
    counterfactual_df = pd.DataFrame(cf_rows)
    counterfactual_df.to_csv(tables_dir / "counterfactual_results.csv", index=False)

    langevin_path = Path("outputs/cross_disaster_comparison/dynamics_potential_routeB_nonparam_exp3/tables/langevin_param_correlation.csv")
    lang_rho = float("nan")
    lang_p = float("nan")
    if langevin_path.exists():
        lang = pd.read_csv(langevin_path)
        row = lang.loc[lang["test"] == "k_ratio_vs_delta_near"]
        if not row.empty:
            lang_rho = _safe_float(row.iloc[0].get("spearman_rho")) or float("nan")
            lang_p = _safe_float(row.iloc[0].get("spearman_p")) or float("nan")

    comparison_rows = [
        {"metric": "rho(alpha_pred, alpha_emp)", "langevin": float("nan"), "diffusion_relaxation": float(rho_model)},
        {"metric": "rho(param_or_alpha, delta_near)", "langevin": float(lang_rho), "diffusion_relaxation": float(rho_model)},
        {
            "metric": "bootstrap_rho(alpha,delta_near)_95ci",
            "langevin": float("nan"),
            "diffusion_relaxation": f"[{np.quantile(rho_boot,0.025):.3f}, {np.quantile(rho_boot,0.975):.3f}]",
        },
        {"metric": "counterfactual_Ds0_rho", "langevin": float("nan"), "diffusion_relaxation": float(no_diff["rho"])},
        {"metric": "global_param_count", "langevin": ">=2 per event", "diffusion_relaxation": "2 global"},
    ]
    pd.DataFrame(comparison_rows).to_csv(tables_dir / "langevin_vs_pde_comparison.csv", index=False)


def run(
    *,
    output_root: Path,
    dt_tables_dir: Path,
    out_dir: Path,
    use_route_b_selected: bool = True,
    r_max_km: float = 200.0,
    min_tiles_overlap: int = 3,
    n_bessel_modes: int = 10,
    daily_average_if_high_freq: bool = True,
    high_freq_thresh_h: float = 16.0,
    k_grid_n: int = 30,
    ds_grid_n: int = 30,
    k_min: float = 1e-4,
    k_max: float = 1.0,
    ds_min: float = 1e-2,
    ds_max: float = 1e3,
    t_start: float = 24.0,
    t_end: float = 120.0,
    n_bootstrap: int = 500,
    seed: int = 42,
    run_until: int = 4,
    k_synth: float = 0.02,
    ds_synth: float = 30.0,
) -> None:
    out_dir = Path(out_dir)
    tables_dir = out_dir / "tables"
    figures_dir = out_dir / "figures"
    _ensure_dir(out_dir)
    _ensure_dir(tables_dir)
    _ensure_dir(figures_dir)

    events = _load_route_b_events(dt_tables_dir=Path(dt_tables_dir), use_route_b_selected=bool(use_route_b_selected))
    event_data, radial_df, _, diag_df = _run_exp0(
        events=events,
        output_root=Path(output_root),
        tables_dir=tables_dir,
        r_max_km=float(r_max_km),
        min_tiles_overlap=int(min_tiles_overlap),
        daily_average_if_high_freq=bool(daily_average_if_high_freq),
        high_freq_thresh_h=float(high_freq_thresh_h),
    )

    if int(run_until) <= 0:
        raise ValueError("run_until 必须在 [1,4]。")
    if int(run_until) >= 1:
        _run_exp1(
            event_data=event_data,
            tables_dir=tables_dir,
            figures_dir=figures_dir,
            r_max_km=float(r_max_km),
            n_bessel_modes=int(n_bessel_modes),
        )

    if int(run_until) >= 2:
        _run_exp2(
            tables_dir=tables_dir,
            figures_dir=figures_dir,
            r_max_km=float(r_max_km),
            n_bessel_modes=int(n_bessel_modes),
            t_start=float(t_start),
            t_end=float(t_end),
            k_synth=float(k_synth),
            ds_synth=float(ds_synth),
        )

    k_best = float("nan")
    ds_best = float("nan")
    pred_df = pd.DataFrame()
    if int(run_until) >= 3:
        k_best, ds_best, pred_df = _run_exp3(
            event_data=event_data,
            tables_dir=tables_dir,
            figures_dir=figures_dir,
            r_max_km=float(r_max_km),
            k_grid_n=int(k_grid_n),
            ds_grid_n=int(ds_grid_n),
            k_min=float(k_min),
            k_max=float(k_max),
            ds_min=float(ds_min),
            ds_max=float(ds_max),
            t_start=float(t_start),
            t_end=float(t_end),
        )

    if int(run_until) >= 4:
        if pred_df.empty or not np.isfinite(k_best) or not np.isfinite(ds_best):
            raise ValueError("Exp4 需要先完成 Exp3 并得到最优参数。")
        _run_exp4(
            event_data=event_data,
            pred_df=pred_df,
            tables_dir=tables_dir,
            k_best=float(k_best),
            ds_best=float(ds_best),
            t_start=float(t_start),
            t_end=float(t_end),
            n_bootstrap=int(n_bootstrap),
            seed=int(seed),
        )

    metadata = {
        "output_root": str(Path(output_root)),
        "dt_tables_dir": str(Path(dt_tables_dir)),
        "out_dir": str(out_dir),
        "n_events": int(len(events)),
        "events": [e.slug for e in events],
        "use_route_b_selected": bool(use_route_b_selected),
        "run_until": int(run_until),
        "r_max_km": float(r_max_km),
        "min_tiles_overlap": int(min_tiles_overlap),
        "n_bessel_modes": int(n_bessel_modes),
        "daily_average_if_high_freq": bool(daily_average_if_high_freq),
        "high_freq_thresh_h": float(high_freq_thresh_h),
        "k_grid_n": int(k_grid_n),
        "ds_grid_n": int(ds_grid_n),
        "k_min": float(k_min),
        "k_max": float(k_max),
        "ds_min": float(ds_min),
        "ds_max": float(ds_max),
        "t_start": float(t_start),
        "t_end": float(t_end),
        "n_bootstrap": int(n_bootstrap),
        "seed": int(seed),
        "k_synth": float(k_synth),
        "ds_synth": float(ds_synth),
        "exp0_profile_rows": int(radial_df.shape[0]),
        "exp0_event_diag_rows": int(diag_df.shape[0]),
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_readme(out_dir)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Direction C：空间扩散-弛豫框架（Exp0-Exp4）")
    p.add_argument("--output-root", type=str, default="outputs")
    p.add_argument("--dt-tables-dir", type=str, default="outputs/cross_disaster_comparison/Dt_decay/tables")
    p.add_argument("--out-dir", type=str, default="outputs/cross_disaster_comparison/spatial_diffusion_results")
    p.add_argument("--use-route-b-selected", type=int, choices=[0, 1], default=1)

    p.add_argument("--r-max-km", type=float, default=200.0)
    p.add_argument("--min-tiles-overlap", type=int, default=3)
    p.add_argument("--n-bessel-modes", type=int, default=10)
    p.add_argument("--daily-average-if-high-freq", type=int, choices=[0, 1], default=1)
    p.add_argument("--high-freq-thresh-h", type=float, default=16.0)

    p.add_argument("--k-grid-n", type=int, default=30)
    p.add_argument("--ds-grid-n", type=int, default=30)
    p.add_argument("--k-min", type=float, default=1e-4)
    p.add_argument("--k-max", type=float, default=1.0)
    p.add_argument("--ds-min", type=float, default=1e-2)
    p.add_argument("--ds-max", type=float, default=1e3)

    p.add_argument("--t-start", type=float, default=24.0)
    p.add_argument("--t-end", type=float, default=120.0)
    p.add_argument("--n-bootstrap", type=int, default=500)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--run-until", type=int, choices=[1, 2, 3, 4], default=4)

    p.add_argument("--k-synth", type=float, default=0.02)
    p.add_argument("--ds-synth", type=float, default=30.0)
    return p


def cli_main() -> None:
    args = build_arg_parser().parse_args()
    run(
        output_root=Path(args.output_root),
        dt_tables_dir=Path(args.dt_tables_dir),
        out_dir=Path(args.out_dir),
        use_route_b_selected=bool(args.use_route_b_selected),
        r_max_km=float(args.r_max_km),
        min_tiles_overlap=int(args.min_tiles_overlap),
        n_bessel_modes=int(args.n_bessel_modes),
        daily_average_if_high_freq=bool(args.daily_average_if_high_freq),
        high_freq_thresh_h=float(args.high_freq_thresh_h),
        k_grid_n=int(args.k_grid_n),
        ds_grid_n=int(args.ds_grid_n),
        k_min=float(args.k_min),
        k_max=float(args.k_max),
        ds_min=float(args.ds_min),
        ds_max=float(args.ds_max),
        t_start=float(args.t_start),
        t_end=float(args.t_end),
        n_bootstrap=int(args.n_bootstrap),
        seed=int(args.seed),
        run_until=int(args.run_until),
        k_synth=float(args.k_synth),
        ds_synth=float(args.ds_synth),
    )
