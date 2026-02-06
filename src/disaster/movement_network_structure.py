from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.movement_io import load_movement_file
from disaster.population_io import parse_window_start_pt, resolve_subdir
from disaster.union_find import UnionFind
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    data_root: Path
    output_dir: Path
    t0_pt: pd.Timestamp = pd.Timestamp("2023-02-05 16:00")
    only_hour_pt: int = 8
    min_edge_weight: float = 10.0
    long_distance_threshold_km: float = 10.0
    summary_offsets_hours: tuple[float, ...] = (-8.0, 16.0, 40.0, 88.0, 160.0, 328.0, 832.0)


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _pick_nearest_windows(windows: list[dict], offsets_hours: tuple[float, ...]) -> list[dict]:
    if not windows:
        return []
    picked: list[dict] = []
    for off in offsets_hours:
        best = min(windows, key=lambda r: abs(float(r["hours_since_quake"]) - float(off)))
        picked.append(best)
    # 去重（不同 offset 可能落到同一窗口）
    seen = set()
    uniq: list[dict] = []
    for r in picked:
        key = (str(r["path"]), float(r["hours_since_quake"]))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq


def _build_undirected_edges_with_distance(
    df: pd.DataFrame,
    *,
    weight_col: str,
    dist_col: str,
    min_weight: float,
) -> pd.DataFrame:
    required = {"start_quadkey", "end_quadkey", weight_col}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Movement 数据缺少列：{missing}")

    w = pd.to_numeric(df[weight_col], errors="coerce")
    u_raw = df["start_quadkey"]
    v_raw = df["end_quadkey"]
    d_raw = pd.to_numeric(df[dist_col], errors="coerce") if dist_col in df.columns else pd.Series(np.nan, index=df.index)

    mask = u_raw.notna() & v_raw.notna() & w.notna() & (w >= float(min_weight))
    sub = df.loc[mask, ["start_quadkey", "end_quadkey"]].copy()
    sub["w"] = w.loc[mask].to_numpy(dtype=float)
    sub["distance_km"] = d_raw.loc[mask].to_numpy(dtype=float)

    # 去掉自环（A->A 不影响连通性）
    sub = sub[sub["start_quadkey"] != sub["end_quadkey"]].copy()
    if sub.empty:
        return pd.DataFrame({"u": [], "v": [], "w": [], "distance_km": []})

    u = sub["start_quadkey"].astype(str).to_numpy()
    v = sub["end_quadkey"].astype(str).to_numpy()
    u2 = np.minimum(u, v)
    v2 = np.maximum(u, v)

    edges = pd.DataFrame({"u": u2, "v": v2, "w": sub["w"].to_numpy(dtype=float), "distance_km": sub["distance_km"].to_numpy(dtype=float)})
    edges = (
        edges.groupby(["u", "v"], as_index=False)
        .agg(
            w=("w", "sum"),
            distance_km=("distance_km", "mean"),
        )
        .reset_index(drop=True)
    )
    return edges


def _component_sizes_from_edges(edges: pd.DataFrame) -> tuple[int, np.ndarray]:
    if edges.empty:
        return 0, np.array([], dtype=int)

    nodes = pd.Index(pd.unique(pd.concat([edges["u"], edges["v"]], ignore_index=True)))
    n_nodes = int(nodes.size)
    node_to_idx = {str(node): int(i) for i, node in enumerate(nodes.astype(str))}
    u_idx = edges["u"].astype(str).map(node_to_idx).to_numpy(dtype=int)
    v_idx = edges["v"].astype(str).map(node_to_idx).to_numpy(dtype=int)

    uf = UnionFind(n_nodes)
    for a, b in zip(u_idx, v_idx, strict=False):
        uf.union(int(a), int(b))

    roots = np.fromiter((uf.find(i) for i in range(n_nodes)), dtype=int, count=n_nodes)
    _, counts = np.unique(roots, return_counts=True)
    return n_nodes, counts.astype(int)


