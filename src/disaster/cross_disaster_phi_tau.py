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

from disaster.physical_model_phi_rt import Config as PhysicalConfig
from disaster.physical_model_phi_rt import run as run_physical
from disaster.geo import haversine_km
from disaster.population_io import load_population_file, parse_window_start_pt, resolve_subdir
from disaster.population_redistribution import Config as RedistributionConfig
from disaster.population_redistribution import run as run_redistribution


@dataclass(frozen=True)
class DisasterSpec:
    slug: str
    name: str
    data_root: Path
    event_type: str
    t0_pt: pd.Timestamp | None
    center_lat: float | None
    center_lon: float | None
    center_track_csv: Path | None = None
    center_track_to_tz: str = "America/Los_Angeles"
    center_track_storm_name: str | None = None
    only_hour_pt: int = 8
    outflow_phi_threshold: float = 0.9
    inflow_phi_threshold: float = 1.1


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    redistribution: Path
    physical_model: Path


def _output_dirs(output_root: Path, slug: str) -> OutputDirs:
    root = output_root / slug
    return OutputDirs(
        root=root,
        redistribution=root / "population_redistribution",
        physical_model=root / "physical_model",
    )


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


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


def _safe_int(x: object, default: int) -> int:
    try:
        if x is None:
            return int(default)
        s = str(x).strip()
        if s == "" or s.lower() == "nan":
            return int(default)
        return int(float(s))
    except Exception:
        return int(default)


def _safe_timestamp(x: object) -> pd.Timestamp | None:
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() == "nan":
        return None
    ts = pd.to_datetime(s, errors="coerce")
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts)


def _safe_str(x: object) -> str:
    if x is None:
        return ""
    s = str(x).strip()
    if s == "" or s.lower() == "nan":
        return ""
    return s


def load_catalog(path: Path) -> list[DisasterSpec]:
    if not path.exists():
        raise FileNotFoundError(f"未找到 catalog：{path}")
    df = pd.read_csv(path)
    required = {"slug", "name", "data_root", "event_type"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"catalog 缺少列：{missing}（来自 {path}）")

    specs: list[DisasterSpec] = []
    for row in df.to_dict(orient="records"):
        track_csv = _safe_str(row.get("center_track_csv")) or _safe_str(row.get("track_csv"))
        # 说明：FBDM population/movement 的固定窗口以 Pacific Time (PT) 给出（见 Docs/facebook_data）。
        # 因此这里默认用 America/Los_Angeles 做对齐（除非 catalog 显式指定其它时区）。
        track_to_tz = _safe_str(row.get("center_track_to_tz")) or "America/Los_Angeles"
        track_storm = _safe_str(row.get("center_track_storm_name")) or _safe_str(row.get("track_storm_name"))
        outflow = _safe_float(row.get("outflow_phi_threshold"))
        inflow = _safe_float(row.get("inflow_phi_threshold"))
        outflow = 0.9 if outflow is None else float(outflow)
        inflow = 1.1 if inflow is None else float(inflow)
        specs.append(
            DisasterSpec(
                slug=str(row["slug"]).strip(),
                name=str(row["name"]).strip(),
                data_root=Path(str(row["data_root"]).strip()),
                event_type=str(row.get("event_type", "")).strip() or "unknown",
                t0_pt=_safe_timestamp(row.get("t0_pt")),
                center_lat=_safe_float(row.get("center_lat")),
                center_lon=_safe_float(row.get("center_lon")),
                center_track_csv=Path(track_csv) if track_csv else None,
                center_track_to_tz=str(track_to_tz),
                center_track_storm_name=str(track_storm) if track_storm else None,
                only_hour_pt=_safe_int(row.get("only_hour_pt"), 8),
                outflow_phi_threshold=float(outflow),
                inflow_phi_threshold=float(inflow),
            )
        )

    bad = [s.slug for s in specs if not s.slug]
    if bad:
        raise SystemExit(f"catalog 中存在空 slug：{bad}")
    return specs


