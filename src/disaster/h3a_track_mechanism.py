from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.h3a_track_report import _half_distance_r0, _load_storm_metadata, _profile_from_phi_long, _storm_name_from_center_by_window
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    output_root: Path
    out_dir: Path
    time_min_hours: float = 0.0
    time_max_hours: float = 72.0
    phi_col: str = "phi_aggregate"
    min_tiles: int = 0
    storm_metadata_csv: Path | None = None
    slugs: tuple[str, ...] = ()


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _infer_slugs(output_root: Path) -> list[str]:
    out: list[str] = []
    for p in sorted(output_root.glob("*/phi_heatmap/tables/phi_rt_long.csv")):
        out.append(p.parents[2].name)
    return out


def _polyline_length_km(lat: np.ndarray, lon: np.ndarray) -> float:
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    ok = np.isfinite(lat) & np.isfinite(lon)
    lat = lat[ok]
    lon = lon[ok]
    if lat.size < 2:
        return float("nan")
    r = 6371.0
    lat1 = np.radians(lat[:-1])
    lon1 = np.radians(lon[:-1])
    lat2 = np.radians(lat[1:])
    lon2 = np.radians(lon[1:])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    d = 2 * r * np.arcsin(np.sqrt(a))
    return float(np.nansum(d))


def _load_track_from_center_by_window(output_root: Path, slug: str) -> tuple[Path | None, str]:
    p = output_root / slug / "phi_heatmap" / "tables" / "center_by_window.csv"
    if not p.exists():
        return None, ""
    df = pd.read_csv(p)
    if df.empty:
        return None, ""
    track_csv = str(df.iloc[0].get("center_track_csv", "")).strip()
    storm_name = str(df.iloc[0].get("center_track_storm_name", "")).strip()
    if not track_csv:
        return None, storm_name
    return Path(track_csv), storm_name


def _load_track_points(track_csv: Path, *, storm_name: str) -> pd.DataFrame:
    df = pd.read_csv(track_csv)
    if "storm_name" in df.columns and storm_name:
        df = df[df["storm_name"].astype(str).str.strip().str.lower() == str(storm_name).strip().lower()].copy()
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["datetime_utc", "lat", "lon"]).copy()
    df = df.sort_values("datetime_utc", kind="stable")
    return df


