from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

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
    min_edge_weight: float = 1.0
    reservoir_size: int = 200_000
    random_seed: int = 0
    snapshot_offsets_hours: tuple[float, ...] = (-24.0, 24.0, 168.0)
    percolation_n_thresholds: int = 30
    network_top_edges: int = 300


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


class ReservoirSampler:
    def __init__(self, k: int, *, seed: int = 0):
        self.k = int(k)
        self.rng = np.random.default_rng(int(seed))
        self.n_seen = 0
        self.sample: list[float] = []

    def update(self, values: Iterable[float]) -> None:
        if self.k <= 0:
            return
        for v in values:
            if not np.isfinite(v):
                continue
            self.n_seen += 1
            if len(self.sample) < self.k:
                self.sample.append(float(v))
                continue
            j = int(self.rng.integers(0, self.n_seen))
            if j < self.k:
                self.sample[j] = float(v)

    def to_array(self) -> np.ndarray:
        if not self.sample:
            return np.array([], dtype=float)
        return np.array(self.sample, dtype=float)


def _quantiles(x: np.ndarray, qs: tuple[float, ...] = (0.5, 0.9, 0.99)) -> dict[str, float]:
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {f"p{int(q*100):02d}": float("nan") for q in qs}
    out: dict[str, float] = {}
    for q in qs:
        out[f"p{int(q*100):02d}"] = float(np.quantile(x, q))
    return out


def _build_undirected_edges(df: pd.DataFrame, *, weight_col: str, min_weight: float) -> pd.DataFrame:
    required = {"start_quadkey", "end_quadkey", weight_col}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Movement 数据缺少列：{missing}")

    w = pd.to_numeric(df[weight_col], errors="coerce")
    u_raw = df["start_quadkey"]
    v_raw = df["end_quadkey"]

    mask = u_raw.notna() & v_raw.notna() & w.notna() & (w >= float(min_weight))
    sub = df.loc[mask, ["start_quadkey", "end_quadkey"]].copy()
    sub["w"] = w.loc[mask].to_numpy(dtype=float)

    # 去掉自环（A->A 不影响连通性；也避免在图上造成噪声）
    sub = sub[sub["start_quadkey"] != sub["end_quadkey"]].copy()
    if sub.empty:
        return pd.DataFrame({"u": [], "v": [], "w": []})

    u = sub["start_quadkey"].astype(str).to_numpy()
    v = sub["end_quadkey"].astype(str).to_numpy()
    u2 = np.minimum(u, v)
    v2 = np.maximum(u, v)

    edges = pd.DataFrame({"u": u2, "v": v2, "w": sub["w"].to_numpy(dtype=float)})
    edges = edges.groupby(["u", "v"], as_index=False)["w"].sum()
    return edges


def _network_metrics_from_edges(edges: pd.DataFrame) -> dict[str, float]:
    if edges.empty:
        return {
            "n_nodes": 0,
            "n_edges": 0,
            "total_flow": 0.0,
            "avg_degree": 0.0,
            "gcc_size": 0,
            "gcc_fraction": float("nan"),
        }

    nodes = pd.Index(pd.unique(pd.concat([edges["u"], edges["v"]], ignore_index=True)))
    n_nodes = int(nodes.size)
    node_to_idx = {str(node): int(i) for i, node in enumerate(nodes.astype(str))}

    u_idx = edges["u"].astype(str).map(node_to_idx).to_numpy(dtype=int)
    v_idx = edges["v"].astype(str).map(node_to_idx).to_numpy(dtype=int)
    w = pd.to_numeric(edges["w"], errors="coerce").to_numpy(dtype=float)

    uf = UnionFind(n_nodes)
    for a, b in zip(u_idx, v_idx, strict=False):
        uf.union(int(a), int(b))

    n_edges = int(len(edges))
    total_flow = float(np.nansum(w))
    avg_degree = float(2.0 * n_edges / n_nodes) if n_nodes > 0 else 0.0
    gcc_size = int(uf.max_size)
    gcc_fraction = float(gcc_size / n_nodes) if n_nodes > 0 else float("nan")
    return {
        "n_nodes": n_nodes,
        "n_edges": n_edges,
        "total_flow": total_flow,
        "avg_degree": avg_degree,
        "gcc_size": gcc_size,
        "gcc_fraction": gcc_fraction,
    }