def _list_population_windows(data_root: Path, *, only_hour_pt: int) -> list[dict]:
    pop_dir = resolve_subdir(data_root, "population")
    files = sorted(pop_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"目录为空：{pop_dir}")
    rows: list[dict] = []
    for path in files:
        ts = parse_window_start_pt(path)
        if int(ts.hour) != int(only_hour_pt):
            continue
        rows.append({"path": path, "window_start_pt": pd.Timestamp(ts)})
    rows = sorted(rows, key=lambda r: pd.Timestamp(r["window_start_pt"]))
    if not rows:
        raise FileNotFoundError(f"未找到 hour={only_hour_pt} 的 population 文件：{pop_dir}")
    return rows


def _load_track_points_for_spec(spec: DisasterSpec) -> pd.DataFrame | None:
    if spec.center_track_csv is None:
        return None
    p = Path(spec.center_track_csv)
    if not p.exists():
        return None
    df = pd.read_csv(p)
    need = {"datetime_utc", "lat", "lon"}
    if not need.issubset(df.columns):
        return None

    if "storm_name" in df.columns and spec.center_track_storm_name:
        want = str(spec.center_track_storm_name).strip().lower()
        df = df[df["storm_name"].astype(str).str.strip().str.lower() == want].copy()

    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True, errors="coerce")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["datetime_utc", "lat", "lon"]).copy()
    if df.empty:
        return None

    # align into local PT timeline used by FBDM filenames
    df["datetime_local"] = df["datetime_utc"].dt.tz_convert(str(spec.center_track_to_tz)).dt.tz_localize(None)
    df = df.sort_values("datetime_local", kind="stable").reset_index(drop=True)
    return df


def _choose_track_anchor(track: pd.DataFrame, *, ref_ts: pd.Timestamp) -> tuple[pd.Timestamp, dict]:
    if track.empty:
        return pd.Timestamp(ref_ts), {"track_anchor_ok": 0}

    track = track.copy()
    if "status" in track.columns:
        st = track["status"].astype(str).str.strip().str.lower()
        land = track[st == "landfall"].copy()
    else:
        land = track.iloc[0:0].copy()

    ref_ts = pd.Timestamp(ref_ts)
    method = "nearest_in_time"
    cand = track
    if not land.empty:
        land_dt = (pd.to_datetime(land["datetime_local"]) - ref_ts).abs()
        land_idx = int(land_dt.astype("timedelta64[ns]").idxmin())
        land_row = land.loc[land_idx]
        land_ts = pd.Timestamp(land_row["datetime_local"])

        # Pre-landfall datasets can start many days before the first tracked landfall. In that case,
        # anchoring to a far-future landfall snaps t0 too late and can drop all tiles by distance.
        if land_ts >= ref_ts and (land_ts - ref_ts) > pd.Timedelta(hours=48):
            cand = track
            method = "nearest_in_time"
        else:
            cand = land
            method = "landfall_nearest_in_time"

    cand = cand.copy()
    cand["dt_abs_h"] = (pd.to_datetime(cand["datetime_local"]) - ref_ts).abs() / pd.to_timedelta(1, unit="h")
    idx = int(cand["dt_abs_h"].astype(float).idxmin())
    row = cand.loc[idx]
    anchor_ts = pd.Timestamp(row["datetime_local"])
    meta = {
        "track_anchor_ok": 1,
        "track_anchor_pt": str(anchor_ts),
        "track_anchor_method": method,
        "track_anchor_status": str(row.get("status", "")).strip(),
        "track_anchor_lat": float(row["lat"]),
        "track_anchor_lon": float(row["lon"]),
    }
    return anchor_ts, meta


def _snap_t0_to_first_window_after_anchor(windows: list[dict], *, anchor_ts: pd.Timestamp) -> tuple[pd.Timestamp, Path | None, dict]:
    for r in windows:
        ts = pd.Timestamp(r["window_start_pt"])
        if ts >= pd.Timestamp(anchor_ts):
            return ts, Path(r["path"]), {"t0_snap_ok": 1, "t0_snap_window_pt": str(ts)}
    return pd.Timestamp(anchor_ts), None, {"t0_snap_ok": 0, "t0_snap_window_pt": ""}


