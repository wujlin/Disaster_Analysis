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
from disaster.movement_io import load_movement_file
from disaster.population_io import parse_window_start_pt
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    data_root: Path
    output_dir: Path
    epicenter_lat: float = 37.174
    epicenter_lon: float = 37.032
    t0_pt: pd.Timestamp = pd.Timestamp("2023-02-05 16:00")
    only_hour_pt: int = 8
    distance_bins_km: tuple[float, ...] = (0.0, 25.0, 50.0, 100.0, 200.0, float("inf"))
    fit_min_hours: float = 0.0
    fit_max_hours: float | None = None
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


def run(cfg: Config, *, max_files: int | None = None) -> None:
    move_dir = cfg.data_root / "movement"
    if not move_dir.exists():
        raise FileNotFoundError(f"未找到目录：{move_dir}")

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

    files_all = sorted(move_dir.glob("*.csv"))
    if not files_all:
        raise FileNotFoundError(f"目录为空：{move_dir}")

    windows: list[dict] = []
    for path in files_all:
        window_start = parse_window_start_pt(path)
        if int(window_start.hour) != int(cfg.only_hour_pt):
            continue
        hs = float((window_start - cfg.t0_pt).total_seconds() / 3600.0)
        windows.append({"path": str(path), "window_start_pt": window_start, "hours_since_quake": hs})
    windows = sorted(windows, key=lambda r: float(r["hours_since_quake"]))
    if max_files is not None:
        windows = windows[: int(max_files)]
    if not windows:
        raise FileNotFoundError(f"未找到 hour={cfg.only_hour_pt} 的 movement 文件：{move_dir}")

    bins = list(cfg.distance_bins_km)
    labels = _distance_band_labels(cfg.distance_bins_km)

    outflow_rows: list[dict] = []
    inflow_rows: list[dict] = []

    for i, meta in enumerate(windows, start=1):
        df = load_movement_file(Path(meta["path"]))
        if df.empty:
            continue

        nb = pd.to_numeric(df.get("n_baseline", np.nan), errors="coerce")
        nc = pd.to_numeric(df.get("n_crisis", np.nan), errors="coerce")
        ok = nb.notna() & nc.notna() & (nb > 0)

        sdist = haversine_km(
            pd.to_numeric(df.get("start_lat", np.nan), errors="coerce").to_numpy(dtype=float),
            pd.to_numeric(df.get("start_lon", np.nan), errors="coerce").to_numpy(dtype=float),
            cfg.epicenter_lat,
            cfg.epicenter_lon,
        )
        edist = haversine_km(
            pd.to_numeric(df.get("end_lat", np.nan), errors="coerce").to_numpy(dtype=float),
            pd.to_numeric(df.get("end_lon", np.nan), errors="coerce").to_numpy(dtype=float),
            cfg.epicenter_lat,
            cfg.epicenter_lon,
        )

        sband = pd.cut(sdist, bins=bins, right=False, labels=labels, include_lowest=True).astype(str)
        eband = pd.cut(edist, bins=bins, right=False, labels=labels, include_lowest=True).astype(str)

        base = pd.DataFrame({"band": sband, "n_baseline": nb, "n_crisis": nc})
        base = base[ok].copy()
        g = base.groupby("band", observed=True).agg(n_edges=("n_baseline", "count"), baseline_sum=("n_baseline", "sum"), crisis_sum=("n_crisis", "sum")).reset_index()
        g["phi_aggregate"] = g["crisis_sum"] / g["baseline_sum"]
        for row in g.itertuples(index=False):
            outflow_rows.append(
                {
                    "window_start_pt": pd.Timestamp(meta["window_start_pt"]),
                    "hours_since_quake": float(meta["hours_since_quake"]),
                    "band": str(row.band),
                    "n_edges": int(row.n_edges),
                    "baseline_sum": float(row.baseline_sum),
                    "crisis_sum": float(row.crisis_sum),
                    "phi_aggregate": float(row.phi_aggregate),
                }
            )

        base2 = pd.DataFrame({"band": eband, "n_baseline": nb, "n_crisis": nc})
        base2 = base2[ok].copy()
        g2 = base2.groupby("band", observed=True).agg(n_edges=("n_baseline", "count"), baseline_sum=("n_baseline", "sum"), crisis_sum=("n_crisis", "sum")).reset_index()
        g2["phi_aggregate"] = g2["crisis_sum"] / g2["baseline_sum"]
        for row in g2.itertuples(index=False):
            inflow_rows.append(
                {
                    "window_start_pt": pd.Timestamp(meta["window_start_pt"]),
                    "hours_since_quake": float(meta["hours_since_quake"]),
                    "band": str(row.band),
                    "n_edges": int(row.n_edges),
                    "baseline_sum": float(row.baseline_sum),
                    "crisis_sum": float(row.crisis_sum),
                    "phi_aggregate": float(row.phi_aggregate),
                }
            )

        if i % 20 == 0:
            print(f"[movement_recovery_by_distance] processed {i}/{len(windows)} windows...")

    if not outflow_rows:
        raise SystemExit("未能生成 outflow 汇总（可能是过滤过严或数据为空）。")

    outflow = pd.DataFrame(outflow_rows).sort_values(["hours_since_quake", "band"], kind="stable")
    inflow = pd.DataFrame(inflow_rows).sort_values(["hours_since_quake", "band"], kind="stable")
    out_outflow = out.tables / "movement_outflow_by_band.csv"
    out_inflow = out.tables / "movement_inflow_by_band.csv"
    outflow.to_csv(out_outflow, index=False)
    inflow.to_csv(out_inflow, index=False)

    # τ 拟合（band-level, phi_aggregate）
    fit_rows: list[dict] = []
    for direction, table in [("outflow", outflow), ("inflow", inflow)]:
        for band, sub in table.groupby("band", sort=False, observed=True):
            sub = sub.sort_values("hours_since_quake", kind="stable")
            t = pd.to_numeric(sub["hours_since_quake"], errors="coerce").to_numpy(dtype=float)
            y = pd.to_numeric(sub["phi_aggregate"], errors="coerce").to_numpy(dtype=float)

            m = np.isfinite(t) & np.isfinite(y)
            t = t[m]
            y = y[m]
            m2 = t >= float(cfg.fit_min_hours)
            if cfg.fit_max_hours is not None:
                m2 &= t <= float(cfg.fit_max_hours)
            t = t[m2]
            y = y[m2]

            fit = _linearized_tau(t, y, tail_frac=float(cfg.tail_frac))
            fit_rows.append(
                {
                    "direction": direction,
                    "band": str(band),
                    "n_points": int(fit["n_points"]),
                    "tau_hours": float(fit["tau"]),
                    "tau_r2": float(fit["r2"]),
                    "fit_ok": int(fit["fit_ok"]),
                }
            )

    fit_df = pd.DataFrame(fit_rows)
    out_fit = out.tables / "movement_tau_by_band.csv"
    fit_df.to_csv(out_fit, index=False)

    # figures（phi_aggregate vs time）
    with ps.paper_style():
        import matplotlib.pyplot as plt

        def _plot(table: pd.DataFrame, *, title: str, out_name: str) -> None:
            fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
            for band, sub in table.groupby("band", sort=False, observed=True):
                sub = sub.sort_values("hours_since_quake", kind="stable")
                ax.plot(sub["hours_since_quake"], sub["phi_aggregate"], marker="o", label=str(band))
            ax.axvline(0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
            ax.axhline(1.0, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.7)
            ax.set_xlabel("Hours since earthquake (PT, 08:00 windows)")
            ax.set_ylabel(r"$\phi_{agg}=\sum n_{crisis}/\sum n_{baseline}$")
            ax.set_title(title)
            ax.legend(frameon=False, ncol=3)
            ps.despine(ax)
            fig.tight_layout()
            save_png_and_pdf(ps, fig, out.figures / out_name)
            plt.close(fig)

        _plot(outflow, title="Movement outflow: phi_aggregate by start-distance band", out_name="movement_outflow_phi_timeseries.png")
        _plot(inflow, title="Movement inflow: phi_aggregate by end-distance band", out_name="movement_inflow_phi_timeseries.png")

    readme = f"""# Movement Recovery by Distance (08:00 windows)

用途：验证“通达性/交通受阻（假说 B）”的外部证据。

## 输入

- `{cfg.data_root}/movement/*.csv`

## 口径

- 仅使用 PT {int(cfg.only_hour_pt):02d}:00 窗口
- outflow：按 start tile 到震中距离分带
- inflow：按 end tile 到震中距离分带
- 仅保留 baseline 与 crisis 同时非空的 OD（overlap edges）
- 统计：$\\phi_{agg}=\\sum n_{crisis}/\\sum n_{baseline}$

## 输出

- `tables/movement_outflow_by_band.csv`
- `tables/movement_inflow_by_band.csv`
- `tables/movement_tau_by_band.csv`（对 band-level $\\phi_{agg}(t)$ 做线性化指数拟合）
- `figures/movement_outflow_phi_timeseries.*`
- `figures/movement_inflow_phi_timeseries.*`
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_fit}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("Data/Turkiye Turkey Earthquake Full Country Version Feb 8 2023"),
        help="数据根目录（包含 movement/ 子目录）",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/movement_recovery_by_distance"), help="输出目录")
    parser.add_argument("--t0-pt", type=str, default="2023-02-05 16:00", help="t=0 的 PT 时间戳")
    parser.add_argument("--only-hour-pt", type=int, default=8, help="仅保留该小时（PT）的窗口（默认 08:00）")
    parser.add_argument("--fit-min-hours", type=float, default=0.0, help="拟合窗口下界（默认 t>=0）")
    parser.add_argument("--fit-max-hours", type=float, default=None, help="拟合窗口上界（默认不限制）")
    parser.add_argument("--max-files", type=int, default=None, help="只处理前 N 个窗口（用于冒烟测试）")
    args = parser.parse_args()

    cfg = Config(
        data_root=args.data_root,
        output_dir=args.output_dir,
        t0_pt=pd.Timestamp(str(args.t0_pt)),
        only_hour_pt=int(args.only_hour_pt),
        fit_min_hours=float(args.fit_min_hours),
        fit_max_hours=float(args.fit_max_hours) if args.fit_max_hours is not None else None,
    )
    run(cfg, max_files=args.max_files)


if __name__ == "__main__":
    cli_main()