def _compute_metrics(edges: pd.DataFrame, *, long_distance_threshold_km: float) -> dict[str, float]:
    if edges.empty:
        return {
            "n_nodes": 0,
            "n_edges": 0,
            "density": float("nan"),
            "avg_degree": 0.0,
            "gcc_fraction": float("nan"),
            "n_components": 0,
            "component_size_std": float("nan"),
            "degree_centralization": float("nan"),
            "top10_degree_share": float("nan"),
            "hub_count": 0,
            "avg_edge_distance": float("nan"),
            "long_distance_edge_fraction": float("nan"),
            "distance_p90": float("nan"),
        }

    n_nodes, comp_sizes = _component_sizes_from_edges(edges)
    n_edges = int(len(edges))
    degrees = pd.concat([edges["u"], edges["v"]], ignore_index=True).astype(str).value_counts().to_numpy(dtype=float)

    avg_degree = float(2.0 * n_edges / n_nodes) if n_nodes > 0 else 0.0
    density = float(2.0 * n_edges / (n_nodes * (n_nodes - 1))) if n_nodes > 1 else float("nan")

    gcc_fraction = float(np.max(comp_sizes) / n_nodes) if n_nodes > 0 and comp_sizes.size else float("nan")
    n_components = int(comp_sizes.size) if comp_sizes.size else 0
    component_size_std = float(np.std(comp_sizes)) if comp_sizes.size else float("nan")

    if n_nodes <= 2 or degrees.size == 0:
        degree_centralization = float("nan")
    else:
        max_degree = float(np.max(degrees))
        degree_centralization = float(np.sum(max_degree - degrees) / ((n_nodes - 1) * (n_nodes - 2)))

    deg_sum = float(np.sum(degrees))
    top_k = int(0.1 * n_nodes) or 1
    top10_degree_share = float(np.sum(np.sort(degrees)[::-1][:top_k]) / deg_sum) if deg_sum > 0 else float("nan")

    hub_count = int(np.sum(degrees > (2.0 * avg_degree))) if degrees.size else 0

    dist = pd.to_numeric(edges["distance_km"], errors="coerce").to_numpy(dtype=float)
    dist = dist[np.isfinite(dist)]
    if dist.size:
        avg_edge_distance = float(np.mean(dist))
        distance_p90 = float(np.percentile(dist, 90))
        long_distance_edge_fraction = float(np.mean(dist > float(long_distance_threshold_km)))
    else:
        avg_edge_distance = float("nan")
        distance_p90 = float("nan")
        long_distance_edge_fraction = float("nan")

    return {
        "n_nodes": float(n_nodes),
        "n_edges": float(n_edges),
        "density": density,
        "avg_degree": avg_degree,
        "gcc_fraction": gcc_fraction,
        "n_components": float(n_components),
        "component_size_std": component_size_std,
        "degree_centralization": degree_centralization,
        "top10_degree_share": top10_degree_share,
        "hub_count": float(hub_count),
        "avg_edge_distance": avg_edge_distance,
        "long_distance_edge_fraction": long_distance_edge_fraction,
        "distance_p90": distance_p90,
    }