def _snap_t0_to_nearest_window(windows: list[dict], *, anchor_ts: pd.Timestamp) -> tuple[pd.Timestamp, Path, dict]:
    """
    将 t0 对齐到“最近的可用 population 窗口”，避免 catalog 给了一个不存在的时刻导致 t0_pt 与 t0_file 不一致。

    返回：(snapped_t0_pt, snapped_t0_file, meta)
    """
    if not windows:
        raise SystemExit("windows 为空，无法 snap t0")
    anchor_ts = pd.Timestamp(anchor_ts)

    best: tuple[float, pd.Timestamp, Path] | None = None  # (abs_dt_hours, ts, path)
    for r in windows:
        ts = pd.Timestamp(r["window_start_pt"])
        dt_h = float(abs((ts - anchor_ts).total_seconds()) / 3600.0)
        cand = (dt_h, ts, Path(r["path"]))
        if best is None or cand[0] < best[0]:
            best = cand
        elif best is not None and cand[0] == best[0]:
            # 平局时：优先选择 anchor 之后的窗口（更接近“事件发生后第一个观测”）
            if cand[1] >= anchor_ts and best[1] < anchor_ts:
                best = cand

    assert best is not None
    dt_h, ts, p = best
    meta = {"t0_snap_ok": 1, "t0_snap_window_pt": str(ts), "t0_snap_delta_hours": float(dt_h)}
    return ts, p, meta


def _weighted_centroid(lat: np.ndarray, lon: np.ndarray, w: np.ndarray) -> tuple[float, float] | None:
    mask = np.isfinite(lat) & np.isfinite(lon) & np.isfinite(w) & (w > 0)
    if not np.any(mask):
        return None
    ww = w[mask].astype(float)
    ww_sum = float(np.sum(ww))
    if ww_sum <= 0:
        return None
    return float(np.sum(lat[mask] * ww) / ww_sum), float(np.sum(lon[mask] * ww) / ww_sum)


