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
from disaster.population_io import load_population_file, parse_window_start_pt
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    data_root: Path
    output_dir: Path
    epicenter_lat: float = 37.174
    epicenter_lon: float = 37.032
    t0_pt: pd.Timestamp = pd.Timestamp("2023-02-05 16:00")
    only_hour_pt: int = 8
    outflow_phi_threshold: float = 0.9
    inflow_phi_threshold: float = 1.1
    distance_bins_km: tuple[float, ...] = (0.0, 25.0, 50.0, 100.0, 200.0, float("inf"))
    snapshot_offsets_hours: tuple[float, ...] = (-8.0, 16.0, 160.0)


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _distance_band_labels(bins: tuple[float, ...]) -> list[str]:
    labels: list[str] = []
    for i in range(len(bins) - 1):
        lo, hi = float(bins[i]), float(bins[i + 1])
        if np.isinf(hi):
            labels.append(f"{int(lo)}km+")
        else:
            labels.append(f"{int(lo)}-{int(hi)}km")
    return labels


def _pick_nearest_windows(windows: list[dict], offsets_hours: tuple[float, ...]) -> list[dict]:
    if not windows:
        return []
    picked: list[dict] = []
    for off in offsets_hours:
        best = min(windows, key=lambda r: abs(float(r["hours_since_quake"]) - float(off)))
        picked.append(best)
    seen = set()
    uniq: list[dict] = []
    for r in picked:
        key = (str(r["path"]), float(r["hours_since_quake"]))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq


