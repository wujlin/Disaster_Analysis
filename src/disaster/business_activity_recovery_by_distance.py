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
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    data_root: Path
    output_dir: Path
    epicenter_lat: float = 37.174
    epicenter_lon: float = 37.032
    t0_pt: pd.Timestamp = pd.Timestamp("2023-02-05 16:00")
    distance_bins_km: tuple[float, ...] = (0.0, 25.0, 50.0, 100.0, 200.0, float("inf"))
    only_vertical: str = "all"
    tail_frac: float = 0.2


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


def _linearized_tau(t: np.ndarray, y: np.ndarray, *, tail_frac: float) -> dict:
    mask = np.isfinite(t) & np.isfinite(y)
    t = t[mask].astype(float)
    y = y[mask].astype(float)
    out = {"fit_ok": 0, "n_points": int(t.size), "tau": float("nan"), "r2": float("nan")}
    if t.size < 6:
        return out
    order = np.argsort(t)
    t = t[order]
    y = y[order]
    t0 = float(t[0])
    tt = t - t0
    y0 = float(y[0])
    k = max(3, int(np.ceil(float(tail_frac) * float(y.size))))
    y_inf = float(np.nanmedian(y[-k:]))
    denom = y0 - y_inf
    if not np.isfinite(denom) or abs(denom) < 1e-12:
        return out
    z = (y - y_inf) / denom
    m = np.isfinite(z) & (z > 0) & (z < 10.0)
    if np.sum(m) < 6:
        return out
    x = tt[m]
    lnz = np.log(z[m])
    X = np.vstack([np.ones_like(x), x]).T
    beta, *_ = np.linalg.lstsq(X, lnz, rcond=None)
    b = float(beta[1])
    if not np.isfinite(b) or b >= 0:
        return out
    y_hat = X @ beta
    resid = lnz - y_hat
    sse = float(np.sum(resid**2))
    sst = float(np.sum((lnz - float(np.mean(lnz))) ** 2))
    r2 = float(1.0 - sse / sst) if sst > 0 else float("nan")
    out.update({"fit_ok": 1, "n_points": int(t.size), "tau": float(-1.0 / b), "r2": r2})
    return out