def auto_t0_and_center(spec: DisasterSpec, *, allow_auto_fallback: bool = True) -> tuple[pd.Timestamp, float, float, dict]:
    """
    返回：(t0_pt, center_lat, center_lon, metadata_dict)
    """

    if not bool(allow_auto_fallback):
        missing_fields: list[str] = []
        if spec.t0_pt is None:
            missing_fields.append("t0_pt")
        if spec.center_lat is None or spec.center_lon is None:
            missing_fields.append("center_lat/center_lon")
        if missing_fields:
            raise ValueError(
                f"{spec.slug}: strict 模式禁用 auto fallback，catalog 必须显式提供 {', '.join(missing_fields)}"
            )

    windows = _list_population_windows(spec.data_root, only_hour_pt=int(spec.only_hour_pt))
    first = windows[0]
    first_ts = pd.Timestamp(first["window_start_pt"])

    # t0：优先对齐 track anchor（landfall/closest approach），否则退化为“首个可用 population 窗口”（并显式 WARNING）。
    t0_method = "provided_exact"
    t0_snap_pt: pd.Timestamp | None = None  # 用于选择“最接近 t0 的可用窗口文件”（center 自动估计用）
    if spec.t0_pt is None:
        track_df = _load_track_points_for_spec(spec)
        if track_df is not None:
            anchor_ts, anchor_meta = _choose_track_anchor(track_df, ref_ts=pd.Timestamp(first_ts))
            use_centroid_anchor = False
            if "status" in track_df.columns:
                st = track_df["status"].astype(str).str.strip().str.lower()
                land = track_df[st == "landfall"].copy()
            else:
                land = track_df.iloc[0:0].copy()

            if not land.empty:
                land_dt = (pd.to_datetime(land["datetime_local"]) - pd.Timestamp(first_ts)).abs()
                land_idx = int(land_dt.astype("timedelta64[ns]").idxmin())
                land_ts = pd.Timestamp(land.loc[land_idx, "datetime_local"])
                if land_ts >= pd.Timestamp(first_ts) and (land_ts - pd.Timestamp(first_ts)) > pd.Timedelta(hours=48):
                    use_centroid_anchor = True

            if use_centroid_anchor:
                df0 = load_population_file(Path(first["path"]))
                lat0 = pd.to_numeric(df0["lat"], errors="coerce").to_numpy(dtype=float)
                lon0 = pd.to_numeric(df0["lon"], errors="coerce").to_numpy(dtype=float)
                w0 = pd.to_numeric(df0.get("n_baseline", np.nan), errors="coerce").to_numpy(dtype=float)
                cen = _weighted_centroid(lat0, lon0, w0)
                if cen is not None:
                    cen_lat, cen_lon = cen
                    d = haversine_km(
                        pd.to_numeric(track_df["lat"], errors="coerce").to_numpy(dtype=float),
                        pd.to_numeric(track_df["lon"], errors="coerce").to_numpy(dtype=float),
                        float(cen_lat),
                        float(cen_lon),
                    )
                    j = int(np.nanargmin(d)) if d.size else 0
                    row = track_df.iloc[int(j)]
                    anchor_ts = pd.Timestamp(row["datetime_local"])
                    anchor_meta = {
                        "track_anchor_ok": 1,
                        "track_anchor_pt": str(anchor_ts),
                        "track_anchor_method": "centroid_nearest_in_space",
                        "track_anchor_status": str(row.get("status", "")).strip(),
                        "track_anchor_lat": float(row["lat"]),
                        "track_anchor_lon": float(row["lon"]),
                        "first_window_baseline_centroid_lat": float(cen_lat),
                        "first_window_baseline_centroid_lon": float(cen_lon),
                    }
                    t0_method = "auto_centroid_nearest_track_nearest_window"
                else:
                    t0_method = "auto_track_anchor_nearest_window"
            else:
                t0_method = "auto_track_anchor_nearest_window"

            t0_pt, t0_file, snap_meta = _snap_t0_to_nearest_window(windows, anchor_ts=anchor_ts)
            t0_snap_pt = pd.Timestamp(t0_pt)
        else:
            anchor_meta = {"track_anchor_ok": 0}
            snap_meta = {"t0_snap_ok": 0, "t0_snap_window_pt": "", "t0_snap_delta_hours": float("nan")}
            t0_pt = pd.Timestamp(first_ts)
            t0_snap_pt = pd.Timestamp(t0_pt)
            t0_method = "auto_first_population_window"
            t0_file = Path(first["path"])
            print(
                f"[cross_disaster_phi_tau][WARNING] {spec.slug}: catalog 未提供 t0_pt 且缺少 track；"
                f"退化为 first_population_window_pt={t0_pt}（低置信度）"
            )
    else:
        t0_raw = pd.Timestamp(spec.t0_pt)
        t0_pt = pd.Timestamp(t0_raw)
        t0_snap_pt, t0_file, snap_meta = _snap_t0_to_nearest_window(windows, anchor_ts=t0_raw)
        track_df = _load_track_points_for_spec(spec)
        if track_df is not None:
            anchor_ts, anchor_meta = _choose_track_anchor(track_df, ref_ts=pd.Timestamp(t0_raw))
        else:
            anchor_meta = {"track_anchor_ok": 0}
            anchor_ts = None
        t0_method = "provided_exact"
        delta_h = float(snap_meta.get("t0_snap_delta_hours", float("nan")))
        if np.isfinite(delta_h) and delta_h > 12.0:
            print(
                f"[cross_disaster_phi_tau][WARNING] {spec.slug}: 提供的 t0_pt={t0_raw} 与最近窗口差 {delta_h:.1f}h；"
                "若本意是对齐 landfall，请确认该数据集最早窗口是否晚于灾害发生。"
            )

    # center_source_ts：用于 center 自动估计的窗口时间戳（t0_pt 本身不一定有对应文件）
    center_source_ts = pd.Timestamp(t0_snap_pt) if t0_snap_pt is not None else pd.Timestamp(t0_pt)
    center_source_file: Path | None = t0_file

    center_method = "provided"
    if spec.center_lat is None or spec.center_lon is None:
        # 若有 track anchor（尤其是飓风/台风等路径型灾害），优先使用 anchor 点作为中心，避免“加权质心被远端异常 tile 拉偏”。
        anchor_lat = _safe_float(anchor_meta.get("track_anchor_lat"))
        anchor_lon = _safe_float(anchor_meta.get("track_anchor_lon"))
        if int(anchor_meta.get("track_anchor_ok", 0)) == 1 and anchor_lat is not None and anchor_lon is not None and np.isfinite(anchor_lat) and np.isfinite(anchor_lon):
            center_lat = float(anchor_lat)
            center_lon = float(anchor_lon)
            center_method = "auto_track_anchor"
            center_source_ts = pd.Timestamp(str(anchor_meta.get("track_anchor_pt", t0_pt)))
            center_source_file = None
        else:
            assert center_source_file is not None
            df = load_population_file(center_source_file)
            lat = pd.to_numeric(df["lat"], errors="coerce").to_numpy(dtype=float)
            lon = pd.to_numeric(df["lon"], errors="coerce").to_numpy(dtype=float)
            diff = pd.to_numeric(df.get("n_difference", np.nan), errors="coerce").to_numpy(dtype=float)
            crisis = pd.to_numeric(df.get("n_crisis", np.nan), errors="coerce").to_numpy(dtype=float)

            # 优先按 |n_difference| 加权，定位“变化最大”的区域
            out = _weighted_centroid(lat, lon, np.abs(diff))
            if out is None:
                out = _weighted_centroid(lat, lon, crisis)
                center_method = "auto_centroid_n_crisis"
            else:
                center_method = "auto_centroid_abs_n_difference"
            if out is None:
                raise SystemExit(f"无法自动估计中心点：{spec.slug}（首窗无有效坐标/权重）")
            center_lat, center_lon = out
            print(
                f"[cross_disaster_phi_tau][WARNING] {spec.slug}: catalog 未提供 center_lat/center_lon，"
                f"已用 {center_method} 在窗口 {Path(center_source_file).name} 上估计中心点（请优先在 catalog 显式提供）。"
            )
    else:
        center_lat, center_lon = float(spec.center_lat), float(spec.center_lon)

    extra = {}
    if int(anchor_meta.get("track_anchor_ok", 0)) == 1 and anchor_meta.get("track_anchor_pt"):
        try:
            anchor_ts = pd.Timestamp(str(anchor_meta["track_anchor_pt"]))
            extra["track_anchor_to_t0_hours"] = float((pd.Timestamp(t0_pt) - anchor_ts).total_seconds() / 3600.0)
        except Exception:
            pass

    fallback_used = bool(str(t0_method).startswith("auto_") or str(center_method).startswith("auto_"))
    if (not bool(allow_auto_fallback)) and fallback_used:
        raise ValueError(
            f"{spec.slug}: strict 模式禁用 auto fallback，但检测到 t0_method={t0_method}, center_method={center_method}"
        )

    meta = {
        "slug": spec.slug,
        "name": spec.name,
        "event_type": spec.event_type,
        "data_root": str(spec.data_root),
        "only_hour_pt": int(spec.only_hour_pt),
        "t0_pt": str(t0_pt),
        "t0_method": t0_method,
        "t0_file": str(Path(t0_file).name) if t0_file else "",
        **anchor_meta,
        **snap_meta,
        **extra,
        "center_lat": float(center_lat),
        "center_lon": float(center_lon),
        "center_method": center_method,
        "center_source_window_pt": str(center_source_ts),
        "center_source_file": str(center_source_file.name) if center_source_file is not None else "",
        "first_population_window_pt": str(first_ts),
        "first_population_window_file": str(Path(first["path"]).name),
        "allow_auto_fallback": int(bool(allow_auto_fallback)),
        "fallback_used": int(fallback_used),
    }
    return t0_pt, float(center_lat), float(center_lon), meta


