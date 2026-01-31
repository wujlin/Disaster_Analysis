from __future__ import annotations

import argparse
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.geo import distance_bin_labels, haversine_km
from disaster.population_io import load_population_file, parse_window_start_pt
from disaster.relaxation_fit import try_fit_relaxation_models
from disaster.viz import plot_relaxation_curves, plot_zscore_heatmap


@dataclass(frozen=True)
class Config:
    data_root: Path
    output_dir: Path
    epicenter_lat: float = 37.174
    epicenter_lon: float = 37.032
    t0_pt: pd.Timestamp = pd.Timestamp("2023-02-05 16:00")
    epsilon: float = 1.0
    distance_bins_km: tuple[float, ...] = (0, 50, 100, 200, 500, 1000, float("inf"))


def _ensure_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path
    fits: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(
        root=root,
        figures=root / "figures",
        tables=root / "tables",
        fits=root / "fits",
    )


def summarize_by_distance(
    df: pd.DataFrame,
    *,
    cfg: Config,
    hours_since_quake: float,
    window_start_pt: pd.Timestamp,
) -> pd.DataFrame:
    dist_km = haversine_km(df["lat"].to_numpy(), df["lon"].to_numpy(), cfg.epicenter_lat, cfg.epicenter_lon)
    labels = distance_bin_labels(cfg.distance_bins_km)
    df = df.assign(
        dist_km=dist_km,
        distance_bin=pd.cut(
            dist_km,
            bins=list(cfg.distance_bins_km),
            right=False,
            labels=labels,
            include_lowest=True,
        ),
    )

    n_baseline = pd.to_numeric(df["n_baseline"], errors="coerce")
    n_crisis = pd.to_numeric(df["n_crisis"], errors="coerce")
    z = pd.to_numeric(df["z_score"], errors="coerce")
    if "percent_change" in df.columns:
        pct = pd.to_numeric(df["percent_change"], errors="coerce")
    else:
        pct = pd.Series(np.nan, index=df.index)
    if "n_difference" in df.columns:
        n_diff = pd.to_numeric(df["n_difference"], errors="coerce")
    else:
        n_diff = pd.Series(np.nan, index=df.index)

    phi = (n_crisis - n_baseline) / (n_baseline + cfg.epsilon)

    z_clip_pos = np.where(z.isna(), np.nan, (z >= 4).astype(float))
    z_clip_neg = np.where(z.isna(), np.nan, (z <= -4).astype(float))

    df = df.assign(
        n_baseline=n_baseline,
        n_crisis=n_crisis,
        z_score=z,
        phi=phi,
        percent_change=pct,
        n_difference=n_diff,
        z_clip_pos=z_clip_pos,
        z_clip_neg=z_clip_neg,
    )

    agg = (
        df.groupby("distance_bin", observed=True)
        .agg(
            tile_count=("quadkey", "count"),
            n_baseline_sum=("n_baseline", "sum"),
            n_baseline_mean=("n_baseline", "mean"),
            n_baseline_std=("n_baseline", "std"),
            n_baseline_count=("n_baseline", "count"),
            n_crisis_sum=("n_crisis", "sum"),
            n_crisis_mean=("n_crisis", "mean"),
            n_crisis_std=("n_crisis", "std"),
            n_crisis_count=("n_crisis", "count"),
            z_score_mean=("z_score", "mean"),
            z_score_std=("z_score", "std"),
            z_score_count=("z_score", "count"),
            phi_mean=("phi", "mean"),
            phi_std=("phi", "std"),
            phi_count=("phi", "count"),
            percent_change_mean=("percent_change", "mean"),
            percent_change_std=("percent_change", "std"),
            percent_change_count=("percent_change", "count"),
            n_difference_mean=("n_difference", "mean"),
            n_difference_std=("n_difference", "std"),
            n_difference_count=("n_difference", "count"),
            z_clip_pos_rate=("z_clip_pos", "mean"),
            z_clip_neg_rate=("z_clip_neg", "mean"),
        )
        .reset_index()
    )

    agg.insert(0, "window_start_pt", window_start_pt)
    agg.insert(1, "hours_since_quake", hours_since_quake)
    return agg