def _safe_weighted_centroid(lat: np.ndarray, lon: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    mask = np.isfinite(lat) & np.isfinite(lon) & np.isfinite(w) & (w > 0)
    if not np.any(mask):
        return float("nan"), float("nan")
    ww = w[mask].astype(float)
    ww_sum = float(np.sum(ww))
    if ww_sum <= 0:
        return float("nan"), float("nan")
    return float(np.sum(lat[mask] * ww) / ww_sum), float(np.sum(lon[mask] * ww) / ww_sum)


def run(cfg: Config, *, max_files: int | None = None) -> None:
    pop_dir = cfg.data_root / "population"
    if not pop_dir.exists():
        raise FileNotFoundError(f"未找到目录：{pop_dir}")

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

    files_all = sorted(pop_dir.glob("*.csv"))
    if not files_all:
        raise FileNotFoundError(f"目录为空：{pop_dir}")

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
        raise FileNotFoundError(f"未找到 hour={cfg.only_hour_pt} 的 population 文件：{pop_dir}")

    band_labels = _distance_band_labels(cfg.distance_bins_km)
    bands = list(cfg.distance_bins_km)

    by_window_rows: list[dict] = []
    by_band_rows: list[dict] = []
    flow_rows: list[dict] = []

    picked = _pick_nearest_windows(windows, cfg.snapshot_offsets_hours)
    picked_set = {str(r["path"]) for r in picked}
    picked_payload: dict[float, pd.DataFrame] = {}

    for i, meta in enumerate(windows, start=1):
        path = Path(meta["path"])
        df = load_population_file(path)

        n_baseline = pd.to_numeric(df["n_baseline"], errors="coerce")
        n_crisis = pd.to_numeric(df["n_crisis"], errors="coerce")
        lat = pd.to_numeric(df["lat"], errors="coerce")
        lon = pd.to_numeric(df["lon"], errors="coerce")

        distance_km = haversine_km(lat.to_numpy(dtype=float), lon.to_numpy(dtype=float), cfg.epicenter_lat, cfg.epicenter_lon)
        phi_ratio = n_crisis.to_numpy(dtype=float) / n_baseline.to_numpy(dtype=float)
        phi_ratio = np.where(np.isfinite(phi_ratio), phi_ratio, np.nan)

        # flow type classification
        flow_type = np.full(len(df), "unknown", dtype=object)
        flow_type[np.isfinite(phi_ratio) & (phi_ratio < float(cfg.outflow_phi_threshold))] = "outflow"
        flow_type[np.isfinite(phi_ratio) & (phi_ratio > float(cfg.inflow_phi_threshold))] = "inflow"
        flow_type[np.isfinite(phi_ratio) & (phi_ratio >= float(cfg.outflow_phi_threshold)) & (phi_ratio <= float(cfg.inflow_phi_threshold))] = "stable"

        diff = n_crisis.to_numpy(dtype=float) - n_baseline.to_numpy(dtype=float)
        net_change = float(np.nansum(diff))

        # outflow/inflow subsets
        out_mask = flow_type == "outflow"
        in_mask = flow_type == "inflow"

        outflow_tile_count = int(np.sum(out_mask))
        inflow_tile_count = int(np.sum(in_mask))
        stable_tile_count = int(np.sum(flow_type == "stable"))
        unknown_tile_count = int(np.sum(flow_type == "unknown"))

        outflow_avg_distance = float(np.nanmean(distance_km[out_mask])) if outflow_tile_count else float("nan")
        inflow_avg_distance = float(np.nanmean(distance_km[in_mask])) if inflow_tile_count else float("nan")

        out_cent_lat, out_cent_lon = _safe_weighted_centroid(
            lat.to_numpy(dtype=float),
            lon.to_numpy(dtype=float),
            n_baseline.to_numpy(dtype=float) * out_mask.astype(float),
        )
        in_cent_lat, in_cent_lon = _safe_weighted_centroid(
            lat.to_numpy(dtype=float),
            lon.to_numpy(dtype=float),
            n_crisis.to_numpy(dtype=float) * in_mask.astype(float),
        )

        by_window_rows.append(
            {
                "window_start_pt": pd.Timestamp(meta["window_start_pt"]),
                "hours_since_quake": float(meta["hours_since_quake"]),
                "only_hour_pt": int(cfg.only_hour_pt),
                "outflow_phi_threshold": float(cfg.outflow_phi_threshold),
                "inflow_phi_threshold": float(cfg.inflow_phi_threshold),
                "outflow_tile_count": outflow_tile_count,
                "inflow_tile_count": inflow_tile_count,
                "stable_tile_count": stable_tile_count,
                "unknown_tile_count": unknown_tile_count,
                "net_population_change": net_change,
                "outflow_centroid_lat": out_cent_lat,
                "outflow_centroid_lon": out_cent_lon,
                "inflow_centroid_lat": in_cent_lat,
                "inflow_centroid_lon": in_cent_lon,
                "outflow_avg_distance": outflow_avg_distance,
                "inflow_avg_distance": inflow_avg_distance,
            }
        )

        # flow classification summary（long）
        for ft in ["outflow", "stable", "inflow", "unknown"]:
            flow_rows.append(
                {
                    "window_start_pt": pd.Timestamp(meta["window_start_pt"]),
                    "hours_since_quake": float(meta["hours_since_quake"]),
                    "flow_type": ft,
                    "tile_count": int(np.sum(flow_type == ft)),
                }
            )

        # distance bands（long）
        band_idx = pd.cut(
            distance_km,
            bins=bands,
            right=False,
            labels=band_labels,
            include_lowest=True,
        )
        both = n_baseline.notna() & n_crisis.notna()
        tmp = pd.DataFrame(
            {
                "distance_band": band_idx.astype(str),
                "n_baseline": n_baseline,
                "n_crisis": n_crisis,
                # 用 baseline∩crisis 的 overlap tiles 构造“可比较子集”，避免新 tiles 稀释平均值
                "baseline_overlap": n_baseline.where(both),
                "crisis_overlap": n_crisis.where(both),
            }
        )
        band_agg = (
            tmp.groupby("distance_band", observed=True)
            .agg(
                n_tiles=("n_baseline", "count"),
                n_tiles_crisis=("n_crisis", "count"),
                n_tiles_overlap=("baseline_overlap", "count"),
                baseline_sum=("n_baseline", "sum"),
                crisis_sum=("n_crisis", "sum"),
                baseline_sum_overlap=("baseline_overlap", "sum"),
                crisis_sum_overlap=("crisis_overlap", "sum"),
            )
            .reset_index()
        )
        band_agg["baseline_mean"] = band_agg["baseline_sum"] / band_agg["n_tiles"]
        band_agg["crisis_mean"] = np.where(
            band_agg["n_tiles_crisis"] > 0,
            band_agg["crisis_sum"] / band_agg["n_tiles_crisis"],
            np.nan,
        )
        band_agg["tile_coverage_ratio"] = np.where(
            band_agg["n_tiles"] > 0,
            band_agg["n_tiles_crisis"] / band_agg["n_tiles"],
            np.nan,
        )
        band_agg["baseline_mean_overlap"] = np.where(
            band_agg["n_tiles_overlap"] > 0,
            band_agg["baseline_sum_overlap"] / band_agg["n_tiles_overlap"],
            np.nan,
        )
        band_agg["crisis_mean_overlap"] = np.where(
            band_agg["n_tiles_overlap"] > 0,
            band_agg["crisis_sum_overlap"] / band_agg["n_tiles_overlap"],
            np.nan,
        )
        band_agg["tile_overlap_ratio"] = np.where(
            band_agg["n_tiles"] > 0,
            band_agg["n_tiles_overlap"] / band_agg["n_tiles"],
            np.nan,
        )
        band_agg["net_change"] = band_agg["crisis_sum"] - band_agg["baseline_sum"]
        band_agg["phi_aggregate"] = band_agg["crisis_sum"] / band_agg["baseline_sum"]
        band_agg.insert(0, "window_start_pt", pd.Timestamp(meta["window_start_pt"]))
        band_agg.insert(1, "hours_since_quake", float(meta["hours_since_quake"]))
        by_band_rows.append(band_agg)

        if str(meta["path"]) in picked_set:
            picked_payload[float(meta["hours_since_quake"])] = pd.DataFrame(
                {
                    "lat": lat,
                    "lon": lon,
                    "flow_type": flow_type,
                }
            )

        if i % 20 == 0:
            print(f"[population_redistribution] processed {i}/{len(windows)} windows...")

    by_window = pd.DataFrame(by_window_rows).sort_values("hours_since_quake", kind="stable")
    by_band = pd.concat(by_band_rows, ignore_index=True).sort_values(["hours_since_quake", "distance_band"], kind="stable")
    flow_summary = pd.DataFrame(flow_rows).sort_values(["hours_since_quake", "flow_type"], kind="stable")

    out_by_window = out.tables / "redistribution_by_window.csv"
    out_by_band = out.tables / "redistribution_by_distance_band.csv"
    out_flow = out.tables / "flow_classification_summary.csv"
    by_window.to_csv(out_by_window, index=False)
    by_band.to_csv(out_by_band, index=False)
    flow_summary.to_csv(out_flow, index=False)

    # figures
    with ps.paper_style():
        import matplotlib.pyplot as plt

        # net_change by distance band timeseries
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        for band, sub in by_band.groupby("distance_band", sort=False, observed=True):
            sub = sub.sort_values("hours_since_quake", kind="stable")
            ax.plot(sub["hours_since_quake"], sub["net_change"], marker="o", label=str(band))
        ax.axvline(0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.set_xlabel("Hours since earthquake (PT, 08:00 windows)")
        ax.set_ylabel("Net population change (sum n_crisis - n_baseline)")
        ax.set_title("Net population change by distance band")
        ax.legend(frameon=False, ncol=3)
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "net_change_by_distance_timeseries.png")
        plt.close(fig)

        # phi_aggregate heatmap
        pivot = (
            by_band.pivot_table(index="distance_band", columns="hours_since_quake", values="phi_aggregate", aggfunc="mean")
            .reindex(index=band_labels)
            .sort_index()
        )
        xs = pivot.columns.to_numpy(dtype=float)
        ys = np.arange(pivot.shape[0], dtype=float)
        z = pivot.to_numpy(dtype=float)

        fig, ax = plt.subplots(figsize=(ps.FIGSIZE_FULL[0], ps.FIGSIZE_FULL[1] * 0.9))
        im = ax.imshow(z, aspect="auto", cmap="RdBu_r", vmin=0.8, vmax=1.2)
        ax.set_yticks(ys)
        ax.set_yticklabels(pivot.index.tolist())
        # x 轴 tick 稀疏化
        if xs.size:
            step = max(1, int(xs.size / 8))
            xt = np.arange(0, xs.size, step)
            ax.set_xticks(xt)
            ax.set_xticklabels([f"{int(xs[j])}" for j in xt], rotation=0)
        ax.set_xlabel("Hours since earthquake (08:00 windows)")
        ax.set_ylabel("Distance band")
        ax.set_title("phi_aggregate(distance, time) heatmap (n_crisis_sum / n_baseline_sum)")
        cb = fig.colorbar(im, ax=ax, shrink=0.9)
        cb.set_label("phi_aggregate")
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "phi_aggregate_heatmap.png")
        plt.close(fig)

        # inflow/outflow spatial（代表性窗口）
        if picked_payload:
            hs_sorted = sorted(picked_payload.keys())
            n = len(hs_sorted)
            fig, axes = plt.subplots(nrows=1, ncols=n, figsize=(ps.FIGSIZE_FULL[0] * n, ps.FIGSIZE_FULL[1]), sharex=False, sharey=False)
            if n == 1:
                axes = [axes]

            color = {"outflow": ps.OKABE_ITO["vermillion"], "inflow": ps.OKABE_ITO["bluish_green"], "stable": ps.OKABE_ITO["gray"]}
            for ax, hs in zip(axes, hs_sorted, strict=False):
                sub = picked_payload[hs]
                for ft in ["outflow", "inflow", "stable"]:
                    m = sub["flow_type"].astype(str) == ft
                    if not m.any():
                        continue
                    ax.scatter(
                        pd.to_numeric(sub.loc[m, "lon"], errors="coerce"),
                        pd.to_numeric(sub.loc[m, "lat"], errors="coerce"),
                        s=6,
                        alpha=0.45 if ft != "stable" else 0.15,
                        color=color[ft],
                        linewidths=0,
                        label=ft,
                        rasterized=True,
                    )
                ax.scatter([cfg.epicenter_lon], [cfg.epicenter_lat], s=80, c=ps.OKABE_ITO["yellow"], edgecolors="black", linewidths=1.0, zorder=5)
                ax.set_title(f"{int(round(float(hs)))}h")
                ax.set_xlabel("Lon")
                ax.set_ylabel("Lat")
                ps.despine(ax)

            handles, labels = axes[0].get_legend_handles_labels()
            if handles:
                fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.02), ncol=3, frameon=False)
                fig.subplots_adjust(bottom=0.12, wspace=0.15)
            else:
                fig.tight_layout()
            fig.suptitle("Population inflow/outflow classification (selected 08:00 windows)", y=0.98)
            save_png_and_pdf(ps, fig, out.figures / "inflow_outflow_spatial.png")
            plt.close(fig)

    t_min = pd.to_datetime(by_window["window_start_pt"]).min()
    t_max = pd.to_datetime(by_window["window_start_pt"]).max()
    readme = f"""# Population Redistribution (08:00 windows)

本目录对应 `Docs/research_plan_network_redistribution.md` 的 **Task 2**：
用“空间再分布”而非“relaxation”视角刻画人口变化。

## 口径

- 仅使用 PT {int(cfg.only_hour_pt):02d}:00 的 population 文件（控制时段周期性）
- phi_ratio = n_crisis / n_baseline
- outflow：phi_ratio < {float(cfg.outflow_phi_threshold)}
- inflow：phi_ratio > {float(cfg.inflow_phi_threshold)}

## 全局信息

- 处理窗口数：{len(by_window)}
- 时间跨度（PT）：{t_min} → {t_max}

## 主要产物

- `tables/redistribution_by_window.csv`：每个窗口的再分布指标（tile 计数、质心、净变化）
- `tables/redistribution_by_distance_band.csv`：按距离带的 phi_aggregate / net_change 时间序列
- `tables/flow_classification_summary.csv`：outflow/stable/inflow 的 tile 计数
- `figures/phi_aggregate_heatmap.*`：phi_aggregate(distance,time) 热力图
- `tables/redistribution_by_distance_band.csv` 额外列：
  - `n_tiles_crisis` / `crisis_mean` / `tile_coverage_ratio`（crisis 端可见性代理）
  - `n_tiles_overlap` / `crisis_mean_overlap` / `tile_overlap_ratio`（baseline∩crisis overlap 子集，避免新 tiles 稀释）
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_by_window}")
    print(f"Done. Wrote: {out_by_band}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("Data/Turkiye Turkey Earthquake Full Country Version Feb 8 2023"),
        help="数据根目录（包含 population/ 子目录）",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/population_redistribution"), help="输出目录")
    parser.add_argument("--max-files", type=int, default=None, help="只处理前 N 个窗口（用于冒烟测试）")
    parser.add_argument("--center-lat", type=float, default=None, help="灾难中心/震中纬度（用于距离分带；默认使用脚本内置值）")
    parser.add_argument("--center-lon", type=float, default=None, help="灾难中心/震中经度（用于距离分带；默认使用脚本内置值）")
    parser.add_argument("--t0-pt", type=str, default="2023-02-05 16:00", help="t=0 的 PT 时间戳")
    parser.add_argument("--only-hour-pt", type=int, default=8, help="仅保留该小时（PT）的窗口（默认 08:00）")
    parser.add_argument("--outflow-phi-threshold", type=float, default=0.9, help="outflow 判定阈值（phi_ratio < thr）")
    parser.add_argument("--inflow-phi-threshold", type=float, default=1.1, help="inflow 判定阈值（phi_ratio > thr）")
    parser.add_argument(
        "--snapshot-offset-hours",
        type=float,
        nargs="*",
        default=[-8.0, 16.0, 160.0],
        help="空间图代表性窗口：相对 t0 的小时偏移（取最近匹配的 08:00 窗口）",
    )
    args = parser.parse_args()

    center_lat = float(args.center_lat) if args.center_lat is not None else 37.174
    center_lon = float(args.center_lon) if args.center_lon is not None else 37.032

    cfg = Config(
        data_root=args.data_root,
        output_dir=args.output_dir,
        epicenter_lat=center_lat,
        epicenter_lon=center_lon,
        t0_pt=pd.Timestamp(str(args.t0_pt)),
        only_hour_pt=int(args.only_hour_pt),
        outflow_phi_threshold=float(args.outflow_phi_threshold),
        inflow_phi_threshold=float(args.inflow_phi_threshold),
        snapshot_offsets_hours=tuple(float(x) for x in args.snapshot_offset_hours),
    )
    run(cfg, max_files=args.max_files)


if __name__ == "__main__":
    cli_main()