def _sign_pattern(phi: np.ndarray, *, eps: float) -> list[str]:
    """
    将 phi 相对 1 的状态离散成 '+', '-', '0'。
    """
    out: list[str] = []
    for v in phi:
        if not np.isfinite(v):
            out.append("?")
        elif v >= 1.0 + float(eps):
            out.append("+")
        elif v <= 1.0 - float(eps):
            out.append("-")
        else:
            out.append("0")
    return out


def _collapse(seq: list[str]) -> list[str]:
    out: list[str] = []
    for s in seq:
        if not out or out[-1] != s:
            out.append(s)
    return out


def detect_three_phase(phi_row: np.ndarray, *, eps: float = 0.05) -> tuple[bool, str, str]:
    """
    三相分离（+ - +）的简单判定：
    - 按距离带顺序得到符号串
    - 丢弃 '0' 与 '?' 后做 run-length collapse
    - 若 collapse 后恰好为 '+-+'，返回 True
    """
    raw = _sign_pattern(phi_row, eps=eps)
    compact = [s for s in raw if s in {"+", "-"}]
    collapsed = _collapse(compact)
    ok = collapsed == ["+", "-", "+"]
    return ok, "".join(raw), "".join(collapsed)


def run_one(
    spec: DisasterSpec,
    *,
    output_root: Path,
    fit_min_hours: float,
    fit_max_hours: float | None,
    plot_times_hours: tuple[float, ...],
    phase_eps: float,
    phase_times_hours: tuple[float, ...],
    allow_auto_fallback: bool = True,
) -> tuple[pd.DataFrame, dict]:
    out = _output_dirs(output_root, spec.slug)
    _ensure_dir(out.root)

    t0_pt, center_lat, center_lon, meta = auto_t0_and_center(spec, allow_auto_fallback=bool(allow_auto_fallback))
    (out.root / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 1: population redistribution
    red_cfg = RedistributionConfig(
        data_root=spec.data_root,
        output_dir=out.redistribution,
        epicenter_lat=float(center_lat),
        epicenter_lon=float(center_lon),
        t0_pt=pd.Timestamp(t0_pt),
        only_hour_pt=int(spec.only_hour_pt),
        outflow_phi_threshold=float(spec.outflow_phi_threshold),
        inflow_phi_threshold=float(spec.inflow_phi_threshold),
    )
    run_redistribution(red_cfg)

    # Step 2: physical model
    input_csv = out.redistribution / "tables" / "redistribution_by_distance_band.csv"
    phy_cfg = PhysicalConfig(
        input_csv=input_csv,
        output_dir=out.physical_model,
        fit_min_hours=float(fit_min_hours),
        fit_max_hours=float(fit_max_hours) if fit_max_hours is not None else None,
        plot_times_hours=tuple(float(x) for x in plot_times_hours),
    )
    run_physical(phy_cfg)

    # Step 3: collect tau + phase separation summary
    fit_csv = out.physical_model / "tables" / "relaxation_fit_by_band.csv"
    fit_df = pd.read_csv(fit_csv)
    fit_df.insert(0, "slug", spec.slug)
    fit_df.insert(1, "name", spec.name)
    fit_df.insert(2, "event_type", spec.event_type)

    phi_matrix_csv = out.physical_model / "tables" / "phi_rt_matrix.csv"
    phi_df = pd.read_csv(phi_matrix_csv)
    phi_df["hours_since_quake"] = pd.to_numeric(phi_df["hours_since_quake"], errors="coerce")
    phi_df = phi_df.dropna(subset=["hours_since_quake"]).copy()
    hours = phi_df["hours_since_quake"].to_numpy(dtype=float)

    band_cols = [c for c in phi_df.columns if c != "hours_since_quake"]
    phase_rows: list[dict] = []
    for t in phase_times_hours:
        if hours.size == 0:
            continue
        idx = int(np.argmin(np.abs(hours - float(t))))
        t_near = float(hours[idx])
        row = phi_df.loc[phi_df.index[idx], band_cols].to_numpy(dtype=float)
        ok, raw, collapsed = detect_three_phase(row, eps=float(phase_eps))
        phase_rows.append(
            {
                "t_req_hours": float(t),
                "t_used_hours": t_near,
                "three_phase_ok": int(ok),
                "pattern_raw": raw,
                "pattern_collapsed": collapsed,
            }
        )

    phase = {
        "slug": spec.slug,
        "name": spec.name,
        "event_type": spec.event_type,
        "phase_eps": float(phase_eps),
        "phase_times_hours": list(float(x) for x in phase_times_hours),
        "rows": phase_rows,
    }
    return fit_df, phase


def write_phase_summary_md(phases: list[dict], out_path: Path) -> None:
    lines: list[str] = []
    lines.append("# Phase Separation Summary (three-phase: + - +)\n")
    lines.append("判定口径：对每个灾难，在若干时间点取最近的窗口，比较距离带的 $\\phi_{agg}$ 相对 1 的符号（>1+eps 为 +，<1-eps 为 -）。\n")

    for ph in phases:
        lines.append(f"## {ph['slug']}  ({ph['event_type']})\n")
        lines.append(f"- name: {ph['name']}\n")
        lines.append(f"- eps: {ph['phase_eps']}\n")
        if not ph["rows"]:
            lines.append("- 无可用窗口（跳过）\n")
            continue
        ok_any = any(int(r["three_phase_ok"]) == 1 for r in ph["rows"])
        lines.append(f"- three-phase exists: {str(ok_any)}\n")
        lines.append("\n| t_req(h) | t_used(h) | three_phase | raw | collapsed |\n|---:|---:|---:|---|---|\n")
        for r in ph["rows"]:
            lines.append(
                f"| {int(round(float(r['t_req_hours'])))} | {int(round(float(r['t_used_hours'])))} | {int(r['three_phase_ok'])} | `{r['pattern_raw']}` | `{r['pattern_collapsed']}` |\n"
            )
        lines.append("\n")

    out_path.write_text("".join(lines), encoding="utf-8")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog.csv"), help="灾难配置表（CSV）")
    parser.add_argument("--output-root", type=Path, default=Path("outputs"), help="输出根目录")
    parser.add_argument("--summary-dir", type=Path, default=Path("outputs/cross_disaster_comparison"), help="跨灾难汇总输出目录")
    parser.add_argument("--fit-min-hours", type=float, default=0.0, help="指数恢复拟合 t>=min")
    parser.add_argument("--fit-max-hours", type=float, default=None, help="指数恢复拟合 t<=max（可选）")
    parser.add_argument("--plot-times-hours", type=float, nargs="*", default=[16, 40, 88, 160, 832], help="每个灾难输出 φ(r) 曲线的时间点（取 nearest）")
    parser.add_argument("--phase-eps", type=float, default=0.05, help="三相分离判定阈值 eps（phi 与 1 的差）")
    parser.add_argument("--phase-times-hours", type=float, nargs="*", default=[16, 40, 88, 160, 832], help="三相分离判定用的时间点（取 nearest）")
    parser.add_argument(
        "--allow-auto-fallback",
        type=int,
        choices=[0, 1],
        default=0,
        help="是否允许 auto t0/center fallback（0=禁用，严格要求 catalog 显式给定；1=允许）",
    )
    args = parser.parse_args()

    specs = load_catalog(args.catalog)
    _ensure_dir(Path(args.summary_dir))

    all_fit: list[pd.DataFrame] = []
    phases: list[dict] = []
    for spec in specs:
        print(f"[cross_disaster] running: {spec.slug} ({spec.name})")
        fit_df, phase = run_one(
            spec,
            output_root=Path(args.output_root),
            fit_min_hours=float(args.fit_min_hours),
            fit_max_hours=float(args.fit_max_hours) if args.fit_max_hours is not None else None,
            plot_times_hours=tuple(float(x) for x in args.plot_times_hours),
            phase_eps=float(args.phase_eps),
            phase_times_hours=tuple(float(x) for x in args.phase_times_hours),
            allow_auto_fallback=bool(args.allow_auto_fallback),
        )
        all_fit.append(fit_df)
        phases.append(phase)

    tau_out = Path(args.summary_dir) / "tau_comparison.csv"
    if all_fit:
        out_df = pd.concat(all_fit, ignore_index=True)
        out_df.to_csv(tau_out, index=False)
        print(f"Done. Wrote: {tau_out}")

    md_out = Path(args.summary_dir) / "phase_separation_summary.md"
    write_phase_summary_md(phases, md_out)
    print(f"Done. Wrote: {md_out}")


if __name__ == "__main__":
    cli_main()
