from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.cross_disaster_phi_tau import auto_t0_and_center, load_catalog
from disaster.geo import distance_bin_labels, haversine_km
from disaster.population_io import load_population_file, parse_window_start_pt
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    catalog: Path
    output_root: Path
    output_dir: Path
    t_crisis_mode: str = "peak_0_25"  # peak_0_25 | fixed
    t_crisis_hours: float | None = None  # used when mode=fixed
    peak_max_hours: float | None = 832.0
    only_hour_pt: int | None = 8  # None 表示不过滤小时
    distance_bins_km: tuple[float, ...] = (0.0, 25.0, 50.0, 100.0, 200.0, float("inf"))
    phi_clip_lo: float = 0.0
    phi_clip_hi: float = 3.0
    min_tiles_per_band: int = 200
    alpha_min: float = -2.0
    alpha_max: float = 2.0
    alpha_step: float = 0.05
    n_bins: int = 45
    x_lo_q: float = 0.5
    x_hi_q: float = 99.5
    binning: str = "auto"  # auto | linear | log


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _alpha_grid(cfg: Config) -> np.ndarray:
    step = float(cfg.alpha_step)
    if step <= 0:
        raise ValueError("alpha_step 必须 > 0")
    return np.arange(float(cfg.alpha_min), float(cfg.alpha_max) + 1e-12, step, dtype=float)


