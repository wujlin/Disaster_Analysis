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
from disaster.movement_io import load_movement_file
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    movement_file: Path
    output_dir: Path
    center_lat: float
    center_lon: float

    start_min_km: float = 50.0
    start_max_km: float = 100.0
    cos_filter: str = "inward"  # inward (cos<0) | outward (cos>0)
    min_flow: float = 1.0
    top_n: int = 150

    curvature: float = 0.22
    n_curve_points: int = 24
    draw_basemap: bool = True
    write_html: bool = True


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _safe_cos(v_lat: np.ndarray, v_lon: np.ndarray, r_lat: np.ndarray, r_lon: np.ndarray) -> np.ndarray:
    dot = v_lat * r_lat + v_lon * r_lon
    v_norm = np.sqrt(v_lat * v_lat + v_lon * v_lon)
    r_norm = np.sqrt(r_lat * r_lat + r_lon * r_lon)
    denom = v_norm * r_norm
    cos = np.full(dot.shape, np.nan, dtype=float)
    ok = np.isfinite(dot) & np.isfinite(denom) & (denom > 0)
    cos[ok] = dot[ok] / denom[ok]
    return np.clip(cos, -1.0, 1.0)


def _lonlat_to_web_mercator(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    r = 6378137.0
    lon_rad = np.radians(lon.astype(float))
    lat_rad = np.radians(lat.astype(float))
    x = r * lon_rad
    y = r * np.log(np.tan(np.pi / 4.0 + lat_rad / 2.0))
    return x, y


def _circle_lonlat(lat0: float, lon0: float, radius_km: float, *, n: int = 360) -> tuple[np.ndarray, np.ndarray]:
    # 近似：1°lat≈110.574km, 1°lon≈111.320km*cos(lat)
    lat0 = float(lat0)
    lon0 = float(lon0)
    dlat = float(radius_km) / 110.574
    dlon = float(radius_km) / (111.320 * max(np.cos(np.radians(lat0)), 1e-6))
    th = np.linspace(0.0, 2 * np.pi, int(n), endpoint=True)
    lat = lat0 + dlat * np.cos(th)
    lon = lon0 + dlon * np.sin(th)
    return lon.astype(float), lat.astype(float)


def _quadratic_bezier(lon0: float, lat0: float, lon1: float, lat1: float, *, curvature: float, n: int) -> tuple[np.ndarray, np.ndarray]:
    p0 = np.array([float(lon0), float(lat0)], dtype=float)
    p2 = np.array([float(lon1), float(lat1)], dtype=float)
    d = p2 - p0
    dist = float(np.hypot(d[0], d[1]))
    if not np.isfinite(dist) or dist <= 0:
        return np.array([p0[0], p2[0]]), np.array([p0[1], p2[1]])
    perp = np.array([-d[1], d[0]], dtype=float)
    perp /= float(np.hypot(perp[0], perp[1]))
    p1 = (p0 + p2) / 2.0 + perp * float(curvature) * dist
    t = np.linspace(0.0, 1.0, int(max(n, 2)), endpoint=True)
    pts = (1 - t)[:, None] ** 2 * p0 + 2 * (1 - t)[:, None] * t[:, None] * p1 + t[:, None] ** 2 * p2
    return pts[:, 0].astype(float), pts[:, 1].astype(float)


def _load_and_filter(cfg: Config) -> pd.DataFrame:
    df = load_movement_file(Path(cfg.movement_file))
    nc = pd.to_numeric(df.get("n_crisis", np.nan), errors="coerce")
    slat = pd.to_numeric(df.get("start_lat", np.nan), errors="coerce")
    slon = pd.to_numeric(df.get("start_lon", np.nan), errors="coerce")
    elat = pd.to_numeric(df.get("end_lat", np.nan), errors="coerce")
    elon = pd.to_numeric(df.get("end_lon", np.nan), errors="coerce")

    keep = nc.notna() & (nc > float(cfg.min_flow)) & slat.notna() & slon.notna() & elat.notna() & elon.notna()
    sub = pd.DataFrame(
        {
            "start_lat": slat.where(keep),
            "start_lon": slon.where(keep),
            "end_lat": elat.where(keep),
            "end_lon": elon.where(keep),
            "n_crisis": nc.where(keep),
        }
    ).dropna()
    if sub.empty:
        return sub

    start_dist = haversine_km(
        sub["start_lat"].to_numpy(dtype=float),
        sub["start_lon"].to_numpy(dtype=float),
        float(cfg.center_lat),
        float(cfg.center_lon),
    )
    end_dist = haversine_km(
        sub["end_lat"].to_numpy(dtype=float),
        sub["end_lon"].to_numpy(dtype=float),
        float(cfg.center_lat),
        float(cfg.center_lon),
    )

    v_lat = sub["end_lat"].to_numpy(dtype=float) - sub["start_lat"].to_numpy(dtype=float)
    v_lon = sub["end_lon"].to_numpy(dtype=float) - sub["start_lon"].to_numpy(dtype=float)
    r_lat = sub["start_lat"].to_numpy(dtype=float) - float(cfg.center_lat)
    r_lon = sub["start_lon"].to_numpy(dtype=float) - float(cfg.center_lon)
    cos_alpha = _safe_cos(v_lat, v_lon, r_lat, r_lon)

    sub = sub.assign(start_distance_km=start_dist, end_distance_km=end_dist, cos_alpha=cos_alpha)
    sub = sub[np.isfinite(sub["cos_alpha"]) & np.isfinite(sub["start_distance_km"])].copy()
    sub = sub[(sub["start_distance_km"] >= float(cfg.start_min_km)) & (sub["start_distance_km"] < float(cfg.start_max_km))].copy()
    if cfg.cos_filter == "outward":
        sub = sub[sub["cos_alpha"] > 0].copy()
    else:
        sub = sub[sub["cos_alpha"] < 0].copy()
    sub = sub.sort_values("n_crisis", ascending=False, kind="stable")
    if int(cfg.top_n) > 0:
        sub = sub.head(int(cfg.top_n)).copy()
    return sub.reset_index(drop=True)


def _plot_static_png(df: pd.DataFrame, cfg: Config, *, out_path: Path) -> None:
    if df.empty:
        raise SystemExit("筛选后无 OD（检查距离带/方向/阈值/top_n）")

    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    # scale line width by sqrt(flow)
    w = df["n_crisis"].to_numpy(dtype=float)
    w_s = np.sqrt(np.maximum(w, 0.0))
    w_min, w_max = float(np.nanmin(w_s)), float(np.nanmax(w_s))
    min_lw, max_lw = 0.7, 4.2
    if np.isfinite(w_min) and np.isfinite(w_max) and w_max > w_min:
        lw = min_lw + (w_s - w_min) / (w_max - w_min) * (max_lw - min_lw)
    else:
        lw = np.full(w_s.shape, 1.6, dtype=float)

    # color by cos_alpha (inward: [-1,0], outward: [0,1])
    cos = df["cos_alpha"].to_numpy(dtype=float)
    vmin, vmax = (-1.0, 0.0) if cfg.cos_filter == "inward" else (0.0, 1.0)

    with ps.paper_style():
        import matplotlib.pyplot as plt
        from matplotlib import cm
        from matplotlib.colors import Normalize

        fig, ax = plt.subplots(figsize=(ps.FIGSIZE_FULL[0], ps.FIGSIZE_FULL[1] * 1.05))

        # basemap (optional): needs contextily + network
        has_basemap = False
        if cfg.draw_basemap:
            try:
                import contextily as ctx  # type: ignore

                has_basemap = True
            except Exception:
                has_basemap = False

        # Precompute bounds in web mercator
        all_lon = np.concatenate([df["start_lon"].to_numpy(dtype=float), df["end_lon"].to_numpy(dtype=float)])
        all_lat = np.concatenate([df["start_lat"].to_numpy(dtype=float), df["end_lat"].to_numpy(dtype=float)])
        x_all, y_all = _lonlat_to_web_mercator(all_lon, all_lat)
        pad = 15000.0  # ~15km
        ax.set_xlim(float(np.nanmin(x_all) - pad), float(np.nanmax(x_all) + pad))
        ax.set_ylim(float(np.nanmin(y_all) - pad), float(np.nanmax(y_all) + pad))

        if has_basemap:
            try:
                import contextily as ctx  # type: ignore

                ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik, crs="EPSG:3857", attribution_size=7)
            except Exception:
                pass

        norm = Normalize(vmin=vmin, vmax=vmax)
        cmap = cm.get_cmap("Blues_r" if cfg.cos_filter == "inward" else "Reds")

        for r, width in zip(df.itertuples(index=False), lw, strict=False):
            lon_curve, lat_curve = _quadratic_bezier(
                r.start_lon,
                r.start_lat,
                r.end_lon,
                r.end_lat,
                curvature=float(cfg.curvature),
                n=int(cfg.n_curve_points),
            )
            x, y = _lonlat_to_web_mercator(lon_curve, lat_curve)
            c = cmap(norm(float(r.cos_alpha)))
            ax.plot(x, y, color=c, linewidth=float(width), alpha=0.75)

        # epicenter + circles
        cx, cy = _lonlat_to_web_mercator(np.array([float(cfg.center_lon)]), np.array([float(cfg.center_lat)]))
        ax.scatter(cx, cy, s=110, c=ps.OKABE_ITO["vermillion"], marker="*", edgecolors="black", linewidths=0.8, zorder=5)

        for rad in [25.0, 50.0, 100.0]:
            lon_c, lat_c = _circle_lonlat(float(cfg.center_lat), float(cfg.center_lon), float(rad), n=300)
            x_c, y_c = _lonlat_to_web_mercator(lon_c, lat_c)
            ax.plot(x_c, y_c, color=ps.OKABE_ITO["black"], linestyle=":", linewidth=1.0, alpha=0.75)

        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(
            f"Intraband OD streamlines ({cfg.cos_filter}, start in [{cfg.start_min_km:g},{cfg.start_max_km:g})km)\\nTop {len(df)} by n_crisis"
        )
        ps.despine(ax)

        sm = cm.ScalarMappable(norm=norm, cmap=cmap)
        sm.set_array([])
        cb = fig.colorbar(sm, ax=ax, shrink=0.82)
        cb.set_label(r"$\cos(\alpha)$")

        fig.tight_layout()
        save_png_and_pdf(ps, fig, out_path)
        plt.close(fig)


