from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.geo import haversine_km
from disaster.population_io import load_population_file, parse_window_start_pt, resolve_subdir
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    data_root: Path
    output_dir: Path
    center_lat: float
    center_lon: float
    t0_pt: pd.Timestamp
    center_track_csv: Path | None = None
    center_track_to_tz: str = "America/Los_Angeles"
    center_track_storm_name: str | None = None
    distance_mode: str = "radial"  # radial: 到中心点距离；path: 到轨迹折线最近距离
    path_distance_method: str = "equirect"  # distance_mode=path 时：equirect(快) | geodesic(精确)
    hours_pt: tuple[int, ...] = (0, 8, 16)
    min_hours: float = -16.0
    max_hours: float = 832.0
    distance_bin_km: float = 10.0
    max_distance_km: float = 500.0
    phi_vmin: float = 0.6
    phi_vmax: float = 1.6
    contour_levels: tuple[float, ...] = (1.0, 0.9, 0.8)
    phase_eps: float = 0.05
    path_clip_pad_hours: float = 24.0
    path_clip_spatial_pad_km: float = 100.0
    path_sector_n: int = 0  # 0 表示不计算；>0 则输出每个 r_bin 的角向覆盖率（用于诊断海陆不对称）
    track_dt_default_hours: float = 6.0  # track 点时间戳间隔估计失败时的默认值
    track_gap_factor: float = 1.5  # 连续段判定：gap_thr = track_dt_est * track_gap_factor


@dataclass(frozen=True)
class CenterTrack:
    t_ns: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    status: np.ndarray | None = None


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _sum_min_count_1(s: pd.Series) -> float:
    """
    避免 pandas 的默认行为：当某组全是 NaN 时 sum() 返回 0.0，导致 phi 伪信号（例如 phi=0）。
    """
    return float(s.sum(min_count=1))


def _list_population_windows(cfg: Config) -> list[dict]:
    pop_dir = resolve_subdir(cfg.data_root, "population")

    files = sorted(pop_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"目录为空：{pop_dir}")

    hours_keep = set(int(h) for h in cfg.hours_pt)
    rows: list[dict] = []
    for p in files:
        ts = parse_window_start_pt(p)
        if hours_keep and int(ts.hour) not in hours_keep:
            continue
        h = float((pd.Timestamp(ts) - pd.Timestamp(cfg.t0_pt)).total_seconds() / 3600.0)
        if h < float(cfg.min_hours) or h > float(cfg.max_hours):
            continue
        rows.append({"path": p, "window_start_pt": pd.Timestamp(ts), "hours_since_quake": float(h)})

    rows = sorted(rows, key=lambda r: float(r["hours_since_quake"]))
    if not rows:
        raise FileNotFoundError(
            f"未找到符合条件的 population 窗口：hours_pt={sorted(hours_keep)}，t范围=[{cfg.min_hours},{cfg.max_hours}]"
        )
    return rows


def _load_center_track(cfg: Config) -> CenterTrack | None:
    if cfg.center_track_csv is None:
        return None
    p = Path(cfg.center_track_csv)
    if not p.exists():
        raise FileNotFoundError(f"未找到 center_track_csv：{p}")

    df = pd.read_csv(p)
    required = {"datetime_utc", "lat", "lon"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"track CSV 缺少列：{missing}（来自 {p}）")

    if "storm_name" in df.columns:
        names = (
            df["storm_name"]
            .dropna()
            .astype(str)
            .map(lambda s: s.strip())
            .replace("", np.nan)
            .dropna()
            .unique()
            .tolist()
        )
        want = str(cfg.center_track_storm_name).strip() if cfg.center_track_storm_name else ""
        if want:
            df = df[df["storm_name"].astype(str).str.strip().str.lower() == want.lower()].copy()
        elif len(names) > 1:
            raise SystemExit(f"track CSV 含多个 storm_name={sorted(names)}；请设置 center_track_storm_name 指定其一（来自 {p}）")

    t_utc = pd.to_datetime(df["datetime_utc"], utc=True, errors="coerce")
    t_local = t_utc.dt.tz_convert(str(cfg.center_track_to_tz)).dt.tz_localize(None)
    lat = pd.to_numeric(df["lat"], errors="coerce")
    lon = pd.to_numeric(df["lon"], errors="coerce")
    status = df["status"].astype(str) if "status" in df.columns else None

    ok = t_local.notna() & lat.notna() & lon.notna()
    t_local = t_local[ok]
    lat = lat[ok]
    lon = lon[ok]
    if status is not None:
        status = status[ok]
    if t_local.empty:
        raise SystemExit(f"track CSV 无有效时间/坐标：{p}")

    t_ns = t_local.astype("datetime64[ns]").astype("int64").to_numpy(dtype=np.int64)
    lat_v = lat.to_numpy(dtype=float)
    lon_v = lon.to_numpy(dtype=float)
    status_v = status.to_numpy(dtype=object) if status is not None else None

    order = np.argsort(t_ns)
    t_ns = t_ns[order]
    lat_v = lat_v[order]
    lon_v = lon_v[order]
    status_v = status_v[order] if status_v is not None else None

    # drop duplicate timestamps (keep last)
    if t_ns.size >= 2:
        keep = np.ones(t_ns.shape[0], dtype=bool)
        keep[:-1] = t_ns[:-1] != t_ns[1:]
        t_ns = t_ns[keep]
        lat_v = lat_v[keep]
        lon_v = lon_v[keep]
        status_v = status_v[keep] if status_v is not None else None

    if status_v is not None:
        status_v = np.array([str(x).strip().lower() for x in status_v.tolist()], dtype=object)

    return CenterTrack(t_ns=t_ns, lat=lat_v, lon=lon_v, status=status_v)


def _center_at(track: CenterTrack, ts: pd.Timestamp) -> tuple[float, float, bool, str]:
    t_ns_arr, lat_arr, lon_arr = track.t_ns, track.lat, track.lon
    x = np.int64(pd.Timestamp(ts).value)
    extrapolated = bool(x < np.int64(t_ns_arr[0]) or x > np.int64(t_ns_arr[-1]))
    if x < np.int64(t_ns_arr[0]):
        extrap_side = "before"
    elif x > np.int64(t_ns_arr[-1]):
        extrap_side = "after"
    else:
        extrap_side = "within"
    lat = float(np.interp(x, t_ns_arr, lat_arr, left=float(lat_arr[0]), right=float(lat_arr[-1])))
    lon = float(np.interp(x, t_ns_arr, lon_arr, left=float(lon_arr[0]), right=float(lon_arr[-1])))
    return lat, lon, extrapolated, extrap_side


