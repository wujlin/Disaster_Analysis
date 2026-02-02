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

from disaster.cross_disaster_phi_tau import auto_t0_and_center, load_catalog
from disaster.geo import distance_bin_labels, haversine_km
from disaster.population_io import load_population_file, parse_window_start_pt
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    catalog: Path
    output_root: Path
    output_dir: Path

    # t_crisis selection
    t_crisis_mode: str = "peak_0_25"  # peak_0_25 | fixed
    t_crisis_hours: float = 88.0
    peak_max_hours: float = 832.0
    only_hour_pt: int = 8

    # distance bands for distributions
    distance_bins_km: tuple[float, ...] = (0.0, 25.0, 50.0, 100.0, 200.0, float("inf"))

    # collapse scan
    alpha_min: float = 0.0
    alpha_max: float = 2.0
    alpha_step: float = 0.05
    n_bins: int = 60
    x_clip_qlo: float = 0.005
    x_clip_qhi: float = 0.995
    min_tiles_per_disaster_band: int = 50
    min_disasters_per_band: int = 2

    # x definition
    phi_scale: str = "mean"  # mean | aggregate


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _band_slug(label: str) -> str:
    return (
        label.replace(" ", "_")
        .replace("-", "_")
        .replace("+", "plus")
        .replace("/", "_")
        .replace("km", "km")
        .replace("__", "_")
    )


def _band_lo_km(label: str) -> float:
    s = str(label)
    if s.endswith("km+"):
        return float(s.replace("km+", ""))
    if "-" in s:
        left = s.split("-", 1)[0]
        return float(left.replace("km", ""))
    return float("inf")


def _pick_peak_band(available: list[str]) -> str:
    if "0-25km" in set(available):
        return "0-25km"
    # fallback: choose smallest lower bound band present
    return sorted(available, key=_band_lo_km)[0]


def _list_population_windows(data_root: Path, *, only_hour_pt: int) -> list[dict]:
    pop_dir = data_root / "population"
    if not pop_dir.exists():
        raise FileNotFoundError(f"未找到目录：{pop_dir}")
    files = sorted(pop_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"目录为空：{pop_dir}")
    rows: list[dict] = []
    for path in files:
        ts = pd.Timestamp(parse_window_start_pt(path))
        if int(ts.hour) != int(only_hour_pt):
            continue
        rows.append({"path": path, "window_start_pt": ts})
    rows = sorted(rows, key=lambda r: pd.Timestamp(r["window_start_pt"]))
    if not rows:
        raise FileNotFoundError(f"未找到 hour={only_hour_pt} 的 population 文件：{pop_dir}")
    return rows


def _nearest_window(windows: list[dict], target: pd.Timestamp) -> dict:
    ts = np.array([pd.Timestamp(w["window_start_pt"]).to_datetime64() for w in windows])
    t = target.to_datetime64()
    idx = int(np.argmin(np.abs(ts - t)))
    return windows[idx]