def _write_folium_html(df: pd.DataFrame, cfg: Config, *, out_html: Path) -> None:
    if df.empty:
        raise SystemExit("筛选后无 OD（检查距离带/方向/阈值/top_n）")
    try:
        import folium  # type: ignore
    except ModuleNotFoundError as e:
        raise SystemExit("缺少依赖：folium。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

    from matplotlib import cm
    from matplotlib.colors import Normalize, to_hex

    vmin, vmax = (-1.0, 0.0) if cfg.cos_filter == "inward" else (0.0, 1.0)
    norm = Normalize(vmin=vmin, vmax=vmax)
    cmap = cm.get_cmap("Blues_r" if cfg.cos_filter == "inward" else "Reds")

    # line width scaling
    w = df["n_crisis"].to_numpy(dtype=float)
    w_s = np.sqrt(np.maximum(w, 0.0))
    w_min, w_max = float(np.nanmin(w_s)), float(np.nanmax(w_s))
    min_lw, max_lw = 1.0, 6.0
    if np.isfinite(w_min) and np.isfinite(w_max) and w_max > w_min:
        lw = min_lw + (w_s - w_min) / (w_max - w_min) * (max_lw - min_lw)
    else:
        lw = np.full(w_s.shape, 2.4, dtype=float)

    m = folium.Map(location=[float(cfg.center_lat), float(cfg.center_lon)], zoom_start=8, tiles="OpenStreetMap")

    # circles
    for rad in [25.0, 50.0, 100.0]:
        folium.Circle(
            location=[float(cfg.center_lat), float(cfg.center_lon)],
            radius=float(rad) * 1000.0,
            color="#000000",
            weight=1,
            fill=False,
            opacity=0.6,
            dash_array="6,6",
        ).add_to(m)

    # epicenter
    folium.Marker(
        location=[float(cfg.center_lat), float(cfg.center_lon)],
        icon=folium.Icon(color="red", icon="star", prefix="fa"),
        popup="Center",
    ).add_to(m)

    for r, width in zip(df.itertuples(index=False), lw, strict=False):
        lon_curve, lat_curve = _quadratic_bezier(
            r.start_lon,
            r.start_lat,
            r.end_lon,
            r.end_lat,
            curvature=float(cfg.curvature),
            n=int(cfg.n_curve_points),
        )
        pts = list(zip(lat_curve.tolist(), lon_curve.tolist(), strict=False))
        color = to_hex(cmap(norm(float(r.cos_alpha))))
        folium.PolyLine(
            locations=[(float(a), float(b)) for a, b in pts],
            color=color,
            weight=float(width),
            opacity=0.75,
        ).add_to(m)

    # fit bounds
    lat_all = np.concatenate([df["start_lat"].to_numpy(dtype=float), df["end_lat"].to_numpy(dtype=float)])
    lon_all = np.concatenate([df["start_lon"].to_numpy(dtype=float), df["end_lon"].to_numpy(dtype=float)])
    bounds = [[float(np.nanmin(lat_all)), float(np.nanmin(lon_all))], [float(np.nanmax(lat_all)), float(np.nanmax(lon_all))]]
    m.fit_bounds(bounds, padding=(20, 20))

    out_html.write_text(m.get_root().render(), encoding="utf-8")


def run(cfg: Config) -> None:
    _ensure_dir(cfg.output_dir)

    df = _load_and_filter(cfg)
    base = f"flow_map_{cfg.cos_filter}_{int(cfg.start_min_km)}_{int(cfg.start_max_km)}km"

    out_png = Path(cfg.output_dir) / f"{base}.png"
    _plot_static_png(df, cfg, out_path=out_png)

    if cfg.write_html:
        out_html = Path(cfg.output_dir) / f"{base}.html"
        _write_folium_html(df, cfg, out_html=out_html)

    out_csv = Path(cfg.output_dir) / "selected_flows.csv"
    df.to_csv(out_csv, index=False)
    print(f"Done. Wrote: {out_png}")
    if cfg.write_html:
        print(f"Done. Wrote: {out_html}")
    print(f"Done. Wrote: {out_csv}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--movement-file", type=Path, required=True, help="输入 movement 单窗口 CSV")
    parser.add_argument("--output-dir", type=Path, required=True, help="输出目录（例如 outputs/turkiye_earthquake_2023/intraband_flow_viz）")
    parser.add_argument("--center-lat", type=float, required=True, help="震中纬度")
    parser.add_argument("--center-lon", type=float, required=True, help="震中经度")
    parser.add_argument("--start-min-km", type=float, default=50.0, help="起点距离下界（km，默认 50）")
    parser.add_argument("--start-max-km", type=float, default=100.0, help="起点距离上界（km，默认 100）")
    parser.add_argument("--cos-filter", type=str, choices=["inward", "outward"], default="inward", help="方向筛选（inward: cos<0；outward: cos>0）")
    parser.add_argument("--min-flow", type=float, default=1.0, help="保留的最小 n_crisis（默认 1）")
    parser.add_argument("--top-n", type=int, default=150, help="取 top N OD（默认 150）")
    parser.add_argument("--curvature", type=float, default=0.22, help="弧线弯曲系数（默认 0.22）")
    parser.add_argument("--n-curve-points", type=int, default=24, help="每条弧线采样点数（默认 24）")
    parser.add_argument("--no-basemap", action="store_true", help="不尝试加载 contextily 底图（默认会尝试）")
    parser.add_argument("--no-html", action="store_true", help="不输出 folium HTML（默认输出）")
    args = parser.parse_args()

    cfg = Config(
        movement_file=Path(args.movement_file),
        output_dir=Path(args.output_dir),
        center_lat=float(args.center_lat),
        center_lon=float(args.center_lon),
        start_min_km=float(args.start_min_km),
        start_max_km=float(args.start_max_km),
        cos_filter=str(args.cos_filter),
        min_flow=float(args.min_flow),
        top_n=int(args.top_n),
        curvature=float(args.curvature),
        n_curve_points=int(args.n_curve_points),
        draw_basemap=not bool(args.no_basemap),
        write_html=not bool(args.no_html),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()

