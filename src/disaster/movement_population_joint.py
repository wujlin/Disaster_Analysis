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
from disaster.population_io import load_population_file, parse_window_start_pt, resolve_subdir
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    data_root: Path
    output_dir: Path
    epicenter_lat: float = 37.174
    epicenter_lon: float = 37.032
    t0_pt: pd.Timestamp = pd.Timestamp("2023-02-05 16:00")
    only_hour_pt: int = 8
    min_edge_weight: float = 10.0
    long_distance_threshold_km: float = 10.0
    hub_threshold: float = 2.0
    snapshot_offsets_hours: tuple[float, ...] = (-8.0, 16.0, 40.0, 88.0, 160.0, 328.0, 832.0)
    hub_pre_offset_hours: float = -8.0
    hub_post_offset_hours: float = 16.0


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _list_windows(data_root: Path, *, subdir: str, t0_pt: pd.Timestamp, only_hour_pt: int) -> dict[pd.Timestamp, dict]:
    try:
        d = resolve_subdir(data_root, subdir)
    except FileNotFoundError:
        return {}
    out: dict[pd.Timestamp, dict] = {}
    for path in sorted(d.glob("*.csv")):
        window_start = parse_window_start_pt(path)
        if int(window_start.hour) != int(only_hour_pt):
            continue
        hours = float((window_start - t0_pt).total_seconds() / 3600.0)
        out[pd.Timestamp(window_start)] = {"path": str(path), "window_start_pt": pd.Timestamp(window_start), "hours_since_quake": hours}
    return out


def _pick_nearest_common(
    common: list[dict],
    offsets: tuple[float, ...],
) -> list[dict]:
    if not common:
        return []
    picked: list[dict] = []
    for off in offsets:
        best = min(common, key=lambda r: abs(float(r["hours_since_quake"]) - float(off)))
        picked.append(best)
    seen = set()
    uniq: list[dict] = []
    for r in picked:
        key = (pd.Timestamp(r["window_start_pt"]), float(r["hours_since_quake"]))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq


def _build_undirected_edges(df_mov: pd.DataFrame, *, min_edge_weight: float) -> pd.DataFrame:
    w = pd.to_numeric(df_mov.get("n_crisis", np.nan), errors="coerce")
    u_raw = df_mov.get("start_quadkey")
    v_raw = df_mov.get("end_quadkey")
    d_raw = pd.to_numeric(df_mov.get("length_km", np.nan), errors="coerce")

    if u_raw is None or v_raw is None:
        return pd.DataFrame({"u": [], "v": [], "w": [], "distance_km": []})

    mask = u_raw.notna() & v_raw.notna() & w.notna() & (w >= float(min_edge_weight))
    sub = df_mov.loc[mask, ["start_quadkey", "end_quadkey"]].copy()
    sub["w"] = w.loc[mask].to_numpy(dtype=float)
    sub["distance_km"] = d_raw.loc[mask].to_numpy(dtype=float)
    sub = sub[sub["start_quadkey"] != sub["end_quadkey"]].copy()
    if sub.empty:
        return pd.DataFrame({"u": [], "v": [], "w": [], "distance_km": []})

    u = sub["start_quadkey"].astype(str).to_numpy()
    v = sub["end_quadkey"].astype(str).to_numpy()
    u2 = np.minimum(u, v)
    v2 = np.maximum(u, v)
    edges = pd.DataFrame({"u": u2, "v": v2, "w": sub["w"].to_numpy(dtype=float), "distance_km": sub["distance_km"].to_numpy(dtype=float)})
    edges = edges.groupby(["u", "v"], as_index=False).agg(w=("w", "sum"), distance_km=("distance_km", "mean"))
    return edges


def _identify_hubs(edges: pd.DataFrame, *, hub_threshold: float) -> tuple[dict[str, float], set[str]]:
    if edges.empty:
        return {}, set()
    nodes = pd.Index(pd.unique(pd.concat([edges["u"], edges["v"]], ignore_index=True))).astype(str)
    n_nodes = int(nodes.size)
    n_edges = int(len(edges))
    avg_degree = float(2.0 * n_edges / n_nodes) if n_nodes > 0 else 0.0
    deg = pd.concat([edges["u"], edges["v"]], ignore_index=True).astype(str).value_counts().to_dict()
    hubs = {n for n, d in deg.items() if float(d) > float(hub_threshold) * avg_degree}
    return {k: float(v) for k, v in deg.items()}, set(hubs)


