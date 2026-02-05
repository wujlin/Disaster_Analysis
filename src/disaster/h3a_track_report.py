from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    output_root: Path
    out_dir: Path
    time_min_hours: float = 0.0
    time_max_hours: float = 72.0
    phi_col: str = "phi_aggregate"
    min_tiles: int = 0
    slugs: tuple[str, ...] = ()
    storm_metadata_csv: Path | None = None


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _infer_slugs(output_root: Path) -> list[str]:
    out: list[str] = []
    for p in sorted(output_root.glob("*/phi_heatmap/tables/phi_rt_long.csv")):
        # outputs_root/<slug>/phi_heatmap/tables/phi_rt_long.csv
        slug = p.parents[2].name
        out.append(slug)
    return out


def _half_distance_r0(r: np.ndarray, y: np.ndarray) -> float:
    r = np.asarray(r, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(r) & np.isfinite(y) & (r > 0) & (y >= 0)
    r = r[ok]
    y = y[ok]
    if r.size < 3:
        return float("nan")

    i_max = int(np.nanargmax(y))
    y_max = float(y[i_max])
    if not np.isfinite(y_max) or y_max <= 0:
        return float("nan")
    target = 0.5 * y_max

    for i in range(i_max + 1, r.size):
        if y[i] <= target:
            r0, y0 = float(r[i - 1]), float(y[i - 1])
            r1, y1 = float(r[i]), float(y[i])
            if y1 == y0:
                return float(r1)
            frac = (target - y0) / (y1 - y0)
            return float(r0 + frac * (r1 - r0))
    return float("nan")


def _load_storm_metadata(path: Path | None) -> dict[str, dict]:
    if path is None or not path.exists():
        return {}
    df = pd.read_csv(path)
    if "storm_name" not in df.columns:
        return {}
    out: dict[str, dict] = {}
    for row in df.to_dict(orient="records"):
        name = str(row.get("storm_name", "")).strip()
        if not name:
            continue
        out[name.lower()] = row
    return out


def _storm_name_from_center_by_window(output_root: Path, slug: str) -> str:
    p = output_root / slug / "phi_heatmap" / "tables" / "center_by_window.csv"
    if not p.exists():
        return ""
    df = pd.read_csv(p)
    if df.empty or "center_track_storm_name" not in df.columns:
        return ""
    name = str(df.iloc[0]["center_track_storm_name"]).strip()
    return "" if name.lower() == "nan" else name


def _profile_from_phi_long(df_long: pd.DataFrame, *, phi_col: str, time_min: float, time_max: float) -> pd.DataFrame:
    df = df_long.copy()
    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df["r_bin_km"] = pd.to_numeric(df["r_bin_km"], errors="coerce")
    df[phi_col] = pd.to_numeric(df[phi_col], errors="coerce")
    df = df.dropna(subset=["hours_since_quake", "r_bin_km"]).copy()
    df = df[(df["hours_since_quake"] >= float(time_min)) & (df["hours_since_quake"] <= float(time_max))].copy()
    if df.empty:
        return pd.DataFrame()

    r_bins = np.sort(df["r_bin_km"].dropna().unique().astype(float))
    dr = float(np.median(np.diff(r_bins))) if r_bins.size >= 2 else 10.0

    agg_map: dict[str, str] = {phi_col: "mean"}
    for c in ["n_tiles", "n_tiles_crisis", "n_tiles_overlap", "baseline_sum", "crisis_sum"]:
        if c in df.columns:
            agg_map[c] = "mean"
    g = df.groupby("r_bin_km", sort=True, observed=True).agg(agg_map).reset_index()
    g = g.rename(columns={phi_col: "phi_mean"})
    if "n_tiles" in g.columns:
        g = g.rename(columns={"n_tiles": "n_tiles_mean"})
    if "n_tiles_crisis" in g.columns:
        g = g.rename(columns={"n_tiles_crisis": "n_tiles_crisis_mean"})
    if "n_tiles_overlap" in g.columns:
        g = g.rename(columns={"n_tiles_overlap": "n_tiles_overlap_mean"})
    if "baseline_sum" in g.columns:
        g = g.rename(columns={"baseline_sum": "baseline_sum_mean"})
    if "crisis_sum" in g.columns:
        g = g.rename(columns={"crisis_sum": "crisis_sum_mean"})

    if "n_tiles_mean" in g.columns and "n_tiles_crisis_mean" in g.columns:
        g["n_eff_mean"] = np.minimum(
            pd.to_numeric(g["n_tiles_mean"], errors="coerce").to_numpy(dtype=float),
            pd.to_numeric(g["n_tiles_crisis_mean"], errors="coerce").to_numpy(dtype=float),
        )

    g["r_center_km"] = pd.to_numeric(g["r_bin_km"], errors="coerce") + dr / 2.0
    g["abs_dev"] = (pd.to_numeric(g["phi_mean"], errors="coerce") - 1.0).abs()
    return g.sort_values("r_center_km", kind="stable")


def run(cfg: Config) -> None:
    out_dir = Path(cfg.out_dir)
    figs = out_dir / "figures"
    tabs = out_dir / "tables"
    _ensure_dir(out_dir)
    _ensure_dir(figs)
    _ensure_dir(tabs)

    slugs = list(cfg.slugs) if cfg.slugs else _infer_slugs(Path(cfg.output_root))
    if not slugs:
        raise SystemExit(f"未找到任何可用 slug（请检查 output_root={cfg.output_root}）")

    meta = _load_storm_metadata(cfg.storm_metadata_csv)

    rows: list[dict] = []
    prof_rows: list[pd.DataFrame] = []
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

        row = {
            "slug": str(slug),
            "storm_name": str(storm_name),
            "time_min_hours": float(cfg.time_min_hours),
            "time_max_hours": float(cfg.time_max_hours),
            "min_tiles": int(cfg.min_tiles),
            "r0_km": float(r0),
            "y_max_abs_phi_minus_1": float(y_max),
            "n_bins_used": int(r.size),
        }
        if storm_meta:
            for k, v in storm_meta.items():
                if k in {"storm_name"}:
                    continue
                row[f"meta_{k}"] = v
        rows.append(row)

        prof2 = prof.copy()
        prof2.insert(0, "slug", str(slug))
        prof2.insert(1, "storm_name", str(storm_name))
        prof_rows.append(prof2)

    if not rows:
        raise SystemExit("没有可用的 profile（请确认 output_root 下存在 phi_heatmap 输出且时间窗匹配）")

    summary = pd.DataFrame(rows)
    summary = summary.sort_values("y_max_abs_phi_minus_1", ascending=False, kind="stable")
    summary.to_csv(tabs / f"track_profile_summary_minTiles{int(cfg.min_tiles)}.csv", index=False)

    if prof_rows:
        pd.concat(prof_rows, ignore_index=True).to_csv(tabs / f"track_profiles_long_minTiles{int(cfg.min_tiles)}.csv", index=False)

    # plots
    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    import matplotlib.pyplot as plt

    colors = [ps.OKABE_ITO["blue"], ps.OKABE_ITO["vermillion"], ps.OKABE_ITO["bluish_green"], ps.OKABE_ITO["orange"]]
    labels = list("abcdefghijklmnopqrstuvwxyz")

    with ps.paper_style():
        fig, axes = plt.subplots(nrows=1, ncols=2, figsize=(ps.FIGSIZE_FULL[0], ps.FIGSIZE_FULL[1] * 0.92))
        ax0, ax1 = axes

        # raw
        for i, row in enumerate(summary.to_dict(orient="records")):
            slug = str(row["slug"])
            storm_name = str(row.get("storm_name", "") or slug)
            vmax = row.get("meta_landfall_vmax_kt", "")
            cat = row.get("meta_landfall_category", "")
            tag = f"{storm_name} ({cat}, {vmax}kt)" if str(vmax).strip() not in {"", "nan"} else storm_name

            prof = pd.read_csv(tabs / f"track_profiles_long_minTiles{int(cfg.min_tiles)}.csv")
            sub = prof[prof["slug"] == slug].copy()
            sub["r_center_km"] = pd.to_numeric(sub["r_center_km"], errors="coerce")
            sub["abs_dev"] = pd.to_numeric(sub["abs_dev"], errors="coerce")
            sub = sub.dropna(subset=["r_center_km", "abs_dev"]).sort_values("r_center_km")

            c = colors[i % len(colors)]
            ax0.plot(sub["r_center_km"], sub["abs_dev"], color=c, linewidth=2.2, label=tag)

        ax0.set_xlabel(r"$d_{path}$ (km)")
        ax0.set_ylabel(r"$|\phi-1|$ (time-avg)")
        ax0.set_title(f"(a) Raw profiles (min_tiles={int(cfg.min_tiles)})")
        ps.despine(ax0)
        ax0.legend(frameon=False, fontsize=9)

        # collapsed
        for i, row in enumerate(summary.to_dict(orient="records")):
            slug = str(row["slug"])
            r0 = float(row["r0_km"])
            y_max = float(row["y_max_abs_phi_minus_1"])
            if not np.isfinite(r0) or r0 <= 0 or not np.isfinite(y_max) or y_max <= 0:
                continue
            prof = pd.read_csv(tabs / f"track_profiles_long_minTiles{int(cfg.min_tiles)}.csv")
            sub = prof[prof["slug"] == slug].copy()
            sub["r_center_km"] = pd.to_numeric(sub["r_center_km"], errors="coerce")
            sub["abs_dev"] = pd.to_numeric(sub["abs_dev"], errors="coerce")
            sub = sub.dropna(subset=["r_center_km", "abs_dev"]).sort_values("r_center_km")

            x = sub["r_center_km"].to_numpy(dtype=float) / float(r0)
            y = sub["abs_dev"].to_numpy(dtype=float) / float(y_max)
            ok = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y >= 0)
            x = x[ok]
            y = y[ok]
            if x.size < 3:
                continue

            c = colors[i % len(colors)]
            ax1.plot(x, y, color=c, linewidth=2.2, alpha=0.85)

        ax1.set_xscale("log")
        ax1.set_xlabel(r"$d_{path}/r_0$")
        ax1.set_ylabel(r"$|\phi-1|/y_{max}$")
        ax1.set_title("(b) Collapse attempt")
        ps.despine(ax1)

        for j, ax in enumerate([ax0, ax1]):
            ps.add_panel_label(ax, labels[j])

        fig.tight_layout()
        save_png_and_pdf(ps, fig, figs / f"track_raw_and_collapse_minTiles{int(cfg.min_tiles)}.png")
        plt.close(fig)