def run(cfg: Config, *, max_files: int | None = None) -> None:
    mov_dir = resolve_subdir(cfg.data_root, "movement")

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

    files_all = sorted(mov_dir.glob("*.csv"))
    if not files_all:
        raise FileNotFoundError(f"目录为空：{mov_dir}")

    windows: list[dict] = []
    for path in files_all:
        window_start = parse_window_start_pt(path)
        if int(window_start.hour) != int(cfg.only_hour_pt):
            continue
        hours = float((window_start - cfg.t0_pt).total_seconds() / 3600.0)
        windows.append({"path": str(path), "window_start_pt": window_start, "hours_since_quake": hours})

    windows = sorted(windows, key=lambda r: float(r["hours_since_quake"]))
    if max_files is not None:
        windows = windows[: int(max_files)]
    if not windows:
        raise FileNotFoundError(f"未找到 hour={cfg.only_hour_pt} 的 movement 文件：{mov_dir}")

    picked = _pick_nearest_windows(windows, cfg.summary_offsets_hours)
    picked_set = {str(r["path"]) for r in picked}
    picked_dist: dict[float, np.ndarray] = {}

    rows: list[dict] = []
    for i, meta in enumerate(windows, start=1):
        path = Path(meta["path"])
        df = load_movement_file(path)
        edges = _build_undirected_edges_with_distance(
            df,
            weight_col="n_crisis",
            dist_col="length_km",
            min_weight=cfg.min_edge_weight,
        )
        metrics = _compute_metrics(edges, long_distance_threshold_km=cfg.long_distance_threshold_km)
        rows.append(
            {
                "window_start_pt": pd.Timestamp(meta["window_start_pt"]),
                "hours_since_quake": float(meta["hours_since_quake"]),
                "only_hour_pt": int(cfg.only_hour_pt),
                "min_edge_weight": float(cfg.min_edge_weight),
                "long_distance_threshold_km": float(cfg.long_distance_threshold_km),
                **metrics,
            }
        )

        if str(meta["path"]) in picked_set and not edges.empty:
            hs = float(meta["hours_since_quake"])
            dist = pd.to_numeric(edges["distance_km"], errors="coerce").to_numpy(dtype=float)
            picked_dist[hs] = dist[np.isfinite(dist)]

        if i % 20 == 0:
            print(f"[movement_network_structure] processed {i}/{len(windows)} windows...")

    metrics_df = pd.DataFrame(rows).sort_values("hours_since_quake", kind="stable")
    out_metrics = out.tables / "network_metrics_extended.csv"
    metrics_df.to_csv(out_metrics, index=False)

    # summary：代表性窗口
    summary_rows: list[dict] = []
    for target in cfg.summary_offsets_hours:
        best = min(windows, key=lambda r: abs(float(r["hours_since_quake"]) - float(target)))
        hs = float(best["hours_since_quake"])
        sub = metrics_df[metrics_df["hours_since_quake"] == hs]
        if sub.empty:
            continue
        row = sub.iloc[0].to_dict()
        row["target_hours_since_quake"] = float(target)
        summary_rows.append(row)
    summary_df = pd.DataFrame(summary_rows).sort_values("target_hours_since_quake", kind="stable")
    out_summary = out.tables / "network_metrics_summary.csv"
    summary_df.to_csv(out_summary, index=False)

    # figures：中心化 / hub_count / 距离分布对比
    with ps.paper_style():
        import matplotlib.pyplot as plt

        # centralization
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        ax.plot(metrics_df["hours_since_quake"], metrics_df["degree_centralization"], marker="o", color=ps.OKABE_ITO["vermillion"])
        ax.axvline(0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.set_xlabel("Hours since earthquake (PT, 08:00 windows)")
        ax.set_ylabel("degree_centralization")
        ax.set_title("Movement network centralization over time (08:00 windows)")
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "centralization_timeseries.png")
        plt.close(fig)

        # hub_count
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        ax.plot(metrics_df["hours_since_quake"], metrics_df["hub_count"], marker="o", color=ps.OKABE_ITO["blue"])
        ax.axvline(0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.set_xlabel("Hours since earthquake (PT, 08:00 windows)")
        ax.set_ylabel("hub_count (deg > 2*avg_degree)")
        ax.set_title("Movement network hub count over time (08:00 windows)")
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "hub_count_timeseries.png")
        plt.close(fig)

        # distance distribution comparison（代表性窗口）
        if picked_dist:
            fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
            for hs in sorted(picked_dist.keys()):
                x = picked_dist[hs]
                if x.size == 0:
                    continue
                ax.hist(x, bins=60, alpha=0.35, label=f"{int(round(hs))}h")
            ax.set_xlabel("Edge distance (km)")
            ax.set_ylabel("Edge count")
            ax.set_title("Edge distance distribution (selected 08:00 windows)")
            ax.legend(frameon=False, ncol=3)
            ps.despine(ax)
            fig.tight_layout()
            save_png_and_pdf(ps, fig, out.figures / "distance_distribution_comparison.png")
            plt.close(fig)

    # README
    t_min = pd.to_datetime(metrics_df["window_start_pt"]).min()
    t_max = pd.to_datetime(metrics_df["window_start_pt"]).max()
    readme = f"""# Movement Network Structure (08:00 windows)

本目录对应 `Docs/research_plan_network_redistribution.md` 的 **Task 1**：
用网络结构指标检验“灾害诱导网络集中化”。

## 口径

- 仅使用 PT {int(cfg.only_hour_pt):02d}:00 的 movement 文件（控制时段周期性）
- 节点：quadkey（tile）
- 边：无向边（把 start/end 当作无向连接，双向聚合）
- 边权：n_crisis（聚合求和）
- 自环（A→A）：丢弃
- 最小边权：{float(cfg.min_edge_weight)}
- 长距离阈值：{float(cfg.long_distance_threshold_km)} km（用于 long_distance_edge_fraction）

## 全局信息

- 处理窗口数：{len(metrics_df)}
- 时间跨度（PT）：{t_min} → {t_max}

## 主要产物

- `tables/network_metrics_extended.csv`：每个窗口的完整指标
- `tables/network_metrics_summary.csv`：代表性窗口（按 hours_since_quake 最近匹配）
- `figures/centralization_timeseries.*`：degree_centralization 时间序列
- `figures/hub_count_timeseries.*`：hub_count 时间序列
- `figures/distance_distribution_comparison.*`：代表性窗口边距离分布对比
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_metrics}")
    print(f"Done. Wrote: {out_summary}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("Data/Turkiye Turkey Earthquake Full Country Version Feb 8 2023"),
        help="数据根目录（包含 movement/ 子目录）",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/movement_network_structure"), help="输出目录")
    parser.add_argument("--max-files", type=int, default=None, help="只处理前 N 个窗口（用于冒烟测试）")
    parser.add_argument("--t0-pt", type=str, default="2023-02-05 16:00", help="t=0 的 PT 时间戳")
    parser.add_argument("--only-hour-pt", type=int, default=8, help="仅保留该小时（PT）的窗口（默认 08:00）")
    parser.add_argument("--min-edge-weight", type=float, default=10.0, help="构网时保留的最小 n_crisis 边权")
    parser.add_argument("--long-distance-threshold-km", type=float, default=10.0, help="长距离阈值（km）")
    parser.add_argument(
        "--summary-offsets-hours",
        type=float,
        nargs="*",
        default=[-8.0, 16.0, 40.0, 88.0, 160.0, 328.0, 832.0],
        help="代表性窗口：相对 t0 的小时偏移（取最近匹配的 08:00 窗口）",
    )
    args = parser.parse_args()

    cfg = Config(
        data_root=args.data_root,
        output_dir=args.output_dir,
        t0_pt=pd.Timestamp(str(args.t0_pt)),
        only_hour_pt=int(args.only_hour_pt),
        min_edge_weight=float(args.min_edge_weight),
        long_distance_threshold_km=float(args.long_distance_threshold_km),
        summary_offsets_hours=tuple(float(x) for x in args.summary_offsets_hours),
    )
    run(cfg, max_files=args.max_files)


if __name__ == "__main__":
    cli_main()