def _load_peak_hours(output_root: Path, slug: str, *, max_hours: float | None) -> float:
    p = output_root / slug / "population_redistribution" / "tables" / "redistribution_by_distance_band.csv"
    if not p.exists():
        raise FileNotFoundError(f"未找到：{p}（t_crisis_mode=peak_0_25 需要先生成 population_redistribution 输出）")
    df = pd.read_csv(p, parse_dates=["window_start_pt"])
    need = {"hours_since_quake", "distance_band", "phi_aggregate"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise SystemExit(f"{p} 缺少列：{miss}")
    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df["phi_aggregate"] = pd.to_numeric(df["phi_aggregate"], errors="coerce")
    df["distance_band"] = df["distance_band"].astype(str)
    df = df[(df["distance_band"] == "0-25km") & (df["hours_since_quake"] >= 0)].copy()
    if max_hours is not None:
        df = df[df["hours_since_quake"] <= float(max_hours)].copy()
    df = df.dropna(subset=["hours_since_quake", "phi_aggregate"]).copy()
    if df.empty:
        raise SystemExit(f"{slug} 的 0-25km 在 t>=0 范围内为空，无法做 peak_0_25。")
    idx = int(df["phi_aggregate"].idxmax())
    return float(df.loc[idx, "hours_since_quake"])


def _list_windows(pop_dir: Path, *, t0_pt: pd.Timestamp, only_hour_pt: int | None) -> list[dict]:
    files = sorted(pop_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"目录为空：{pop_dir}")
    rows: list[dict] = []
    for p in files:
        ts = parse_window_start_pt(p)
        if only_hour_pt is not None and int(ts.hour) != int(only_hour_pt):
            continue
        hs = float((pd.Timestamp(ts) - pd.Timestamp(t0_pt)).total_seconds() / 3600.0)
        rows.append({"path": p, "window_start_pt": pd.Timestamp(ts), "hours_since_quake": float(hs)})
    rows = sorted(rows, key=lambda r: float(r["hours_since_quake"]))
    if not rows:
        raise FileNotFoundError(f"未找到 hour={only_hour_pt} 的窗口：{pop_dir}")
    return rows


def _pick_nearest_window(rows: list[dict], target_hours: float) -> dict:
    if not rows:
        raise ValueError("rows 为空")
    return min(rows, key=lambda r: abs(float(r["hours_since_quake"]) - float(target_hours)))


def _phi_by_band_for_window(
    pop_path: Path,
    *,
    center_lat: float,
    center_lon: float,
    distance_bins_km: tuple[float, ...],
    phi_clip_lo: float,
    phi_clip_hi: float,
) -> dict[str, np.ndarray]:
    df = load_population_file(pop_path)
    n_baseline = pd.to_numeric(df["n_baseline"], errors="coerce").to_numpy(dtype=float)
    n_crisis = pd.to_numeric(df["n_crisis"], errors="coerce").to_numpy(dtype=float)
    lat = pd.to_numeric(df["lat"], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(df["lon"], errors="coerce").to_numpy(dtype=float)

    ok = np.isfinite(n_baseline) & np.isfinite(n_crisis) & np.isfinite(lat) & np.isfinite(lon) & (n_baseline > 0)
    if not np.any(ok):
        return {}

    phi = (n_crisis[ok] / n_baseline[ok]).astype(float)
    phi = np.where(np.isfinite(phi), np.clip(phi, float(phi_clip_lo), float(phi_clip_hi)), np.nan)
    dist = haversine_km(lat[ok], lon[ok], float(center_lat), float(center_lon)).astype(float)

    labels = distance_bin_labels(distance_bins_km)
    band = pd.cut(dist, bins=list(distance_bins_km), right=False, labels=labels, include_lowest=True).astype(str)
    band = np.asarray(band, dtype=object)

    out: dict[str, np.ndarray] = {}
    for lab in labels:
        m = (band == lab) & np.isfinite(phi)
        if np.any(m):
            out[str(lab)] = phi[m].astype(float)
    return out


def _safe_pow_mean(mean_phi: float, alpha: float) -> float:
    if not np.isfinite(mean_phi) or mean_phi <= 0:
        return float("nan")
    return float(np.exp(float(alpha) * float(np.log(mean_phi))))


def _make_bins(x_all: np.ndarray, *, cfg: Config) -> tuple[np.ndarray, str, float, float]:
    x_all = np.asarray(x_all, dtype=float)
    x_all = x_all[np.isfinite(x_all) & (x_all > 0)]
    if x_all.size < 10:
        return np.array([]), "linear", float("nan"), float("nan")

    lo_q = float(cfg.x_lo_q)
    hi_q = float(cfg.x_hi_q)
    lo = float(np.nanpercentile(x_all, lo_q))
    hi = float(np.nanpercentile(x_all, hi_q))
    if not (np.isfinite(lo) and np.isfinite(hi) and hi > lo and lo > 0):
        return np.array([]), "linear", float("nan"), float("nan")

    mode = str(cfg.binning).strip().lower()
    if mode not in {"auto", "linear", "log"}:
        mode = "auto"
    if mode == "auto":
        mode = "log" if (hi / lo) >= 50.0 else "linear"

    n_bins = int(cfg.n_bins)
    if n_bins < 10:
        n_bins = 10

    if mode == "log":
        bins = np.logspace(np.log10(lo), np.log10(hi), n_bins + 1)
    else:
        bins = np.linspace(lo, hi, n_bins + 1)
    return bins.astype(float), mode, float(lo), float(hi)


def _hist_density(x: np.ndarray, bins: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0 or bins.size < 2:
        return np.full(max(0, bins.size - 1), np.nan, dtype=float)
    h, _ = np.histogram(x, bins=bins, density=True)
    return h.astype(float)


def _bin_centers(bins: np.ndarray, *, mode: str) -> np.ndarray:
    if bins.size < 2:
        return np.array([])
    if mode == "log":
        return np.sqrt(bins[:-1] * bins[1:]).astype(float)
    return ((bins[:-1] + bins[1:]) / 2.0).astype(float)


def _collapse_residual(densities: list[np.ndarray], bins: np.ndarray) -> float:
    if not densities or bins.size < 2:
        return float("nan")
    P = np.vstack(densities).astype(float)  # (n_disasters, n_bins)
    if P.size == 0:
        return float("nan")
    mean = np.nanmean(P, axis=0)
    var = np.nanmean((P - mean) ** 2, axis=0)
    w = np.diff(bins).astype(float)
    ww = w[np.isfinite(var)]
    vv = var[np.isfinite(var)]
    if ww.size == 0 or float(np.sum(ww)) <= 0:
        return float("nan")
    return float(np.sum(vv * ww) / np.sum(ww))


def run(cfg: Config) -> None:
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

    specs = load_catalog(cfg.catalog)
    labels = distance_bin_labels(cfg.distance_bins_km)

    # 1) 为每个灾害选择 t_crisis window，并提取 tile-level φ 分布（按距离带）
    per_disaster: dict[str, dict] = {}
    summary_rows: list[dict] = []

    mode = str(cfg.t_crisis_mode).strip().lower()
    if mode not in {"peak_0_25", "fixed"}:
        raise SystemExit(f"未知 t_crisis_mode：{cfg.t_crisis_mode}（可选：peak_0_25/fixed）")
    if mode == "fixed" and cfg.t_crisis_hours is None:
        raise SystemExit("t_crisis_mode=fixed 需要提供 --t-crisis-hours")

    for spec in specs:
        t0_pt, center_lat, center_lon, _meta = auto_t0_and_center(spec)
        pop_dir = spec.data_root / "population"
        windows = _list_windows(pop_dir, t0_pt=pd.Timestamp(t0_pt), only_hour_pt=cfg.only_hour_pt)

        if mode == "fixed":
            target = float(cfg.t_crisis_hours)
        else:
            target = _load_peak_hours(cfg.output_root, spec.slug, max_hours=cfg.peak_max_hours)

        picked = _pick_nearest_window(windows, float(target))
        pop_path = Path(picked["path"])
        used_hours = float(picked["hours_since_quake"])
        used_ts = pd.Timestamp(picked["window_start_pt"])

        phi_by_band = _phi_by_band_for_window(
            pop_path,
            center_lat=float(center_lat),
            center_lon=float(center_lon),
            distance_bins_km=cfg.distance_bins_km,
            phi_clip_lo=float(cfg.phi_clip_lo),
            phi_clip_hi=float(cfg.phi_clip_hi),
        )

        per_disaster[spec.slug] = {
            "slug": spec.slug,
            "name": spec.name,
            "event_type": spec.event_type,
            "t0_pt": pd.Timestamp(t0_pt),
            "center_lat": float(center_lat),
            "center_lon": float(center_lon),
            "t_target_hours": float(target),
            "t_used_hours": float(used_hours),
            "window_start_pt": used_ts,
            "population_file": str(pop_path),
            "phi_by_band": phi_by_band,
        }

        for band in labels:
            vals = phi_by_band.get(str(band))
            if vals is None or vals.size == 0:
                continue
            v = vals.astype(float)
            summary_rows.append(
                {
                    "slug": spec.slug,
                    "event_type": spec.event_type,
                    "t_target_hours": float(target),
                    "t_used_hours": float(used_hours),
                    "window_start_pt": str(used_ts),
                    "distance_band": str(band),
                    "n_tiles": int(v.size),
                    "phi_mean": float(np.nanmean(v)),
                    "phi_median": float(np.nanmedian(v)),
                    "phi_std": float(np.nanstd(v)),
                    "phi_p95": float(np.nanpercentile(v, 95)),
                    "phi_p99": float(np.nanpercentile(v, 99)),
                }
            )

    summary_df = pd.DataFrame(summary_rows)
    out_summary = out.tables / "phi_samples_summary.csv"
    summary_df.to_csv(out_summary, index=False)

    # 2) 对每个距离带做 α 扫描，优化坍缩残差
    alpha_grid = _alpha_grid(cfg)
    best_rows: list[dict] = []

    for band in labels:
        # 收集可用灾害
        series: list[dict] = []
        for slug, meta in per_disaster.items():
            vals = meta["phi_by_band"].get(str(band))
            if vals is None:
                continue
            vals = np.asarray(vals, dtype=float)
            vals = vals[np.isfinite(vals)]
            if vals.size < int(cfg.min_tiles_per_band):
                continue
            mu = float(np.nanmean(vals))
            if not np.isfinite(mu) or mu <= 0:
                continue
            series.append({"slug": slug, "event_type": meta["event_type"], "phi": vals, "mean": mu})

        if len(series) < 2:
            continue

        scan_rows: list[dict] = []
        best_alpha = float("nan")
        best_e = float("inf")
        best_bins = np.array([])
        best_bins_mode = "linear"
        best_xlo = float("nan")
        best_xhi = float("nan")

        for a in alpha_grid:
            scaled: list[np.ndarray] = []
            for item in series:
                scale = _safe_pow_mean(float(item["mean"]), float(a))
                if not np.isfinite(scale) or scale <= 0:
                    continue
                x = item["phi"] / scale
                x = x[np.isfinite(x) & (x > 0)]
                if x.size:
                    scaled.append(x.astype(float))

            if len(scaled) < 2:
                scan_rows.append({"distance_band": str(band), "alpha": float(a), "E": float("nan"), "n_disasters": int(len(scaled))})
                continue

            x_all = np.concatenate(scaled) if scaled else np.array([])
            bins, bins_mode, xlo, xhi = _make_bins(x_all, cfg=cfg)
            if bins.size < 2:
                scan_rows.append({"distance_band": str(band), "alpha": float(a), "E": float("nan"), "n_disasters": int(len(scaled))})
                continue

            densities = [_hist_density(x, bins) for x in scaled]
            e = _collapse_residual(densities, bins)
            scan_rows.append({"distance_band": str(band), "alpha": float(a), "E": float(e), "n_disasters": int(len(scaled))})
            if np.isfinite(e) and float(e) < float(best_e):
                best_e = float(e)
                best_alpha = float(a)
                best_bins = bins
                best_bins_mode = str(bins_mode)
                best_xlo = float(xlo)
                best_xhi = float(xhi)

        scan_df = pd.DataFrame(scan_rows)
        out_scan = out.tables / f"alpha_scan_{str(band).replace('+', 'plus')}.csv"
        scan_df.to_csv(out_scan, index=False)

        if not np.isfinite(best_alpha):
            continue

        best_rows.append(
            {
                "distance_band": str(band),
                "alpha_star": float(best_alpha),
                "E_min": float(best_e),
                "n_disasters_used": int(len(series)),
                "binning": str(best_bins_mode),
                "xlo_q": float(cfg.x_lo_q),
                "xhi_q": float(cfg.x_hi_q),
                "x_min": float(best_xlo),
                "x_max": float(best_xhi),
                "t_crisis_mode": str(mode),
                "only_hour_pt": int(cfg.only_hour_pt) if cfg.only_hour_pt is not None else -1,
                "phi_clip_lo": float(cfg.phi_clip_lo),
                "phi_clip_hi": float(cfg.phi_clip_hi),
            }
        )

        # residual plot
        with ps.paper_style():
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
            x = pd.to_numeric(scan_df["alpha"], errors="coerce").to_numpy(dtype=float)
            y = pd.to_numeric(scan_df["E"], errors="coerce").to_numpy(dtype=float)
            m = np.isfinite(x) & np.isfinite(y)
            ax.plot(x[m], y[m], color=ps.OKABE_ITO["blue"], linewidth=2.2)
            if np.isfinite(best_alpha):
                ax.axvline(float(best_alpha), color=ps.OKABE_ITO["vermillion"], linestyle=":", linewidth=1.6, alpha=0.85)
            ax.set_xlabel(r"Scaling exponent $\alpha$")
            ax.set_ylabel(r"Residual $E(\alpha)$")
            ax.set_title(f"Collapse residual vs alpha ({band})")
            ps.despine(ax)
            fig.tight_layout()
            save_png_and_pdf(ps, fig, out.figures / f"residual_E_alpha_{str(band).replace('+', 'plus')}.png")
            plt.close(fig)

        # collapse plot at alpha*
        centers = _bin_centers(best_bins, mode=best_bins_mode)
        with ps.paper_style():
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
            palette = [
                ps.OKABE_ITO["blue"],
                ps.OKABE_ITO["vermillion"],
                ps.OKABE_ITO["bluish_green"],
                ps.OKABE_ITO["orange"],
                ps.OKABE_ITO["sky_blue"],
                ps.OKABE_ITO["reddish_purple"],
            ]
            for i, item in enumerate(series):
                scale = _safe_pow_mean(float(item["mean"]), float(best_alpha))
                if not np.isfinite(scale) or scale <= 0:
                    continue
                x = item["phi"] / scale
                dens = _hist_density(x, best_bins)
                color = palette[i % len(palette)]
                ax.plot(centers, dens, color=color, linewidth=2.0, alpha=0.9, label=str(item["slug"]))

            if best_bins_mode == "log":
                ax.set_xscale("log")
            ax.set_xlabel(r"$x=\phi/\langle \phi \rangle^{\alpha}$")
            ax.set_ylabel(r"$p(x)$")
            ax.set_title(f"PDF collapse ({band}), alpha*={best_alpha:.2f}")
            ax.legend(frameon=False, loc="upper right")
            ps.despine(ax)
            fig.tight_layout()
            save_png_and_pdf(ps, fig, out.figures / f"collapse_pdf_{str(band).replace('+', 'plus')}.png")
            plt.close(fig)

    best_df = pd.DataFrame(best_rows)
    out_best = out.tables / "best_alpha_by_band.csv"
    best_df.to_csv(out_best, index=False)

    readme = f"""# Finite-size scaling (FSS) collapse for tile-level $\\phi$

目标：对每个灾害、每个距离带，在一个指定的 crisis 时刻 $t_{{crisis}}$ 提取 tile-level
$$\\phi = n_{{crisis}}/n_{{baseline}}$$
并做尺度变换 $x=\\phi/\\langle\\phi\\rangle^\\alpha$，优化 $\\alpha$ 使不同灾害的 $p(x)$ 曲线坍缩。

## t_crisis 选择

- mode: `{mode}`
  - `peak_0_25`：每个灾害用 `outputs/<slug>/population_redistribution/.../redistribution_by_distance_band.csv` 的 `0-25km` 在 t>=0（且可选 `peak_max_hours`）内的 `phi_aggregate` 峰值时刻作为 t_crisis
  - `fixed`：所有灾害使用相同的 `t_crisis_hours`

## 主要输出

- `tables/phi_samples_summary.csv`：每个灾害 × 距离带的 φ 分布摘要（n/mean/quantiles）
- `tables/best_alpha_by_band.csv`：每个距离带的最优 α 与最小残差
- `tables/alpha_scan_<band>.csv`：每个距离带的 E(α) 扫描结果
- `figures/residual_E_alpha_<band>.*`：残差曲线
- `figures/collapse_pdf_<band>.*`：坍缩图（不同灾害不同颜色）

## 参数（写入 best_alpha_by_band.csv）

- distance_bins_km: {list(cfg.distance_bins_km)}
- only_hour_pt: {cfg.only_hour_pt}
- phi_clip: [{float(cfg.phi_clip_lo)}, {float(cfg.phi_clip_hi)}]
- alpha_grid: [{float(cfg.alpha_min)}, {float(cfg.alpha_max)}] step {float(cfg.alpha_step)}
- binning: {cfg.binning}, x-quantiles: [{float(cfg.x_lo_q)}, {float(cfg.x_hi_q)}]
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_best}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog.csv"), help="灾难配置表（CSV）")
    parser.add_argument("--output-root", type=Path, default=Path("outputs"), help="outputs 根目录（读取 population_redistribution 用）")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/cross_disaster_comparison/phi_fss_collapse"),
        help="输出目录",
    )
    parser.add_argument("--t-crisis-mode", type=str, default="peak_0_25", help="peak_0_25 | fixed")
    parser.add_argument("--t-crisis-hours", type=float, default=None, help="t_crisis_mode=fixed 时使用（hours_since_quake）")
    parser.add_argument("--peak-max-hours", type=float, default=832.0, help="peak_0_25 的搜索上界（小时）")
    parser.add_argument("--only-hour-pt", type=int, default=8, help="只使用该小时的窗口（默认 08:00；设为 -1 表示不过滤）")
    parser.add_argument("--phi-clip-hi", type=float, default=3.0, help="tile-level φ 的上界裁剪（默认 3）")
    parser.add_argument("--min-tiles-per-band", type=int, default=200, help="每个灾害在该 band 的最少 tiles（默认 200）")
    parser.add_argument("--alpha-min", type=float, default=-2.0)
    parser.add_argument("--alpha-max", type=float, default=2.0)
    parser.add_argument("--alpha-step", type=float, default=0.05)
    parser.add_argument("--n-bins", type=int, default=45, help="直方图 bins 数（默认 45）")
    parser.add_argument("--binning", type=str, default="auto", help="auto | linear | log")
    args = parser.parse_args()

    only_hour = None if int(args.only_hour_pt) < 0 else int(args.only_hour_pt)

    cfg = Config(
        catalog=args.catalog,
        output_root=args.output_root,
        output_dir=args.output_dir,
        t_crisis_mode=str(args.t_crisis_mode),
        t_crisis_hours=float(args.t_crisis_hours) if args.t_crisis_hours is not None else None,
        peak_max_hours=float(args.peak_max_hours) if args.peak_max_hours is not None else None,
        only_hour_pt=only_hour,
        phi_clip_hi=float(args.phi_clip_hi),
        min_tiles_per_band=int(args.min_tiles_per_band),
        alpha_min=float(args.alpha_min),
        alpha_max=float(args.alpha_max),
        alpha_step=float(args.alpha_step),
        n_bins=int(args.n_bins),
        binning=str(args.binning),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()