def _load_business_activity_file(path: Path) -> pd.DataFrame:
    wanted = {
        "polygon_id",
        "polygon_name",
        "polygon_level",
        "polygon_version",
        "country",
        "business_vertical",
        "activity_quantile",
        "latitude",
        "longitude",
        "lat",
        "lon",
        "ds",
    }
    df = pd.read_csv(path, usecols=lambda c: c in wanted, na_values=["\\N", ""])
    df = df.rename(columns={"latitude": "lat", "longitude": "lon"})
    for col in ["lat", "lon", "activity_quantile"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "ds" in df.columns:
        df["ds"] = pd.to_datetime(df["ds"], errors="coerce")
    return df


def run(cfg: Config) -> None:
    ba_dir = cfg.data_root / "business activity"
    if not ba_dir.exists():
        raise FileNotFoundError(f"未找到目录：{ba_dir}")

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

    files = sorted(ba_dir.rglob("*.csv"))
    if not files:
        raise FileNotFoundError(f"目录为空：{ba_dir}")

    frames: list[pd.DataFrame] = []
    for i, path in enumerate(files, start=1):
        df = _load_business_activity_file(path)
        if not df.empty:
            df["source_file"] = str(path.name)
            frames.append(df)
        if i % 10 == 0:
            print(f"[business_activity] loaded {i}/{len(files)} files...")

    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if data.empty:
        raise SystemExit("Business activity 数据为空或字段无法识别。")

    if "business_vertical" in data.columns:
        data = data[data["business_vertical"].astype(str).str.lower() == str(cfg.only_vertical).lower()].copy()
    if data.empty:
        raise SystemExit(f"未找到 business_vertical={cfg.only_vertical} 的记录。")

    for col in ["lat", "lon", "activity_quantile", "ds"]:
        if col not in data.columns:
            raise SystemExit(f"缺少列：{col}")

    data = data[data["ds"].notna()].copy()
    data["hours_since_quake"] = (pd.to_datetime(data["ds"]) - cfg.t0_pt).dt.total_seconds() / 3600.0
    data["distance_km"] = haversine_km(
        pd.to_numeric(data["lat"], errors="coerce").to_numpy(dtype=float),
        pd.to_numeric(data["lon"], errors="coerce").to_numpy(dtype=float),
        cfg.epicenter_lat,
        cfg.epicenter_lon,
    )

    bins = list(cfg.distance_bins_km)
    labels = _distance_band_labels(cfg.distance_bins_km)
    data["band"] = pd.cut(data["distance_km"], bins=bins, right=False, labels=labels, include_lowest=True).astype(str)
    data["activity_quantile"] = pd.to_numeric(data["activity_quantile"], errors="coerce")
    data = data[data["band"].isin(set(labels)) & data["activity_quantile"].notna()].copy()
    if data.empty:
        raise SystemExit("按距离分带后数据为空。")

    by = (
        data.groupby(["ds", "hours_since_quake", "band"], observed=True)
        .agg(n_polygons=("activity_quantile", "count"), activity_mean=("activity_quantile", "mean"))
        .reset_index()
        .sort_values(["hours_since_quake", "band"], kind="stable")
    )
    out_ts = out.tables / "business_activity_by_band.csv"
    by.to_csv(out_ts, index=False)

    # τ 拟合（band-level, activity_mean）
    fit_rows: list[dict] = []
    for band, sub in by.groupby("band", sort=False, observed=True):
        sub = sub.sort_values("hours_since_quake", kind="stable")
        t = pd.to_numeric(sub["hours_since_quake"], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(sub["activity_mean"], errors="coerce").to_numpy(dtype=float)
        fit = _linearized_tau(t, y, tail_frac=float(cfg.tail_frac))
        fit_rows.append({"band": str(band), "n_points": int(fit["n_points"]), "tau_hours": float(fit["tau"]), "tau_r2": float(fit["r2"]), "fit_ok": int(fit["fit_ok"])})

    fit_df = pd.DataFrame(fit_rows)
    out_fit = out.tables / "business_activity_tau_by_band.csv"
    fit_df.to_csv(out_fit, index=False)

    # plot
    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        for band, sub in by.groupby("band", sort=False, observed=True):
            sub = sub.sort_values("hours_since_quake", kind="stable")
            ax.plot(sub["hours_since_quake"], sub["activity_mean"], marker="o", label=str(band))
        ax.axvline(0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.axhline(0.5, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.7)
        ax.set_xlabel("Hours since earthquake (PT)")
        ax.set_ylabel("Business activity quantile (mean)")
        ax.set_title("Business activity recovery by distance band")
        ax.legend(frameon=False, ncol=3)
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "business_activity_timeseries.png")
        plt.close(fig)

    readme = f"""# Business Activity Recovery by Distance

用途：作为独立经济 proxy，检验 population 侧的空间恢复模式是否可复现。

## 输入

- `{cfg.data_root}/business activity/**/*.csv`

## 口径

- business_vertical = `{cfg.only_vertical}`
- activity 指标：`activity_quantile`（文档定义为相对 baseline 的 quantile；0.5≈正常）
- 距离：polygon centroid (lat/lon) → 震中

## 输出

- `tables/business_activity_by_band.csv`
- `tables/business_activity_tau_by_band.csv`（对 band-level mean(activity) 做线性化指数拟合）
- `figures/business_activity_timeseries.*`
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_fit}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("Data/Turkiye Turkey Earthquake Full Country Version Feb 8 2023"),
        help="数据根目录（包含 business activity/ 子目录）",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/business_activity_validation"), help="输出目录")
    parser.add_argument("--t0-pt", type=str, default="2023-02-05 16:00", help="t=0 的 PT 时间戳")
    parser.add_argument("--only-vertical", type=str, default="all", help="只保留该 business_vertical（默认 all）")
    args = parser.parse_args()

    cfg = Config(
        data_root=args.data_root,
        output_dir=args.output_dir,
        t0_pt=pd.Timestamp(str(args.t0_pt)),
        only_vertical=str(args.only_vertical),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()