def run(cfg: Config) -> None:
    mov_map = _list_windows(cfg.data_root, subdir="movement", t0_pt=cfg.t0_pt, only_hour_pt=cfg.only_hour_pt)
    pop_map = _list_windows(cfg.data_root, subdir="population", t0_pt=cfg.t0_pt, only_hour_pt=cfg.only_hour_pt)
    if not mov_map:
        raise FileNotFoundError(f"未找到 movement 数据（hour={cfg.only_hour_pt}）：{cfg.data_root / 'movement'}")
    if not pop_map:
        raise FileNotFoundError(f"未找到 population 数据（hour={cfg.only_hour_pt}）：{cfg.data_root / 'population'}")

    common_keys = sorted(set(mov_map.keys()) & set(pop_map.keys()))
    if not common_keys:
        raise RuntimeError("movement 与 population 没有共同的 08:00 窗口（请检查数据是否同一批次）")

    common = [mov_map[k] | {"population_path": pop_map[k]["path"]} for k in common_keys]
    picked = _pick_nearest_common(common, cfg.snapshot_offsets_hours)
    if not picked:
        raise RuntimeError("无法选择代表性窗口（common windows 为空）")

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

    tile_rows: list[pd.DataFrame] = []
    corr_rows: list[dict] = []

    picked_by_hours = {float(r["hours_since_quake"]): r for r in picked}

    # 选取 hub pre/post 窗口
    hub_pre = min(picked, key=lambda r: abs(float(r["hours_since_quake"]) - float(cfg.hub_pre_offset_hours)))
    hub_post = min(picked, key=lambda r: abs(float(r["hours_since_quake"]) - float(cfg.hub_post_offset_hours)))

    hub_pre_df_mov = load_movement_file(Path(hub_pre["path"]))
    hub_post_df_mov = load_movement_file(Path(hub_post["path"]))
    hub_post_df_pop = load_population_file(Path(hub_post["population_path"]))

    edges_pre = _build_undirected_edges(hub_pre_df_mov, min_edge_weight=cfg.min_edge_weight)
    edges_post = _build_undirected_edges(hub_post_df_mov, min_edge_weight=cfg.min_edge_weight)
    deg_pre, hubs_pre = _identify_hubs(edges_pre, hub_threshold=cfg.hub_threshold)
    deg_post, hubs_post = _identify_hubs(edges_post, hub_threshold=cfg.hub_threshold)
    new_hubs = hubs_post - hubs_pre

    # coords：优先用 population（更稳定），缺失再用 movement
    pop_coords = (
        hub_post_df_pop[["quadkey", "lat", "lon"]]
        .dropna()
        .astype({"quadkey": "string"})
        .drop_duplicates(subset=["quadkey"])
        .set_index("quadkey")[["lat", "lon"]]
    )
    coords: dict[str, tuple[float, float]] = {str(k): (float(v["lat"]), float(v["lon"])) for k, v in pop_coords.iterrows()}

    for src_col, lat_col, lon_col, qcol in [
        ("start", "start_lat", "start_lon", "start_quadkey"),
        ("end", "end_lat", "end_lon", "end_quadkey"),
    ]:
        if {lat_col, lon_col, qcol} <= set(hub_post_df_mov.columns):
            tmp = hub_post_df_mov[[qcol, lat_col, lon_col]].dropna()
            for q, la, lo in tmp.itertuples(index=False):
                key = str(q)
                if key not in coords and np.isfinite(la) and np.isfinite(lo):
                    coords[key] = (float(la), float(lo))

    hub_rows: list[dict] = []
    for node in sorted(hubs_pre | hubs_post):
        lat_lon = coords.get(str(node), (float("nan"), float("nan")))
        lat, lon = lat_lon
        dist = float("nan")
        if np.isfinite(lat) and np.isfinite(lon):
            dist = float(haversine_km(np.array([lat]), np.array([lon]), cfg.epicenter_lat, cfg.epicenter_lon)[0])
        hub_rows.append(
            {
                "quadkey": str(node),
                "is_pre_hub": int(node in hubs_pre),
                "is_post_hub": int(node in hubs_post),
                "is_new_hub": int(node in new_hubs),
                "degree_pre": float(deg_pre.get(str(node), 0.0)),
                "degree_post": float(deg_post.get(str(node), 0.0)),
                "lat": lat,
                "lon": lon,
                "distance_to_epicenter_km": dist,
                "hub_pre_hours_since_quake": float(hub_pre["hours_since_quake"]),
                "hub_post_hours_since_quake": float(hub_post["hours_since_quake"]),
            }
        )
    hub_comp = pd.DataFrame(hub_rows).sort_values(["is_new_hub", "degree_post"], ascending=[False, False], kind="stable")
    out_hub = out.tables / "hub_comparison.csv"
    hub_comp.to_csv(out_hub, index=False)

    # tile-level joint metrics（代表性窗口）
    for hs, meta in picked_by_hours.items():
        df_pop = load_population_file(Path(meta["population_path"]))
        df_mov = load_movement_file(Path(meta["path"]))

        pop = df_pop[["quadkey", "lat", "lon", "n_baseline", "n_crisis"]].copy()
        pop["quadkey"] = pop["quadkey"].astype("string")
        pop["n_baseline"] = pd.to_numeric(pop["n_baseline"], errors="coerce")
        pop["n_crisis"] = pd.to_numeric(pop["n_crisis"], errors="coerce")
        pop["phi_ratio"] = pop["n_crisis"] / pop["n_baseline"]
        pop["hours_since_quake"] = float(meta["hours_since_quake"])
        pop["window_start_pt"] = pd.Timestamp(meta["window_start_pt"])

        mov = df_mov[["start_quadkey", "end_quadkey", "n_crisis", "length_km"]].copy()
        mov["start_quadkey"] = mov["start_quadkey"].astype("string")
        mov["end_quadkey"] = mov["end_quadkey"].astype("string")
        mov["n_crisis"] = pd.to_numeric(mov["n_crisis"], errors="coerce")
        mov["length_km"] = pd.to_numeric(mov.get("length_km", np.nan), errors="coerce")
        mov = mov[mov["n_crisis"].notna()].copy()

        inflow = mov.groupby("end_quadkey", observed=True)["n_crisis"].sum()
        outflow = mov.groupby("start_quadkey", observed=True)["n_crisis"].sum()
        net = inflow.sub(outflow, fill_value=0.0).rename("net_inflow")

        merged = pop.merge(inflow.rename("inflow"), left_on="quadkey", right_index=True, how="left")
        merged = merged.merge(outflow.rename("outflow"), left_on="quadkey", right_index=True, how="left")
        merged = merged.merge(net, left_on="quadkey", right_index=True, how="left")
        merged["inflow"] = merged["inflow"].fillna(0.0)
        merged["outflow"] = merged["outflow"].fillna(0.0)
        merged["net_inflow"] = merged["net_inflow"].fillna(0.0)

        # correlation（phi_ratio vs net_inflow）
        valid = merged[["phi_ratio", "net_inflow"]].replace([np.inf, -np.inf], np.nan).dropna()
        corr = float(valid["phi_ratio"].corr(valid["net_inflow"])) if len(valid) >= 50 else float("nan")
        corr_rows.append(
            {
                "window_start_pt": pd.Timestamp(meta["window_start_pt"]),
                "hours_since_quake": float(meta["hours_since_quake"]),
                "n_tiles": int(len(pop)),
                "corr_phi_vs_net_inflow": corr,
            }
        )
        tile_rows.append(merged[["window_start_pt", "hours_since_quake", "quadkey", "lat", "lon", "phi_ratio", "inflow", "outflow", "net_inflow"]])

    tile_df = pd.concat(tile_rows, ignore_index=True)
    corr_df = pd.DataFrame(corr_rows).sort_values("hours_since_quake", kind="stable")
    out_tile = out.tables / "tile_level_joint_metrics.csv"
    out_corr = out.tables / "phi_vs_net_inflow_correlation.csv"
    tile_df.to_csv(out_tile, index=False)
    corr_df.to_csv(out_corr, index=False)

    # long distance destinations（用 hub_post 窗口）
    long_df = hub_post_df_mov.copy()
    long_df["n_crisis"] = pd.to_numeric(long_df.get("n_crisis", np.nan), errors="coerce")
    long_df["length_km"] = pd.to_numeric(long_df.get("length_km", np.nan), errors="coerce")
    long_df = long_df[long_df["n_crisis"].notna() & long_df["length_km"].notna()].copy()
    long_df = long_df[long_df["length_km"] > float(cfg.long_distance_threshold_km)].copy()
    dest = long_df.groupby("end_quadkey", observed=True)["n_crisis"].sum().sort_values(ascending=False).head(20).reset_index()
    dest = dest.rename(columns={"end_quadkey": "destination_quadkey", "n_crisis": "long_distance_inflow"})
    out_dest = out.tables / "long_distance_destinations.csv"
    dest.to_csv(out_dest, index=False)

    # figures
    with ps.paper_style():
        import matplotlib.pyplot as plt
        from matplotlib.collections import LineCollection

        # scatter：phi vs net_inflow（用 hub_post 窗口）
        post_hs = float(hub_post["hours_since_quake"])
        post_tile = tile_df[tile_df["hours_since_quake"] == post_hs].copy()
        x = pd.to_numeric(post_tile["net_inflow"], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(post_tile["phi_ratio"], errors="coerce").to_numpy(dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        x, y = x[mask], y[mask]
        if x.size:
            x0, x1 = np.quantile(x, [0.01, 0.99])
            x_plot = np.clip(x, x0, x1)
        else:
            x_plot = x
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        ax.scatter(x_plot, y, s=6, alpha=0.25, color=ps.OKABE_ITO["blue"], linewidths=0, rasterized=True)
        ax.set_xlabel("net_inflow (clipped to 1%–99% for display)")
        ax.set_ylabel("phi_ratio (n_crisis / n_baseline)")
        ax.set_title(f"phi vs net_inflow (post window: {int(round(post_hs))}h)")
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "phi_vs_net_inflow_scatter.png")
        plt.close(fig)

        # hub spatial evolution
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        pre = hub_comp[hub_comp["is_pre_hub"] == 1]
        post = hub_comp[hub_comp["is_post_hub"] == 1]
        new = hub_comp[hub_comp["is_new_hub"] == 1]
        if not pre.empty:
            ax.scatter(pre["lon"], pre["lat"], s=28, alpha=0.35, color=ps.OKABE_ITO["gray"], label="pre hubs", linewidths=0)
        if not post.empty:
            ax.scatter(post["lon"], post["lat"], s=28, alpha=0.35, color=ps.OKABE_ITO["sky_blue"], label="post hubs", linewidths=0)
        if not new.empty:
            ax.scatter(new["lon"], new["lat"], s=40, alpha=0.75, color=ps.OKABE_ITO["vermillion"], label="new hubs", linewidths=0)
        ax.scatter([cfg.epicenter_lon], [cfg.epicenter_lat], s=90, c=ps.OKABE_ITO["yellow"], edgecolors="black", linewidths=1.0, zorder=5)
        ax.set_xlabel("Lon")
        ax.set_ylabel("Lat")
        ax.set_title("Hub spatial evolution (pre vs post, 08:00 windows)")
        ax.legend(frameon=False, loc="upper right")
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "hub_spatial_evolution.png")
        plt.close(fig)

        # long distance flow map（post window）
        if not long_df.empty:
            top = long_df.sort_values("n_crisis", ascending=False, kind="stable").head(300)
            segs = []
            widths = []
            for r in top.itertuples(index=False):
                if not (np.isfinite(r.start_lat) and np.isfinite(r.start_lon) and np.isfinite(r.end_lat) and np.isfinite(r.end_lon)):
                    continue
                segs.append([(float(r.start_lon), float(r.start_lat)), (float(r.end_lon), float(r.end_lat))])
                widths.append(float(r.n_crisis))
            fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
            if segs:
                w_arr = np.asarray(widths, dtype=float)
                lw = 0.3 + 2.2 * (w_arr / np.nanmax(w_arr))
                lc = LineCollection(segs, linewidths=lw, colors=ps.OKABE_ITO["vermillion"], alpha=0.18)
                ax.add_collection(lc)
            ax.scatter([cfg.epicenter_lon], [cfg.epicenter_lat], s=90, c=ps.OKABE_ITO["yellow"], edgecolors="black", linewidths=1.0, zorder=5)
            ax.set_xlabel("Lon")
            ax.set_ylabel("Lat")
            ax.set_title(f"Long-distance flows (> {float(cfg.long_distance_threshold_km)} km), post window {int(round(post_hs))}h")
            ps.despine(ax)
            fig.tight_layout()
            save_png_and_pdf(ps, fig, out.figures / "long_distance_flow_map.png")
            plt.close(fig)

    readme = f"""# Movement-Population Joint Analysis (08:00 windows)

本目录对应 `Docs/research_plan_network_redistribution.md` 的 **Task 3**：
把 Movement（OD）与 Population（tile）合并，检验“网络重组 ↔ 人口再分布”的空间关联。

## 口径

- 仅使用 PT {int(cfg.only_hour_pt):02d}:00 窗口
- population phi_ratio = n_crisis / n_baseline
- movement net_inflow = sum(inflow n_crisis) - sum(outflow n_crisis)（按 quadkey 聚合）
- hub：degree > {float(cfg.hub_threshold)} * avg_degree（在无向 OD 图上，度为 unweighted degree）
- 长距离：length_km > {float(cfg.long_distance_threshold_km)} km

## 代表性窗口（按 hours_since_quake 最近匹配）

{", ".join(str(int(round(float(x)))) + "h" for x in cfg.snapshot_offsets_hours)}

## 输出

- `tables/tile_level_joint_metrics.csv`：代表性窗口的 tile-level phi_ratio + (inflow/outflow/net_inflow)
- `tables/phi_vs_net_inflow_correlation.csv`：每个代表性窗口的相关系数
- `tables/hub_comparison.csv`：震前/震后 hub 与 new_hubs
- `tables/long_distance_destinations.csv`：长距离 OD 的主要目的地（post window）
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_tile}")
    print(f"Done. Wrote: {out_hub}")
    print(f"Done. Wrote: {out_dest}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("Data/Turkiye Turkey Earthquake Full Country Version Feb 8 2023"),
        help="数据根目录（包含 movement/ 与 population/ 子目录）",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/movement_population_joint"), help="输出目录")
    parser.add_argument("--t0-pt", type=str, default="2023-02-05 16:00", help="t=0 的 PT 时间戳")
    parser.add_argument("--only-hour-pt", type=int, default=8, help="仅保留该小时（PT）的窗口（默认 08:00）")
    parser.add_argument("--min-edge-weight", type=float, default=10.0, help="构网时保留的最小 n_crisis 边权")
    parser.add_argument("--long-distance-threshold-km", type=float, default=10.0, help="长距离阈值（km）")
    parser.add_argument("--hub-threshold", type=float, default=2.0, help="hub 阈值（deg > thr * avg_degree）")
    parser.add_argument(
        "--snapshot-offset-hours",
        type=float,
        nargs="*",
        default=[-8.0, 16.0, 40.0, 88.0, 160.0, 328.0, 832.0],
        help="代表性窗口：相对 t0 的小时偏移（取最近匹配的 08:00 窗口）",
    )
    parser.add_argument("--hub-pre-offset-hours", type=float, default=-8.0, help="hub 对比：震前窗口偏移（默认 -8h）")
    parser.add_argument("--hub-post-offset-hours", type=float, default=16.0, help="hub 对比：震后窗口偏移（默认 +16h）")
    args = parser.parse_args()

    cfg = Config(
        data_root=args.data_root,
        output_dir=args.output_dir,
        t0_pt=pd.Timestamp(str(args.t0_pt)),
        only_hour_pt=int(args.only_hour_pt),
        min_edge_weight=float(args.min_edge_weight),
        long_distance_threshold_km=float(args.long_distance_threshold_km),
        hub_threshold=float(args.hub_threshold),
        snapshot_offsets_hours=tuple(float(x) for x in args.snapshot_offset_hours),
        hub_pre_offset_hours=float(args.hub_pre_offset_hours),
        hub_post_offset_hours=float(args.hub_post_offset_hours),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()

