from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.geo import haversine_km
from disaster.population_io import resolve_subdir
from disaster.viz import save_png_and_pdf


_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")
_DATE_TIME_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})_(\d{4})")


@dataclass(frozen=True)
class Config:
    data_root: Path
    output_dir: Path
    epicenter_lat: float = 37.174
    epicenter_lon: float = 37.032
    t0_pt: pd.Timestamp = pd.Timestamp("2023-02-05 16:00")
    distance_bins_km: tuple[float, ...] = (0.0, 25.0, 50.0, 100.0, 200.0, float("inf"))
    population_by_band_csv: Path | None = Path("outputs/population_redistribution/tables/redistribution_by_distance_band.csv")


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


def _parse_ds_from_filename(path: Path) -> pd.Timestamp | None:
    m = _DATE_TIME_RE.search(path.name)
    if m:
        date_str, hhmm = m.group(1), m.group(2)
        hh, mm = int(hhmm[:2]), int(hhmm[2:])
        return pd.Timestamp(f"{date_str} {hh:02d}:{mm:02d}")
    m = _DATE_RE.search(path.name)
    if m:
        return pd.Timestamp(f"{m.group(1)} 00:00")
    return None


def _load_network_coverage_file(path: Path) -> pd.DataFrame:
    wanted = {
        "quadkey",
        "latitude",
        "longitude",
        "lat",
        "lon",
        "coverage",
        "no_coverage",
        "p_connectivity",
        "country",
        "ds",
        "date_time",
    }
    df = pd.read_csv(path, usecols=lambda c: c in wanted, na_values=["\\N", ""])
    df = df.rename(columns={"latitude": "lat", "longitude": "lon"})
    for col in ["lat", "lon", "coverage", "no_coverage", "p_connectivity"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "ds" in df.columns:
        df["ds"] = pd.to_datetime(df["ds"], errors="coerce")
    return df


def run(cfg: Config) -> None:
    nc_dir = resolve_subdir(cfg.data_root, "network coverage")

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

    files = sorted(nc_dir.rglob("*.csv"))
    if not files:
        raise FileNotFoundError(f"目录为空：{nc_dir}")

    bins = list(cfg.distance_bins_km)
    labels = _distance_band_labels(cfg.distance_bins_km)

    rows: list[dict] = []
    for i, path in enumerate(files, start=1):
        df = _load_network_coverage_file(path)
        if df.empty or "lat" not in df.columns or "lon" not in df.columns:
            continue

        ds = None
        if "ds" in df.columns:
            ds = df["ds"].dropna().iloc[0] if df["ds"].notna().any() else None
        if ds is None:
            ds = _parse_ds_from_filename(path)
        if ds is None:
            continue
        ds = pd.Timestamp(ds)

        dist = haversine_km(
            pd.to_numeric(df["lat"], errors="coerce").to_numpy(dtype=float),
            pd.to_numeric(df["lon"], errors="coerce").to_numpy(dtype=float),
            cfg.epicenter_lat,
            cfg.epicenter_lon,
        )
        band = pd.cut(dist, bins=bins, right=False, labels=labels, include_lowest=True).astype(str)

        # outage proxy：优先 no_coverage，其次 1-coverage，其次 1-p_connectivity
        if "no_coverage" in df.columns:
            outage = pd.to_numeric(df["no_coverage"], errors="coerce").to_numpy(dtype=float)
        elif "coverage" in df.columns:
            cov = pd.to_numeric(df["coverage"], errors="coerce").to_numpy(dtype=float)
            outage = 1.0 - cov
        elif "p_connectivity" in df.columns:
            p = pd.to_numeric(df["p_connectivity"], errors="coerce").to_numpy(dtype=float)
            outage = 1.0 - p
        else:
            continue

        tmp = pd.DataFrame({"band": band, "outage": outage})
        tmp = tmp[tmp["band"].isin(set(labels))].copy()
        g = tmp.groupby("band", observed=True).agg(n_tiles=("outage", "count"), outage_mean=("outage", "mean")).reset_index()
        for row in g.itertuples(index=False):
            rows.append(
                {
                    "ds": pd.Timestamp(ds).normalize(),
                    "hours_since_quake": float((pd.Timestamp(ds) - cfg.t0_pt).total_seconds() / 3600.0),
                    "band": str(row.band),
                    "n_tiles": int(row.n_tiles),
                    "outage_mean": float(row.outage_mean),
                    "source_file": str(path.name),
                }
            )

        if i % 30 == 0:
            print(f"[network_coverage_validation] processed {i}/{len(files)} files...")

    if not rows:
        raise SystemExit("未生成任何 network coverage 统计结果（检查字段名或文件格式）。")

    nc = pd.DataFrame(rows).sort_values(["ds", "band"], kind="stable")
    out_nc = out.tables / "network_coverage_outage_by_band.csv"
    nc.to_csv(out_nc, index=False)

    # 可选：与 population 距离带表对齐（按日期）
    out_join = None
    pop_path = cfg.population_by_band_csv
    if pop_path is not None and Path(pop_path).exists():
        pop = pd.read_csv(pop_path, parse_dates=["window_start_pt"])
        if {"window_start_pt", "distance_band", "phi_aggregate"} <= set(pop.columns):
            pop["ds"] = pd.to_datetime(pop["window_start_pt"]).dt.normalize()
            pop = pop.rename(columns={"distance_band": "band"})
            pop["phi_aggregate"] = pd.to_numeric(pop["phi_aggregate"], errors="coerce")
            pop = pop[pop["band"].isin(set(labels))].copy()
            merged = nc.merge(pop[["ds", "band", "phi_aggregate"]], on=["ds", "band"], how="left")
            out_join = out.tables / "network_coverage_vs_population_by_band.csv"
            merged.to_csv(out_join, index=False)

    # plot: outage(t) by band
    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        for band, sub in nc.groupby("band", sort=False, observed=True):
            sub = sub.sort_values("hours_since_quake", kind="stable")
            ax.plot(sub["hours_since_quake"], sub["outage_mean"], marker="o", label=str(band))
        ax.axvline(0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.axhline(0.0, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.6)
        ax.set_xlabel("Hours since earthquake (PT)")
        ax.set_ylabel("Outage proxy (mean)")
        ax.set_title("Network coverage outage proxy by distance band")
        ax.legend(frameon=False, ncol=3)
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "network_outage_timeseries.png")
        plt.close(fig)

    readme = f"""# Network Coverage Validation

目的：排除“Population 下降只是因为手机没信号/网络中断”的混淆。
本脚本把 network coverage 数据按距离带聚合，给出 outage proxy 的时序；并可选与 population 距离带表按日期对齐输出。

## 输入

- `{cfg.data_root}/network coverage/**/*.csv`
- （可选）`{cfg.population_by_band_csv}`

## 输出

- `tables/network_coverage_outage_by_band.csv`
- `figures/network_outage_timeseries.*`
- （可选）`tables/network_coverage_vs_population_by_band.csv`
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_nc}")
    if out_join is not None:
        print(f"Done. Wrote: {out_join}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("Data/Turkiye Turkey Earthquake Full Country Version Feb 8 2023"),
        help="数据根目录（包含 network coverage/ 子目录）",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/network_coverage_validation"), help="输出目录")
    parser.add_argument("--center-lat", type=float, default=None, help="灾难中心/震中纬度（默认使用脚本内置值）")
    parser.add_argument("--center-lon", type=float, default=None, help="灾难中心/震中经度（默认使用脚本内置值）")
    parser.add_argument("--t0-pt", type=str, default="2023-02-05 16:00", help="t=0 的 PT 时间戳")
    parser.add_argument(
        "--population-by-band-csv",
        type=Path,
        default=Path("outputs/population_redistribution/tables/redistribution_by_distance_band.csv"),
        help="（可选）population 距离带表，用于对齐对照",
    )
    args = parser.parse_args()

    center_lat = float(args.center_lat) if args.center_lat is not None else 37.174
    center_lon = float(args.center_lon) if args.center_lon is not None else 37.032

    pop = args.population_by_band_csv if args.population_by_band_csv.exists() else None
    cfg = Config(
        data_root=args.data_root,
        output_dir=args.output_dir,
        epicenter_lat=center_lat,
        epicenter_lon=center_lon,
        t0_pt=pd.Timestamp(str(args.t0_pt)),
        population_by_band_csv=pop,
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()