def _percolation_scan(edges: pd.DataFrame, *, n_thresholds: int) -> pd.DataFrame:
    """
    渗流扫描：逐步提高边权阈值（去掉弱边），观察最大连通分量占比的崩塌过程。
    """

    if edges.empty:
        return pd.DataFrame({"threshold": [], "gcc_fraction": []})

    nodes = pd.Index(pd.unique(pd.concat([edges["u"], edges["v"]], ignore_index=True)))
    n_nodes = int(nodes.size)
    node_to_idx = {str(node): int(i) for i, node in enumerate(nodes.astype(str))}

    u_idx = edges["u"].astype(str).map(node_to_idx).to_numpy(dtype=int)
    v_idx = edges["v"].astype(str).map(node_to_idx).to_numpy(dtype=int)
    w_full = pd.to_numeric(edges["w"], errors="coerce").to_numpy(dtype=float)
    w = w_full[np.isfinite(w_full)]
    if w.size == 0 or n_nodes == 0:
        return pd.DataFrame({"threshold": [], "gcc_fraction": []})

    n = int(max(2, n_thresholds))
    qs = np.linspace(0.0, 1.0, n)
    thresholds = np.unique(np.quantile(w, qs))
    thresholds = np.sort(thresholds)  # 阈值从小到大：逐步去掉弱边（更直观）

    rows: list[dict[str, float]] = []
    for thr in thresholds:
        uf = UnionFind(n_nodes)
        keep = np.isfinite(w_full) & (w_full >= float(thr))
        for a, b in zip(u_idx[keep], v_idx[keep], strict=False):
            uf.union(int(a), int(b))
        rows.append({"threshold": float(thr), "gcc_fraction": float(uf.max_size / n_nodes)})

    return pd.DataFrame(rows).sort_values("threshold", ascending=True, kind="stable")


def _pick_nearest_windows(windows: list[dict], offsets_hours: tuple[float, ...]) -> list[dict]:
    if not windows:
        return []
    out: list[dict] = []
    for off in offsets_hours:
        best = min(windows, key=lambda r: abs(float(r["hours_since_quake"]) - float(off)))
        out.append(best)
    # 去重（不同 offset 可能落到同一窗口）
    seen = set()
    uniq: list[dict] = []
    for r in out:
        key = (str(r["path"]), float(r["hours_since_quake"]))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq


def _build_quadkey_coords(df: pd.DataFrame) -> dict[str, tuple[float, float]]:
    """
    构造 quadkey -> (lat, lon) 字典，用于网络可视化。
    优先使用文件中提供的 start/end 坐标。
    """

    coords: dict[str, tuple[float, float]] = {}
    if {"start_quadkey", "start_lat", "start_lon"} <= set(df.columns):
        sub = df[["start_quadkey", "start_lat", "start_lon"]].dropna()
        for q, lat, lon in sub.itertuples(index=False):
            key = str(q)
            if key not in coords and np.isfinite(lat) and np.isfinite(lon):
                coords[key] = (float(lat), float(lon))
    if {"end_quadkey", "end_lat", "end_lon"} <= set(df.columns):
        sub = df[["end_quadkey", "end_lat", "end_lon"]].dropna()
        for q, lat, lon in sub.itertuples(index=False):
            key = str(q)
            if key not in coords and np.isfinite(lat) and np.isfinite(lon):
                coords[key] = (float(lat), float(lon))
    return coords


