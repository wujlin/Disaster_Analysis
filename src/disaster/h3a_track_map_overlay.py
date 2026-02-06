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

from disaster.population_io import load_population_file
from disaster.geo import haversine_km
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    output_root: Path
    slug: str
    out_dir: Path
    phase0_csv: Path | None = None
    top_k_tiles: int = 80
    min_abs_dev: float = 0.05


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _equirect_xy_km(lat_deg: np.ndarray, lon_deg: np.ndarray, *, lat0_deg: float, lon0_deg: float) -> tuple[np.ndarray, np.ndarray]:
    r_earth_km = 6371.0088
    lat = np.deg2rad(lat_deg.astype(float))
    lon = np.deg2rad(lon_deg.astype(float))
    lat0 = float(np.deg2rad(float(lat0_deg)))
    lon0 = float(np.deg2rad(float(lon0_deg)))
    x = (lon - lon0) * np.cos(lat0) * r_earth_km
    y = (lat - lat0) * r_earth_km
    return x, y


def _xy_to_latlon_deg(x_km: np.ndarray, y_km: np.ndarray, *, lat0_deg: float, lon0_deg: float) -> tuple[np.ndarray, np.ndarray]:
    r_earth_km = 6371.0088
    lat0 = float(np.deg2rad(float(lat0_deg)))
    lon0 = float(np.deg2rad(float(lon0_deg)))
    lat = lat0 + (y_km.astype(float) / r_earth_km)
    lon = lon0 + (x_km.astype(float) / (np.cos(lat0) * r_earth_km))
    return np.rad2deg(lat), np.rad2deg(lon)


