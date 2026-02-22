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
    from scipy.stats import pearsonr, spearmanr
except ModuleNotFoundError as e:
    raise ModuleNotFoundError("缺少依赖：scipy。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.cross_disaster_phi_tau import DisasterSpec, auto_t0_and_center, load_catalog
from disaster.geo import haversine_km
from disaster.movement_io import load_movement_file
from disaster.plot_style import FIGSIZE_FULL, OKABE_ITO, apply_paper_style, save_figure
from disaster.population_io import parse_window_start_pt, resolve_subdir


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


@dataclass(frozen=True)
class WindowRef:
    path: Path
    window_start_pt: pd.Timestamp
    hours_since_peak: float


@dataclass
class EventPrepared:
    meta: EventMeta
    spec: DisasterSpec
    t0_pt: pd.Timestamp
    t_peak_pt: pd.Timestamp
    center_lat: float
    center_lon: float
    center_source: str
    movement_windows: list[WindowRef]


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


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    if s.lower() == "nan":
        return ""
    return s


def _to_bool_series(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s.copy()
    return s.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y"})


def _load_route_b_events(dt_tables_dir: Path, *, use_route_b_selected: bool) -> list[EventMeta]:
    p = Path(dt_tables_dir) / "Dt_routeB_sample_flags.csv"
    if not p.exists():
        raise FileNotFoundError(f"未找到：{p}")
    df = pd.read_csv(p)
    required = [
        "slug",
        "short_name",
        "disaster_type",
        "event_type",
        "t_peak_hours",
        "D_peak",
        "near_delta_peak_windows_mean",
        "alpha",
    ]
    miss = [c for c in required if c not in df.columns]
    if miss:
        raise ValueError(f"{p} 缺少列：{miss}")
    if use_route_b_selected:
        if "route_b_selected" not in df.columns:
            raise ValueError(f"{p} 缺少 route_b_selected 列，无法保证口径一致。")
        df = df.loc[_to_bool_series(df["route_b_selected"])].copy()
    if df.empty:
        raise ValueError("Route B 事件为空。")

    rows: list[EventMeta] = []
    bad: list[str] = []
    for _, r in df.iterrows():
        slug = _safe_str(r.get("slug"))
        if not slug:
            continue
        t_peak = _safe_float(r.get("t_peak_hours"))
        D_peak = _safe_float(r.get("D_peak"))
        delta_near = _safe_float(r.get("near_delta_peak_windows_mean"))
        alpha = _safe_float(r.get("alpha"))
        if t_peak is None or D_peak is None or delta_near is None or alpha is None:
            bad.append(slug)
            continue
        rows.append(
            EventMeta(
                slug=slug,
                short_name=_safe_str(r.get("short_name")) or slug[:24],
                disaster_type=_safe_str(r.get("disaster_type")),
                event_type=_safe_str(r.get("event_type")),
                t_peak_hours=float(t_peak),
                D_peak=float(D_peak),
                delta_near=float(delta_near),
                alpha=float(alpha),
            )
        )
    if bad:
        raise ValueError(f"以下事件缺失 t_peak/D_peak/delta_near/alpha：{sorted(bad)}")
    return sorted(rows, key=lambda x: x.slug)


def _resolve_specs(catalog_path: Path) -> dict[str, DisasterSpec]:
    specs = load_catalog(Path(catalog_path))
    out = {s.slug: s for s in specs}
    dup = [k for k, v in pd.Series([s.slug for s in specs]).value_counts().items() if v > 1]
    if dup:
        raise ValueError(f"catalog slug 重复：{dup}")
    return out


def _resolve_track_path(spec: DisasterSpec, catalog_path: Path) -> Path | None:
    if spec.center_track_csv is None:
        return None
    p = Path(spec.center_track_csv)
    if p.exists():
        return p
    p2 = Path(catalog_path).parent / p
    if p2.exists():
        return p2
    return None


def _load_track_points(spec: DisasterSpec, catalog_path: Path) -> pd.DataFrame | None:
    p = _resolve_track_path(spec, catalog_path)
    if p is None:
        return None
    df = pd.read_csv(p)
    need = {"datetime_utc", "lat", "lon"}
    if not need.issubset(df.columns):
        raise ValueError(f"track CSV 缺少列：{sorted(need - set(df.columns))}（{p}）")

    if "storm_name" in df.columns and spec.center_track_storm_name:
        want = str(spec.center_track_storm_name).strip().lower()
        df = df[df["storm_name"].astype(str).str.strip().str.lower() == want].copy()
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True, errors="coerce")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["datetime_utc", "lat", "lon"]).copy()
    if df.empty:
        return None
    df["datetime_local"] = df["datetime_utc"].dt.tz_convert(str(spec.center_track_to_tz)).dt.tz_localize(None)
    df = df.sort_values("datetime_local", kind="stable").reset_index(drop=True)
    return df