def run(cfg: Config, *, max_files: int | None = None) -> None:
    mov_dir = resolve_subdir(cfg.data_root, "movement")

    out = _output_dirs(cfg.output_dir)
    _ensure_dir(out.root)
    _ensure_dir(out.figures)
    _ensure_dir(out.tables)

    files = sorted(mov_dir.glob("*.csv"))
    if max_files is not None:
        files = files[: int(max_files)]
    if not files:
        raise FileNotFoundError(f"目录为空：{mov_dir}")

    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    dist_sampler = ReservoirSampler(cfg.reservoir_size, seed=cfg.random_seed)
    base_sampler = ReservoirSampler(cfg.reservoir_size, seed=cfg.random_seed + 1)
    crisis_sampler = ReservoirSampler(cfg.reservoir_size, seed=cfg.random_seed + 2)

    window_rows: list[dict] = []
    net_rows: list[dict] = []
    windows_index: list[dict] = []

    for i, path in enumerate(files, start=1):
        try:
            window_start = parse_window_start_pt(path)
        except Exception:
            # fallback：从文件内 date_time 推断
            head = pd.read_csv(path, usecols=lambda c: c == "date_time", na_values=["\\N", ""], nrows=1)
            if "date_time" not in head.columns or head.empty:
                raise ValueError(f"无法解析窗口时间（文件名与 date_time 均失败）：{path.name}")
            window_start = pd.to_datetime(head["date_time"].iloc[0])

        hours = float((window_start - cfg.t0_pt).total_seconds() / 3600.0)
        df = load_movement_file(path)

        n_rows = int(len(df))
        n_od_pairs = int(df[["start_quadkey", "end_quadkey"]].dropna().shape[0]) if {"start_quadkey", "end_quadkey"} <= set(df.columns) else 0
        n_with_crisis = int(pd.to_numeric(df.get("n_crisis", np.nan), errors="coerce").notna().sum())

        length_km = pd.to_numeric(df.get("length_km", np.nan), errors="coerce")
        dist_sampler.update(length_km.to_numpy(dtype=float))
        base_sampler.update(pd.to_numeric(df.get("n_baseline", np.nan), errors="coerce").to_numpy(dtype=float))
        crisis_sampler.update(pd.to_numeric(df.get("n_crisis", np.nan), errors="coerce").to_numpy(dtype=float))

        dist_q = _quantiles(length_km.to_numpy(dtype=float))
        base_q = _quantiles(pd.to_numeric(df.get("n_baseline", np.nan), errors="coerce").to_numpy(dtype=float))
        crisis_q = _quantiles(pd.to_numeric(df.get("n_crisis", np.nan), errors="coerce").to_numpy(dtype=float))

        window_rows.append(
            {
                "window_start_pt": window_start,
                "hours_since_quake": hours,
                "n_rows": n_rows,
                "n_od_pairs_nonnull": n_od_pairs,
                "n_with_n_crisis": n_with_crisis,
                "dist_p50_km": dist_q["p50"],
                "dist_p90_km": dist_q["p90"],
                "dist_p99_km": dist_q["p99"],
                "n_baseline_p50": base_q["p50"],
                "n_baseline_p90": base_q["p90"],
                "n_baseline_p99": base_q["p99"],
                "n_crisis_p50": crisis_q["p50"],
                "n_crisis_p90": crisis_q["p90"],
                "n_crisis_p99": crisis_q["p99"],
            }
        )

        edges = _build_undirected_edges(df, weight_col="n_crisis", min_weight=cfg.min_edge_weight)
        nm = _network_metrics_from_edges(edges)
        net_rows.append(
            {
                "window_start_pt": window_start,
                "hours_since_quake": hours,
                "min_edge_weight": float(cfg.min_edge_weight),
                **nm,
            }
        )
        windows_index.append({"path": str(path), "window_start_pt": window_start, "hours_since_quake": hours})

        if i % 20 == 0:
            print(f"[movement] processed {i}/{len(files)} files...")

    window_stats = pd.DataFrame(window_rows).sort_values("hours_since_quake", kind="stable")
    net_stats = pd.DataFrame(net_rows).sort_values("hours_since_quake", kind="stable")
    window_stats.to_csv(out.tables / "movement_window_stats.csv", index=False)
    net_stats.to_csv(out.tables / "movement_network_metrics_by_window.csv", index=False)

    # 任务3：order parameter（最大连通分量占比）随时间变化
    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        ax.plot(net_stats["hours_since_quake"], net_stats["gcc_fraction"], marker="o", color=ps.OKABE_ITO["blue"])
        ax.axvline(0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.set_xlabel("Hours since earthquake (PT windows)")
        ax.set_ylabel("GCC fraction")
        ax.set_title("Movement network order parameter: GCC fraction over time")
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "movement_order_parameter_gcc_fraction_over_time.png")
        plt.close(fig)

    # 任务1：OD 距离分布（用 reservoir sample 近似）
    dist_all = dist_sampler.to_array()
    if dist_all.size > 0:
        with ps.paper_style():
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
            ax.hist(dist_all, bins=60, color=ps.OKABE_ITO["sky_blue"], alpha=0.9)
            ax.set_xlabel("OD distance (km)")
            ax.set_ylabel("Sample count")
            ax.set_title("Movement OD distance distribution (reservoir sample)")
            ps.despine(ax)
            fig.tight_layout()
            save_png_and_pdf(ps, fig, out.figures / "movement_od_distance_hist.png")
            plt.close(fig)

    # 任务2/3：选定窗口（震前1天、震后1天、震后1周）网络对比 + 渗流扫描
    picked = _pick_nearest_windows(windows_index, cfg.snapshot_offsets_hours)
    if picked:
        perco_rows: list[pd.DataFrame] = []
        viz_payload: list[dict] = []
        for w in picked:
            path = Path(w["path"])
            df = load_movement_file(path)
            edges = _build_undirected_edges(df, weight_col="n_crisis", min_weight=cfg.min_edge_weight)
            scan = _percolation_scan(edges, n_thresholds=int(cfg.percolation_n_thresholds))
            scan.insert(0, "hours_since_quake", float(w["hours_since_quake"]))
            scan.insert(0, "window_start_pt", pd.Timestamp(w["window_start_pt"]))
            perco_rows.append(scan)

            coords = _build_quadkey_coords(df)
            viz_payload.append(
                {
                    "window_start_pt": pd.Timestamp(w["window_start_pt"]),
                    "hours_since_quake": float(w["hours_since_quake"]),
                    "edges": edges,
                    "coords": coords,
                }
            )

        perco = pd.concat(perco_rows, ignore_index=True) if perco_rows else pd.DataFrame()
        perco.to_csv(out.tables / "movement_percolation_scan_selected_windows.csv", index=False)

        # percolation figure
        if not perco.empty:
            with ps.paper_style():
                import matplotlib.pyplot as plt

                fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
                for (ws, hs), sub in perco.groupby(["window_start_pt", "hours_since_quake"], sort=False):
                    sub = sub.sort_values("threshold", ascending=True, kind="stable")
                    label = f"{int(round(float(hs)))}h"
                    ax.plot(sub["threshold"], sub["gcc_fraction"], marker="o", label=label)
                ax.set_xlabel("Edge weight threshold (keep edges with w >= threshold)")
                ax.set_ylabel("GCC fraction")
                ax.set_title("Percolation scan (selected windows)")
                ax.legend(frameon=False)
                ps.despine(ax)
                fig.tight_layout()
                save_png_and_pdf(ps, fig, out.figures / "movement_percolation_scan_selected_windows.png")
                plt.close(fig)

        # network visualization：每个窗口画 top-K 边
        with ps.paper_style():
            import matplotlib.pyplot as plt
            from matplotlib.collections import LineCollection

            n = len(viz_payload)
            fig, axes = plt.subplots(nrows=1, ncols=n, figsize=(ps.FIGSIZE_FULL[0] * n, ps.FIGSIZE_FULL[1]), sharex=False, sharey=False)
            if n == 1:
                axes = [axes]

            for ax, payload in zip(axes, viz_payload, strict=False):
                edges = payload["edges"].sort_values("w", ascending=False, kind="stable").head(int(cfg.network_top_edges))
                coords = payload["coords"]

                segs = []
                widths = []
                for u, v, wgt in edges[["u", "v", "w"]].itertuples(index=False):
                    cu = coords.get(str(u))
                    cv = coords.get(str(v))
                    if cu is None or cv is None:
                        continue
                    (lat_u, lon_u) = cu
                    (lat_v, lon_v) = cv
                    segs.append([(lon_u, lat_u), (lon_v, lat_v)])
                    widths.append(float(wgt))

                if segs:
                    widths_arr = np.asarray(widths, dtype=float)
                    # 线宽做轻量压缩，避免极大权重导致“糊成一坨”
                    lw = 0.3 + 2.2 * (widths_arr / np.nanmax(widths_arr))
                    lc = LineCollection(segs, linewidths=lw, colors=ps.OKABE_ITO["vermillion"], alpha=0.28)
                    ax.add_collection(lc)

                # 画节点（只画出现在 top edges 中的端点）
                nodes = pd.Index(pd.unique(pd.concat([edges["u"], edges["v"]], ignore_index=True))).astype(str).tolist()
                xs, ys = [], []
                for node in nodes:
                    c = coords.get(str(node))
                    if c is None:
                        continue
                    xs.append(float(c[1]))
                    ys.append(float(c[0]))
                if xs:
                    ax.scatter(xs, ys, s=10, color=ps.OKABE_ITO["blue"], alpha=0.55, linewidths=0)

                ax.set_title(f"{int(round(float(payload['hours_since_quake'])))}h")
                ax.set_xlabel("Lon")
                ax.set_ylabel("Lat")
                ps.despine(ax)

            fig.suptitle(f"Movement network (top {int(cfg.network_top_edges)} edges by n_crisis)", y=0.98)
            fig.tight_layout(rect=(0, 0, 1, 0.95))
            save_png_and_pdf(ps, fig, out.figures / "movement_network_top_edges_selected_windows.png")
            plt.close(fig)

    # README：输出基本统计 + 字段说明 + 复现命令
    base_all = base_sampler.to_array()
    crisis_all = crisis_sampler.to_array()

    n_windows = int(len(files))
    t_min = pd.to_datetime(window_stats["window_start_pt"]).min()
    t_max = pd.to_datetime(window_stats["window_start_pt"]).max()
    dist_summary = _quantiles(dist_all) if dist_all.size else {"p50": float("nan"), "p90": float("nan"), "p99": float("nan")}
    base_summary = _quantiles(base_all) if base_all.size else {"p50": float("nan"), "p90": float("nan"), "p99": float("nan")}
    crisis_summary = _quantiles(crisis_all) if crisis_all.size else {"p50": float("nan"), "p90": float("nan"), "p99": float("nan")}

    readme = f"""# Movement Criticality Feasibility (Turkey 2023)

本目录用于回答：**Movement（OD）数据能否支撑“网络临界性/渗流扫描”分析？**

## 数据口径（来自 Docs/facebook_data/movement.md）

- 数据：Movement Between Places During Crisis (Bing Tiles)
- 时间窗：相邻 8 小时窗口之间的“转移”（date_time 多为 08:00 / 16:00 PT）
- 指标：每条 OD（start_quadkey → end_quadkey）提供 n_baseline / n_crisis / z_score / percent_change 等
- 隐私保护：小计数向量会被 drop / 置空（因此**不建议**用 inbound/outbound 求净流入来解释）

## 本次输出（你可以直接看这些文件）

- `tables/movement_window_stats.csv`：每个时间窗口的基本统计（OD 对数量、距离分布、n_baseline/n_crisis量级）
- `tables/movement_network_metrics_by_window.csv`：每个时间窗口的网络指标（GCC fraction 等）
- `tables/movement_percolation_scan_selected_windows.csv`：选定窗口的渗流扫描结果
- `figures/movement_order_parameter_gcc_fraction_over_time.*`：order parameter（GCC fraction）随时间
- `figures/movement_percolation_scan_selected_windows.*`：渗流曲线（选定窗口）
- `figures/movement_network_top_edges_selected_windows.*`：网络可视化（每个窗口 top edges）

## 全局摘要（基于 reservoir sample 近似）

- 时间窗口数：{n_windows}
- 时间跨度（PT）：{t_min} → {t_max}
- OD 距离（km）分位数：p50={dist_summary['p50']:.2f}, p90={dist_summary['p90']:.2f}, p99={dist_summary['p99']:.2f}
- n_baseline 分位数：p50={base_summary['p50']:.2f}, p90={base_summary['p90']:.2f}, p99={base_summary['p99']:.2f}
- n_crisis 分位数：p50={crisis_summary['p50']:.2f}, p90={crisis_summary['p90']:.2f}, p99={crisis_summary['p99']:.2f}

## 网络构建规则（本脚本）

- 节点：quadkey（tile）
- 边：无向边（把 start/end 当作无向连接，且把双向 OD 聚合到同一条无向边）
- 边权：n_crisis（按无向边聚合后求和）
- 自环（A→A）：丢弃（不影响连通性）
- 最小边权阈值：{float(cfg.min_edge_weight)}
- order parameter：最大连通分量占比（GCC fraction）

## 复现命令（全量数据示例）

```bash
python scripts/movement_criticality.py \\
  --data-root <FULL_DATA_ROOT> \\
  --output-dir outputs/movement_criticality \\
  --min-edge-weight {float(cfg.min_edge_weight)} \\
  --snapshot-offset-hours -24 24 168 \\
  --percolation-n-thresholds {int(cfg.percolation_n_thresholds)} \\
  --network-top-edges {int(cfg.network_top_edges)}
```
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Outputs written to: {out.root}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("Data/Turkiye Turkey Earthquake Full Country Version Feb 8 2023"),
        help="数据根目录（包含 movement/ 子目录）",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/movement_criticality"), help="输出目录")
    parser.add_argument("--max-files", type=int, default=None, help="只处理前 N 个文件（用于快速冒烟测试）")
    parser.add_argument("--t0-pt", type=str, default="2023-02-05 16:00", help="t=0 的 PT 时间戳（默认与 population 分析一致）")
    parser.add_argument("--min-edge-weight", type=float, default=1.0, help="构网时保留的最小 n_crisis 边权")
    parser.add_argument("--reservoir-size", type=int, default=200_000, help="用于全局分位数/直方图的 reservoir sample 大小")
    parser.add_argument("--random-seed", type=int, default=0, help="随机种子（reservoir sampling）")
    parser.add_argument(
        "--snapshot-offset-hours",
        type=float,
        nargs="*",
        default=[-24.0, 24.0, 168.0],
        help="选定窗口：相对 t0 的小时偏移（默认：-24, +24, +168）",
    )
    parser.add_argument("--percolation-n-thresholds", type=int, default=30, help="渗流扫描的阈值个数（quantile grid）")
    parser.add_argument("--network-top-edges", type=int, default=300, help="网络可视化中保留的 top edges 数量")
    args = parser.parse_args()

    cfg = Config(
        data_root=args.data_root,
        output_dir=args.output_dir,
        t0_pt=pd.Timestamp(str(args.t0_pt)),
        min_edge_weight=float(args.min_edge_weight),
        reservoir_size=int(args.reservoir_size),
        random_seed=int(args.random_seed),
        snapshot_offsets_hours=tuple(float(x) for x in args.snapshot_offset_hours),
        percolation_n_thresholds=int(args.percolation_n_thresholds),
        network_top_edges=int(args.network_top_edges),
    )
    run(cfg, max_files=args.max_files)


if __name__ == "__main__":
    cli_main()