def cli_main() -> None:
    p = argparse.ArgumentParser(description="H3a: 飓风路径几何下的 φ(d_path) 报告（原始曲线 + 坍缩）")
    p.add_argument("--output-root", type=Path, default=Path("outputs_trackpath"))
    p.add_argument("--out-dir", type=Path, default=Path("outputs_trackpath/_tmp_h3a_track_report"))
    p.add_argument("--time-min-hours", type=float, default=0.0)
    p.add_argument("--time-max-hours", type=float, default=72.0)
    p.add_argument("--phi-col", type=str, default="phi_aggregate")
    p.add_argument("--min-tiles", type=int, default=0, help="稳健性过滤：仅保留 n_eff_mean>=min_tiles 的距离 bins")
    p.add_argument("--slugs", type=str, nargs="*", default=[], help="可选：只分析指定 slugs（默认自动发现）")
    p.add_argument("--storm-metadata-csv", type=Path, default=Path("Docs/storm_tracks/storm_intensity_2024.csv"))
    args = p.parse_args()

    cfg = Config(
        output_root=Path(args.output_root),
        out_dir=Path(args.out_dir),
        time_min_hours=float(args.time_min_hours),
        time_max_hours=float(args.time_max_hours),
        phi_col=str(args.phi_col),
        min_tiles=int(args.min_tiles),
        slugs=tuple(str(s) for s in args.slugs) if args.slugs else (),
        storm_metadata_csv=Path(args.storm_metadata_csv) if args.storm_metadata_csv is not None else None,
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()

