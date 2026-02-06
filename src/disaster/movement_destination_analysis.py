from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.geo import distance_bin_labels, haversine_km
from disaster.movement_io import load_movement_file
from disaster.population_io import parse_window_start_pt, resolve_subdir
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    data_root: Path
    output_dir: Path
    center_lat: float
    center_lon: float
    t0_pt: pd.Timestamp

    slug: str | None = None
    only_hour_pt: int = 8
    min_hours: float = -16.0
    max_hours: float = 832.0

    target_hours: float = 40.0
    distance_bins_km: tuple[float, ...] = (0.0, 25.0, 50.0, 100.0, 200.0, float("inf"))
    start_band: str = "50-100km"
    cos_filter: str = "inward"  # inward (<0) | outward (>0)

    min_flow: float = 1.0
    clip_cos: bool = True

    hist_bin_km: float = 10.0
    hist_max_km: float = 500.0


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _parse_movement_window_start(path: Path) -> pd.Timestamp:
    try:
        return pd.Timestamp(parse_window_start_pt(path))
    except Exception:
        head = pd.read_csv(path, usecols=lambda c: c == "date_time", na_values=["\\N", ""], nrows=1)
        if "date_time" not in head.columns or head.empty:
            raise ValueError(f"无法解析窗口时间（文件名与 date_time 均失败）：{path.name}")
        return pd.Timestamp(pd.to_datetime(head["date_time"].iloc[0], errors="coerce"))


def _list_movement_windows(cfg: Config) -> list[dict]:
    mov_dir = resolve_subdir(cfg.data_root, "movement")

    files = sorted(mov_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"目录为空：{mov_dir}")

    rows: list[dict] = []
    for path in files:
        ts = _parse_movement_window_start(path)
        if int(ts.hour) != int(cfg.only_hour_pt):
            continue
        hs = float((pd.Timestamp(ts) - pd.Timestamp(cfg.t0_pt)).total_seconds() / 3600.0)
        if hs < float(cfg.min_hours) or hs > float(cfg.max_hours):
            continue
        rows.append({"path": path, "window_start_pt": pd.Timestamp(ts), "hours_since_quake": hs})

    rows = sorted(rows, key=lambda r: float(r["hours_since_quake"]))
    if not rows:
        raise FileNotFoundError(f"未找到符合条件的 movement 窗口：hour={cfg.only_hour_pt}, t∈[{cfg.min_hours},{cfg.max_hours}]")
    return rows


def _pick_nearest_window(windows: list[dict], target_hours: float) -> dict:
    return min(windows, key=lambda r: abs(float(r["hours_since_quake"]) - float(target_hours)))


