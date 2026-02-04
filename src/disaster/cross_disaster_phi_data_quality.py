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

from disaster.cross_disaster_phi_tau import DisasterSpec, load_catalog
from disaster.geo import haversine_km
from disaster.population_io import load_population_file, parse_window_start_pt
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _out_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _read_phi_rt_long(*, output_root: Path, slug: str) -> pd.DataFrame | None:
    p = output_root / slug / "phi_heatmap" / "tables" / "phi_rt_long.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    if "hours_since_quake" in df.columns:
        df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    if "r_bin_km" in df.columns:
        df["r_bin_km"] = pd.to_numeric(df["r_bin_km"], errors="coerce")
    for c in [
        "phi_aggregate",
        "phi_overlap",
        "n_tiles",
        "n_tiles_crisis",
        "n_tiles_overlap",
        "baseline_sum",
        "crisis_sum",
        "baseline_sum_overlap",
        "crisis_sum_overlap",
        "tile_overlap_ratio",
    ]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _read_disaster_metadata(*, output_root: Path, slug: str) -> dict:
    p = output_root / slug / "metadata.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _filter_time(df: pd.DataFrame, *, min_hours: float, max_hours: float | None) -> pd.DataFrame:
    if df.empty:
        return df
    if "hours_since_quake" not in df.columns:
        return df.iloc[0:0].copy()
    out = df.copy()
    out = out[np.isfinite(out["hours_since_quake"].to_numpy(dtype=float))]
    out = out[out["hours_since_quake"] >= float(min_hours)]
    if max_hours is not None:
        out = out[out["hours_since_quake"] <= float(max_hours)]
    return out