def _center_at_peak_from_track(track_df: pd.DataFrame, t_peak_pt: pd.Timestamp, *, allow_extrapolation: bool) -> tuple[float, float]:
    t = pd.to_datetime(track_df["datetime_local"]).astype("int64").to_numpy(dtype=np.int64)
    lat = pd.to_numeric(track_df["lat"], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(track_df["lon"], errors="coerce").to_numpy(dtype=float)
    x = np.int64(pd.Timestamp(t_peak_pt).value)
    if t.size < 2:
        raise ValueError("track 点不足（<2），无法插值中心。")
    t_min = int(np.min(t))
    t_max = int(np.max(t))
    if (x < t_min or x > t_max) and (not allow_extrapolation):
        raise ValueError(
            f"t_peak={pd.Timestamp(t_peak_pt)} 超出 track 时间范围 "
            f"[{pd.to_datetime(t_min)}, {pd.to_datetime(t_max)}]，且未允许外推。"
        )
    lat_c = float(np.interp(x, t, lat, left=float(lat[0]), right=float(lat[-1])))
    lon_c = float(np.interp(x, t, lon, left=float(lon[0]), right=float(lon[-1])))
    return lat_c, lon_c


def _list_movement_windows(data_root: Path) -> list[tuple[pd.Timestamp, Path]]:
    mov_dir = resolve_subdir(data_root, "movement")
    files = sorted(mov_dir.glob("*.csv"))
    rows: list[tuple[pd.Timestamp, Path]] = []
    for p in files:
        ts = parse_window_start_pt(p)
        rows.append((pd.Timestamp(ts), p))
    rows = sorted(rows, key=lambda x: x[0])
    return rows


def _dxdy_km(lat0: np.ndarray, lon0: np.ndarray, lat1: np.ndarray, lon1: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    latm = np.radians((lat0 + lat1) / 2.0)
    dx = (lon1 - lon0) * 111.320 * np.cos(latm)
    dy = (lat1 - lat0) * 110.574
    return dx, dy


def _weighted_percentile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    x = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    mask = np.isfinite(x) & np.isfinite(w) & (w > 0)
    x = x[mask]
    w = w[mask]
    if x.size == 0:
        return float("nan")
    order = np.argsort(x)
    x = x[order]
    w = w[order]
    cdf = np.cumsum(w) / float(np.sum(w))
    qq = float(np.clip(q, 0.0, 100.0)) / 100.0
    idx = int(np.searchsorted(cdf, qq, side="left"))
    idx = int(np.clip(idx, 0, x.size - 1))
    return float(x[idx])


def _circular_resultant(theta: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    ang = np.asarray(theta, dtype=float)
    ww = np.asarray(w, dtype=float)
    mask = np.isfinite(ang) & np.isfinite(ww) & (ww > 0)
    ang = ang[mask]
    ww = ww[mask]
    if ang.size == 0:
        return float("nan"), float("nan")
    c = float(np.sum(ww * np.cos(ang)))
    s = float(np.sum(ww * np.sin(ang)))
    wsum = float(np.sum(ww))
    if wsum <= 0:
        return float("nan"), float("nan")
    r_bar = float(np.sqrt(c * c + s * s) / wsum)
    theta_mean = float(np.arctan2(s, c))
    return theta_mean, r_bar


def _partial_spearman(x: np.ndarray, y: np.ndarray, controls: np.ndarray) -> tuple[float, float, int]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(controls, dtype=float)
    if z.ndim == 1:
        z = z.reshape(-1, 1)
    ok = np.isfinite(x) & np.isfinite(y) & np.all(np.isfinite(z), axis=1)
    if np.sum(ok) < z.shape[1] + 3:
        return float("nan"), float("nan"), int(np.sum(ok))

    x = x[ok]
    y = y[ok]
    z = z[ok]
    rx = pd.Series(x).rank(method="average").to_numpy(dtype=float)
    ry = pd.Series(y).rank(method="average").to_numpy(dtype=float)
    rz = np.column_stack([pd.Series(z[:, i]).rank(method="average").to_numpy(dtype=float) for i in range(z.shape[1])])
    X = np.column_stack([np.ones(rx.shape[0], dtype=float), rz])
    bx, *_ = np.linalg.lstsq(X, rx, rcond=None)
    by, *_ = np.linalg.lstsq(X, ry, rcond=None)
    ex = rx - X @ bx
    ey = ry - X @ by
    if np.std(ex) < 1e-12 or np.std(ey) < 1e-12:
        return float("nan"), float("nan"), int(rx.shape[0])
    r, p = pearsonr(ex, ey)
    return float(r), float(p), int(rx.shape[0])


def _spearman_pair(x: np.ndarray, y: np.ndarray) -> tuple[float, float, int]:
    xx = np.asarray(x, dtype=float)
    yy = np.asarray(y, dtype=float)
    ok = np.isfinite(xx) & np.isfinite(yy)
    n = int(np.sum(ok))
    if n < 3:
        return float("nan"), float("nan"), n
    rho, p = spearmanr(xx[ok], yy[ok], nan_policy="omit")
    return float(rho), float(p), n


def _fit_alpha_return(ts_h: np.ndarray, r_vals: np.ndarray, *, fit_min_h: float, fit_max_h: float) -> tuple[float, float, int]:
    t = np.asarray(ts_h, dtype=float)
    r = np.asarray(r_vals, dtype=float)
    ok = np.isfinite(t) & np.isfinite(r) & (t > 0) & (r > 0) & (t >= float(fit_min_h)) & (t <= float(fit_max_h))
    if int(np.sum(ok)) < 3:
        return float("nan"), float("nan"), int(np.sum(ok))
    lx = np.log(t[ok])
    ly = np.log(r[ok])
    slope, intercept = np.polyfit(lx, ly, 1)
    yhat = slope * lx + intercept
    ss_res = float(np.sum((ly - yhat) ** 2))
    ss_tot = float(np.sum((ly - np.mean(ly)) ** 2))
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 1e-12 else float("nan")
    alpha = float(-slope)
    return alpha, r2, int(np.sum(ok))


def _load_window_enriched(path: Path, *, center_lat: float, center_lon: float) -> pd.DataFrame:
    df = load_movement_file(path)
    need = {"start_lat", "start_lon", "end_lat", "end_lon", "n_baseline", "n_crisis", "n_difference", "length_km"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise ValueError(f"{path} 缺少列：{miss}")
    for c in ["start_lat", "start_lon", "end_lat", "end_lon", "n_baseline", "n_crisis", "n_difference", "length_km"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["start_lat", "start_lon", "end_lat", "end_lon", "n_difference", "n_baseline", "n_crisis", "length_km"]).copy()
    if df.empty:
        return df

    df["start_dist_km"] = haversine_km(df["start_lat"].to_numpy(dtype=float), df["start_lon"].to_numpy(dtype=float), float(center_lat), float(center_lon))
    df["end_dist_km"] = haversine_km(df["end_lat"].to_numpy(dtype=float), df["end_lon"].to_numpy(dtype=float), float(center_lat), float(center_lon))
    df["w_abs"] = np.abs(df["n_difference"].to_numpy(dtype=float))

    dx_flow, dy_flow = _dxdy_km(
        df["start_lat"].to_numpy(dtype=float),
        df["start_lon"].to_numpy(dtype=float),
        df["end_lat"].to_numpy(dtype=float),
        df["end_lon"].to_numpy(dtype=float),
    )
    dx_rad, dy_rad = _dxdy_km(
        np.full(len(df), float(center_lat), dtype=float),
        np.full(len(df), float(center_lon), dtype=float),
        df["start_lat"].to_numpy(dtype=float),
        df["start_lon"].to_numpy(dtype=float),
    )
    theta_flow = np.arctan2(dy_flow, dx_flow)
    theta_rad = np.arctan2(dy_rad, dx_rad)
    radial_norm = np.sqrt(dx_rad**2 + dy_rad**2)
    cos_align = np.cos(theta_flow - theta_rad)
    cos_align[radial_norm < 1e-6] = np.nan
    df["theta_flow"] = theta_flow
    df["theta_radial"] = theta_rad
    df["cos_alignment"] = cos_align
    return df


def _prepare_events(
    *,
    route_b_events: list[EventMeta],
    spec_map: dict[str, DisasterSpec],
    catalog_path: Path,
    peak_window_hours: float,
    use_track_center_at_peak: bool,
    allow_track_extrapolation: bool,
    require_all_events: bool,
) -> tuple[list[EventPrepared], pd.DataFrame, list[str]]:
    prepared: list[EventPrepared] = []
    avail_rows: list[dict[str, Any]] = []
    missing: list[str] = []

    for meta in route_b_events:
        row: dict[str, Any] = {
            "slug": meta.slug,
            "short_name": meta.short_name,
            "has_catalog": 0,
            "has_movement": 0,
            "n_timesteps": 0,
            "date_min": "",
            "date_max": "",
            "t0_pt": "",
            "t_peak_pt": "",
            "center_lat": np.nan,
            "center_lon": np.nan,
            "center_source": "",
            "t0_method": "",
            "center_method": "",
            "t0_snap_delta_hours": np.nan,
            "track_anchor_ok": np.nan,
            "warning_flags": "",
            "note": "",
        }
        spec = spec_map.get(meta.slug)
        if spec is None:
            row["note"] = "catalog_missing"
            avail_rows.append(row)
            missing.append(meta.slug)
            continue
        row["has_catalog"] = 1

        try:
            t0_pt, c_lat, c_lon, auto_meta = auto_t0_and_center(spec)
        except Exception as e:
            row["note"] = f"auto_t0_and_center_failed:{type(e).__name__}:{e}"
            avail_rows.append(row)
            missing.append(meta.slug)
            continue

        t0_pt = pd.Timestamp(t0_pt)
        t_peak_pt = t0_pt + pd.to_timedelta(float(meta.t_peak_hours), unit="h")
        center_lat = float(c_lat)
        center_lon = float(c_lon)
        center_source = "static_or_auto"
        t0_method = str(auto_meta.get("t0_method", ""))
        center_method = str(auto_meta.get("center_method", ""))
        t0_snap_delta_hours = auto_meta.get("t0_snap_delta_hours", np.nan)
        track_anchor_ok = auto_meta.get("track_anchor_ok", np.nan)
        warning_flags: list[str] = []
        if t0_method == "auto_first_population_window":
            warning_flags.append("t0_auto_first_window")
        try:
            td = float(t0_snap_delta_hours)
            if np.isfinite(td) and td > 12.0:
                warning_flags.append("t0_snap_delta_gt12h")
        except Exception:
            pass
        if center_method.startswith("auto_"):
            warning_flags.append("center_auto_estimated")

        if use_track_center_at_peak:
            try:
                track_df = _load_track_points(spec, catalog_path)
                if track_df is not None and not track_df.empty:
                    center_lat, center_lon = _center_at_peak_from_track(
                        track_df,
                        t_peak_pt=pd.Timestamp(t_peak_pt),
                        allow_extrapolation=bool(allow_track_extrapolation),
                    )
                    center_source = "track_at_t_peak"
            except Exception as e:
                row["note"] = f"track_center_failed:{type(e).__name__}:{e}"
                avail_rows.append(row)
                missing.append(meta.slug)
                continue

        try:
            windows_raw = _list_movement_windows(spec.data_root)
        except Exception as e:
            row["note"] = f"movement_unavailable:{type(e).__name__}:{e}"
            avail_rows.append(row)
            missing.append(meta.slug)
            continue

        windows = [
            WindowRef(path=p, window_start_pt=ts, hours_since_peak=float((pd.Timestamp(ts) - pd.Timestamp(t_peak_pt)).total_seconds() / 3600.0))
            for ts, p in windows_raw
        ]
        if not windows:
            row["note"] = "movement_empty"
            avail_rows.append(row)
            missing.append(meta.slug)
            continue

        row.update(
            {
                "has_movement": 1,
                "n_timesteps": int(len(windows)),
                "date_min": str(windows[0].window_start_pt),
                "date_max": str(windows[-1].window_start_pt),
                "t0_pt": str(t0_pt),
                "t_peak_pt": str(t_peak_pt),
                "center_lat": float(center_lat),
                "center_lon": float(center_lon),
                "center_source": center_source,
                "t0_method": t0_method,
                "center_method": center_method,
                "t0_snap_delta_hours": t0_snap_delta_hours,
                "track_anchor_ok": track_anchor_ok,
                "warning_flags": "|".join(warning_flags),
                "note": "ok",
            }
        )
        prepared.append(
            EventPrepared(
                meta=meta,
                spec=spec,
                t0_pt=pd.Timestamp(t0_pt),
                t_peak_pt=pd.Timestamp(t_peak_pt),
                center_lat=float(center_lat),
                center_lon=float(center_lon),
                center_source=center_source,
                movement_windows=windows,
            )
        )
        avail_rows.append(row)

    avail_df = pd.DataFrame(avail_rows).sort_values("slug", kind="stable").reset_index(drop=True)
    return prepared, avail_df, sorted(missing)


def _aggregate_event_metrics(
    event: EventPrepared,
    *,
    peak_window_hours: float,
    near_km: float,
    far_km: float,
    long_distance_km: float,
    return_fit_min_h: float,
    return_fit_max_h: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    windows = event.movement_windows
    if not windows:
        raise ValueError(f"{event.meta.slug} 无 movement 窗口。")

    peak_set = [w for w in windows if abs(float(w.hours_since_peak)) <= float(peak_window_hours)]
    struct_set = sorted(peak_set if peak_set else windows, key=lambda w: abs(float(w.hours_since_peak)))[:3]
    nearest_peak = min(windows, key=lambda w: abs(float(w.hours_since_peak)))
    post_set = [w for w in windows if float(w.hours_since_peak) > 0]

    F_total_acc = 0.0
    F_out_near_acc = 0.0
    F_in_far_acc = 0.0
    F_long_acc = 0.0
    F_out_near_pos_acc = 0.0

    angles: list[np.ndarray] = []
    angle_w: list[np.ndarray] = []
    align_vals: list[np.ndarray] = []
    align_w: list[np.ndarray] = []
    evac_dest_flow: dict[str, float] = {}
    evac_lengths: list[np.ndarray] = []
    evac_w: list[np.ndarray] = []

    # Exp-M1/M2: peak 周边窗口
    for w in peak_set:
        df = _load_window_enriched(w.path, center_lat=event.center_lat, center_lon=event.center_lon)
        if df.empty:
            continue
        start_near = df["start_dist_km"] < float(near_km)
        end_near = df["end_dist_km"] < float(near_km)
        start_far = (df["start_dist_km"] >= float(near_km)) & (df["start_dist_km"] <= float(far_km))
        end_far = (df["end_dist_km"] >= float(near_km)) & (df["end_dist_km"] <= float(far_km))

        n_diff = df["n_difference"].to_numpy(dtype=float)
        w_abs = df["w_abs"].to_numpy(dtype=float)
        F_total_acc += float(np.nansum(w_abs))
        F_out_near_acc += float(np.nansum(n_diff[start_near & end_far]))
        F_in_far_acc += float(np.nansum(n_diff[start_far & end_near]))
        F_long_acc += float(np.nansum(n_diff[df["length_km"].to_numpy(dtype=float) > float(long_distance_km)]))
        F_out_near_pos_acc += float(np.nansum(np.maximum(n_diff[start_near & end_far], 0.0)))

    for w in struct_set:
        df = _load_window_enriched(w.path, center_lat=event.center_lat, center_lon=event.center_lon)
        if df.empty:
            continue
        start_near = df["start_dist_km"] < float(near_km)
        end_far = (df["end_dist_km"] >= float(near_km)) & (df["end_dist_km"] <= float(far_km))
        n_diff = df["n_difference"].to_numpy(dtype=float)
        w_abs = df["w_abs"].to_numpy(dtype=float)

        mask_dir = start_near & np.isfinite(df["theta_flow"].to_numpy(dtype=float)) & (w_abs > 0)
        if np.any(mask_dir):
            angles.append(df.loc[mask_dir, "theta_flow"].to_numpy(dtype=float))
            angle_w.append(w_abs[mask_dir.to_numpy(dtype=bool)])

        mask_align = start_near & np.isfinite(df["cos_alignment"].to_numpy(dtype=float)) & (w_abs > 0)
        if np.any(mask_align):
            align_vals.append(df.loc[mask_align, "cos_alignment"].to_numpy(dtype=float))
            align_w.append(w_abs[mask_align.to_numpy(dtype=bool)])

        mask_evac = start_near & end_far & (n_diff > 0)
        if np.any(mask_evac):
            evac = df.loc[mask_evac, ["end_quadkey", "length_km", "n_difference"]].copy()
            evac["flow"] = pd.to_numeric(evac["n_difference"], errors="coerce")
            g = evac.groupby("end_quadkey", observed=True)["flow"].sum()
            for k, v in g.items():
                key = str(k)
                evac_dest_flow[key] = evac_dest_flow.get(key, 0.0) + float(v)
            evac_lengths.append(evac["length_km"].to_numpy(dtype=float))
            evac_w.append(evac["flow"].to_numpy(dtype=float))

    theta_mean = float("nan")
    R_bar = float("nan")
    if angles:
        ang = np.concatenate(angles)
        ww = np.concatenate(angle_w)
        theta_mean, R_bar = _circular_resultant(ang, ww)

    cos_alignment = float("nan")
    if align_vals:
        a = np.concatenate(align_vals)
        ww = np.concatenate(align_w)
        mask = np.isfinite(a) & np.isfinite(ww) & (ww > 0)
        if np.any(mask):
            cos_alignment = float(np.sum(a[mask] * ww[mask]) / np.sum(ww[mask]))

    HHI_dest = float("nan")
    if evac_dest_flow:
        x = np.array(list(evac_dest_flow.values()), dtype=float)
        x = x[np.isfinite(x) & (x > 0)]
        if x.size > 0:
            s = float(np.sum(x))
            p = x / s
            HHI_dest = float(np.sum(p * p))

    d_median = float("nan")
    d_p90 = float("nan")
    if evac_lengths:
        lens = np.concatenate(evac_lengths)
        ww = np.concatenate(evac_w)
        d_median = _weighted_percentile(lens, ww, 50.0)
        d_p90 = _weighted_percentile(lens, ww, 90.0)

    # Exp-M3: 回流时间序列
    return_rows: list[dict[str, Any]] = []
    has_peak_window = len(peak_set) > 0
    F_total = float(F_total_acc) if has_peak_window else float("nan")
    F_out_near = float(F_out_near_acc) if has_peak_window else float("nan")
    F_in_far = float(F_in_far_acc) if has_peak_window else float("nan")
    F_long = float(F_long_acc) if has_peak_window else float("nan")
    denom = float(F_out_near_pos_acc) if has_peak_window else float("nan")
    for w in post_set:
        df = _load_window_enriched(w.path, center_lat=event.center_lat, center_lon=event.center_lon)
        if df.empty:
            continue
        start_far = (df["start_dist_km"] >= float(near_km)) & (df["start_dist_km"] <= float(far_km))
        end_near = df["end_dist_km"] < float(near_km)
        mask_ret = start_far & end_near & (df["n_difference"] > 0)
        ret_flow = float(np.nansum(df.loc[mask_ret, "n_difference"].to_numpy(dtype=float)))
        ratio = float(ret_flow / denom) if np.isfinite(denom) and denom > 1e-12 else float("nan")
        return_rows.append(
            {
                "slug": event.meta.slug,
                "short_name": event.meta.short_name,
                "window_start_pt": pd.Timestamp(w.window_start_pt),
                "hours_since_peak": float(w.hours_since_peak),
                "return_flow": ret_flow,
                "R_return": ratio,
                "denominator_F_out_near_pos": denom,
                "n_vectors_return": int(np.sum(mask_ret.to_numpy(dtype=bool))),
            }
        )
    return_cols = [
        "slug",
        "short_name",
        "window_start_pt",
        "hours_since_peak",
        "return_flow",
        "R_return",
        "denominator_F_out_near_pos",
        "n_vectors_return",
    ]
    if return_rows:
        return_df = pd.DataFrame(return_rows).sort_values("hours_since_peak", kind="stable").reset_index(drop=True)
    else:
        return_df = pd.DataFrame(columns=return_cols)
    alpha_return = float("nan")
    alpha_return_r2 = float("nan")
    alpha_return_n = 0
    if not return_df.empty:
        a, r2, nfit = _fit_alpha_return(
            return_df["hours_since_peak"].to_numpy(dtype=float),
            return_df["R_return"].to_numpy(dtype=float),
            fit_min_h=float(return_fit_min_h),
            fit_max_h=float(return_fit_max_h),
        )
        alpha_return = float(a)
        alpha_return_r2 = float(r2)
        alpha_return_n = int(nfit)

    # Exp-M4: 原地不动比例（最近峰值窗口）
    peak_df = _load_window_enriched(nearest_peak.path, center_lat=event.center_lat, center_lon=event.center_lon)
    stay_put_ratio_peak = float("nan")
    if not peak_df.empty and {"start_quadkey", "end_quadkey"} <= set(peak_df.columns):
        mask_stay = (
            (peak_df["start_quadkey"].astype(str) == peak_df["end_quadkey"].astype(str))
            & (peak_df["start_dist_km"] < float(near_km))
        )
        num = float(np.nansum(peak_df.loc[mask_stay, "n_crisis"].to_numpy(dtype=float)))
        den = float(np.nansum(peak_df.loc[mask_stay, "n_baseline"].to_numpy(dtype=float)))
        if den > 1e-12:
            stay_put_ratio_peak = float(num / den)

    row = {
        "slug": event.meta.slug,
        "short_name": event.meta.short_name,
        "disaster_type": event.meta.disaster_type,
        "event_type": event.meta.event_type,
        "alpha": float(event.meta.alpha),
        "delta_near": float(event.meta.delta_near),
        "D_peak": float(event.meta.D_peak),
        "t_peak_hours": float(event.meta.t_peak_hours),
        "t_peak_pt": str(event.t_peak_pt),
        "center_lat": float(event.center_lat),
        "center_lon": float(event.center_lon),
        "center_source": str(event.center_source),
        "n_windows_total": int(len(windows)),
        "n_windows_peak_pm": int(len(peak_set)),
        "n_windows_struct": int(len(struct_set)),
        "n_windows_post": int(len(post_set)),
        "has_peak_window": int(has_peak_window),
        "F_total": float(F_total),
        "F_out_near": float(F_out_near),
        "F_in_far": float(F_in_far),
        "F_long": float(F_long),
        "R_bar": float(R_bar),
        "theta_mean": float(theta_mean),
        "cos_alignment": float(cos_alignment),
        "HHI_dest": float(HHI_dest),
        "d_median": float(d_median),
        "d_p90": float(d_p90),
        "alpha_return": float(alpha_return),
        "alpha_return_r2": float(alpha_return_r2),
        "alpha_return_n": int(alpha_return_n),
        "stay_put_ratio_peak": float(stay_put_ratio_peak),
    }
    return row, return_df


def _build_correlations(metrics_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    metric_cols = [
        "F_total",
        "F_out_near",
        "F_in_far",
        "F_long",
        "R_bar",
        "cos_alignment",
        "HHI_dest",
        "d_median",
        "d_p90",
        "alpha_return",
        "stay_put_ratio_peak",
    ]
    targets = ["alpha", "D_peak", "delta_near"]

    corr_rows: list[dict[str, Any]] = []
    for m in metric_cols:
        x = metrics_df[m].to_numpy(dtype=float) if m in metrics_df.columns else np.array([], dtype=float)
        for t in targets:
            y = metrics_df[t].to_numpy(dtype=float)
            rho, p, n = _spearman_pair(x, y)
            corr_rows.append({"metric": m, "target": t, "n": int(n), "spearman_rho": float(rho), "spearman_p": float(p)})
    corr_df = pd.DataFrame(corr_rows)

    part_rows: list[dict[str, Any]] = []
    for m in metric_cols:
        if m not in metrics_df.columns:
            continue
        r, p, n = _partial_spearman(
            metrics_df[m].to_numpy(dtype=float),
            metrics_df["alpha"].to_numpy(dtype=float),
            metrics_df[["D_peak"]].to_numpy(dtype=float),
        )
        part_rows.append(
            {
                "metric": m,
                "target": "alpha",
                "controls": "D_peak",
                "n": int(n),
                "partial_spearman_r": float(r),
                "partial_p": float(p),
            }
        )
    partial_df = pd.DataFrame(part_rows)
    return corr_df, partial_df


def _scatter_plot(
    *,
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    ax: plt.Axes,
    title: str,
    color: str,
) -> None:
    if df.empty or x_col not in df.columns or y_col not in df.columns:
        ax.set_title(title)
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes, ha="center", va="center")
        return
    sub = df[[x_col, y_col]].replace([np.inf, -np.inf], np.nan).dropna()
    if sub.empty:
        ax.set_title(title)
        ax.text(0.5, 0.5, "No valid data", transform=ax.transAxes, ha="center", va="center")
        return
    ax.scatter(sub[x_col], sub[y_col], s=46, alpha=0.85, color=color)
    rho, p, n = _spearman_pair(sub[x_col].to_numpy(dtype=float), sub[y_col].to_numpy(dtype=float))
    ax.set_title(f"{title}\nρ={rho:.3f}, p={p:.3g}, n={n}", fontsize=10)
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)


def _plot_figures(metrics_df: pd.DataFrame, out_fig_dir: Path) -> None:
    apply_paper_style()

    fig1, axes1 = plt.subplots(1, 2, figsize=(11, 4.2))
    _scatter_plot(
        df=metrics_df,
        x_col="F_total",
        y_col="alpha",
        ax=axes1[0],
        title="F_total vs α",
        color=OKABE_ITO["blue"],
    )
    _scatter_plot(
        df=metrics_df,
        x_col="F_out_near",
        y_col="alpha",
        ax=axes1[1],
        title="F_out_near vs α",
        color=OKABE_ITO["vermillion"],
    )
    fig1.tight_layout()
    save_figure(fig1, out_fig_dir / "evacuation_flow_vs_alpha.png")
    plt.close(fig1)

    fig2, axes2 = plt.subplots(1, 2, figsize=(11, 4.2))
    _scatter_plot(
        df=metrics_df,
        x_col="R_bar",
        y_col="alpha",
        ax=axes2[0],
        title="R_bar vs α",
        color=OKABE_ITO["bluish_green"],
    )
    _scatter_plot(
        df=metrics_df,
        x_col="cos_alignment",
        y_col="alpha",
        ax=axes2[1],
        title="cos_alignment vs α",
        color=OKABE_ITO["orange"],
    )
    fig2.tight_layout()
    save_figure(fig2, out_fig_dir / "directionality_vs_alpha.png")
    plt.close(fig2)

    fig3, ax3 = plt.subplots(figsize=FIGSIZE_FULL)
    _scatter_plot(
        df=metrics_df,
        x_col="alpha_return",
        y_col="alpha",
        ax=ax3,
        title="α_return vs α",
        color=OKABE_ITO["reddish_purple"],
    )
    fig3.tight_layout()
    save_figure(fig3, out_fig_dir / "return_rate_comparison.png")
    plt.close(fig3)


def _write_readme(out_dir: Path) -> None:
    text = """# Movement 分析输出（D_peak → α 机制检验）

## 口径
- 事件集合：Route B (`Dt_routeB_sample_flags.csv` 中 `route_b_selected=True`)
- 时间窗口：以每事件 `t_peak` 为中心，默认 ±24h（Exp-M1）
- 近场/远场：近场 `<50km`，远场 `50-200km`
- 序列拟合：`alpha_return` 在 `t'∈[24h,120h]` 做 log-log 斜率

## 关键指标定义
- `F_total`：峰值窗口内 `Σ|n_difference|`
- `F_out_near`：峰值窗口内 `Σ n_difference`（start_near & end_far）
- `F_in_far`：峰值窗口内 `Σ n_difference`（start_far & end_near）
- `F_long`：峰值窗口内 `Σ n_difference`（length_km > long_distance_km）
- `R_bar`：近场起点流向角的加权圆统计 resultant length（方向性）
- `cos_alignment`：流向与“远离灾害中心”方向一致性（加权均值）
- `HHI_dest`：近场疏散（start_near & end_far & n_diff>0）目的地集中度
- `alpha_return`：回流率 `R_return(t)` 的 log-log 衰减斜率

## 限制
- DFG 对小流量 OD 做隐私截断（baseline/crisis <10 移除），可能抬高 `HHI_dest`
- 对飓风类事件，若可用则使用 `t_peak` 时刻的 track 中心；否则使用 catalog/auto 中心
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def run(
    *,
    catalog: Path,
    output_root: Path,
    dt_tables_dir: Path,
    out_dir: Path,
    use_route_b_selected: bool = True,
    selected_slugs: list[str] | None = None,
    peak_window_hours: float = 24.0,
    near_km: float = 50.0,
    far_km: float = 200.0,
    long_distance_km: float = 50.0,
    use_track_center_at_peak: bool = True,
    allow_track_extrapolation: bool = False,
    return_fit_min_h: float = 24.0,
    return_fit_max_h: float = 120.0,
    require_all_events: bool = False,
) -> None:
    out_dir = Path(out_dir)
    tables_dir = out_dir / "tables"
    fig_dir = out_dir / "figures"
    _ensure_dir(out_dir)
    _ensure_dir(tables_dir)
    _ensure_dir(fig_dir)

    route_b = _load_route_b_events(Path(dt_tables_dir), use_route_b_selected=bool(use_route_b_selected))
    if selected_slugs:
        wanted = {str(x).strip() for x in selected_slugs if str(x).strip()}
        route_b = [e for e in route_b if e.slug in wanted]
        if not route_b:
            raise ValueError("selected_slugs 过滤后没有事件。")

    spec_map = _resolve_specs(Path(catalog))
    missing_catalog = sorted(set(e.slug for e in route_b) - set(spec_map.keys()))
    if missing_catalog:
        raise ValueError(f"catalog 缺失 Route B 事件：{missing_catalog}")

    prepared, avail_df, missing = _prepare_events(
        route_b_events=route_b,
        spec_map=spec_map,
        catalog_path=Path(catalog),
        peak_window_hours=float(peak_window_hours),
        use_track_center_at_peak=bool(use_track_center_at_peak),
        allow_track_extrapolation=bool(allow_track_extrapolation),
        require_all_events=bool(require_all_events),
    )
    avail_df.to_csv(tables_dir / "movement_data_availability.csv", index=False)
    warn_df = avail_df.copy()
    warn_df["status"] = np.where(
        warn_df["note"] != "ok",
        "fatal",
        np.where(warn_df["warning_flags"].astype(str).str.len() > 0, "warning", "clean"),
    )
    warn_df = warn_df.sort_values(["status", "slug"], kind="stable").reset_index(drop=True)
    warn_df.to_csv(tables_dir / "movement_warning_registry.csv", index=False)
    if require_all_events and missing:
        missing_df = avail_df.loc[avail_df["slug"].isin(missing), ["slug", "note"]].copy()
        missing_pairs = [f"{r.slug} -> {r.note}" for r in missing_df.itertuples(index=False)]
        raise ValueError(
            "movement 数据或事件配置不完整，缺失事件："
            f"{missing}。详情：{missing_pairs}。"
            f"详情文件：{tables_dir / 'movement_data_availability.csv'}"
        )

    metrics_rows: list[dict[str, Any]] = []
    return_rows: list[pd.DataFrame] = []
    for ev in prepared:
        row, ret_df = _aggregate_event_metrics(
            ev,
            peak_window_hours=float(peak_window_hours),
            near_km=float(near_km),
            far_km=float(far_km),
            long_distance_km=float(long_distance_km),
            return_fit_min_h=float(return_fit_min_h),
            return_fit_max_h=float(return_fit_max_h),
        )
        metrics_rows.append(row)
        return_rows.append(ret_df)

    metrics_df = pd.DataFrame(metrics_rows).sort_values("slug", kind="stable").reset_index(drop=True)
    if metrics_df.empty:
        raise ValueError("无可用 movement 指标（请先检查 movement_data_availability.csv）。")

    metrics_df.to_csv(tables_dir / "movement_evacuation_metrics.csv", index=False)
    ret_all = pd.concat(return_rows, ignore_index=True) if return_rows else pd.DataFrame(
        columns=["slug", "short_name", "window_start_pt", "hours_since_peak", "return_flow", "R_return", "denominator_F_out_near_pos", "n_vectors_return"]
    )
    ret_all = ret_all.sort_values(["slug", "hours_since_peak"], kind="stable").reset_index(drop=True)
    ret_all.to_csv(tables_dir / "movement_return_timeseries.csv", index=False)

    corr_df, partial_df = _build_correlations(metrics_df)
    corr_df.to_csv(tables_dir / "movement_alpha_correlations.csv", index=False)
    partial_df.to_csv(tables_dir / "movement_partial_correlations.csv", index=False)

    _plot_figures(metrics_df, fig_dir)
    _write_readme(out_dir)

    metadata = {
        "catalog": str(Path(catalog)),
        "output_root": str(Path(output_root)),
        "dt_tables_dir": str(Path(dt_tables_dir)),
        "n_route_b_events": int(len(route_b)),
        "n_prepared_events": int(len(prepared)),
        "use_route_b_selected": bool(use_route_b_selected),
        "selected_slugs": [e.slug for e in route_b],
        "peak_window_hours": float(peak_window_hours),
        "near_km": float(near_km),
        "far_km": float(far_km),
        "long_distance_km": float(long_distance_km),
        "use_track_center_at_peak": bool(use_track_center_at_peak),
        "allow_track_extrapolation": bool(allow_track_extrapolation),
        "return_fit_min_h": float(return_fit_min_h),
        "return_fit_max_h": float(return_fit_max_h),
        "require_all_events": bool(require_all_events),
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Movement 数据分析（Exp-M1~M4）")
    p.add_argument("--catalog", type=str, default="Docs/cross_disaster_catalog_extended.csv")
    p.add_argument("--output-root", type=str, default="outputs")
    p.add_argument("--dt-tables-dir", type=str, default="outputs/cross_disaster_comparison/Dt_decay/tables")
    p.add_argument("--out-dir", type=str, default="outputs/cross_disaster_comparison/movement_analysis")

    p.add_argument("--use-route-b-selected", type=int, choices=[0, 1], default=1)
    p.add_argument("--selected-slugs", type=str, default="", help="可选：逗号分隔，仅运行这些 slug。")
    p.add_argument("--peak-window-hours", type=float, default=24.0)
    p.add_argument("--near-km", type=float, default=50.0)
    p.add_argument("--far-km", type=float, default=200.0)
    p.add_argument("--long-distance-km", type=float, default=50.0)

    p.add_argument("--use-track-center-at-peak", type=int, choices=[0, 1], default=1)
    p.add_argument("--allow-track-extrapolation", type=int, choices=[0, 1], default=0)
    p.add_argument("--return-fit-min-h", type=float, default=24.0)
    p.add_argument("--return-fit-max-h", type=float, default=120.0)
    p.add_argument("--require-all-events", type=int, choices=[0, 1], default=0)
    return p


def cli_main() -> None:
    args = build_arg_parser().parse_args()
    slugs = [s.strip() for s in str(args.selected_slugs).split(",") if s.strip()]
    run(
        catalog=Path(args.catalog),
        output_root=Path(args.output_root),
        dt_tables_dir=Path(args.dt_tables_dir),
        out_dir=Path(args.out_dir),
        use_route_b_selected=bool(args.use_route_b_selected),
        selected_slugs=slugs,
        peak_window_hours=float(args.peak_window_hours),
        near_km=float(args.near_km),
        far_km=float(args.far_km),
        long_distance_km=float(args.long_distance_km),
        use_track_center_at_peak=bool(args.use_track_center_at_peak),
        allow_track_extrapolation=bool(args.allow_track_extrapolation),
        return_fit_min_h=float(args.return_fit_min_h),
        return_fit_max_h=float(args.return_fit_max_h),
        require_all_events=bool(args.require_all_events),
    )