def _distance_band_indices(dist_km: np.ndarray, bins_km: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(bins_km, dist_km.astype(float), side="right") - 1
    return idx.astype(int)


def _safe_cos(v_lat: np.ndarray, v_lon: np.ndarray, r_lat: np.ndarray, r_lon: np.ndarray, *, clip: bool) -> np.ndarray:
    dot = v_lat * r_lat + v_lon * r_lon
    v_norm = np.sqrt(v_lat * v_lat + v_lon * v_lon)
    r_norm = np.sqrt(r_lat * r_lat + r_lon * r_lon)
    denom = v_norm * r_norm
    cos = np.full(dot.shape, np.nan, dtype=float)
    ok = np.isfinite(dot) & np.isfinite(denom) & (denom > 0)
    cos[ok] = dot[ok] / denom[ok]
    if clip:
        cos = np.clip(cos, -1.0, 1.0)
    return cos


def run(cfg: Config) -> None:
    out_root = Path(cfg.output_dir)
    out_fig = out_root / "figures"
    out_tab = out_root / "tables"
    _ensure_dir(out_root)
    _ensure_dir(out_fig)
    _ensure_dir(out_tab)

    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    bins_km = np.array(cfg.distance_bins_km, dtype=float)
    if bins_km.ndim != 1 or bins_km.size < 2:
        raise ValueError("distance_bins_km 至少需要 2 个边界值")
    if not np.isinf(bins_km[-1]):
        bins_km = np.concatenate([bins_km, [float("inf")]])
    labels = distance_bin_labels(bins_km)
    if str(cfg.start_band) not in set(labels):
        raise ValueError(f"start_band 不在可用距离带中：{cfg.start_band}；可选：{labels}")
    n_bands = int(len(labels))
    start_band_idx = int(labels.index(str(cfg.start_band)))

    windows = _list_movement_windows(cfg)
    picked = _pick_nearest_window(windows, float(cfg.target_hours))
    path = Path(picked["path"])
    window_start = pd.Timestamp(picked["window_start_pt"])
    hs = float(picked["hours_since_quake"])

    df = load_movement_file(path)
    nc = pd.to_numeric(df.get("n_crisis", np.nan), errors="coerce").to_numpy(dtype=float)
    slat = pd.to_numeric(df.get("start_lat", np.nan), errors="coerce").to_numpy(dtype=float)
    slon = pd.to_numeric(df.get("start_lon", np.nan), errors="coerce").to_numpy(dtype=float)
    elat = pd.to_numeric(df.get("end_lat", np.nan), errors="coerce").to_numpy(dtype=float)
    elon = pd.to_numeric(df.get("end_lon", np.nan), errors="coerce").to_numpy(dtype=float)

    keep = np.isfinite(nc) & (nc > float(cfg.min_flow)) & np.isfinite(slat) & np.isfinite(slon) & np.isfinite(elat) & np.isfinite(elon)
    if not np.any(keep):
        raise SystemExit("该窗口无有效 OD（n_crisis 与坐标过滤后为空）")

    nc = nc[keep]
    slat = slat[keep]
    slon = slon[keep]
    elat = elat[keep]
    elon = elon[keep]

    v_lat = elat - slat
    v_lon = elon - slon
    r_lat = slat - float(cfg.center_lat)
    r_lon = slon - float(cfg.center_lon)
    cos_alpha = _safe_cos(v_lat, v_lon, r_lat, r_lon, clip=bool(cfg.clip_cos))

    sdist = haversine_km(slat, slon, float(cfg.center_lat), float(cfg.center_lon))
    edist = haversine_km(elat, elon, float(cfg.center_lat), float(cfg.center_lon))
    sidx = _distance_band_indices(sdist, bins_km)
    eidx = _distance_band_indices(edist, bins_km)

    ok = np.isfinite(cos_alpha) & np.isfinite(sdist) & np.isfinite(edist) & (sidx >= 0) & (sidx < n_bands) & (eidx >= 0) & (eidx < n_bands)
    nc = nc[ok]
    cos_alpha = cos_alpha[ok]
    sidx = sidx[ok].astype(int)
    eidx = eidx[ok].astype(int)
    edist = edist[ok].astype(float)

    if cfg.cos_filter == "outward":
        sel = (sidx == start_band_idx) & (cos_alpha > 0)
        cos_desc = "cos_alpha > 0 (outward)"
    else:
        sel = (sidx == start_band_idx) & (cos_alpha < 0)
        cos_desc = "cos_alpha < 0 (inward)"

    if not np.any(sel):
        raise SystemExit("筛选后无样本（检查 start_band / cos_filter / target_hours）")

    nc_sel = nc[sel]
    eidx_sel = eidx[sel]
    edist_sel = edist[sel]
    sdist_sel = sdist[ok][sel].astype(float)

    total_flow = float(np.nansum(nc_sel))
    n_od = int(nc_sel.size)

    dest_flow_by_band = np.bincount(eidx_sel, weights=nc_sel, minlength=n_bands).astype(float)
    dest_rows: list[dict] = []
    for k, band in enumerate(labels):
        w = float(dest_flow_by_band[k])
        dest_rows.append(
            {
                "dest_band": str(band),
                "flow_sum": w,
                "flow_fraction": (w / total_flow) if total_flow > 0 else float("nan"),
            }
        )
    dest_df = pd.DataFrame(dest_rows)
    dest_df["dest_band"] = pd.Categorical(dest_df["dest_band"], categories=[str(x) for x in labels], ordered=True)
    dest_df = dest_df.sort_values(["dest_band"], kind="stable").reset_index(drop=True)
    out_dest = out_tab / "destination_band_shares.csv"
    dest_df.to_csv(out_dest, index=False)

    # histogram of destination distance
    step = float(cfg.hist_bin_km)
    max_r = float(cfg.hist_max_km)
    edges = np.arange(0.0, max_r + 1e-9, step, dtype=float)
    if edges.size < 2:
        raise ValueError("hist_bin_km/hist_max_km 配置不合法")
    hist, _ = np.histogram(edist_sel, bins=edges, weights=nc_sel)
    centers = 0.5 * (edges[:-1] + edges[1:])
    hist_df = pd.DataFrame(
        {
            "bin_left_km": edges[:-1].astype(float),
            "bin_right_km": edges[1:].astype(float),
            "bin_center_km": centers.astype(float),
            "flow_sum": hist.astype(float),
        }
    )
    hist_df["flow_fraction"] = hist_df["flow_sum"] / total_flow if total_flow > 0 else np.nan
    out_hist = out_tab / "destination_distance_hist.csv"
    hist_df.to_csv(out_hist, index=False)

    # origin distance histogram (for Task A)
    hist_o, _ = np.histogram(sdist_sel, bins=edges, weights=nc_sel)
    origin_df = pd.DataFrame(
        {
            "bin_left_km": edges[:-1].astype(float),
            "bin_right_km": edges[1:].astype(float),
            "bin_center_km": centers.astype(float),
            "flow_sum": hist_o.astype(float),
        }
    )
    origin_df["flow_fraction"] = origin_df["flow_sum"] / total_flow if total_flow > 0 else np.nan
    out_origin = out_tab / "origin_distance_hist.csv"
    origin_df.to_csv(out_origin, index=False)

    # summary
    share_0_25 = float(dest_df.loc[dest_df["dest_band"] == "0-25km", "flow_fraction"].iloc[0]) if "0-25km" in set(dest_df["dest_band"].astype(str)) else float("nan")
    share_25_50 = float(dest_df.loc[dest_df["dest_band"] == "25-50km", "flow_fraction"].iloc[0]) if "25-50km" in set(dest_df["dest_band"].astype(str)) else float("nan")
    summary = pd.DataFrame(
        [
            {
                "slug": cfg.slug,
                "picked_window_start_pt": str(window_start),
                "picked_hours_since_quake": float(hs),
                "movement_file": str(path.name),
                "start_band": str(cfg.start_band),
                "cos_filter": str(cfg.cos_filter),
                "n_od": int(n_od),
                "total_flow_sum": float(total_flow),
                "share_dest_0_25km": share_0_25,
                "share_dest_25_50km": share_25_50,
            }
        ]
    )
    out_sum = out_tab / "destination_analysis_summary.csv"
    summary.to_csv(out_sum, index=False)

    # plot histogram
    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        ax.plot(hist_df["bin_center_km"], hist_df["flow_fraction"], color=ps.OKABE_ITO["blue"], linewidth=2.4)
        ax.set_xlabel("Destination distance to center (km)")
        ax.set_ylabel("Flow fraction (weighted by n_crisis)")
        title_label = cfg.slug or "event"
        ax.set_title(f"Destination distance histogram ({title_label})\\nstart={cfg.start_band}, {cos_desc}, t={hs:g}h")
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out_fig / "destination_distance_hist.png")
        plt.close(fig)

    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        ax.plot(origin_df["bin_center_km"], origin_df["flow_fraction"], color=ps.OKABE_ITO["vermillion"], linewidth=2.4)
        ax.set_xlabel("Origin distance to center (km)")
        ax.set_ylabel("Flow fraction (weighted by n_crisis)")
        title_label = cfg.slug or "event"
        ax.set_title(f"Origin distance histogram ({title_label})\\nstart={cfg.start_band}, {cos_desc}, t={hs:g}h")
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out_fig / "origin_distance_hist.png")
        plt.close(fig)

    readme = f"""# Movement 终点分析（按方向筛选）

本目录用于验证：在指定时间窗口 t、指定起点距离带 start_band 下，方向筛选（cos_alpha）后的流动终点主要落在哪些距离范围/距离带。

## 本次运行配置

- slug: {cfg.slug}
- center: ({float(cfg.center_lat):.4f}, {float(cfg.center_lon):.4f})
- t0_pt: {pd.Timestamp(cfg.t0_pt)}
- only_hour_pt: {int(cfg.only_hour_pt)}
- target_hours: {float(cfg.target_hours):g}（实际选取最近窗口 hs={hs:g}）
- start_band: {cfg.start_band}
- cos_filter: {cos_desc}
- distance_bins_km: {list(float(x) for x in bins_km)}

## 输出

- `tables/destination_analysis_summary.csv`：本次筛选的样本量与关键比例
- `tables/destination_band_shares.csv`：终点落入各距离带的流量占比
- `tables/destination_distance_hist.csv`：终点距离分布（按 n_crisis 加权）
- `tables/origin_distance_hist.csv`：起点距离分布（按 n_crisis 加权）
- `figures/destination_distance_hist.*`：终点距离直方图（流量占比）
- `figures/origin_distance_hist.*`：起点距离直方图（流量占比）
"""
    (out_root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_sum}")
    print(f"Done. Wrote: {out_dest}")
    print(f"Done. Wrote: {out_hist}")
    print(f"Done. Wrote: {out_origin}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True, help="数据根目录（包含 movement/）")
    parser.add_argument("--output-dir", type=Path, required=True, help="输出目录（例如 outputs/<slug>/movement_destination_analysis）")
    parser.add_argument("--center-lat", type=float, required=True, help="中心点纬度（震中/灾害中心）")
    parser.add_argument("--center-lon", type=float, required=True, help="中心点经度（震中/灾害中心）")
    parser.add_argument("--t0-pt", type=str, required=True, help="t=0 的 PT 时间戳（例如 2023-02-05 16:00）")
    parser.add_argument("--slug", type=str, default=None, help="用于 README 的标签（默认 None）")

    parser.add_argument("--only-hour-pt", type=int, default=8, help="仅使用该小时（PT）的窗口（默认 08:00）")
    parser.add_argument("--min-hours", type=float, default=-16.0, help="最小 hours_since_quake（默认 -16）")
    parser.add_argument("--max-hours", type=float, default=832.0, help="最大 hours_since_quake（默认 832）")
    parser.add_argument("--target-hours", type=float, default=40.0, help="目标时刻（小时，默认 40h）")
    parser.add_argument("--distance-bins-km", type=float, nargs="*", default=[0, 25, 50, 100, 200], help="距离带边界（km，不含 inf）")
    parser.add_argument("--start-band", type=str, default="50-100km", help="筛选起点距离带（默认 50-100km）")
    parser.add_argument("--cos-filter", type=str, choices=["inward", "outward"], default="inward", help="方向筛选（inward: cos<0; outward: cos>0）")
    parser.add_argument("--min-flow", type=float, default=1.0, help="保留的最小 n_crisis（默认 1）")
    parser.add_argument("--no-clip-cos", action="store_true", help="不对 cos_alpha 裁剪到 [-1,1]")
    parser.add_argument("--hist-bin-km", type=float, default=10.0, help="终点距离直方图 bin 宽度（km，默认 10）")
    parser.add_argument("--hist-max-km", type=float, default=500.0, help="终点距离直方图最大距离（km，默认 500）")
    args = parser.parse_args()

    bins = [float(x) for x in args.distance_bins_km]
    if not bins or bins[0] != 0.0:
        bins = [0.0] + bins
    bins = sorted(set(bins))
    bins.append(float("inf"))

    cfg = Config(
        data_root=args.data_root,
        output_dir=args.output_dir,
        center_lat=float(args.center_lat),
        center_lon=float(args.center_lon),
        t0_pt=pd.Timestamp(str(args.t0_pt)),
        slug=(str(args.slug).strip() if args.slug else None),
        only_hour_pt=int(args.only_hour_pt),
        min_hours=float(args.min_hours),
        max_hours=float(args.max_hours),
        target_hours=float(args.target_hours),
        distance_bins_km=tuple(float(x) for x in bins),
        start_band=str(args.start_band),
        cos_filter=str(args.cos_filter),
        min_flow=float(args.min_flow),
        clip_cos=not bool(args.no_clip_cos),
        hist_bin_km=float(args.hist_bin_km),
        hist_max_km=float(args.hist_max_km),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()