def _summary_one(
    *,
    spec: DisasterSpec,
    df: pd.DataFrame | None,
    min_hours: float,
    max_hours: float | None,
    output_root: Path,
) -> dict:
    meta = _read_disaster_metadata(output_root=output_root, slug=spec.slug)

    if df is None or df.empty:
        return {
            "slug": spec.slug,
            "name": spec.name,
            "event_type": spec.event_type,
            "t0_pt": meta.get("t0_pt", ""),
            "t0_method": meta.get("t0_method", ""),
            "center_lat": meta.get("center_lat", ""),
            "center_lon": meta.get("center_lon", ""),
            "center_method": meta.get("center_method", ""),
            "min_hours": float(min_hours),
            "max_hours": float(max_hours) if max_hours is not None else "",
            "n_rows": 0,
            "note": "missing_or_empty_phi_rt_long",
        }

    df = _filter_time(df, min_hours=float(min_hours), max_hours=max_hours)
    if df.empty:
        return {
            "slug": spec.slug,
            "name": spec.name,
            "event_type": spec.event_type,
            "t0_pt": meta.get("t0_pt", ""),
            "t0_method": meta.get("t0_method", ""),
            "center_lat": meta.get("center_lat", ""),
            "center_lon": meta.get("center_lon", ""),
            "center_method": meta.get("center_method", ""),
            "min_hours": float(min_hours),
            "max_hours": float(max_hours) if max_hours is not None else "",
            "n_rows": 0,
            "note": "empty_after_time_filter",
        }

    def _count_zero_nan(series: pd.Series) -> tuple[int, int]:
        s = pd.to_numeric(series, errors="coerce")
        n_nan = int(s.isna().sum())
        n_zero = int((s == 0).sum())
        return n_zero, n_nan

    n_rows = int(len(df))
    phi_agg = pd.to_numeric(df.get("phi_aggregate", pd.Series([np.nan] * n_rows)), errors="coerce")
    phi_ov = pd.to_numeric(df.get("phi_overlap", pd.Series([np.nan] * n_rows)), errors="coerce")

    phi0_agg, phinan_agg = _count_zero_nan(phi_agg)
    phi0_ov, phinan_ov = _count_zero_nan(phi_ov)
    n_phi_gt2_agg = int((phi_agg > 2).sum())
    n_phi_gt2_ov = int((phi_ov > 2).sum())
    n_phi_inf_agg = int(np.isinf(phi_agg.to_numpy(dtype=float)).sum())
    n_phi_inf_ov = int(np.isinf(phi_ov.to_numpy(dtype=float)).sum())

    def _min_nonzero(series: pd.Series) -> float:
        x = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(x) & (x > 0)
        return float(np.min(x[ok])) if int(np.sum(ok)) > 0 else float("nan")

    min_phi_nonzero_agg = _min_nonzero(phi_agg)
    min_phi_nonzero_ov = _min_nonzero(phi_ov)

    r = pd.to_numeric(df.get("r_bin_km", pd.Series([np.nan] * n_rows)), errors="coerce")
    r_min = float(np.nanmin(r.to_numpy(dtype=float))) if r.notna().any() else float("nan")
    r_max = float(np.nanmax(r.to_numpy(dtype=float))) if r.notna().any() else float("nan")

    # tile-weighted fractions（近似“tile 占比”，以每行的 n_tiles/n_tiles_overlap 作权重）
    w_tiles = pd.to_numeric(df.get("n_tiles", pd.Series([np.nan] * n_rows)), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    w_tiles_sum = float(np.sum(w_tiles))
    w_tiles_phi0 = float(np.sum(w_tiles[(phi_agg == 0).to_numpy(dtype=bool)]))
    w_tiles_phinan = float(np.sum(w_tiles[phi_agg.isna().to_numpy(dtype=bool)]))
    w_tiles_phigt2 = float(np.sum(w_tiles[(phi_agg > 2).to_numpy(dtype=bool)]))

    w_ov = pd.to_numeric(df.get("n_tiles_overlap", pd.Series([np.nan] * n_rows)), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    w_ov_sum = float(np.sum(w_ov))
    w_zero_ov = float(np.sum(w_ov[(phi_ov == 0).to_numpy(dtype=bool)]))
    w_nan_ov = float(np.sum(w_ov[phi_ov.isna().to_numpy(dtype=bool)]))
    w_gt2_ov = float(np.sum(w_ov[(phi_ov > 2).to_numpy(dtype=bool)]))

    r_zero_ov = (
        float(pd.to_numeric(df.loc[phi_ov == 0, "r_bin_km"], errors="coerce").median()) if "r_bin_km" in df.columns else float("nan")
    )
    r_nan_ov = (
        float(pd.to_numeric(df.loc[phi_ov.isna(), "r_bin_km"], errors="coerce").median()) if "r_bin_km" in df.columns else float("nan")
    )

    baseline_sum = pd.to_numeric(df.get("baseline_sum", pd.Series([np.nan] * n_rows)), errors="coerce")
    crisis_sum = pd.to_numeric(df.get("crisis_sum", pd.Series([np.nan] * n_rows)), errors="coerce")
    baseline_sum_ov = pd.to_numeric(df.get("baseline_sum_overlap", pd.Series([np.nan] * n_rows)), errors="coerce")
    crisis_sum_ov = pd.to_numeric(df.get("crisis_sum_overlap", pd.Series([np.nan] * n_rows)), errors="coerce")
    n_phi0_agg_due_crisis0 = int(((phi_agg == 0) & (crisis_sum == 0) & (baseline_sum > 0)).sum())
    n_phi0_ov_due_crisis0 = int(((phi_ov == 0) & (crisis_sum_ov == 0) & (baseline_sum_ov > 0)).sum())

    baseline_total_overlap_cv = float("nan")
    if "hours_since_quake" in df.columns and "baseline_sum_overlap" in df.columns:
        bt = df.groupby("hours_since_quake", sort=True, observed=True)["baseline_sum_overlap"].sum(min_count=1)
        x = pd.to_numeric(bt, errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(x)
        x = x[ok]
        if x.size >= 2:
            mu = float(np.mean(x))
            sd = float(np.std(x))
            baseline_total_overlap_cv = float(sd / mu) if np.isfinite(mu) and mu != 0 else float("nan")

    return {
        "slug": spec.slug,
        "name": spec.name,
        "event_type": spec.event_type,
        "t0_pt": meta.get("t0_pt", ""),
        "t0_method": meta.get("t0_method", ""),
        "center_lat": meta.get("center_lat", ""),
        "center_lon": meta.get("center_lon", ""),
        "center_method": meta.get("center_method", ""),
        "min_hours": float(min_hours),
        "max_hours": float(max_hours) if max_hours is not None else "",
        "n_rows": n_rows,
        "r_min_km": r_min,
        "r_max_km": r_max,
        # PI: φ 分布特征
        "n_phi_aggregate_zero": int(phi0_agg),
        "n_phi_aggregate_nan": int(phinan_agg),
        "n_phi_aggregate_gt_2": int(n_phi_gt2_agg),
        "n_phi_aggregate_inf": int(n_phi_inf_agg),
        "frac_phi_aggregate_zero": float(phi0_agg / n_rows) if n_rows else float("nan"),
        "frac_phi_aggregate_nan": float(phinan_agg / n_rows) if n_rows else float("nan"),
        "frac_phi_aggregate_gt_2": float(n_phi_gt2_agg / n_rows) if n_rows else float("nan"),
        "min_phi_aggregate_nonzero": float(min_phi_nonzero_agg),
        "n_phi_overlap_zero": int(phi0_ov),
        "n_phi_overlap_nan": int(phinan_ov),
        "n_phi_overlap_gt_2": int(n_phi_gt2_ov),
        "n_phi_overlap_inf": int(n_phi_inf_ov),
        "frac_phi_overlap_zero": float(phi0_ov / n_rows) if n_rows else float("nan"),
        "frac_phi_overlap_nan": float(phinan_ov / n_rows) if n_rows else float("nan"),
        "frac_phi_overlap_gt_2": float(n_phi_gt2_ov / n_rows) if n_rows else float("nan"),
        "min_phi_overlap_nonzero": float(min_phi_nonzero_ov),
        # weighted fractions
        "sum_n_tiles": float(w_tiles_sum),
        "frac_tiles_weighted_phi_aggregate_zero": float(w_tiles_phi0 / w_tiles_sum) if w_tiles_sum > 0 else float("nan"),
        "frac_tiles_weighted_phi_aggregate_nan": float(w_tiles_phinan / w_tiles_sum) if w_tiles_sum > 0 else float("nan"),
        "frac_tiles_weighted_phi_aggregate_gt_2": float(w_tiles_phigt2 / w_tiles_sum) if w_tiles_sum > 0 else float("nan"),
        "sum_n_tiles_overlap": float(w_ov_sum),
        "frac_tiles_weighted_phi_overlap_zero": float(w_zero_ov / w_ov_sum) if w_ov_sum > 0 else float("nan"),
        "frac_tiles_weighted_phi_overlap_nan": float(w_nan_ov / w_ov_sum) if w_ov_sum > 0 else float("nan"),
        "frac_tiles_weighted_phi_overlap_gt_2": float(w_gt2_ov / w_ov_sum) if w_ov_sum > 0 else float("nan"),
        # PI: φ=0 的成因（聚合层面）
        "n_phi_aggregate_zero_due_crisis_sum_0": int(n_phi0_agg_due_crisis0),
        "n_phi_overlap_zero_due_crisis_sum_0": int(n_phi0_ov_due_crisis0),
        # PI: baseline 一致性（粗略代理）
        "baseline_total_overlap_cv": float(baseline_total_overlap_cv),
        # 帮助定位 φ=0/NaN 是否集中在某些距离
        "median_r_km_phi_overlap_zero": float(r_zero_ov),
        "median_r_km_phi_overlap_nan": float(r_nan_ov),
        "note": "",
    }


def _spatial_coverage_by_band_one(
    *,
    slug: str,
    event_type: str,
    df: pd.DataFrame,
    min_hours: float,
    max_hours: float | None,
    band_km: float = 50.0,
) -> pd.DataFrame:
    df = _filter_time(df, min_hours=float(min_hours), max_hours=max_hours)
    if df.empty or "r_bin_km" not in df.columns:
        return pd.DataFrame(
            columns=[
                "slug",
                "event_type",
                "band_start_km",
                "band_end_km",
                "n_time_windows",
                "median_n_tiles_overlap",
                "mean_n_tiles_overlap",
                "min_n_tiles_overlap",
                "max_n_tiles_overlap",
                "median_tile_overlap_ratio",
                "frac_rows_phi_overlap_zero",
                "frac_rows_phi_overlap_nan",
            ]
        )

    r = pd.to_numeric(df["r_bin_km"], errors="coerce").to_numpy(dtype=float)
    band_start = np.floor(r / float(band_km)) * float(band_km)
    tmp = df.copy()
    tmp["band_start_km"] = band_start.astype(float)
    tmp["band_end_km"] = (tmp["band_start_km"].to_numpy(dtype=float) + float(band_km)).astype(float)
    tmp["n_tiles_overlap"] = pd.to_numeric(tmp.get("n_tiles_overlap"), errors="coerce")
    tmp["n_tiles"] = pd.to_numeric(tmp.get("n_tiles"), errors="coerce")

    # band x time: sum tile counts across 10km r_bins
    bt = (
        tmp.groupby(["hours_since_quake", "band_start_km"], observed=True)
        .agg(
            n_tiles_overlap=("n_tiles_overlap", "sum"),
            n_tiles=("n_tiles", "sum"),
        )
        .reset_index()
    )
    bt["tile_overlap_ratio"] = np.where(bt["n_tiles"] > 0, bt["n_tiles_overlap"] / bt["n_tiles"], np.nan)

    out = (
        bt.groupby("band_start_km", observed=True)
        .agg(
            n_time_windows=("hours_since_quake", "nunique"),
            median_n_tiles_overlap=("n_tiles_overlap", "median"),
            mean_n_tiles_overlap=("n_tiles_overlap", "mean"),
            min_n_tiles_overlap=("n_tiles_overlap", "min"),
            max_n_tiles_overlap=("n_tiles_overlap", "max"),
            median_tile_overlap_ratio=("tile_overlap_ratio", "median"),
        )
        .reset_index()
        .sort_values("band_start_km")
    )
    out["band_end_km"] = out["band_start_km"].to_numpy(dtype=float) + float(band_km)
    out.insert(0, "event_type", event_type)
    out.insert(0, "slug", slug)

    # row fractions (phi_overlap==0/NaN) within this band (aggregated rows)
    phi_ov = pd.to_numeric(tmp.get("phi_overlap"), errors="coerce")
    frac_rows = (
        tmp.assign(phi_overlap_num=phi_ov)
        .groupby("band_start_km", observed=True)
        .agg(
            n_rows=("phi_overlap_num", "size"),
            n_zero=("phi_overlap_num", lambda s: int((pd.to_numeric(s, errors="coerce") == 0).sum())),
            n_nan=("phi_overlap_num", lambda s: int(pd.to_numeric(s, errors="coerce").isna().sum())),
        )
        .reset_index()
    )
    frac_rows["frac_rows_phi_overlap_zero"] = np.where(frac_rows["n_rows"] > 0, frac_rows["n_zero"] / frac_rows["n_rows"], np.nan)
    frac_rows["frac_rows_phi_overlap_nan"] = np.where(frac_rows["n_rows"] > 0, frac_rows["n_nan"] / frac_rows["n_rows"], np.nan)

    out = out.merge(frac_rows[["band_start_km", "frac_rows_phi_overlap_zero", "frac_rows_phi_overlap_nan"]], on="band_start_km", how="left")
    return out[
        [
            "slug",
            "event_type",
            "band_start_km",
            "band_end_km",
            "n_time_windows",
            "median_n_tiles_overlap",
            "mean_n_tiles_overlap",
            "min_n_tiles_overlap",
            "max_n_tiles_overlap",
            "median_tile_overlap_ratio",
            "frac_rows_phi_overlap_zero",
            "frac_rows_phi_overlap_nan",
        ]
    ]


def _spatial_coverage_summary_from_by_band(by_band: pd.DataFrame) -> pd.DataFrame:
    if by_band.empty:
        return pd.DataFrame(
            columns=[
                "slug",
                "event_type",
                "r_max_with_ge_10_tiles_km",
                "r_max_with_ge_10_tiles_band_start_km",
                "r_max_with_any_tiles_km",
            ]
        )
    rows: list[dict] = []
    for (slug, event_type), sub in by_band.groupby(["slug", "event_type"], observed=True):
        med = pd.to_numeric(sub["median_n_tiles_overlap"], errors="coerce")
        band_start = pd.to_numeric(sub["band_start_km"], errors="coerce")
        band_end = pd.to_numeric(sub["band_end_km"], errors="coerce")

        ok_any = med.notna() & (med > 0)
        r_any = float(np.nanmax(band_end[ok_any].to_numpy(dtype=float))) if ok_any.any() else float("nan")

        ok10 = med.notna() & (med >= 10)
        r10 = float(np.nanmax(band_end[ok10].to_numpy(dtype=float))) if ok10.any() else float("nan")
        r10_start = float(np.nanmax(band_start[ok10].to_numpy(dtype=float))) if ok10.any() else float("nan")

        rows.append(
            {
                "slug": slug,
                "event_type": event_type,
                "r_max_with_ge_10_tiles_km": r10,
                "r_max_with_ge_10_tiles_band_start_km": r10_start,
                "r_max_with_any_tiles_km": r_any,
            }
        )
    return pd.DataFrame(rows)


def _maybe_plot_turkey_phi_zero_tiles(
    *,
    specs: list[DisasterSpec],
    output_root: Path,
    out_tables: Path,
    out_figures: Path,
    turkey_slug: str,
    time_min: float,
    time_max: float,
) -> None:
    spec = next((s for s in specs if s.slug == turkey_slug), None)
    if spec is None:
        return

    meta = _read_disaster_metadata(output_root=output_root, slug=turkey_slug)
    if not meta:
        return

    center_lat = meta.get("center_lat", None)
    center_lon = meta.get("center_lon", None)
    t0_pt = meta.get("t0_pt", None)
    only_hour_pt = int(meta.get("only_hour_pt", spec.only_hour_pt) or 8)
    if center_lat is None or center_lon is None or t0_pt is None:
        return

    try:
        center_lat_f = float(center_lat)
        center_lon_f = float(center_lon)
        t0 = pd.Timestamp(str(t0_pt))
    except Exception:
        return

    pop_dir = Path(spec.data_root) / "population"
    if not pop_dir.exists():
        pop_dir = Path(spec.data_root) / "raw" / "population"
    if not pop_dir.exists():
        return

    files = sorted(pop_dir.glob("*.csv"))
    if not files:
        return

    agg: dict[str, dict] = {}
    for p in files:
        try:
            ts = parse_window_start_pt(p)
        except Exception:
            continue
        if int(ts.hour) != int(only_hour_pt):
            continue
        h = float((pd.Timestamp(ts) - pd.Timestamp(t0)).total_seconds() / 3600.0)
        if h < float(time_min) or h > float(time_max):
            continue

        df = load_population_file(p)
        nb = pd.to_numeric(df.get("n_baseline"), errors="coerce").to_numpy(dtype=float)
        nc = pd.to_numeric(df.get("n_crisis"), errors="coerce").to_numpy(dtype=float)
        lat = pd.to_numeric(df.get("lat"), errors="coerce").to_numpy(dtype=float)
        lon = pd.to_numeric(df.get("lon"), errors="coerce").to_numpy(dtype=float)
        qk = df.get("quadkey")
        if qk is None:
            continue
        qk = qk.astype(str).to_numpy()

        ok = np.isfinite(nb) & np.isfinite(nc) & np.isfinite(lat) & np.isfinite(lon)
        phi_zero = ok & (nb > 0) & (nc <= 0)
        if int(np.sum(phi_zero)) == 0:
            continue

        dist = haversine_km(lat[phi_zero], lon[phi_zero], float(center_lat_f), float(center_lon_f))
        for qq, la, lo, dd in zip(qk[phi_zero], lat[phi_zero], lon[phi_zero], dist.tolist(), strict=False):
            d = agg.get(str(qq))
            if d is None:
                agg[str(qq)] = {"quadkey": str(qq), "lat": float(la), "lon": float(lo), "distance_km": float(dd), "n_windows_phi_zero": 1}
            else:
                d["n_windows_phi_zero"] = int(d["n_windows_phi_zero"]) + 1

    if not agg:
        return

    tiles = pd.DataFrame(list(agg.values()))
    tiles.sort_values(["n_windows_phi_zero", "distance_km"], ascending=[False, True]).to_csv(
        out_tables / "turkey_phi_zero_tiles.csv", index=False
    )

    bins = np.arange(0.0, float(np.nanmax(tiles["distance_km"].to_numpy(dtype=float))) + 10.0, 10.0, dtype=float)
    weights = tiles["n_windows_phi_zero"].to_numpy(dtype=float)
    hist, edges = np.histogram(tiles["distance_km"].to_numpy(dtype=float), bins=bins, weights=weights)
    hist_df = pd.DataFrame({"bin_left_km": edges[:-1], "bin_right_km": edges[1:], "weighted_count": hist})
    hist_df.to_csv(out_tables / "turkey_phi_zero_distance_hist.csv", index=False)

    import matplotlib.pyplot as plt

    from disaster import plot_style as ps  # type: ignore

    fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
    sc = ax.scatter(
        tiles["lon"].to_numpy(dtype=float),
        tiles["lat"].to_numpy(dtype=float),
        c=tiles["n_windows_phi_zero"].to_numpy(dtype=float),
        s=6,
        alpha=0.7,
        cmap="viridis",
        linewidths=0,
        rasterized=True,
    )
    ax.scatter([center_lon_f], [center_lat_f], s=80, c=ps.OKABE_ITO["vermillion"], edgecolors="black", linewidths=0.8, zorder=5)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"{turkey_slug}: tiles with phi==0 (t in [{time_min},{time_max}]h, PT hour={only_hour_pt:02d})")
    ps.despine(ax)
    cb = fig.colorbar(sc, ax=ax, shrink=0.88)
    cb.set_label("count of windows with phi==0")
    fig.tight_layout()
    save_png_and_pdf(ps, fig, out_figures / "turkey_phi_zero_map.png")
    plt.close(fig)

    fig2, ax2 = plt.subplots(figsize=ps.FIGSIZE_FULL)
    ax2.bar(hist_df["bin_left_km"].to_numpy(dtype=float), hist_df["weighted_count"].to_numpy(dtype=float), width=10.0, align="edge")
    ax2.set_xlabel("distance to center (km)")
    ax2.set_ylabel("weighted count (by n_windows_phi_zero)")
    ax2.set_title(f"{turkey_slug}: phi==0 distance histogram (t in [{time_min},{time_max}]h)")
    ps.despine(ax2)
    fig2.tight_layout()
    save_png_and_pdf(ps, fig2, out_figures / "turkey_phi_zero_distance_hist.png")
    plt.close(fig2)


def _by_rbin_one(
    *,
    slug: str,
    event_type: str,
    df: pd.DataFrame,
    min_hours: float,
    max_hours: float | None,
) -> pd.DataFrame:
    df = _filter_time(df, min_hours=float(min_hours), max_hours=max_hours)
    if df.empty or "r_bin_km" not in df.columns:
        return pd.DataFrame(
            columns=[
                "slug",
                "event_type",
                "r_bin_km",
                "n_rows",
                "frac_phi_overlap_zero",
                "frac_phi_overlap_nan",
                "mean_n_tiles_overlap",
                "mean_tile_overlap_ratio",
            ]
        )

    rows: list[dict] = []
    for r, sub in df.groupby("r_bin_km", sort=True, observed=True):
        n = int(len(sub))
        phi = pd.to_numeric(sub.get("phi_overlap"), errors="coerce")
        n_zero = int((phi == 0).sum())
        n_nan = int(phi.isna().sum())
        rows.append(
            {
                "slug": slug,
                "event_type": event_type,
                "r_bin_km": float(r),
                "n_rows": n,
                "frac_phi_overlap_zero": float(n_zero / n) if n else float("nan"),
                "frac_phi_overlap_nan": float(n_nan / n) if n else float("nan"),
                "mean_n_tiles_overlap": float(pd.to_numeric(sub.get("n_tiles_overlap"), errors="coerce").mean())
                if "n_tiles_overlap" in sub.columns
                else float("nan"),
                "mean_tile_overlap_ratio": float(pd.to_numeric(sub.get("tile_overlap_ratio"), errors="coerce").mean())
                if "tile_overlap_ratio" in sub.columns
                else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def _radial_profile_phi(
    *,
    df: pd.DataFrame,
    time_min: float,
    time_max: float,
) -> pd.DataFrame:
    df = _filter_time(df, min_hours=float(time_min), max_hours=float(time_max))
    if df.empty or "r_bin_km" not in df.columns:
        return pd.DataFrame(columns=["r_bin_km", "phi_aggregate_mean", "phi_overlap_mean", "n_rows"])
    g = df.groupby("r_bin_km", sort=True, observed=True)

    out = g.agg(
        phi_aggregate_mean=("phi_aggregate", "mean"),
        phi_overlap_mean=("phi_overlap", "mean"),
        n_rows=("r_bin_km", "size"),
        mean_n_tiles_overlap=("n_tiles_overlap", "mean"),
        frac_phi_overlap_zero=("phi_overlap", lambda s: float((pd.to_numeric(s, errors="coerce") == 0).sum() / len(s)) if len(s) else float("nan")),
        frac_phi_overlap_nan=("phi_overlap", lambda s: float(pd.to_numeric(s, errors="coerce").isna().sum() / len(s)) if len(s) else float("nan")),
    ).reset_index()
    out["time_min_hours"] = float(time_min)
    out["time_max_hours"] = float(time_max)
    return out


def _choose_example_slugs(
    *,
    catalog: list[DisasterSpec],
    n_examples: int,
    phase0_csv: Path | None,
    explicit: str | None,
) -> list[str]:
    slugs = [s.slug for s in catalog]
    if explicit:
        want = [x.strip() for x in str(explicit).split(",") if x.strip()]
        return [x for x in want if x in set(slugs)]

    if phase0_csv is not None and phase0_csv.exists():
        s0 = pd.read_csv(phase0_csv)
        if {"slug", "S"}.issubset(set(s0.columns)):
            s0["S"] = pd.to_numeric(s0["S"], errors="coerce")
            s0 = s0.dropna(subset=["S"]).sort_values("S", ascending=False)
            picked = []
            for x in s0["slug"].astype(str).tolist():
                if x in set(slugs):
                    picked.append(x)
                if len(picked) >= int(n_examples):
                    break
            if picked:
                return picked

    return slugs[: int(n_examples)]


def run(cfg) -> None:
    specs = load_catalog(Path(cfg.catalog))
    out = _out_dirs(Path(cfg.out_dir))
    _ensure_dir(out.root)
    _ensure_dir(out.figures)
    _ensure_dir(out.tables)

    summary_rows: list[dict] = []
    coverage_by_band_all: list[pd.DataFrame] = []
    by_rbin_all: list[pd.DataFrame] = []
    profiles_all: list[pd.DataFrame] = []

    for spec in specs:
        df = _read_phi_rt_long(output_root=Path(cfg.output_root), slug=spec.slug)
        summary_rows.append(
            _summary_one(
                spec=spec,
                df=df,
                min_hours=float(cfg.min_hours),
                max_hours=cfg.max_hours,
                output_root=Path(cfg.output_root),
            )
        )
        if df is not None and not df.empty:
            coverage_by_band_all.append(
                _spatial_coverage_by_band_one(
                    slug=spec.slug,
                    event_type=spec.event_type,
                    df=df,
                    min_hours=float(cfg.min_hours),
                    max_hours=cfg.max_hours,
                    band_km=float(cfg.coverage_band_km),
                )
            )
            by_rbin_all.append(
                _by_rbin_one(
                    slug=spec.slug,
                    event_type=spec.event_type,
                    df=df,
                    min_hours=float(cfg.min_hours),
                    max_hours=cfg.max_hours,
                )
            )
            prof = _radial_profile_phi(df=df, time_min=float(cfg.profile_time_min), time_max=float(cfg.profile_time_max))
            if not prof.empty:
                prof.insert(0, "event_type", spec.event_type)
                prof.insert(0, "slug", spec.slug)
                profiles_all.append(prof)

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(out.tables / "data_quality_by_disaster.csv", index=False)
    # backward compatible
    summary_df.to_csv(out.tables / "phi_zero_nan_summary.csv", index=False)

    if coverage_by_band_all:
        by_band_df = pd.concat(coverage_by_band_all, ignore_index=True)
        by_band_df.to_csv(out.tables / "spatial_coverage_by_band.csv", index=False)
        cov_sum = _spatial_coverage_summary_from_by_band(by_band_df)
        cov_sum.to_csv(out.tables / "spatial_coverage_by_disaster.csv", index=False)
    else:
        pd.DataFrame().to_csv(out.tables / "spatial_coverage_by_band.csv", index=False)
        pd.DataFrame().to_csv(out.tables / "spatial_coverage_by_disaster.csv", index=False)

    if by_rbin_all:
        pd.concat(by_rbin_all, ignore_index=True).to_csv(out.tables / "phi_zero_nan_by_rbin.csv", index=False)
    else:
        pd.DataFrame().to_csv(out.tables / "phi_zero_nan_by_rbin.csv", index=False)

    if profiles_all:
        pd.concat(profiles_all, ignore_index=True).to_csv(out.tables / "phi_radial_profile_examples_window.csv", index=False)
    else:
        pd.DataFrame().to_csv(out.tables / "phi_radial_profile_examples_window.csv", index=False)

    # Example plots
    example_slugs = _choose_example_slugs(
        catalog=specs,
        n_examples=int(cfg.n_examples),
        phase0_csv=Path(cfg.phase0_csv) if cfg.phase0_csv else None,
        explicit=str(cfg.example_slugs) if cfg.example_slugs else None,
    )
    if example_slugs:
        _plot_examples(
            specs=specs,
            output_root=Path(cfg.output_root),
            out_dir=out.figures,
            example_slugs=example_slugs,
            profile_time_min=float(cfg.profile_time_min),
            profile_time_max=float(cfg.profile_time_max),
        )

    if getattr(cfg, "turkey_slug", None):
        _maybe_plot_turkey_phi_zero_tiles(
            specs=specs,
            output_root=Path(cfg.output_root),
            out_tables=out.tables,
            out_figures=out.figures,
            turkey_slug=str(cfg.turkey_slug),
            time_min=float(cfg.turkey_time_min),
            time_max=float(cfg.turkey_time_max),
        )

    readme = f"""# Cross-disaster Phi Data Quality Diagnosis

本目录用于在下结论前，先做 **φ 数据质量诊断**（基于 `outputs/<slug>/phi_heatmap/tables/phi_rt_long.csv`）。

## 运行配置

- catalog: `{cfg.catalog}`
- output_root: `{cfg.output_root}`
- 时间过滤：hours_since_quake ∈ [{float(cfg.min_hours)}, {cfg.max_hours}]
- 径向剖面窗口：[{float(cfg.profile_time_min)}, {float(cfg.profile_time_max)}] 小时

## 输出

- `tables/data_quality_by_disaster.csv`：每个灾害的 φ 分布诊断（φ=0/NaN/φ>2/min_nonzero，含加权版本；并记录 t0/center 元数据）
- `tables/spatial_coverage_by_disaster.csv`：每个灾害的空间覆盖摘要（r_max_with_ge_10_tiles 等）
- `tables/spatial_coverage_by_band.csv`：按 {float(cfg.coverage_band_km)}km 距离带汇总 n_tiles（检查 coverage drop / 边界效应）
- `tables/phi_zero_nan_summary.csv`：兼容旧输出名（同 data_quality_by_disaster）
- `tables/phi_zero_nan_by_rbin.csv`：φ=0/NaN 在距离 r_bin 上的分布（按时间汇总）
- `figures/phi_radial_profiles_examples.*`：若干“典型灾害”的 φ(r) 径向剖面（不是 |φ-1|）
- `figures/phi_zero_fraction_by_distance_examples.*`：典型灾害 φ=0 的距离分布（按行比例）

## Turkey φ=0 tile 诊断（若可访问 raw population 数据）

- `tables/turkey_phi_zero_tiles.csv`
- `tables/turkey_phi_zero_distance_hist.csv`
- `figures/turkey_phi_zero_map.*`
- `figures/turkey_phi_zero_distance_hist.*`
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")


def _plot_examples(
    *,
    specs: list[DisasterSpec],
    output_root: Path,
    out_dir: Path,
    example_slugs: list[str],
    profile_time_min: float,
    profile_time_max: float,
) -> None:
    import matplotlib.pyplot as plt

    from disaster import plot_style as ps  # type: ignore

    spec_by_slug = {s.slug: s for s in specs}
    n = int(len(example_slugs))
    ncols = 2
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(ps.FIGSIZE_FULL[0] * ncols, ps.FIGSIZE_FULL[1] * nrows))
    axes = np.asarray(axes).reshape(-1)

    for ax, slug in zip(axes.tolist(), example_slugs, strict=False):
        spec = spec_by_slug.get(slug)
        df = _read_phi_rt_long(output_root=output_root, slug=slug)
        if spec is None or df is None or df.empty:
            ax.set_title(f"{slug} (missing)")
            ax.axis("off")
            continue

        prof = _radial_profile_phi(df=df, time_min=float(profile_time_min), time_max=float(profile_time_max))
        if prof.empty:
            ax.set_title(f"{slug} (empty)")
            ax.axis("off")
            continue

        x = pd.to_numeric(prof["r_bin_km"], errors="coerce").to_numpy(dtype=float)
        y_ov = pd.to_numeric(prof["phi_overlap_mean"], errors="coerce").to_numpy(dtype=float)
        y_ag = pd.to_numeric(prof["phi_aggregate_mean"], errors="coerce").to_numpy(dtype=float)

        ax.plot(x, y_ov, color=ps.OKABE_ITO["blue"], linewidth=2.0, label="phi_overlap (mean)")
        ax.plot(x, y_ag, color=ps.OKABE_ITO["gray"], linewidth=1.2, alpha=0.8, label="phi_aggregate (mean)")
        ax.axhline(1.0, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.7)
        ax.set_title(f"{spec.event_type}: {slug}")
        ax.set_xlabel("r (km)")
        ax.set_ylabel("phi")
        ps.despine(ax)

    for ax in axes[n:].tolist():
        ax.axis("off")

    handles, labels = axes[0].get_legend_handles_labels() if n > 0 else ([], [])
    if handles:
        fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=2, frameon=False)
        fig.subplots_adjust(bottom=0.12)
    fig.tight_layout()
    save_png_and_pdf(ps, fig, out_dir / "phi_radial_profiles_examples.png")
    plt.close(fig)

    # zero fraction by distance
    fig2, axes2 = plt.subplots(nrows=nrows, ncols=ncols, figsize=(ps.FIGSIZE_FULL[0] * ncols, ps.FIGSIZE_FULL[1] * nrows))
    axes2 = np.asarray(axes2).reshape(-1)
    for ax, slug in zip(axes2.tolist(), example_slugs, strict=False):
        spec = spec_by_slug.get(slug)
        df = _read_phi_rt_long(output_root=output_root, slug=slug)
        if spec is None or df is None or df.empty:
            ax.set_title(f"{slug} (missing)")
            ax.axis("off")
            continue
        df = _filter_time(df, min_hours=float(profile_time_min), max_hours=float(profile_time_max))
        if df.empty:
            ax.set_title(f"{slug} (empty)")
            ax.axis("off")
            continue
        by_r = _by_rbin_one(slug=slug, event_type=spec.event_type, df=df, min_hours=float(profile_time_min), max_hours=float(profile_time_max))
        if by_r.empty:
            ax.axis("off")
            continue
        x = pd.to_numeric(by_r["r_bin_km"], errors="coerce").to_numpy(dtype=float)
        y0 = pd.to_numeric(by_r["frac_phi_overlap_zero"], errors="coerce").to_numpy(dtype=float)
        ax.plot(x, y0, color=ps.OKABE_ITO["vermillion"], linewidth=2.0)
        ax.set_ylim(-0.02, 1.02)
        ax.set_title(f"{spec.event_type}: {slug}")
        ax.set_xlabel("r (km)")
        ax.set_ylabel("frac(phi_overlap==0)")
        ps.despine(ax)

    for ax in axes2[n:].tolist():
        ax.axis("off")
    fig2.tight_layout()
    save_png_and_pdf(ps, fig2, out_dir / "phi_zero_fraction_by_distance_examples.png")
    plt.close(fig2)


def cli_main() -> None:
    p = argparse.ArgumentParser(description="跨灾害 φ 数据质量诊断（phi=0/NaN 分布 + φ(r) 径向剖面）")
    p.add_argument("--catalog", type=Path, required=True, help="灾害 catalog（含 slug/name/event_type/data_root 等列）")
    p.add_argument("--output-root", type=Path, default=Path("outputs"), help="outputs 根目录（包含 <slug>/phi_heatmap/）")
    p.add_argument("--out-dir", type=Path, default=Path("outputs/_tmp_phi_data_quality"), help="输出目录")
    p.add_argument("--min-hours", type=float, default=0.0, help="统计 φ=0/NaN 时的最小 hours_since_quake（默认 0）")
    p.add_argument("--max-hours", type=float, default=None, help="统计 φ=0/NaN 时的最大 hours_since_quake（默认不设）")
    p.add_argument("--profile-time-min", type=float, default=24.0, help="径向剖面（示例图）时间窗口下界（默认 24）")
    p.add_argument("--profile-time-max", type=float, default=72.0, help="径向剖面（示例图）时间窗口上界（默认 72）")
    p.add_argument("--coverage-band-km", type=float, default=50.0, help="空间覆盖诊断的距离带宽度（km，默认 50）")
    p.add_argument("--n-examples", type=int, default=4, help="默认绘制多少个示例灾害（默认 4）")
    p.add_argument("--phase0-csv", type=Path, default=None, help="可选：phase0_signal_strength.csv（用于按 S 选 top 示例）")
    p.add_argument("--example-slugs", type=str, default=None, help="可选：指定示例 slug（逗号分隔），优先级最高")
    p.add_argument("--turkey-slug", type=str, default="turkiye_earthquake_2023", help="Turkey φ=0 tile 诊断用的 slug（默认 turkiye_earthquake_2023）")
    p.add_argument("--turkey-time-min", type=float, default=0.0, help="Turkey φ=0 tile 诊断时间下界（hours since t0，默认 0）")
    p.add_argument("--turkey-time-max", type=float, default=72.0, help="Turkey φ=0 tile 诊断时间上界（hours since t0，默认 72）")
    args = p.parse_args()

    run(args)


if __name__ == "__main__":
    cli_main()