def _try_load_metadata(output_root: Path, slug: str) -> dict | None:
    path = output_root / slug / "metadata.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _select_t_crisis_window(
    *,
    spec,
    cfg: Config,
    t0_pt: pd.Timestamp,
    center_lat: float,
    center_lon: float,
) -> tuple[pd.Timestamp, float, str]:
    """
    返回 (window_start_pt, hours_since_quake, method_detail)
    """
    windows = _list_population_windows(spec.data_root, only_hour_pt=int(cfg.only_hour_pt))

    if cfg.t_crisis_mode == "fixed":
        target = pd.Timestamp(t0_pt) + pd.Timedelta(hours=float(cfg.t_crisis_hours))
        picked = _nearest_window(windows, target)
        ws = pd.Timestamp(picked["window_start_pt"])
        hs = float((ws - pd.Timestamp(t0_pt)).total_seconds() / 3600.0)
        return ws, hs, f"fixed_nearest_to_{float(cfg.t_crisis_hours):g}h"

    if cfg.t_crisis_mode != "peak_0_25":
        raise SystemExit(f"不支持的 --t-crisis-mode：{cfg.t_crisis_mode}（仅支持 peak_0_25 / fixed）")

    # Prefer reusing existing population_redistribution outputs (fast, consistent with existing pipeline).
    by_band_csv = cfg.output_root / spec.slug / "population_redistribution" / "tables" / "redistribution_by_distance_band.csv"
    if by_band_csv.exists():
        df = pd.read_csv(by_band_csv)
        if {"hours_since_quake", "window_start_pt", "distance_band", "phi_aggregate"} <= set(df.columns):
            df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
            df = df.dropna(subset=["hours_since_quake"]).copy()
            df = df[(df["hours_since_quake"] >= 0) & (df["hours_since_quake"] <= float(cfg.peak_max_hours))].copy()
            if not df.empty:
                bands = sorted(set(df["distance_band"].astype(str)))
                band = _pick_peak_band(bands)
                sub = df[df["distance_band"].astype(str) == band].copy()
                sub["phi_aggregate"] = pd.to_numeric(sub["phi_aggregate"], errors="coerce")
                sub = sub.dropna(subset=["phi_aggregate"]).copy()
                if not sub.empty:
                    idx = int(sub["phi_aggregate"].to_numpy(dtype=float).argmax())
                    row = sub.iloc[idx]
                    ws = pd.Timestamp(row["window_start_pt"])
                    hs = float(row["hours_since_quake"])
                    return ws, hs, f"peak_phi_aggregate_{band}_from_existing_table"

    # Fallback: scan population windows and compute band-level phi_aggregate (slow but self-contained).
    labels = distance_bin_labels(cfg.distance_bins_km)
    peak_band = _pick_peak_band(labels)
    bins = list(cfg.distance_bins_km)

    peak_ws: pd.Timestamp | None = None
    peak_hs: float = float("nan")
    peak_phi: float = float("-inf")
    for w in windows:
        ws = pd.Timestamp(w["window_start_pt"])
        hs = float((ws - pd.Timestamp(t0_pt)).total_seconds() / 3600.0)
        if hs < 0 or hs > float(cfg.peak_max_hours):
            continue
        df = load_population_file(Path(w["path"]))
        lat = pd.to_numeric(df.get("lat", np.nan), errors="coerce").to_numpy(dtype=float)
        lon = pd.to_numeric(df.get("lon", np.nan), errors="coerce").to_numpy(dtype=float)
        nb = pd.to_numeric(df.get("n_baseline", np.nan), errors="coerce").to_numpy(dtype=float)
        nc = pd.to_numeric(df.get("n_crisis", np.nan), errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(lat) & np.isfinite(lon) & np.isfinite(nb) & np.isfinite(nc) & (nb > 0)
        if not np.any(ok):
            continue
        dist = haversine_km(lat, lon, float(center_lat), float(center_lon))
        band = pd.cut(dist, bins=bins, right=False, labels=labels, include_lowest=True).astype(str).to_numpy()
        m = ok & (band == peak_band)
        if not np.any(m):
            continue
        base_sum = float(np.nansum(nb[m]))
        crisis_sum = float(np.nansum(nc[m]))
        if base_sum <= 0:
            continue
        phi = float(crisis_sum / base_sum)
        if phi > peak_phi:
            peak_phi = phi
            peak_ws = ws
            peak_hs = hs

    if peak_ws is None or not np.isfinite(peak_phi):
        raise SystemExit(f"无法确定 t_crisis：{spec.slug}（peak_0_25 模式下无有效窗口/数据）")
    return peak_ws, float(peak_hs), f"peak_phi_aggregate_{peak_band}_from_population_scan"


def _hist_density(x: np.ndarray, bins: np.ndarray) -> np.ndarray:
    if x.size == 0:
        return np.full(bins.size - 1, np.nan, dtype=float)
    h, _ = np.histogram(x, bins=bins, density=True)
    return h.astype(float)


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
    bins = list(cfg.distance_bins_km)

    # Collect tile-level phi samples by (band, disaster)
    phi_samples: dict[str, dict[str, np.ndarray]] = {}
    band_stats_rows: list[dict] = []

    for spec in specs:
        meta = _try_load_metadata(cfg.output_root, spec.slug)
        if meta is not None:
            t0_pt = pd.Timestamp(meta.get("t0_pt"))
            center_lat = float(meta.get("center_lat"))
            center_lon = float(meta.get("center_lon"))
            meta_method = "metadata_json"
        else:
            t0_pt, center_lat, center_lon, _meta = auto_t0_and_center(spec)
            meta_method = "auto_t0_and_center"

        # Allow overriding only_hour_pt globally from CLI
        if int(cfg.only_hour_pt) != int(spec.only_hour_pt):
            spec = type(spec)(**{**spec.__dict__, "only_hour_pt": int(cfg.only_hour_pt)})  # type: ignore

        ws, hs, t_method = _select_t_crisis_window(spec=spec, cfg=cfg, t0_pt=t0_pt, center_lat=center_lat, center_lon=center_lon)

        windows = _list_population_windows(spec.data_root, only_hour_pt=int(cfg.only_hour_pt))
        picked = _nearest_window(windows, ws)
        pop_path = Path(picked["path"])
        ws = pd.Timestamp(picked["window_start_pt"])
        hs = float((ws - pd.Timestamp(t0_pt)).total_seconds() / 3600.0)

        df = load_population_file(pop_path)
        lat = pd.to_numeric(df.get("lat", np.nan), errors="coerce").to_numpy(dtype=float)
        lon = pd.to_numeric(df.get("lon", np.nan), errors="coerce").to_numpy(dtype=float)
        nb = pd.to_numeric(df.get("n_baseline", np.nan), errors="coerce").to_numpy(dtype=float)
        nc = pd.to_numeric(df.get("n_crisis", np.nan), errors="coerce").to_numpy(dtype=float)

        ok = np.isfinite(lat) & np.isfinite(lon) & np.isfinite(nb) & np.isfinite(nc) & (nb > 0)
        if not np.any(ok):
            print(f"[phi_fss_collapse] {spec.slug}: no valid tiles at t_crisis (overlap & n_baseline>0).")
            continue

        dist = haversine_km(lat, lon, float(center_lat), float(center_lon))
        band = pd.cut(dist, bins=bins, right=False, labels=labels, include_lowest=True).astype(str).to_numpy()

        phi = (nc / nb).astype(float)

        for b in labels:
            m = ok & (band == str(b))
            if not np.any(m):
                continue
            phi_i = phi[m]
            phi_i = phi_i[np.isfinite(phi_i)]
            if phi_i.size == 0:
                continue

            # store samples
            phi_samples.setdefault(str(b), {})[spec.slug] = phi_i

            # scale stats (per disaster & band)
            base_sum = float(np.nansum(nb[m]))
            crisis_sum = float(np.nansum(nc[m]))
            phi_agg = float(crisis_sum / base_sum) if base_sum > 0 else float("nan")
            band_stats_rows.append(
                {
                    "slug": spec.slug,
                    "name": spec.name,
                    "event_type": spec.event_type,
                    "t0_pt": str(t0_pt),
                    "center_lat": float(center_lat),
                    "center_lon": float(center_lon),
                    "metadata_source": meta_method,
                    "t_crisis_mode": cfg.t_crisis_mode,
                    "t_crisis_method": t_method,
                    "t_crisis_window_start_pt": str(ws),
                    "t_crisis_hours_since_quake": float(hs),
                    "population_file": str(pop_path.name),
                    "distance_band": str(b),
                    "n_tiles": int(phi_i.size),
                    "phi_mean": float(np.nanmean(phi_i)),
                    "phi_median": float(np.nanmedian(phi_i)),
                    "phi_p10": float(np.nanpercentile(phi_i, 10)),
                    "phi_p90": float(np.nanpercentile(phi_i, 90)),
                    "phi_aggregate": phi_agg,
                }
            )

        print(f"[phi_fss_collapse] {spec.slug}: picked t_crisis {ws} (hs={hs:g}) from {pop_path.name}")

    if not band_stats_rows:
        raise SystemExit("未提取到任何灾害的 tile-level φ 样本（检查数据目录/only_hour_pt/t_crisis 选择）。")

    summary_df = pd.DataFrame(band_stats_rows)
    out_summary = out.tables / "phi_samples_summary.csv"
    summary_df.to_csv(out_summary, index=False)

    # Scan alpha per band and generate plots
    alpha_values = np.arange(float(cfg.alpha_min), float(cfg.alpha_max) + 1e-12, float(cfg.alpha_step), dtype=float)
    best_rows: list[dict] = []

    for band_label, by_disaster in phi_samples.items():
        # Only keep disasters with enough tiles
        usable: dict[str, np.ndarray] = {k: v for k, v in by_disaster.items() if int(v.size) >= int(cfg.min_tiles_per_disaster_band)}
        if len(usable) < int(cfg.min_disasters_per_band):
            print(f"[phi_fss_collapse] band={band_label}: usable disasters too few ({len(usable)}). Skip.")
            continue

        # Precompute phi_scale per disaster for this band
        scales: dict[str, float] = {}
        for slug, phi_i in usable.items():
            sub = summary_df[(summary_df["slug"] == slug) & (summary_df["distance_band"] == band_label)]
            if sub.empty:
                continue
            if cfg.phi_scale == "aggregate":
                scales[slug] = float(pd.to_numeric(sub["phi_aggregate"], errors="coerce").iloc[0])
            else:
                scales[slug] = float(pd.to_numeric(sub["phi_mean"], errors="coerce").iloc[0])

        scales = {k: v for k, v in scales.items() if np.isfinite(v) and v > 0}
        usable = {k: v for k, v in usable.items() if k in scales}
        if len(usable) < int(cfg.min_disasters_per_band):
            print(f"[phi_fss_collapse] band={band_label}: usable disasters too few after scaling filter ({len(usable)}). Skip.")
            continue

        scan_rows: list[dict] = []
        for a in alpha_values:
            xs: dict[str, np.ndarray] = {}
            for slug, phi_i in usable.items():
                s = float(scales[slug])
                x = phi_i.astype(float) / (s**float(a))
                x = x[np.isfinite(x)]
                if x.size < int(cfg.min_tiles_per_disaster_band):
                    continue
                # quantile clip (per disaster)
                qlo, qhi = np.nanquantile(x, [float(cfg.x_clip_qlo), float(cfg.x_clip_qhi)])
                if not np.isfinite(qlo) or not np.isfinite(qhi) or qhi <= qlo:
                    continue
                x = x[(x >= float(qlo)) & (x <= float(qhi))]
                if x.size < int(cfg.min_tiles_per_disaster_band):
                    continue
                xs[slug] = x

            if len(xs) < int(cfg.min_disasters_per_band):
                scan_rows.append({"alpha": float(a), "E": float("nan"), "n_disasters": int(len(xs)), "x_min": float("nan"), "x_max": float("nan")})
                continue

            x_min = float(min(float(np.nanmin(v)) for v in xs.values()))
            x_max = float(max(float(np.nanmax(v)) for v in xs.values()))
            if not (np.isfinite(x_min) and np.isfinite(x_max) and x_max > x_min):
                scan_rows.append({"alpha": float(a), "E": float("nan"), "n_disasters": int(len(xs)), "x_min": x_min, "x_max": x_max})
                continue

            bins_arr = np.linspace(x_min, x_max, int(cfg.n_bins) + 1, dtype=float)
            ps_list = []
            for slug, x in xs.items():
                p = _hist_density(x, bins_arr)
                if np.any(np.isfinite(p)):
                    ps_list.append(p)
            if len(ps_list) < int(cfg.min_disasters_per_band):
                scan_rows.append({"alpha": float(a), "E": float("nan"), "n_disasters": int(len(ps_list)), "x_min": x_min, "x_max": x_max})
                continue

            P = np.vstack(ps_list)
            p_mean = np.nanmean(P, axis=0)
            var = np.nanmean((P - p_mean) ** 2, axis=0)
            dx = np.diff(bins_arr)
            E = float(np.nansum(var * dx) / np.nansum(dx))

            scan_rows.append({"alpha": float(a), "E": E, "n_disasters": int(len(ps_list)), "x_min": x_min, "x_max": x_max})

        scan_df = pd.DataFrame(scan_rows)
        out_scan = out.tables / f"alpha_scan_{_band_slug(band_label)}.csv"
        scan_df.to_csv(out_scan, index=False)

        # best alpha
        scan_ok = scan_df[np.isfinite(pd.to_numeric(scan_df["E"], errors="coerce"))].copy()
        if scan_ok.empty:
            print(f"[phi_fss_collapse] band={band_label}: no valid E(alpha). Skip plots.")
            continue
        best_idx = int(pd.to_numeric(scan_ok["E"], errors="coerce").to_numpy(dtype=float).argmin())
        best = scan_ok.iloc[best_idx]
        alpha_star = float(best["alpha"])
        E_min = float(best["E"])
        n_used = int(best["n_disasters"])

        best_rows.append({"distance_band": band_label, "alpha_star": alpha_star, "E_min": E_min, "n_disasters": n_used, "phi_scale": cfg.phi_scale})

        # Plot E(alpha)
        with ps.paper_style():
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
            ax.plot(scan_df["alpha"], scan_df["E"], marker="o", color=ps.OKABE_ITO["blue"], alpha=0.9)
            ax.axvline(alpha_star, color=ps.OKABE_ITO["vermillion"], linestyle="--", linewidth=1.6, alpha=0.9, label=f"alpha*={alpha_star:.3g}")
            ax.set_xlabel(r"$\alpha$")
            ax.set_ylabel(r"$E(\alpha)$ (weighted variance)")
            ax.set_title(f"Residual scan for band {band_label} (scale={cfg.phi_scale})")
            ax.legend(frameon=False)
            ps.despine(ax)
            fig.tight_layout()
            save_png_and_pdf(ps, fig, out.figures / f"residual_E_alpha_{_band_slug(band_label)}.png")
            plt.close(fig)

        # Plot collapsed pdf curves at alpha*
        # Recompute xs and use common bins at alpha*
        xs: dict[str, np.ndarray] = {}
        for slug, phi_i in usable.items():
            s = float(scales[slug])
            x = phi_i.astype(float) / (s**float(alpha_star))
            x = x[np.isfinite(x)]
            if x.size < int(cfg.min_tiles_per_disaster_band):
                continue
            qlo, qhi = np.nanquantile(x, [float(cfg.x_clip_qlo), float(cfg.x_clip_qhi)])
            if not np.isfinite(qlo) or not np.isfinite(qhi) or qhi <= qlo:
                continue
            x = x[(x >= float(qlo)) & (x <= float(qhi))]
            if x.size < int(cfg.min_tiles_per_disaster_band):
                continue
            xs[slug] = x

        if len(xs) >= int(cfg.min_disasters_per_band):
            x_min = float(min(float(np.nanmin(v)) for v in xs.values()))
            x_max = float(max(float(np.nanmax(v)) for v in xs.values()))
            bins_arr = np.linspace(x_min, x_max, int(cfg.n_bins) + 1, dtype=float)
            centers = 0.5 * (bins_arr[:-1] + bins_arr[1:])
            with ps.paper_style():
                import matplotlib.pyplot as plt

                fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
                for slug, x in sorted(xs.items()):
                    p = _hist_density(x, bins_arr)
                    ax.plot(centers, p, label=slug, alpha=0.85)
                ax.set_xlabel(r"$x=\phi/\bar{\phi}^{\alpha}$" if cfg.phi_scale == "mean" else r"$x=\phi/\phi_{agg}^{\alpha}$")
                ax.set_ylabel(r"$p(x)$")
                ax.set_title(f"Collapse at alpha*={alpha_star:.3g} for band {band_label}")
                ax.legend(frameon=False, ncol=2, fontsize=8)
                ps.despine(ax)
                fig.tight_layout()
                save_png_and_pdf(ps, fig, out.figures / f"collapse_pdf_{_band_slug(band_label)}.png")
                plt.close(fig)

    best_df = pd.DataFrame(best_rows).sort_values(["distance_band"], kind="stable")
    out_best = out.tables / "best_alpha_by_band.csv"
    best_df.to_csv(out_best, index=False)

    readme = f"""# φ 分布数据坍缩验证（FSS-style, single-window）

目的：在选定的 t_crisis 单窗口截面上，比较不同灾害在相同距离带的 tile-level φ=n_crisis/n_baseline 分布是否可通过幂指数缩放坍缩。

## 输入

- `--catalog`：{cfg.catalog}
- 每个灾害读取 1 个 population 窗口文件（t_crisis）

## t_crisis 选择

- mode={cfg.t_crisis_mode}
- fixed：取 t=t0+{float(cfg.t_crisis_hours):g}h 的最近窗口
- peak_0_25：优先复用 `outputs/<slug>/population_redistribution/tables/redistribution_by_distance_band.csv`，在 0–{float(cfg.peak_max_hours):g}h 内取最靠近中心距离带（优先 0-25km，否则取最小 band）的 `phi_aggregate` 峰值窗口

## 坍缩定义

- tile-level：φ_i = n_crisis / n_baseline（只保留 n_baseline>0 且二者非空）
- 距离带：{list(cfg.distance_bins_km)}
- 缩放变量：x = φ_i / s^α，其中 s 为每灾害/距离带的尺度
    - `--phi-scale=mean`：s = mean(φ_i)（默认）
    - `--phi-scale=aggregate`：s = phi_aggregate = sum(n_crisis)/sum(n_baseline)
- p(x)：统一 bins 的直方图密度
- 残差：E(α) = ∫ Var_i[p_i(x)] dx（用 bin 宽加权近似）

## 主要输出

- `tables/phi_samples_summary.csv`：每灾害/距离带的样本量与尺度统计（含 t_crisis 选择详情）
- `tables/alpha_scan_<band>.csv`：每距离带的 E(α) 扫描
- `tables/best_alpha_by_band.csv`：每距离带最优 α*
- `figures/residual_E_alpha_<band>.*`：E(α) 曲线
- `figures/collapse_pdf_<band>.*`：坍缩后的 p(x)
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_best}")
    print(f"Done. Wrote: {out_summary}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog.csv"), help="灾难配置表（CSV）")
    parser.add_argument("--output-root", type=Path, default=Path("outputs"), help="输出根目录（用于读取已有 outputs/<slug>/...）")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/cross_disaster_comparison/phi_fss_collapse"), help="本脚本输出目录")

    parser.add_argument("--t-crisis-mode", type=str, default="peak_0_25", choices=["peak_0_25", "fixed"], help="t_crisis 选择模式")
    parser.add_argument("--t-crisis-hours", type=float, default=88.0, help="fixed 模式：t_crisis= t0 + hours（取最近窗口）")
    parser.add_argument("--peak-max-hours", type=float, default=832.0, help="peak 模式：只在 0..max_hours 内找峰值")
    parser.add_argument("--only-hour-pt", type=int, default=8, help="仅使用该小时（PT）的窗口（默认 08:00）")

    parser.add_argument("--alpha-min", type=float, default=0.0, help="α 扫描下界")
    parser.add_argument("--alpha-max", type=float, default=2.0, help="α 扫描上界")
    parser.add_argument("--alpha-step", type=float, default=0.05, help="α 扫描步长")
    parser.add_argument("--n-bins", type=int, default=60, help="直方图 bins 数")
    parser.add_argument("--x-clip-qlo", type=float, default=0.005, help="x 分位数裁剪下界")
    parser.add_argument("--x-clip-qhi", type=float, default=0.995, help="x 分位数裁剪上界")
    parser.add_argument("--min-tiles-per-disaster-band", type=int, default=50, help="每灾害/距离带最少 tiles 数")
    parser.add_argument("--min-disasters-per-band", type=int, default=2, help="每距离带最少灾害数")
    parser.add_argument("--phi-scale", type=str, default="mean", choices=["mean", "aggregate"], help="尺度 s 的定义")

    args = parser.parse_args()

    cfg = Config(
        catalog=args.catalog,
        output_root=args.output_root,
        output_dir=args.output_dir,
        t_crisis_mode=str(args.t_crisis_mode),
        t_crisis_hours=float(args.t_crisis_hours),
        peak_max_hours=float(args.peak_max_hours),
        only_hour_pt=int(args.only_hour_pt),
        alpha_min=float(args.alpha_min),
        alpha_max=float(args.alpha_max),
        alpha_step=float(args.alpha_step),
        n_bins=int(args.n_bins),
        x_clip_qlo=float(args.x_clip_qlo),
        x_clip_qhi=float(args.x_clip_qhi),
        min_tiles_per_disaster_band=int(args.min_tiles_per_disaster_band),
        min_disasters_per_band=int(args.min_disasters_per_band),
        phi_scale=str(args.phi_scale),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()