def _haversine_pairwise_km(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    r = 6371.0
    lat1 = np.radians(lat1.astype(float))
    lon1 = np.radians(lon1.astype(float))
    lat2 = np.radians(lat2.astype(float))
    lon2 = np.radians(lon2.astype(float))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def _polyline_length_km(lat_arr: np.ndarray, lon_arr: np.ndarray) -> float:
    lat_arr = np.asarray(lat_arr, dtype=float)
    lon_arr = np.asarray(lon_arr, dtype=float)
    ok = np.isfinite(lat_arr) & np.isfinite(lon_arr)
    lat_arr = lat_arr[ok]
    lon_arr = lon_arr[ok]
    if lat_arr.size < 2:
        return float("nan")
    d = _haversine_pairwise_km(lat_arr[:-1], lon_arr[:-1], lat_arr[1:], lon_arr[1:])
    return float(np.nansum(d))


def _select_longest_contiguous_segment(
    t_ns: np.ndarray,
    keep: np.ndarray,
    *,
    dt_default_hours: float,
    gap_factor: float,
) -> tuple[int, int] | None:
    t_ns = np.asarray(t_ns, dtype=np.int64)
    keep = np.asarray(keep, dtype=bool)
    if t_ns.size != keep.size or t_ns.size < 2:
        return None
    if int(np.sum(keep)) < 2:
        return None

    if t_ns.size >= 3:
        dt_hours = float(np.median(np.diff(t_ns.astype(np.int64))) / 1e9 / 3600.0)
        dt_hours = dt_hours if np.isfinite(dt_hours) and dt_hours > 0 else float(dt_default_hours)
    else:
        dt_hours = float(dt_default_hours)
    gap_thr = dt_hours * float(gap_factor)

    best: tuple[int, int, int, float] | None = None  # (start,end,n,duration_h)
    start: int | None = None
    last_true: int | None = None
    for i in range(keep.size):
        if bool(keep[i]) and start is None:
            start = i
            last_true = i
            continue
        if start is None:
            continue
        if bool(keep[i]):
            assert last_true is not None
            gap_h = float((t_ns[i] - t_ns[last_true]) / 1e9 / 3600.0)
            if gap_h > gap_thr:
                end = int(last_true)
                n = int(end - start + 1)
                dur = float((t_ns[end] - t_ns[start]) / 1e9 / 3600.0)
                cand = (start, end, n, dur)
                if best is None or (cand[2], cand[3]) > (best[2], best[3]):
                    best = cand
                start = i
                last_true = i
            else:
                last_true = i
            continue

        assert last_true is not None
        end = int(last_true)
        n = int(end - start + 1)
        dur = float((t_ns[end] - t_ns[start]) / 1e9 / 3600.0)
        cand = (start, end, n, dur)
        if best is None or (cand[2], cand[3]) > (best[2], best[3]):
            best = cand
        start = None
        last_true = None

    if start is not None and last_true is not None:
        end = int(last_true)
        n = int(end - start + 1)
        dur = float((t_ns[end] - t_ns[start]) / 1e9 / 3600.0)
        cand = (start, end, n, dur)
        if best is None or (cand[2], cand[3]) > (best[2], best[3]):
            best = cand

    if best is None:
        return None
    return int(best[0]), int(best[1])


def _choose_track_anchor(track: CenterTrack, *, t0_pt: pd.Timestamp) -> tuple[np.int64, dict]:
    t0_ns = np.int64(pd.Timestamp(t0_pt).value)
    t_ns = track.t_ns
    if t_ns.size == 0:
        return t0_ns, {"path_track_anchor_ok": 0}

    if track.status is not None and track.status.size == t_ns.size:
        is_land = np.array([str(x).strip().lower() == "landfall" for x in track.status.tolist()], dtype=bool)
    else:
        is_land = np.zeros(t_ns.shape[0], dtype=bool)

    # Default: prefer landfall anchors. For "pre-landfall" datasets that start many days before the
    # first tracked landfall, anchoring to a far-future landfall will clip the path segment away
    # from the affected tiles and can drop all data by distance. In that case, fall back to the
    # nearest track point to t0.
    method = "nearest_t0"
    cand = np.arange(t_ns.size, dtype=int)
    if np.any(is_land):
        cand_land = np.where(is_land)[0]
        d_land = np.abs(t_ns[cand_land].astype(np.int64) - t0_ns)
        j_land = int(cand_land[int(np.argmin(d_land))])
        land_ts = pd.to_datetime(int(t_ns[j_land]))
        if land_ts >= pd.Timestamp(t0_pt) and (land_ts - pd.Timestamp(t0_pt)) > pd.Timedelta(hours=48):
            cand = np.arange(t_ns.size, dtype=int)
            method = "nearest_t0"
        else:
            cand = cand_land
            method = "landfall_nearest_t0"

    d = np.abs(t_ns[cand].astype(np.int64) - t0_ns)
    j = int(cand[int(np.argmin(d))])

    anchor_ns = np.int64(t_ns[j])
    meta = {
        "path_track_anchor_ok": 1,
        "path_track_anchor_pt": str(pd.to_datetime(int(anchor_ns))),
        "path_track_anchor_method": method,
        "path_track_anchor_status": str(track.status[j]) if track.status is not None else "",
    }
    return anchor_ns, meta


def _clip_track_for_path(track: CenterTrack, cfg: Config) -> tuple[tuple[np.ndarray, np.ndarray], dict]:
    """
    关键修复：避免用“风暴完整生命周期 track”构建 d_path。

    裁剪策略：
    - 时间：以 t0（或 t0 附近 landfall）为 anchor，按 ±pad_hours 保留 track 点；
    - 空间：仅保留距离 (center_lat,center_lon) <= (max_distance_km + spatial_pad_km) 的 track 点；
    - 连续段：若出现多个不连续片段，只取“最长连续段”，避免跨缺口连直线。
    """
    full_len_km = float(_polyline_length_km(track.lat, track.lon))
    full_n = int(track.lat.size)

    anchor_ns, anchor_meta = _choose_track_anchor(track, t0_pt=pd.Timestamp(cfg.t0_pt))
    pad_h = float(cfg.path_clip_pad_hours)
    if pad_h > 0:
        anchor_ts = pd.to_datetime(int(anchor_ns))
        t_lo = np.int64((pd.Timestamp(anchor_ts) - pd.to_timedelta(pad_h, unit="h")).value)
        t_hi = np.int64((pd.Timestamp(anchor_ts) + pd.to_timedelta(pad_h, unit="h")).value)
    else:
        t_lo = np.int64(track.t_ns.min())
        t_hi = np.int64(track.t_ns.max())
    keep_time = (track.t_ns >= t_lo) & (track.t_ns <= t_hi)

    spatial_r_km = float(cfg.max_distance_km) + float(cfg.path_clip_spatial_pad_km)
    d_center = haversine_km(track.lat.astype(float), track.lon.astype(float), float(cfg.center_lat), float(cfg.center_lon))
    keep_spatial = np.isfinite(d_center) & (d_center <= spatial_r_km)

    keep_both = keep_time & keep_spatial

    def _apply_keep(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict] | None:
        seg = _select_longest_contiguous_segment(
            track.t_ns,
            mask,
            dt_default_hours=float(cfg.track_dt_default_hours),
            gap_factor=float(cfg.track_gap_factor),
        )
        if seg is None:
            return None
        a, b = seg
        take = np.zeros(mask.shape[0], dtype=bool)
        take[a : b + 1] = True
        take = take & mask
        if int(np.sum(take)) < 2:
            return None
        lat2 = track.lat[take].astype(float)
        lon2 = track.lon[take].astype(float)
        idx = np.where(take)[0]
        meta2 = {
            "path_track_clip_start_pt": str(pd.to_datetime(int(track.t_ns[int(idx[0])]))),
            "path_track_clip_end_pt": str(pd.to_datetime(int(track.t_ns[int(idx[-1])]))),
            "path_track_points_used": int(lat2.size),
            "path_track_length_km": float(_polyline_length_km(lat2, lon2)),
        }
        return lat2, lon2, meta2

    clip_kind = "time_and_spatial"
    out = _apply_keep(keep_both)
    if out is None:
        clip_kind = "time_only"
        out = _apply_keep(keep_time)
    if out is None:
        clip_kind = "spatial_only"
        out = _apply_keep(keep_spatial)
    if out is None:
        clip_kind = "full"
        lat2 = track.lat.astype(float)
        lon2 = track.lon.astype(float)
        out_meta = {
            "path_track_clip_start_pt": str(pd.to_datetime(int(track.t_ns[0]))),
            "path_track_clip_end_pt": str(pd.to_datetime(int(track.t_ns[-1]))),
            "path_track_points_used": int(lat2.size),
            "path_track_length_km": float(_polyline_length_km(lat2, lon2)),
        }
    else:
        lat2, lon2, out_meta = out

    used_len_km = float(out_meta.get("path_track_length_km", float("nan")))
    ratio = float(used_len_km / float(cfg.max_distance_km)) if np.isfinite(used_len_km) and float(cfg.max_distance_km) > 0 else float("nan")
    ratio_total = float(full_len_km / float(cfg.max_distance_km)) if np.isfinite(full_len_km) and float(cfg.max_distance_km) > 0 else float("nan")

    meta = {
        "path_track_clip_ok": 1 if int(out_meta.get("path_track_points_used", 0)) >= 2 else 0,
        "path_track_clip_kind": str(clip_kind),
        "path_track_clip_pad_hours": float(pad_h),
        "path_track_clip_spatial_radius_km": float(spatial_r_km),
        "path_track_points_total": int(full_n),
        "path_track_length_total_km": float(full_len_km),
        "path_track_keep_time_points": int(np.sum(keep_time)),
        "path_track_keep_spatial_points": int(np.sum(keep_spatial)),
        "path_track_keep_both_points": int(np.sum(keep_both)),
        "path_track_length_ratio_to_rmax": float(ratio),
        "path_track_length_total_ratio_to_rmax": float(ratio_total),
        **anchor_meta,
        **out_meta,
    }
    return (lat2, lon2), meta


def _equirect_xy_km(
    lat_deg: np.ndarray, lon_deg: np.ndarray, *, lat0_deg: float, lon0_deg: float
) -> tuple[np.ndarray, np.ndarray]:
    """
    简单等距圆柱投影（equirectangular approximation）。
    目的：在不引入 shapely/pyproj 依赖的前提下，计算点到折线的近似距离（km）。
    """
    r_earth_km = 6371.0088
    lat = np.deg2rad(lat_deg.astype(float))
    lon = np.deg2rad(lon_deg.astype(float))
    lat0 = float(np.deg2rad(float(lat0_deg)))
    lon0 = float(np.deg2rad(float(lon0_deg)))
    x = (lon - lon0) * np.cos(lat0) * r_earth_km
    y = (lat - lat0) * r_earth_km
    return x, y


def _angular_distance_rad(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """
    球面两点角距离（弧度，haversine 形式）。
    输入可广播；返回同形状数组。
    """
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    a = np.clip(a, 0.0, 1.0)
    return 2.0 * np.arctan2(np.sqrt(a), np.sqrt(np.maximum(1.0 - a, 0.0)))


def _bearing_rad(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """
    初始方位角（弧度，[-pi,pi]），从 (lat1,lon1) 指向 (lat2,lon2)。
    lat1/lon1 为标量，lat2/lon2 为数组（便于向量化）。
    """
    dlon = lon2 - float(lon1)
    y = np.sin(dlon) * np.cos(lat2)
    x = np.cos(float(lat1)) * np.sin(lat2) - np.sin(float(lat1)) * np.cos(lat2) * np.cos(dlon)
    return np.arctan2(y, x)


def _min_dist_to_polyline_geodesic_km(
    lat_deg: np.ndarray,
    lon_deg: np.ndarray,
    *,
    seg_a_lat_deg: np.ndarray,
    seg_a_lon_deg: np.ndarray,
    seg_b_lat_deg: np.ndarray,
    seg_b_lon_deg: np.ndarray,
) -> np.ndarray:
    """
    点到折线（球面大圆线段序列）的最小距离（km）。
    使用 cross-track / along-track 公式判断投影是否落在线段内；
    若不在线段内，则取到端点的最小距离。
    """
    ok = np.isfinite(lat_deg) & np.isfinite(lon_deg)
    d_out = np.full(lat_deg.shape, np.nan, dtype=float)
    if not np.any(ok):
        return d_out

    r_earth_km = 6371.0088

    lat_p = np.deg2rad(lat_deg[ok].astype(float))
    lon_p = np.deg2rad(lon_deg[ok].astype(float))

    a_lat = np.deg2rad(np.asarray(seg_a_lat_deg, dtype=float))
    a_lon = np.deg2rad(np.asarray(seg_a_lon_deg, dtype=float))
    b_lat = np.deg2rad(np.asarray(seg_b_lat_deg, dtype=float))
    b_lon = np.deg2rad(np.asarray(seg_b_lon_deg, dtype=float))

    min_delta = np.full(lat_p.shape, np.inf, dtype=float)
    for la, loa, lb, lob in zip(a_lat.tolist(), a_lon.tolist(), b_lat.tolist(), b_lon.tolist(), strict=False):
        la = float(la)
        loa = float(loa)
        lb = float(lb)
        lob = float(lob)

        delta12 = float(_angular_distance_rad(np.array(la), np.array(loa), np.array(lb), np.array(lob)))
        if not np.isfinite(delta12) or delta12 <= 0:
            delta13 = _angular_distance_rad(np.array(la), np.array(loa), lat_p, lon_p)
            min_delta = np.minimum(min_delta, delta13)
            continue

        theta12 = float(_bearing_rad(la, loa, np.array([lb]), np.array([lob]))[0])
        delta13 = _angular_distance_rad(np.array(la), np.array(loa), lat_p, lon_p)
        theta13 = _bearing_rad(la, loa, lat_p, lon_p)

        theta_diff = theta13 - theta12
        sin_xt = np.sin(delta13) * np.sin(theta_diff)
        sin_xt = np.clip(sin_xt, -1.0, 1.0)
        delta_xt = np.arcsin(sin_xt)

        # signed along-track distance from A to the perpendicular projection on great-circle AB
        delta_at = np.arctan2(np.sin(delta13) * np.cos(theta_diff), np.cos(delta13))

        mask_start = delta_at < 0
        mask_end = delta_at > float(delta12)
        mask_within = (~mask_start) & (~mask_end)

        d_seg = np.empty_like(delta13)
        d_seg[mask_within] = np.abs(delta_xt[mask_within])
        d_seg[mask_start] = delta13[mask_start]
        if np.any(mask_end):
            delta23 = _angular_distance_rad(np.array(lb), np.array(lob), lat_p[mask_end], lon_p[mask_end])
            d_seg[mask_end] = delta23

        min_delta = np.minimum(min_delta, d_seg)

    d_out[ok] = min_delta * float(r_earth_km)
    return d_out


def _min_dist_to_polyline_km(
    lat_deg: np.ndarray,
    lon_deg: np.ndarray,
    *,
    seg_ax: np.ndarray,
    seg_ay: np.ndarray,
    seg_bx: np.ndarray,
    seg_by: np.ndarray,
    lat0_deg: float,
    lon0_deg: float,
) -> np.ndarray:
    ok = np.isfinite(lat_deg) & np.isfinite(lon_deg)
    d = np.full(lat_deg.shape, np.nan, dtype=float)
    if not np.any(ok):
        return d

    x, y = _equirect_xy_km(lat_deg[ok], lon_deg[ok], lat0_deg=float(lat0_deg), lon0_deg=float(lon0_deg))
    min_d2 = np.full(x.shape, np.inf, dtype=float)
    for ax, ay, bx, by in zip(seg_ax.tolist(), seg_ay.tolist(), seg_bx.tolist(), seg_by.tolist(), strict=False):
        abx = float(bx) - float(ax)
        aby = float(by) - float(ay)
        denom = abx * abx + aby * aby
        if denom <= 0:
            continue
        t = ((x - float(ax)) * abx + (y - float(ay)) * aby) / denom
        t = np.clip(t, 0.0, 1.0)
        cx = float(ax) + t * abx
        cy = float(ay) + t * aby
        d2 = (x - cx) ** 2 + (y - cy) ** 2
        min_d2 = np.minimum(min_d2, d2)

    d_ok = np.sqrt(min_d2)
    d[ok] = d_ok
    return d


def _min_dist_to_polyline_km_with_vector(
    lat_deg: np.ndarray,
    lon_deg: np.ndarray,
    *,
    seg_ax: np.ndarray,
    seg_ay: np.ndarray,
    seg_bx: np.ndarray,
    seg_by: np.ndarray,
    lat0_deg: float,
    lon0_deg: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ok = np.isfinite(lat_deg) & np.isfinite(lon_deg)
    d = np.full(lat_deg.shape, np.nan, dtype=float)
    dx = np.full(lat_deg.shape, np.nan, dtype=float)
    dy = np.full(lat_deg.shape, np.nan, dtype=float)
    if not np.any(ok):
        return d, dx, dy

    x, y = _equirect_xy_km(lat_deg[ok], lon_deg[ok], lat0_deg=float(lat0_deg), lon0_deg=float(lon0_deg))
    min_d2 = np.full(x.shape, np.inf, dtype=float)
    dx_best = np.full(x.shape, np.nan, dtype=float)
    dy_best = np.full(x.shape, np.nan, dtype=float)
    for ax, ay, bx, by in zip(seg_ax.tolist(), seg_ay.tolist(), seg_bx.tolist(), seg_by.tolist(), strict=False):
        abx = float(bx) - float(ax)
        aby = float(by) - float(ay)
        denom = abx * abx + aby * aby
        if denom <= 0:
            continue
        t = ((x - float(ax)) * abx + (y - float(ay)) * aby) / denom
        t = np.clip(t, 0.0, 1.0)
        cx = float(ax) + t * abx
        cy = float(ay) + t * aby
        d2 = (x - cx) ** 2 + (y - cy) ** 2
        take = d2 < min_d2
        if np.any(take):
            dx_best[take] = (x - cx)[take]
            dy_best[take] = (y - cy)[take]
            min_d2[take] = d2[take]

    d_ok = np.sqrt(min_d2)
    d[ok] = d_ok
    dx[ok] = dx_best
    dy[ok] = dy_best
    return d, dx, dy


def _distance_bins(cfg: Config) -> np.ndarray:
    step = float(cfg.distance_bin_km)
    if step <= 0:
        raise ValueError("distance_bin_km 必须 > 0")
    max_r = float(cfg.max_distance_km)
    if max_r <= 0:
        raise ValueError("max_distance_km 必须 > 0")
    return np.arange(0.0, max_r, step, dtype=float)


def _sign(v: float, *, eps: float) -> str:
    if not np.isfinite(float(v)):
        return "?"
    if float(v) >= 1.0 + float(eps):
        return "+"
    if float(v) <= 1.0 - float(eps):
        return "-"
    return "0"


def _collapse(seq: list[str]) -> list[str]:
    out: list[str] = []
    for s in seq:
        if not out or out[-1] != s:
            out.append(s)
    return out


def _three_phase_ok(phi: np.ndarray, *, eps: float) -> tuple[bool, str]:
    raw = [_sign(float(v), eps=eps) for v in phi]
    compact = [s for s in raw if s in {"+", "-"}]
    collapsed = _collapse(compact)
    return collapsed == ["+", "-", "+"], "".join(collapsed)


def _contiguous_true_blocks(times: np.ndarray, ok: np.ndarray) -> list[dict]:
    if times.size == 0 or ok.size == 0 or times.size != ok.size:
        return []
    dt = float(np.median(np.diff(times))) if times.size >= 2 else 8.0
    blocks: list[dict] = []
    start_idx: int | None = None
    for i in range(ok.size):
        if bool(ok[i]) and start_idx is None:
            start_idx = i
            continue
        if start_idx is None:
            continue
        is_last = i == ok.size - 1
        gap = float(times[i] - times[i - 1]) if i >= 1 else dt
        if (not bool(ok[i])) or (gap > dt * 1.5) or is_last:
            end_idx = i if (bool(ok[i]) and is_last) else i - 1
            t0 = float(times[start_idx])
            t1 = float(times[end_idx])
            n = int(end_idx - start_idx + 1)
            blocks.append({"t_start_hours": t0, "t_end_hours": t1, "duration_hours": float(t1 - t0), "n_windows": n})
            start_idx = None
    return blocks


def run(cfg: Config, *, max_files: int | None = None) -> None:
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

    windows = _list_population_windows(cfg)
    if max_files is not None:
        windows = windows[: int(max_files)]

    track = _load_center_track(cfg)
    distance_mode = str(cfg.distance_mode).strip().lower() or "radial"
    if distance_mode not in {"radial", "path"}:
        raise SystemExit(f"不支持的 distance_mode：{cfg.distance_mode}（仅支持 radial/path）")

    path_ctx: dict | None = None
    track_meta: dict = {}
    if distance_mode == "path":
        if track is None:
            raise SystemExit("distance_mode=path 需要 center_track_csv（用于定义灾害路径折线）")

        (lat_arr, lon_arr), track_meta = _clip_track_for_path(track, cfg)
        if lat_arr.size < 2:
            raise SystemExit("distance_mode=path 需要至少 2 个轨迹点")
        clip_kind = str(track_meta.get("path_track_clip_kind", "")).strip().lower()
        if clip_kind and clip_kind != "time_and_spatial":
            print(
                f"[phi_heatmap][WARNING] track clipping used fallback: clip_kind={clip_kind} "
                f"(keep_time={int(track_meta.get('path_track_keep_time_points', 0))}, "
                f"keep_spatial={int(track_meta.get('path_track_keep_spatial_points', 0))}, "
                f"keep_both={int(track_meta.get('path_track_keep_both_points', 0))}, "
                f"points_total={int(track_meta.get('path_track_points_total', 0))}, "
                f"points_used={int(track_meta.get('path_track_points_used', 0))})"
            )
        if clip_kind == "full":
            print(
                "[phi_heatmap][WARNING] track clipping fell back to full track "
                f"(points_total={int(track_meta.get('path_track_points_total', 0))}, "
                f"points_used={int(track_meta.get('path_track_points_used', 0))}, "
                f"len_total_km={float(track_meta.get('path_track_length_total_km', float('nan'))):.1f}, "
                f"len_used_km={float(track_meta.get('path_track_length_km', float('nan'))):.1f})"
            )
        lat0 = float(np.nanmean(lat_arr))
        lon0 = float(np.nanmean(lon_arr))
        x_tr, y_tr = _equirect_xy_km(lat_arr, lon_arr, lat0_deg=lat0, lon0_deg=lon0)
        path_method = str(cfg.path_distance_method).strip().lower() or "equirect"
        if path_method not in {"equirect", "geodesic"}:
            raise SystemExit(f"不支持的 path_distance_method：{cfg.path_distance_method}（仅支持 equirect/geodesic）")
        path_ctx = {
            "lat0": float(lat0),
            "lon0": float(lon0),
            "seg_ax": x_tr[:-1].astype(float),
            "seg_ay": y_tr[:-1].astype(float),
            "seg_bx": x_tr[1:].astype(float),
            "seg_by": y_tr[1:].astype(float),
            "seg_a_lat_deg": lat_arr[:-1].astype(float),
            "seg_a_lon_deg": lon_arr[:-1].astype(float),
            "seg_b_lat_deg": lat_arr[1:].astype(float),
            "seg_b_lon_deg": lon_arr[1:].astype(float),
            "track_points_used": int(track_meta.get("path_track_points_used", int(lat_arr.size))),
            "track_length_km": float(track_meta.get("path_track_length_km", float("nan"))),
            "path_distance_method": str(path_method),
        }

    r_bins = _distance_bins(cfg)
    step = float(cfg.distance_bin_km)
    r_max = float(cfg.max_distance_km)

    rows: list[pd.DataFrame] = []
    center_rows: list[dict] = []
    track_time_min_pt = str(pd.to_datetime(int(track.t_ns.min()))) if track is not None and track.t_ns.size else ""
    track_time_max_pt = str(pd.to_datetime(int(track.t_ns.max()))) if track is not None and track.t_ns.size else ""

    extrap_count = 0
    for i, meta in enumerate(windows, start=1):
        p = Path(meta["path"])
        df = load_population_file(p)

        n_baseline = pd.to_numeric(df["n_baseline"], errors="coerce").to_numpy(dtype=float)
        n_crisis = pd.to_numeric(df["n_crisis"], errors="coerce").to_numpy(dtype=float)
        lat = pd.to_numeric(df["lat"], errors="coerce").to_numpy(dtype=float)
        lon = pd.to_numeric(df["lon"], errors="coerce").to_numpy(dtype=float)

        window_ts = pd.Timestamp(meta["window_start_pt"])
        center_used_for_distance = 1 if distance_mode == "radial" else 0
        if track is None:
            center_lat, center_lon = float(cfg.center_lat), float(cfg.center_lon)
            center_mode = "static"
            center_extrapolated = 0
            center_extrap_side = ""
        else:
            center_lat, center_lon, is_extrap, side = _center_at(track, window_ts)
            center_extrapolated = 1 if bool(is_extrap) else 0
            center_extrap_side = str(side)
            center_mode = "track_extrapolated" if center_extrapolated else "track"
            extrap_count += int(center_extrapolated)
        center_rows.append(
            {
                "window_start_pt": window_ts,
                "hours_since_quake": float(meta["hours_since_quake"]),
                "center_lat": float(center_lat),
                "center_lon": float(center_lon),
                "center_mode": str(center_mode),
                "center_used_for_distance": int(center_used_for_distance),
                "center_extrapolated": int(center_extrapolated),
                "center_extrapolation_side": str(center_extrap_side),
                "center_track_time_min_pt": str(track_time_min_pt),
                "center_track_time_max_pt": str(track_time_max_pt),
                "distance_mode": str(distance_mode),
                "center_track_csv": str(cfg.center_track_csv) if cfg.center_track_csv is not None else "",
                "center_track_to_tz": str(cfg.center_track_to_tz),
                "center_track_storm_name": str(cfg.center_track_storm_name) if cfg.center_track_storm_name else "",
                "path_track_points_used": int(path_ctx.get("track_points_used", 0)) if path_ctx is not None else 0,
                "path_track_length_km": float(path_ctx.get("track_length_km", float("nan"))) if path_ctx is not None else float("nan"),
                "path_distance_method": str(path_ctx.get("path_distance_method", "")) if path_ctx is not None else "",
                "path_track_clip_ok": int(track_meta.get("path_track_clip_ok", 0)) if track_meta else 0,
                "path_track_clip_kind": str(track_meta.get("path_track_clip_kind", "")) if track_meta else "",
                "path_track_clip_start_pt": str(track_meta.get("path_track_clip_start_pt", "")) if track_meta else "",
                "path_track_clip_end_pt": str(track_meta.get("path_track_clip_end_pt", "")) if track_meta else "",
                "path_track_clip_pad_hours": float(track_meta.get("path_track_clip_pad_hours", float("nan"))) if track_meta else float("nan"),
                "path_track_clip_spatial_radius_km": float(track_meta.get("path_track_clip_spatial_radius_km", float("nan"))) if track_meta else float("nan"),
                "path_track_points_total": int(track_meta.get("path_track_points_total", 0)) if track_meta else 0,
                "path_track_length_total_km": float(track_meta.get("path_track_length_total_km", float("nan"))) if track_meta else float("nan"),
                "path_track_keep_time_points": int(track_meta.get("path_track_keep_time_points", 0)) if track_meta else 0,
                "path_track_keep_spatial_points": int(track_meta.get("path_track_keep_spatial_points", 0)) if track_meta else 0,
                "path_track_keep_both_points": int(track_meta.get("path_track_keep_both_points", 0)) if track_meta else 0,
                "path_track_length_ratio_to_rmax": float(track_meta.get("path_track_length_ratio_to_rmax", float("nan"))) if track_meta else float("nan"),
                "path_track_length_total_ratio_to_rmax": float(track_meta.get("path_track_length_total_ratio_to_rmax", float("nan"))) if track_meta else float("nan"),
                "path_track_anchor_ok": int(track_meta.get("path_track_anchor_ok", 0)) if track_meta else 0,
                "path_track_anchor_pt": str(track_meta.get("path_track_anchor_pt", "")) if track_meta else "",
                "path_track_anchor_method": str(track_meta.get("path_track_anchor_method", "")) if track_meta else "",
                "path_track_anchor_status": str(track_meta.get("path_track_anchor_status", "")) if track_meta else "",
            }
        )

        dx = None
        dy = None
        if distance_mode == "radial":
            dist = haversine_km(lat, lon, float(center_lat), float(center_lon))
        else:
            assert path_ctx is not None
            method = str(path_ctx.get("path_distance_method", "equirect")).strip().lower() or "equirect"
            if int(cfg.path_sector_n) > 0:
                dist_e, dx, dy = _min_dist_to_polyline_km_with_vector(
                    lat,
                    lon,
                    seg_ax=path_ctx["seg_ax"],
                    seg_ay=path_ctx["seg_ay"],
                    seg_bx=path_ctx["seg_bx"],
                    seg_by=path_ctx["seg_by"],
                    lat0_deg=float(path_ctx["lat0"]),
                    lon0_deg=float(path_ctx["lon0"]),
                )
                if method == "geodesic":
                    dist = _min_dist_to_polyline_geodesic_km(
                        lat,
                        lon,
                        seg_a_lat_deg=path_ctx["seg_a_lat_deg"],
                        seg_a_lon_deg=path_ctx["seg_a_lon_deg"],
                        seg_b_lat_deg=path_ctx["seg_b_lat_deg"],
                        seg_b_lon_deg=path_ctx["seg_b_lon_deg"],
                    )
                else:
                    dist = dist_e
            else:
                if method == "geodesic":
                    dist = _min_dist_to_polyline_geodesic_km(
                        lat,
                        lon,
                        seg_a_lat_deg=path_ctx["seg_a_lat_deg"],
                        seg_a_lon_deg=path_ctx["seg_a_lon_deg"],
                        seg_b_lat_deg=path_ctx["seg_b_lat_deg"],
                        seg_b_lon_deg=path_ctx["seg_b_lon_deg"],
                    )
                else:
                    dist = _min_dist_to_polyline_km(
                        lat,
                        lon,
                        seg_ax=path_ctx["seg_ax"],
                        seg_ay=path_ctx["seg_ay"],
                        seg_bx=path_ctx["seg_bx"],
                        seg_by=path_ctx["seg_by"],
                        lat0_deg=float(path_ctx["lat0"]),
                        lon0_deg=float(path_ctx["lon0"]),
                    )
        r_bin = np.floor(dist / step) * step
        keep = np.isfinite(r_bin) & (r_bin >= 0) & (r_bin < r_max)

        tmp = pd.DataFrame(
            {
                "r_bin_km": r_bin[keep].astype(float),
                "n_baseline": n_baseline[keep],
                "n_crisis": n_crisis[keep],
            }
        )
        if distance_mode == "path" and int(cfg.path_sector_n) > 0 and dx is not None and dy is not None:
            dxk = dx[keep]
            dyk = dy[keep]
            ang = np.arctan2(dyk.astype(float), dxk.astype(float))
            ang = np.where(np.isfinite(ang), (ang + 2 * np.pi) % (2 * np.pi), np.nan)
            sector = np.floor(ang / (2 * np.pi / float(cfg.path_sector_n))).astype(float)
            sector[~np.isfinite(sector)] = np.nan
            tmp["sector"] = sector
        both = tmp["n_baseline"].notna() & tmp["n_crisis"].notna()
        tmp["baseline_overlap"] = tmp["n_baseline"].where(both)
        tmp["crisis_overlap"] = tmp["n_crisis"].where(both)

        agg_args = dict(
            n_tiles=("n_baseline", "count"),
            n_tiles_crisis=("n_crisis", "count"),
            n_tiles_overlap=("baseline_overlap", "count"),
            baseline_sum=("n_baseline", _sum_min_count_1),
            crisis_sum=("n_crisis", _sum_min_count_1),
            baseline_sum_overlap=("baseline_overlap", _sum_min_count_1),
            crisis_sum_overlap=("crisis_overlap", _sum_min_count_1),
        )
        if "sector" in tmp.columns:
            agg_args["path_sector_occupied"] = ("sector", pd.Series.nunique)

        agg = tmp.groupby("r_bin_km", observed=True).agg(**agg_args).reset_index()
        agg["phi_aggregate"] = agg["crisis_sum"] / agg["baseline_sum"]
        agg["phi_overlap"] = agg["crisis_sum_overlap"] / agg["baseline_sum_overlap"]
        agg.loc[agg["n_tiles"] <= 0, "phi_aggregate"] = np.nan
        agg.loc[agg["n_tiles_overlap"] <= 0, "phi_overlap"] = np.nan
        agg["tile_overlap_ratio"] = np.where(agg["n_tiles"] > 0, agg["n_tiles_overlap"] / agg["n_tiles"], np.nan)
        if "path_sector_occupied" in agg.columns:
            agg["path_coverage_frac"] = agg["path_sector_occupied"] / float(cfg.path_sector_n)
        agg.insert(0, "window_start_pt", pd.Timestamp(meta["window_start_pt"]))
        agg.insert(1, "hours_since_quake", float(meta["hours_since_quake"]))

        rows.append(agg)

        if i % 20 == 0:
            print(f"[phi_heatmap] processed {i}/{len(windows)} windows...")

    if extrap_count and track_time_min_pt and track_time_max_pt:
        print(
            f"[phi_heatmap][WARNING] center extrapolated for {int(extrap_count)}/{int(len(windows))} windows "
            f"(track_time_range=[{track_time_min_pt},{track_time_max_pt}])"
        )

    long_df = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    out_long = out.tables / "phi_rt_long.csv"
    long_df.to_csv(out_long, index=False)

    pd.DataFrame(center_rows).to_csv(out.tables / "center_by_window.csv", index=False)

    # pivot：r_bin_km x hours_since_quake
    pivot = long_df.pivot(index="r_bin_km", columns="hours_since_quake", values="phi_aggregate").sort_index().sort_index(axis=1)
    pivot = pivot.reindex(index=r_bins)
    t_step = 8.0
    ts_unique = long_df["hours_since_quake"].dropna().unique().astype(float)
    ts_unique = np.sort(ts_unique)
    if ts_unique.size >= 2:
        dt = float(np.median(np.diff(ts_unique)))
        if np.isfinite(dt) and dt > 0:
            t_step = float(dt)
    t_grid = np.arange(float(cfg.min_hours), float(cfg.max_hours) + 1e-9, float(t_step), dtype=float)
    pivot = pivot.reindex(columns=t_grid)
    out_matrix = out.tables / "phi_rt_matrix.csv"
    pivot.reset_index().to_csv(out_matrix, index=False)

    # three-phase detection by time
    times = pivot.columns.to_numpy(dtype=float)
    ok_rows: list[dict] = []
    ok_flags: list[bool] = []
    patterns: list[str] = []
    for t in times:
        phi = pivot[t].to_numpy(dtype=float)
        ok, collapsed = _three_phase_ok(phi, eps=float(cfg.phase_eps))
        if float(t) < 0:
            ok = False
        ok_flags.append(bool(ok))
        patterns.append(collapsed)
        ok_rows.append({"hours_since_quake": float(t), "three_phase_ok": int(bool(ok)), "pattern_collapsed": str(collapsed)})

    ok_df = pd.DataFrame(ok_rows)
    out_ok = out.tables / "three_phase_by_time.csv"
    ok_df.to_csv(out_ok, index=False)

    blocks = _contiguous_true_blocks(times=times, ok=np.array(ok_flags, dtype=bool))
    blocks_df = pd.DataFrame(blocks)
    out_blocks = out.tables / "three_phase_windows.csv"
    blocks_df.to_csv(out_blocks, index=False)

    # heatmap
    with ps.paper_style():
        import matplotlib.pyplot as plt
        from matplotlib.colors import TwoSlopeNorm

        z = pivot.to_numpy(dtype=float)
        xs = pivot.columns.to_numpy(dtype=float)
        ys = pivot.index.to_numpy(dtype=float)

        fig, ax = plt.subplots(figsize=(ps.FIGSIZE_FULL[0], ps.FIGSIZE_FULL[1] * 1.05))

        if xs.size >= 2:
            x_step = float(np.median(np.diff(xs)))
        else:
            x_step = 8.0
        if ys.size >= 2:
            y_step = float(np.median(np.diff(ys)))
        else:
            y_step = float(cfg.distance_bin_km)

        x_centers = xs
        y_centers = ys + y_step / 2.0

        norm = TwoSlopeNorm(vmin=float(cfg.phi_vmin), vcenter=1.0, vmax=float(cfg.phi_vmax))
        im = ax.imshow(
            z,
            origin="lower",
            aspect="auto",
            cmap="RdBu_r",
            norm=norm,
            extent=[float(xs.min() - x_step / 2.0), float(xs.max() + x_step / 2.0), float(ys.min()), float(ys.max() + y_step)],
        )

        # 三相分离窗口阴影
        for b in blocks:
            ax.axvspan(float(b["t_start_hours"]) - x_step / 2.0, float(b["t_end_hours"]) + x_step / 2.0, color=ps.OKABE_ITO["gray"], alpha=0.12, linewidth=0)

        # 等值线（phi=1/0.9/0.8）
        try:
            xx, yy = np.meshgrid(x_centers, y_centers)
            cs = ax.contour(
                xx,
                yy,
                z,
                levels=[float(x) for x in cfg.contour_levels],
                colors=[ps.OKABE_ITO["black"]] * len(cfg.contour_levels),
                linewidths=1.0,
                linestyles=["--", ":", ":"][: len(cfg.contour_levels)],
                alpha=0.85,
            )
            ax.clabel(cs, inline=True, fontsize=8, fmt=lambda v: f"{v:.1f}")
        except Exception:
            pass

        ax.axvline(0.0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.set_xlabel("Hours since event (PT windows, 8h step)")
        ax.set_ylabel("Distance to center r (km)")
        ax.set_title(r"$\phi_{agg}(r,t)$ heatmap (red>1, white=1, blue<1)")

        cb = fig.colorbar(im, ax=ax, shrink=0.92)
        cb.set_label(r"$\phi_{agg}=\sum n_{crisis}/\sum n_{baseline}$")

        # y ticks 稀疏化（每 50km）
        if ys.size:
            yt = np.arange(0, float(cfg.max_distance_km) + 1e-9, 50.0)
            ax.set_yticks(yt)
            ax.set_yticklabels([f"{int(v)}" for v in yt])
        # x ticks 稀疏化
        if xs.size:
            step_idx = max(1, int(xs.size / 10))
            xt_idx = np.arange(0, xs.size, step_idx)
            ax.set_xticks(xs[xt_idx])
            ax.set_xticklabels([f"{int(round(xs[j]))}" for j in xt_idx])

        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "phi_rt_heatmap.png")
        plt.close(fig)

    t_min = pd.to_datetime(long_df["window_start_pt"]).min() if not long_df.empty else None
    t_max = pd.to_datetime(long_df["window_start_pt"]).max() if not long_df.empty else None
    readme = f"""# Phi Heatmap (Task 4)

本目录对应 `Opinion_PI.md` 的 **任务 4**：计算并可视化连续版本的 $\\phi(r,t)$：

- 距离：0–{int(cfg.max_distance_km)} km，每 {int(cfg.distance_bin_km)} km 一个 bin
- 时间：每 8 小时一个窗口（PT），t 范围 [{float(cfg.min_hours)}, {float(cfg.max_hours)}] 小时
- 指标：$\\phi_{{agg}}(r,t)=\\sum n_{{crisis}}/\\sum n_{{baseline}}$

## 配置

 - center: ({float(cfg.center_lat):.4f}, {float(cfg.center_lon):.4f})
 - center_track_csv: {cfg.center_track_csv}
 - center_track_to_tz: {cfg.center_track_to_tz}
 - center_track_storm_name: {cfg.center_track_storm_name}
 - distance_mode: {distance_mode}
 - path_distance_method: {str(cfg.path_distance_method).strip().lower() or "equirect"}
 - path_clip_pad_hours: {float(cfg.path_clip_pad_hours)}
 - path_clip_spatial_pad_km: {float(cfg.path_clip_spatial_pad_km)}
 - path_sector_n: {int(cfg.path_sector_n)}
 - track_dt_default_hours: {float(cfg.track_dt_default_hours)}
 - track_gap_factor: {float(cfg.track_gap_factor)}
 - t0_pt: {pd.Timestamp(cfg.t0_pt)}
 - hours_pt: {list(int(h) for h in cfg.hours_pt)}

## 输出

- `tables/phi_rt_long.csv`：长表（每个窗口 × 每个 r_bin 的汇总）
- `tables/phi_rt_matrix.csv`：宽表（rows=r_bin_km, cols=hours_since_quake）
- `tables/center_by_window.csv`：每个时间窗口使用的中心点（static 或 track 插值）
- `tables/three_phase_by_time.csv`：三相分离判定（按时间）
- `tables/three_phase_windows.csv`：三相分离连续时间段
- `figures/phi_rt_heatmap.*`：热力图（含 φ=1/0.9/0.8 等值线）

## 覆盖时间（PT）

- {t_min} → {t_max}
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_long}")
    print(f"Done. Wrote: {out_matrix}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True, help="数据根目录（包含 population/）")
    parser.add_argument("--output-dir", type=Path, required=True, help="输出目录")
    parser.add_argument("--center-lat", type=float, required=True, help="中心点纬度（震中/灾害中心）")
    parser.add_argument("--center-lon", type=float, required=True, help="中心点经度（震中/灾害中心）")
    parser.add_argument("--center-track-csv", type=Path, default=None, help="可选：时变中心轨迹 CSV（含 datetime_utc,lat,lon 列）")
    parser.add_argument("--center-track-to-tz", type=str, default="America/Los_Angeles", help="轨迹时间从 UTC 转到该时区再对齐（默认 America/Los_Angeles）")
    parser.add_argument("--center-track-storm-name", type=str, default=None, help="可选：当轨迹 CSV 含多个 storm_name 时用于过滤")
    parser.add_argument(
        "--distance-mode",
        type=str,
        default="radial",
        choices=["radial", "path"],
        help="距离定义：radial=到中心点（static/track）；path=到轨迹折线最近距离（需要 center_track_csv）",
    )
    parser.add_argument(
        "--path-distance-method",
        type=str,
        default="equirect",
        choices=["equirect", "geodesic"],
        help="distance_mode=path 时：点到轨迹距离算法（默认 equirect；geodesic 更精确但更慢）",
    )
    parser.add_argument("--path-clip-pad-hours", type=float, default=24.0, help="distance_mode=path 时，轨迹折线按时间裁剪的前后 padding（小时，默认 24）")
    parser.add_argument(
        "--path-clip-spatial-pad-km",
        type=float,
        default=100.0,
        help="distance_mode=path 时，轨迹折线按空间半径裁剪的 padding（km，默认 100；总半径=max_distance_km+pad）",
    )
    parser.add_argument("--path-sector-n", type=int, default=0, help="distance_mode=path 时角向覆盖率诊断：扇区数（0=不计算，默认 0）")
    parser.add_argument("--t0-pt", type=str, required=True, help="t=0 的 PT 时间戳（例如 2023-02-05 16:00）")
    parser.add_argument("--hours-pt", type=int, nargs="*", default=[0, 8, 16], help="保留哪些 PT 小时窗口（默认 0 8 16）")
    parser.add_argument("--min-hours", type=float, default=-16.0, help="最小 hours_since_quake（默认 -16）")
    parser.add_argument("--max-hours", type=float, default=832.0, help="最大 hours_since_quake（默认 832）")
    parser.add_argument("--distance-bin-km", type=float, default=10.0, help="距离 bin 宽度（km，默认 10）")
    parser.add_argument("--max-distance-km", type=float, default=500.0, help="最大距离（km，默认 500）")
    parser.add_argument("--phi-vmin", type=float, default=0.6, help="热力图 vmin（默认 0.6）")
    parser.add_argument("--phi-vmax", type=float, default=1.6, help="热力图 vmax（默认 1.6）")
    parser.add_argument("--track-dt-default-hours", type=float, default=6.0, help="track 点时间间隔估计失败时的默认 dt（小时，默认 6）")
    parser.add_argument("--track-gap-factor", type=float, default=1.5, help="track 连续段判定：gap_thr = dt_est * factor（默认 1.5）")
    parser.add_argument("--max-files", type=int, default=None, help="最多处理多少个窗口文件（冒烟测试用）")
    args = parser.parse_args()

    cfg = Config(
        data_root=args.data_root,
        output_dir=args.output_dir,
        center_lat=float(args.center_lat),
        center_lon=float(args.center_lon),
        center_track_csv=Path(args.center_track_csv) if args.center_track_csv is not None else None,
        center_track_to_tz=str(args.center_track_to_tz),
        center_track_storm_name=str(args.center_track_storm_name) if args.center_track_storm_name else None,
        distance_mode=str(args.distance_mode),
        path_distance_method=str(args.path_distance_method),
        t0_pt=pd.Timestamp(str(args.t0_pt)),
        path_clip_pad_hours=float(args.path_clip_pad_hours),
        path_clip_spatial_pad_km=float(args.path_clip_spatial_pad_km),
        path_sector_n=int(args.path_sector_n),
        hours_pt=tuple(int(x) for x in args.hours_pt),
        min_hours=float(args.min_hours),
        max_hours=float(args.max_hours),
        distance_bin_km=float(args.distance_bin_km),
        max_distance_km=float(args.max_distance_km),
        phi_vmin=float(args.phi_vmin),
        phi_vmax=float(args.phi_vmax),
        track_dt_default_hours=float(args.track_dt_default_hours),
        track_gap_factor=float(args.track_gap_factor),
    )
    run(cfg, max_files=int(args.max_files) if args.max_files is not None else None)


if __name__ == "__main__":
    cli_main()