def _corr(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    if int(np.sum(ok)) < 2:
        return float("nan")
    xx = x[ok]
    yy = y[ok]
    if float(np.nanstd(xx)) == 0.0 or float(np.nanstd(yy)) == 0.0:
        return float("nan")
    return float(np.corrcoef(xx, yy)[0, 1])


def run(cfg: Config) -> None:
    out_dir = Path(cfg.out_dir)
    figs = out_dir / "figures"
    tabs = out_dir / "tables"
    _ensure_dir(figs)
    _ensure_dir(tabs)

    slugs = list(cfg.slugs) if cfg.slugs else _infer_slugs(Path(cfg.output_root))
    if not slugs:
        raise SystemExit("未找到任何 hurricane 输出（请检查 output_root）")

    meta = _load_storm_metadata(cfg.storm_metadata_csv)

    rows: list[dict] = []
    for slug in slugs:
        p = Path(cfg.output_root) / slug / "phi_heatmap" / "tables" / "phi_rt_long.csv"
        if not p.exists():
            continue
        df_long = pd.read_csv(p)
        prof = _profile_from_phi_long(
            df_long,
            phi_col=str(cfg.phi_col),
            time_min=float(cfg.time_min_hours),
            time_max=float(cfg.time_max_hours),
        )
        if prof.empty:
            continue

        if int(cfg.min_tiles) > 0 and "n_eff_mean" in prof.columns:
            prof = prof[pd.to_numeric(prof["n_eff_mean"], errors="coerce") >= float(cfg.min_tiles)].copy()
        if prof.empty:
            continue

        r = pd.to_numeric(prof["r_center_km"], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(prof["abs_dev"], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(r) & np.isfinite(y) & (r > 0) & (y >= 0)
        r = r[ok]
        y = y[ok]
        if r.size < 3:
            continue
        y_max = float(np.nanmax(y))
        r0 = float(_half_distance_r0(r, y))

        storm_name = _storm_name_from_center_by_window(Path(cfg.output_root), slug)
        storm_meta = meta.get(storm_name.lower(), {}) if storm_name else {}

        baseline_total = float("nan")
        baseline_near_20 = float("nan")
        baseline_near_r0 = float("nan")
        exposure_frac_20 = float("nan")
        exposure_frac_r0 = float("nan")
        if "baseline_sum_mean" in prof.columns:
            b = pd.to_numeric(prof["baseline_sum_mean"], errors="coerce").to_numpy(dtype=float)
            rr = pd.to_numeric(prof["r_center_km"], errors="coerce").to_numpy(dtype=float)
            okb = np.isfinite(b) & np.isfinite(rr) & (rr >= 0)
            b = b[okb]
            rr = rr[okb]
            baseline_total = float(np.nansum(b)) if b.size else float("nan")
            baseline_near_20 = float(np.nansum(b[rr <= 20.0])) if b.size else float("nan")
            baseline_near_r0 = float(np.nansum(b[rr <= float(r0)])) if b.size and np.isfinite(r0) else float("nan")
            exposure_frac_20 = float(baseline_near_20 / baseline_total) if baseline_total and np.isfinite(baseline_total) else float("nan")
            exposure_frac_r0 = float(baseline_near_r0 / baseline_total) if baseline_total and np.isfinite(baseline_total) else float("nan")

        # track length
        track_csv, storm_name_track = _load_track_from_center_by_window(Path(cfg.output_root), slug)
        track_len_km = float("nan")
        if track_csv is not None and track_csv.exists():
            tr = _load_track_points(track_csv, storm_name=storm_name_track)
            if not tr.empty:
                track_len_km = _polyline_length_km(tr["lat"].to_numpy(dtype=float), tr["lon"].to_numpy(dtype=float))

        row = {
            "slug": str(slug),
            "storm_name": str(storm_name),
            "time_min_hours": float(cfg.time_min_hours),
            "time_max_hours": float(cfg.time_max_hours),
            "min_tiles": int(cfg.min_tiles),
            "r0_km": float(r0),
            "y_max_abs_phi_minus_1": float(y_max),
            "baseline_total_mean": float(baseline_total),
            "baseline_near_20km_mean": float(baseline_near_20),
            "baseline_near_r0_mean": float(baseline_near_r0),
            "exposure_frac_20km": float(exposure_frac_20),
            "exposure_frac_r0": float(exposure_frac_r0),
            "track_length_km": float(track_len_km),
        }
        if storm_meta:
            for k, v in storm_meta.items():
                if k in {"storm_name"}:
                    continue
                row[f"meta_{k}"] = v
        rows.append(row)

    if not rows:
        raise SystemExit("没有可用样本（请先生成 outputs_trackpath/<slug>/phi_heatmap/...）")

    df = pd.DataFrame(rows).sort_values("y_max_abs_phi_minus_1", ascending=False, kind="stable")
    df.to_csv(tabs / f"h3a_mechanism_summary_minTiles{int(cfg.min_tiles)}.csv", index=False)

    # correlations
    corr_rows = [
        {
            "x": "track_length_km",
            "y": "r0_km",
            "corr": _corr(df["track_length_km"].to_numpy(dtype=float), df["r0_km"].to_numpy(dtype=float)),
            "n": int(df.shape[0]),
        },
        {
            "x": "exposure_frac_20km",
            "y": "y_max_abs_phi_minus_1",
            "corr": _corr(df["exposure_frac_20km"].to_numpy(dtype=float), df["y_max_abs_phi_minus_1"].to_numpy(dtype=float)),
            "n": int(df.shape[0]),
        },
    ]
    pd.DataFrame(corr_rows).to_csv(tabs / f"h3a_mechanism_correlations_minTiles{int(cfg.min_tiles)}.csv", index=False)

    # plots (simple)
    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    import matplotlib.pyplot as plt

    with ps.paper_style():
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_HALF)
        ax.scatter(df["track_length_km"], df["r0_km"], s=55, color=ps.OKABE_ITO["blue"], alpha=0.9, linewidths=0)
        for _, r in df.iterrows():
            ax.text(float(r["track_length_km"]), float(r["r0_km"]), str(r.get("storm_name") or r["slug"]), fontsize=8)
        ax.set_xlabel("Track length (km)")
        ax.set_ylabel(r"$r_0$ (km)")
        ax.set_title("r0 vs track length")
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, figs / f"r0_vs_track_length_minTiles{int(cfg.min_tiles)}.png")
        plt.close(fig)

    with ps.paper_style():
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_HALF)
        ax.scatter(df["exposure_frac_20km"], df["y_max_abs_phi_minus_1"], s=55, color=ps.OKABE_ITO["vermillion"], alpha=0.9, linewidths=0)
        for _, r in df.iterrows():
            ax.text(float(r["exposure_frac_20km"]), float(r["y_max_abs_phi_minus_1"]), str(r.get("storm_name") or r["slug"]), fontsize=8)
        ax.set_xlabel("Exposure fraction (d_path<=20km)")
        ax.set_ylabel(r"$y_{max}=\max_r |\phi-1|$")
        ax.set_title("y_max vs exposure")
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, figs / f"ymax_vs_exposure_minTiles{int(cfg.min_tiles)}.png")
        plt.close(fig)


def cli_main() -> None:
    p = argparse.ArgumentParser(description="H3a: 机制层指标（r0 vs 轨迹长度，y_max vs 暴露）")
    p.add_argument("--output-root", type=Path, default=Path("outputs_trackpath"))
    p.add_argument("--out-dir", type=Path, default=Path("outputs_trackpath/_tmp_h3a_mechanism"))
    p.add_argument("--time-min-hours", type=float, default=0.0)
    p.add_argument("--time-max-hours", type=float, default=72.0)
    p.add_argument("--phi-col", type=str, default="phi_aggregate")
    p.add_argument("--min-tiles", type=int, default=0)
    p.add_argument("--slugs", type=str, nargs="*", default=[])
    p.add_argument("--storm-metadata-csv", type=Path, default=Path("Docs/storm_tracks/storm_intensity_2024.csv"))
    args = p.parse_args()

    cfg = Config(
        output_root=Path(args.output_root),
        out_dir=Path(args.out_dir),
        time_min_hours=float(args.time_min_hours),
        time_max_hours=float(args.time_max_hours),
        phi_col=str(args.phi_col),
        min_tiles=int(args.min_tiles),
        storm_metadata_csv=Path(args.storm_metadata_csv) if args.storm_metadata_csv is not None else None,
        slugs=tuple(str(s) for s in args.slugs) if args.slugs else (),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()