def run(cfg: Config, *, max_files: int | None = None) -> None:
    pop_dir = cfg.data_root / "population"
    if not pop_dir.exists():
        raise FileNotFoundError(f"未找到目录：{pop_dir}")

    out = _output_dirs(cfg.output_dir)
    _ensure_output_dir(out.root)
    _ensure_output_dir(out.figures)
    _ensure_output_dir(out.tables)
    _ensure_output_dir(out.fits)

    files = sorted(pop_dir.glob("*.csv"))
    if max_files is not None:
        files = files[: max_files]
    if not files:
        raise FileNotFoundError(f"目录为空：{pop_dir}")

    ps = None
    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    # 1) t=0 热力图（2023-02-05 16:00 PT 窗口）
    t0_candidates = list(pop_dir.glob("*_2023-02-05_1600.csv"))
    if len(t0_candidates) != 1:
        raise RuntimeError(f"无法唯一定位 t=0 文件（2023-02-05_1600）：{t0_candidates}")
    t0_df = load_population_file(t0_candidates[0])
    t0_df["z_score"] = pd.to_numeric(t0_df["z_score"], errors="coerce")

    with ps.paper_style():
        plot_zscore_heatmap(
            t0_df,
            out.figures / "population_zscore_heatmap_t0_2023-02-05_1600PT.png",
            title="Population z_score heatmap (t=0 window, 2023-02-05 16:00 PT)",
            cfg=cfg,
            ps=ps,
        )

    # 2) 全时序：按距离箱聚合
    records: list[pd.DataFrame] = []
    for i, path in enumerate(files, start=1):
        window_start = parse_window_start_pt(path)
        hours = (window_start - cfg.t0_pt).total_seconds() / 3600.0
        df = load_population_file(path)
        df["z_score"] = pd.to_numeric(df["z_score"], errors="coerce")
        records.append(summarize_by_distance(df, cfg=cfg, hours_since_quake=hours, window_start_pt=window_start))
        if i % 20 == 0:
            print(f"[population] processed {i}/{len(files)} files...")

    ts = pd.concat(records, ignore_index=True)
    ts = ts.sort_values(["hours_since_quake", "distance_bin"], kind="stable")
    ts.to_csv(out.tables / "population_relaxation_by_distance.csv", index=False)

    with ps.paper_style():
        plot_relaxation_curves(
            ts,
            y_col="z_score_mean",
            y_std_col="z_score_std",
            y_n_col="z_score_count",
            output_path=out.figures / "population_relaxation_zscore_by_distance.png",
            title="Population relaxation: mean z_score(t) by distance to epicenter",
            cfg=cfg,
            ps=ps,
        )
        plot_relaxation_curves(
            ts,
            y_col="phi_mean",
            y_std_col="phi_std",
            y_n_col="phi_count",
            output_path=out.figures / "population_relaxation_phi_by_distance.png",
            title="Population relaxation (robustness): mean phi(t) by distance to epicenter",
            cfg=cfg,
            ps=ps,
        )

    # 3) 拟合（可选：若环境缺 scipy 会自动跳过）
    try_fit_relaxation_models(
        ts,
        out.fits / "population_relaxation_fit_best_bic.csv",
        exclude_t0=True,
    )

    # 4) clipping 概览
    clip_summary = (
        ts.groupby("distance_bin", observed=True)
        .agg(
            n_windows=("hours_since_quake", "count"),
            z_clip_pos_rate_mean=("z_clip_pos_rate", "mean"),
            z_clip_neg_rate_mean=("z_clip_neg_rate", "mean"),
        )
        .reset_index()
    )
    clip_summary.to_csv(out.tables / "population_zscore_clipping_summary.csv", index=False)

    print(f"Done. Outputs written to: {out.root}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("Data/Turkiye Turkey Earthquake Full Country Version Feb 8 2023"),
        help="数据根目录（包含 population/ 子目录）",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/population_relaxation"), help="输出目录")
    parser.add_argument("--max-files", type=int, default=None, help="只处理前 N 个文件（用于快速冒烟测试）")
    parser.add_argument(
        "--bin-width-km",
        type=float,
        default=None,
        help="若指定，则使用等宽距离分箱（例如 50 表示每 50km 一个 bin），覆盖到 max-bin-km，并额外加一个开区间 bin（max-bin-km+）。",
    )
    parser.add_argument("--max-bin-km", type=float, default=1000.0, help="等宽距离分箱的最大右端（默认 1000km）")
    args = parser.parse_args()

    cfg = Config(data_root=args.data_root, output_dir=args.output_dir)
    if args.bin_width_km is not None:
        width = float(args.bin_width_km)
        if not np.isfinite(width) or width <= 0:
            raise SystemExit(f"--bin-width-km 必须为正数：{args.bin_width_km}")
        max_km = float(args.max_bin_km)
        if not np.isfinite(max_km) or max_km <= width:
            raise SystemExit(f"--max-bin-km 必须大于 bin width：max={args.max_bin_km}, width={args.bin_width_km}")

        edges = list(np.arange(0.0, max_km + 1e-9, width))
        if not edges or edges[-1] != max_km:
            edges.append(max_km)
        edges.append(float("inf"))
        cfg = replace(cfg, distance_bins_km=tuple(float(x) for x in edges))
    run(cfg, max_files=args.max_files)