def _nearest_point_on_polyline_xy(
    px: np.ndarray,
    py: np.ndarray,
    *,
    seg_ax: np.ndarray,
    seg_ay: np.ndarray,
    seg_bx: np.ndarray,
    seg_by: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    返回每个点到折线的最近点坐标 (cx,cy) 以及距离 (d_km)。
    实现为逐 segment 扫描（K<=O(100) 足够）。
    """
    px = np.asarray(px, dtype=float)
    py = np.asarray(py, dtype=float)
    cx_best = np.full(px.shape, np.nan, dtype=float)
    cy_best = np.full(px.shape, np.nan, dtype=float)
    d2_best = np.full(px.shape, np.inf, dtype=float)

    for ax, ay, bx, by in zip(seg_ax.tolist(), seg_ay.tolist(), seg_bx.tolist(), seg_by.tolist(), strict=False):
        abx = float(bx) - float(ax)
        aby = float(by) - float(ay)
        denom = abx * abx + aby * aby
        if denom <= 0:
            continue
        t = ((px - float(ax)) * abx + (py - float(ay)) * aby) / denom
        t = np.clip(t, 0.0, 1.0)
        cx = float(ax) + t * abx
        cy = float(ay) + t * aby
        d2 = (px - cx) ** 2 + (py - cy) ** 2
        take = d2 < d2_best
        cx_best[take] = cx[take]
        cy_best[take] = cy[take]
        d2_best[take] = d2[take]

    d = np.sqrt(d2_best)
    d[~np.isfinite(d2_best)] = np.nan
    return cx_best, cy_best, d


def _load_track_from_center_by_window(output_root: Path, slug: str) -> tuple[Path, str]:
    p = output_root / slug / "phi_heatmap" / "tables" / "center_by_window.csv"
    if not p.exists():
        raise FileNotFoundError(f"未找到：{p}")
    df = pd.read_csv(p)
    if df.empty:
        raise SystemExit(f"{p} 为空")
    track_csv = str(df.iloc[0].get("center_track_csv", "")).strip()
    storm_name = str(df.iloc[0].get("center_track_storm_name", "")).strip()
    if not track_csv:
        raise SystemExit(f"{p} 中 center_track_csv 为空（无法画路径）")
    if not storm_name:
        raise SystemExit(f"{p} 中 center_track_storm_name 为空（无法过滤多 storm track）")
    return Path(track_csv), storm_name


def _load_track_points(track_csv: Path, *, storm_name: str) -> pd.DataFrame:
    df = pd.read_csv(track_csv)
    need = {"datetime_utc", "lat", "lon"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise SystemExit(f"track CSV 缺少列：{miss}（来自 {track_csv}）")
    if "storm_name" in df.columns:
        df = df[df["storm_name"].astype(str).str.strip().str.lower() == str(storm_name).strip().lower()].copy()
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["datetime_utc", "lat", "lon"]).copy()
    df = df.sort_values("datetime_utc", kind="stable")
    if df.shape[0] < 2:
        raise SystemExit(f"track 点数不足（<{2}）：{track_csv} storm={storm_name}")
    return df


def _clip_track_points_like_phi_heatmap(
    track: pd.DataFrame,
    *,
    center_track_to_tz: str,
    clip_start_pt: str,
    clip_end_pt: str,
    center_lat: float,
    center_lon: float,
    spatial_radius_km: float,
) -> pd.DataFrame:
    """
    关键修复：可视化时的路径应与 `phi_heatmap(distance_mode=path)` 使用的裁剪段一致，
    避免把完整生命周期 track 画进图里导致误解。
    """
    if track.empty:
        return track

    out = track.copy()
    out["datetime_local"] = out["datetime_utc"].dt.tz_convert(str(center_track_to_tz)).dt.tz_localize(None)

    t0 = pd.to_datetime(str(clip_start_pt).strip(), errors="coerce")
    t1 = pd.to_datetime(str(clip_end_pt).strip(), errors="coerce")
    if not pd.isna(t0) and not pd.isna(t1):
        out = out[(out["datetime_local"] >= pd.Timestamp(t0)) & (out["datetime_local"] <= pd.Timestamp(t1))].copy()

    rr = float(spatial_radius_km)
    if np.isfinite(rr) and rr > 0:
        d = haversine_km(out["lat"].to_numpy(dtype=float), out["lon"].to_numpy(dtype=float), float(center_lat), float(center_lon))
        out = out[np.isfinite(d) & (d <= rr)].copy()

    out = out.sort_values("datetime_utc", kind="stable")
    return out


def _find_t_at_S(phase0_csv: Path | None, slug: str) -> float | None:
    if phase0_csv is None or not phase0_csv.exists():
        return None
    df = pd.read_csv(phase0_csv)
    if df.empty or "slug" not in df.columns or "t_at_S" not in df.columns:
        return None
    sub = df[df["slug"].astype(str) == str(slug)]
    if sub.empty:
        return None
    t = pd.to_numeric(sub.iloc[0]["t_at_S"], errors="coerce")
    return None if pd.isna(t) else float(t)


def _find_population_file(data_root: Path, ts_pt: pd.Timestamp) -> Path | None:
    pop_dir = data_root / "population"
    if not pop_dir.exists():
        return None
    pat = f"*_{ts_pt:%Y-%m-%d}_{ts_pt:%H%M}.csv"
    hits = sorted(pop_dir.glob(pat))
    return hits[0] if hits else None


def run(cfg: Config) -> None:
    out_dir = Path(cfg.out_dir)
    figs = out_dir / "figures"
    tabs = out_dir / "tables"
    _ensure_dir(figs)
    _ensure_dir(tabs)

    meta_path = Path(cfg.output_root) / cfg.slug / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"未找到：{meta_path}")
    meta = _load_json(meta_path)
    data_root = Path(str(meta.get("data_root", "")).strip())
    t0_pt = pd.Timestamp(str(meta.get("t0_pt", "")).strip())
    center_lat = float(meta.get("center_lat", np.nan))
    center_lon = float(meta.get("center_lon", np.nan))

    track_csv, storm_name = _load_track_from_center_by_window(Path(cfg.output_root), cfg.slug)
    track = _load_track_points(track_csv, storm_name=storm_name)

    # clip track points to the same segment used by phi_heatmap (distance_mode=path)
    cbw_path = Path(cfg.output_root) / cfg.slug / "phi_heatmap" / "tables" / "center_by_window.csv"
    if cbw_path.exists():
        cbw = pd.read_csv(cbw_path)
        if not cbw.empty:
            row0 = cbw.iloc[0].to_dict()
            center_track_to_tz = str(row0.get("center_track_to_tz", "America/Los_Angeles") or "America/Los_Angeles")
            clip_start_pt = str(row0.get("path_track_clip_start_pt", "") or "")
            clip_end_pt = str(row0.get("path_track_clip_end_pt", "") or "")
            spatial_r = float(pd.to_numeric(row0.get("path_track_clip_spatial_radius_km"), errors="coerce"))

            clipped = _clip_track_points_like_phi_heatmap(
                track,
                center_track_to_tz=center_track_to_tz,
                clip_start_pt=clip_start_pt,
                clip_end_pt=clip_end_pt,
                center_lat=float(center_lat),
                center_lon=float(center_lon),
                spatial_radius_km=float(spatial_r),
            )
            if clipped.shape[0] >= 2:
                track = clipped

    # choose time slice
    phase0_csv = cfg.phase0_csv
    if phase0_csv is None:
        phase0_csv = Path(cfg.output_root) / "_tmp_h3a_track_collapse" / "tables" / "phase0_signal_strength.csv"
    t_at_S = _find_t_at_S(phase0_csv, cfg.slug)
    if t_at_S is None:
        t_at_S = 0.0
    ts_pt = pd.Timestamp(t0_pt) + pd.to_timedelta(float(t_at_S), unit="h")

    pop_file = _find_population_file(data_root, ts_pt)
    if pop_file is None:
        # fallback: use metadata's center_source_file if present
        src_name = str(meta.get("center_source_file", "")).strip()
        cand = data_root / "population" / src_name if src_name else None
        pop_file = cand if cand is not None and cand.exists() else None
    if pop_file is None:
        raise SystemExit(f"未找到 population 文件（data_root={data_root} ts_pt={ts_pt}）")

    pop = load_population_file(Path(pop_file))
    pop["n_baseline"] = pd.to_numeric(pop["n_baseline"], errors="coerce")
    pop["n_crisis"] = pd.to_numeric(pop["n_crisis"], errors="coerce")
    pop["phi_tile"] = pop["n_crisis"] / pop["n_baseline"]
    pop["abs_dev"] = (pop["phi_tile"] - 1.0).abs()
    pop = pop.dropna(subset=["lat", "lon", "phi_tile", "abs_dev"]).copy()
    pop = pop[np.isfinite(pop["phi_tile"].to_numpy(dtype=float)) & np.isfinite(pop["abs_dev"].to_numpy(dtype=float))].copy()
    pop = pop[pop["abs_dev"] >= float(cfg.min_abs_dev)].copy()
    if pop.empty:
        raise SystemExit("该窗口无足够 tile-level φ 信号（abs_dev 过滤后为空）")

    pop = pop.sort_values("abs_dev", ascending=False, kind="stable").head(int(cfg.top_k_tiles)).copy()

    # polyline segments (xy in km)
    lat_arr = track["lat"].to_numpy(dtype=float)
    lon_arr = track["lon"].to_numpy(dtype=float)
    lat0 = float(np.nanmean(lat_arr))
    lon0 = float(np.nanmean(lon_arr))
    x_tr, y_tr = _equirect_xy_km(lat_arr, lon_arr, lat0_deg=lat0, lon0_deg=lon0)
    seg_ax, seg_ay = x_tr[:-1], y_tr[:-1]
    seg_bx, seg_by = x_tr[1:], y_tr[1:]

    px, py = _equirect_xy_km(pop["lat"].to_numpy(dtype=float), pop["lon"].to_numpy(dtype=float), lat0_deg=lat0, lon0_deg=lon0)
    cx, cy, d_km = _nearest_point_on_polyline_xy(px, py, seg_ax=seg_ax, seg_ay=seg_ay, seg_bx=seg_bx, seg_by=seg_by)
    near_lat, near_lon = _xy_to_latlon_deg(cx, cy, lat0_deg=lat0, lon0_deg=lon0)
    pop["d_path_km"] = d_km
    pop["nearest_lat"] = near_lat
    pop["nearest_lon"] = near_lon

    out_csv = tabs / f"{cfg.slug}_top_tiles_t{int(round(float(t_at_S)))}h.csv"
    pop[["lat", "lon", "phi_tile", "abs_dev", "d_path_km", "nearest_lat", "nearest_lon"]].to_csv(out_csv, index=False)

    # map overlay (folium)
    try:
        import folium

        m = folium.Map(location=[float(np.nanmean(lat_arr)), float(np.nanmean(lon_arr))], zoom_start=6, tiles="OpenStreetMap")
        folium.PolyLine(list(zip(lat_arr.tolist(), lon_arr.tolist(), strict=False)), color="#111111", weight=3, opacity=0.9).add_to(m)

        if "status" in track.columns:
            land = track[track["status"].astype(str).str.strip().str.lower() == "landfall"]
            if not land.empty:
                rr = land.iloc[0]
                folium.Marker(
                    location=[float(rr["lat"]), float(rr["lon"])],
                    popup=f"{storm_name} landfall\\n{str(rr['datetime_utc'])}",
                    icon=folium.Icon(color="red", icon="info-sign"),
                ).add_to(m)

        for _, r in pop.iterrows():
            phi = float(r["phi_tile"])
            color = "#D55E00" if phi > 1.0 else "#0072B2"
            folium.CircleMarker(
                location=[float(r["lat"]), float(r["lon"])],
                radius=4,
                color=color,
                fill=True,
                fill_opacity=0.85,
                weight=1,
                popup=f"phi={phi:.3f}, |phi-1|={float(r['abs_dev']):.3f}, d_path={float(r['d_path_km']):.1f}km",
            ).add_to(m)
            folium.PolyLine(
                [(float(r["lat"]), float(r["lon"])), (float(r["nearest_lat"]), float(r["nearest_lon"]))],
                color="#777777",
                weight=1,
                opacity=0.6,
            ).add_to(m)

        out_html = figs / f"{cfg.slug}_track_overlay_t{int(round(float(t_at_S)))}h.html"
        m.save(str(out_html))
    except ModuleNotFoundError:
        out_html = None

    # static plot (no basemap)
    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    import matplotlib.pyplot as plt

    with ps.paper_style():
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        ax.plot(lon_arr, lat_arr, color=ps.OKABE_ITO["black"], linewidth=2.2, label="Track")
        ax.scatter(pop["lon"], pop["lat"], s=24, c=ps.OKABE_ITO["vermillion"], alpha=0.85, linewidths=0, label="Top tiles")
        ax.plot(
            np.vstack([pop["lon"].to_numpy(), pop["nearest_lon"].to_numpy()]),
            np.vstack([pop["lat"].to_numpy(), pop["nearest_lat"].to_numpy()]),
            color=ps.OKABE_ITO["gray"],
            linewidth=0.8,
            alpha=0.55,
        )
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.set_title(f"{cfg.slug}: track overlay (t={float(t_at_S):.0f}h, top_k={int(cfg.top_k_tiles)})")
        ax.legend(frameon=False)
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, figs / f"{cfg.slug}_track_overlay_t{int(round(float(t_at_S)))}h.png")
        plt.close(fig)


def cli_main() -> None:
    p = argparse.ArgumentParser(description="H3a: 路径几何 overlay（track + tile→path 最近距离示意）")
    p.add_argument("--output-root", type=Path, default=Path("outputs_trackpath"))
    p.add_argument("--slug", type=str, required=True)
    p.add_argument("--out-dir", type=Path, default=Path("outputs_trackpath/_tmp_h3a_track_overlay"))
    p.add_argument("--phase0-csv", type=Path, default=None, help="用于选择 t_at_S 的表（默认 outputs_trackpath/_tmp_h3a_track_collapse/...）")
    p.add_argument("--top-k-tiles", type=int, default=80)
    p.add_argument("--min-abs-dev", type=float, default=0.05)
    args = p.parse_args()

    cfg = Config(
        output_root=Path(args.output_root),
        slug=str(args.slug),
        out_dir=Path(args.out_dir),
        phase0_csv=Path(args.phase0_csv) if args.phase0_csv is not None else None,
        top_k_tiles=int(args.top_k_tiles),
        min_abs_dev=float(args.min_abs_dev),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()
