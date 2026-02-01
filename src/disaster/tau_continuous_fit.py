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
    only_hour_pt: int = 8  # -1 表示不过滤小时（用于冒烟测试/诊断）
    fit_min_hours: float = 0.0
    fit_max_hours: float | None = None
    min_points: int = 20
    tail_frac: float = 0.2
    phi_clip_lo: float = 0.0
    phi_clip_hi: float = 3.0
    intensity_recovery_threshold: float = 0.95
    bootstrap_samples: int = 1000
    seed: int = 7


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _linearized_tau(t: np.ndarray, y: np.ndarray, *, tail_frac: float) -> dict:
    """
    线性化指数恢复拟合（无需 scipy）：
    - 先用尾部中位数估计 y_inf
    - 再对 log((y - y_inf)/(y0 - y_inf)) ~ a + b * (t - t0) 做线性回归
    """

    out = {
        "fit_ok": 0,
        "n_points": int(len(t)),
        "tau": float("nan"),
        "y0": float("nan"),
        "y_inf": float("nan"),
        "slope": float("nan"),
        "r2": float("nan"),
    }

    mask = np.isfinite(t) & np.isfinite(y)
    t = t[mask].astype(float)
    y = y[mask].astype(float)
    if t.size < 6:
        out["n_points"] = int(t.size)
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
        out.update({"n_points": int(t.size), "y0": y0, "y_inf": y_inf})
        return out

    z = (y - y_inf) / denom
    m = np.isfinite(z) & (z > 0) & (z < 10.0)
    if np.sum(m) < 6:
        out.update({"n_points": int(t.size), "y0": y0, "y_inf": y_inf})
        return out

    x = tt[m]
    lnz = np.log(z[m])

    X = np.vstack([np.ones_like(x), x]).T
    beta, *_ = np.linalg.lstsq(X, lnz, rcond=None)
    a, b = float(beta[0]), float(beta[1])
    if not np.isfinite(b) or b >= 0:
        out.update({"n_points": int(t.size), "y0": y0, "y_inf": y_inf, "slope": b})
        return out

    y_hat = X @ beta
    resid = lnz - y_hat
    sse = float(np.sum(resid**2))
    sst = float(np.sum((lnz - float(np.mean(lnz))) ** 2))
    r2 = float(1.0 - sse / sst) if sst > 0 else float("nan")

    tau = float(-1.0 / b)
    out.update({"fit_ok": 1, "n_points": int(t.size), "tau": tau, "y0": y0, "y_inf": y_inf, "slope": b, "r2": r2})
    return out


def _fit_quadratic_loglog(r_km: np.ndarray, tau_h: np.ndarray) -> dict:
    """
    拟合：log(tau) = a + b log(r) + c log(r)^2
    返回参数与 r*（若 c>0）。
    """

    out = {
        "fit_ok": 0,
        "a": float("nan"),
        "b": float("nan"),
        "c": float("nan"),
        "r_star_km": float("nan"),
    }
    mask = np.isfinite(r_km) & np.isfinite(tau_h) & (r_km > 0) & (tau_h > 0)
    r = r_km[mask].astype(float)
    tau = tau_h[mask].astype(float)
    if r.size < 50:
        return out

    x = np.log(r)
    y = np.log(tau)
    X = np.vstack([np.ones_like(x), x, x**2]).T
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    a, b, c = (float(beta[0]), float(beta[1]), float(beta[2]))
    if np.isfinite(c) and c > 0 and np.isfinite(b):
        x_star = -b / (2.0 * c)
        r_star = float(np.exp(x_star))
    else:
        r_star = float("nan")
    out.update({"fit_ok": 1, "a": a, "b": b, "c": c, "r_star_km": r_star})
    return out


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
        if int(cfg.only_hour_pt) >= 0 and int(window_start.hour) != int(cfg.only_hour_pt):
            continue
        hs = float((window_start - cfg.t0_pt).total_seconds() / 3600.0)
        windows.append({"path": str(path), "window_start_pt": window_start, "hours_since_quake": hs})
    windows = sorted(windows, key=lambda r: float(r["hours_since_quake"]))
    if max_files is not None:
        windows = windows[: int(max_files)]
    if not windows:
        if int(cfg.only_hour_pt) >= 0:
            raise FileNotFoundError(f"未找到 hour={cfg.only_hour_pt} 的 population 文件：{pop_dir}")
        raise FileNotFoundError(f"未找到 population 文件：{pop_dir}")

    pre = [w for w in windows if float(w["hours_since_quake"]) < 0]
    post = [w for w in windows if float(w["hours_since_quake"]) >= 0]
    if not pre:
        raise SystemExit("未找到 hours_since_quake < 0 的震前窗口（请检查 t0 或数据起始日期）。")
    if not post:
        raise SystemExit("未找到震后窗口（hours_since_quake >= 0）。")

    # 1) 震前 tiles 参考（定义 tile universe）
    pre_rows: list[pd.DataFrame] = []
    for w in pre:
        df = load_population_file(Path(w["path"]))
        nb = pd.to_numeric(df["n_baseline"], errors="coerce")
        nc = pd.to_numeric(df["n_crisis"], errors="coerce")
        lat = pd.to_numeric(df["lat"], errors="coerce")
        lon = pd.to_numeric(df["lon"], errors="coerce")
        ok = nb.notna() & nc.notna() & (nb > 0)
        sub = pd.DataFrame(
            {
                "quadkey": df["quadkey"].astype("string"),
                "lat": lat,
                "lon": lon,
                "n_crisis_pre": nc,
            }
        )
        sub = sub[ok].copy()
        pre_rows.append(sub)

    pre_df = pd.concat(pre_rows, ignore_index=True)
    pre_df = pre_df.dropna(subset=["quadkey", "lat", "lon", "n_crisis_pre"]).copy()
    pre_df["distance_km"] = haversine_km(
        pre_df["lat"].to_numpy(dtype=float),
        pre_df["lon"].to_numpy(dtype=float),
        cfg.epicenter_lat,
        cfg.epicenter_lon,
    )
    tile_meta = (
        pre_df.groupby("quadkey", observed=True)
        .agg(lat=("lat", "mean"), lon=("lon", "mean"), distance_km=("distance_km", "mean"), n_crisis_pre=("n_crisis_pre", "mean"))
        .reset_index()
    )
    tile_meta = tile_meta[np.isfinite(tile_meta["distance_km"].to_numpy(dtype=float))].copy()
    tile_meta = tile_meta[tile_meta["n_crisis_pre"].to_numpy(dtype=float) > 0].copy()
    if tile_meta.empty:
        raise SystemExit("震前 overlap tiles 为空（可能是 sample 太小或字段全为 \\N）。")

    pre_crisis_by_q = dict(zip(tile_meta["quadkey"].astype(str), tile_meta["n_crisis_pre"].to_numpy(dtype=float), strict=False))
    tile_set = set(tile_meta["quadkey"].astype(str).tolist())

    # 2) 震后观测：phi_i(t)=n_crisis/n_baseline
    obs_rows: list[pd.DataFrame] = []
    for i, w in enumerate(post, start=1):
        df = load_population_file(Path(w["path"]))
        df["quadkey"] = df["quadkey"].astype("string")
        df = df[df["quadkey"].astype(str).isin(tile_set)].copy()
        if df.empty:
            continue

        nb = pd.to_numeric(df["n_baseline"], errors="coerce")
        nc = pd.to_numeric(df["n_crisis"], errors="coerce")
        ok = nb.notna() & nc.notna() & (nb > 0)
        phi = (nc.to_numpy(dtype=float) / nb.to_numpy(dtype=float)).astype(float)
        phi = np.where(np.isfinite(phi) & (phi >= float(cfg.phi_clip_lo)) & (phi <= float(cfg.phi_clip_hi)), phi, np.nan)
        sub = pd.DataFrame(
            {
                "quadkey": df["quadkey"].astype("string"),
                "hours_since_quake": float(w["hours_since_quake"]),
                "phi_ratio": phi,
                "n_crisis": nc,
                "n_baseline": nb,
            }
        )
        sub = sub[ok & np.isfinite(sub["phi_ratio"].to_numpy(dtype=float))].copy()
        if not sub.empty:
            obs_rows.append(sub)

        if i % 20 == 0:
            print(f"[tau_continuous_fit] processed {i}/{len(post)} post windows...")

    if not obs_rows:
        raise SystemExit("震后可用观测为空（可能是过滤过严或数据全部为 \\N）。")

    obs = pd.concat(obs_rows, ignore_index=True)
    obs["hours_since_quake"] = pd.to_numeric(obs["hours_since_quake"], errors="coerce")
    obs = obs[obs["hours_since_quake"].notna()].copy()

    # 拟合窗口裁剪
    t = obs["hours_since_quake"].to_numpy(dtype=float)
    m_fit = t >= float(cfg.fit_min_hours)
    if cfg.fit_max_hours is not None:
        m_fit &= t <= float(cfg.fit_max_hours)
    obs = obs[m_fit].copy()
    if obs.empty:
        raise SystemExit("拟合窗口内没有观测点（检查 fit_min/max_hours）。")

    # 3) tile-level τ_i + “可见性/强度”恢复时间
    rows: list[dict] = []
    for quadkey, sub in obs.groupby("quadkey", sort=False, observed=True):
        tt = pd.to_numeric(sub["hours_since_quake"], errors="coerce").to_numpy(dtype=float)
        yy = pd.to_numeric(sub["phi_ratio"], errors="coerce").to_numpy(dtype=float)
        mask = np.isfinite(tt) & np.isfinite(yy)
        tt = tt[mask]
        yy = yy[mask]
        if tt.size < int(cfg.min_points):
            continue

        fit = _linearized_tau(tt, yy, tail_frac=float(cfg.tail_frac))
        if int(fit["fit_ok"]) != 1:
            continue

        # recovery proxies (tile-level)
        t_first_overlap = float(np.nanmin(tt)) if tt.size else float("nan")

        # intensity: n_crisis / n_crisis_pre
        nc = pd.to_numeric(sub["n_crisis"], errors="coerce").to_numpy(dtype=float)[mask]
        pre_nc = float(pre_crisis_by_q.get(str(quadkey), float("nan")))
        if not np.isfinite(pre_nc) or pre_nc <= 0:
            continue
        ratio = np.where(np.isfinite(nc) & (pre_nc > 0), nc / pre_nc, np.nan)
        ok_thr = np.isfinite(ratio) & (ratio >= float(cfg.intensity_recovery_threshold))
        t_intensity_geq_thr = float(np.nanmin(tt[ok_thr])) if np.any(ok_thr) else float("nan")

        rows.append(
            {
                "quadkey": str(quadkey),
                "n_points": int(fit["n_points"]),
                "tau_hours": float(fit["tau"]),
                "tau_r2": float(fit["r2"]),
                "phi0": float(fit["y0"]),
                "phi_inf": float(fit["y_inf"]),
                "t_first_overlap_hours": float(t_first_overlap),
                "t_intensity_geq_thr_hours": float(t_intensity_geq_thr),
                "intensity_thr": float(cfg.intensity_recovery_threshold),
            }
        )

    if not rows:
        raise SystemExit("tile-level τ 拟合结果为空（可能是 min_points 过高或 sample 时间跨度过短）。")

    tile_tau = pd.DataFrame(rows)
    tile_tau = tile_tau.merge(tile_meta, on="quadkey", how="left")
    tile_tau["distance_km"] = pd.to_numeric(tile_tau["distance_km"], errors="coerce")
    tile_tau["tau_hours"] = pd.to_numeric(tile_tau["tau_hours"], errors="coerce")
    tile_tau = tile_tau[np.isfinite(tile_tau["distance_km"]) & np.isfinite(tile_tau["tau_hours"])].copy()

    out_tiles = out.tables / "tile_level_tau.csv"
    tile_tau.sort_values(["distance_km", "tau_hours"], kind="stable").to_csv(out_tiles, index=False)

    # 4) 连续 τ(r) 拟合 + bootstrap CI
    r = tile_tau["distance_km"].to_numpy(dtype=float)
    tau = tile_tau["tau_hours"].to_numpy(dtype=float)
    fit = _fit_quadratic_loglog(r, tau)

    fit_row = {
        "model": "logtau = a + b*logr + c*logr^2",
        "n_tiles": int(len(tile_tau)),
        **fit,
    }
    out_fit = out.tables / "tau_r_fit_quadratic.csv"
    pd.DataFrame([fit_row]).to_csv(out_fit, index=False)

    rng = np.random.default_rng(int(cfg.seed))
    bs = int(cfg.bootstrap_samples)
    idx = np.arange(len(tile_tau), dtype=int)

    # r grid (log spaced)
    r_min = float(np.nanpercentile(r, 1)) if np.isfinite(r).any() else 1.0
    r_max = float(np.nanpercentile(r, 99)) if np.isfinite(r).any() else 1000.0
    r_min = max(1e-3, r_min)
    if r_max <= r_min:
        r_max = r_min * 10.0
    r_grid = np.exp(np.linspace(np.log(r_min), np.log(r_max), 80))

    def _predict(a: float, b: float, c: float, rvals: np.ndarray) -> np.ndarray:
        x = np.log(rvals)
        y = a + b * x + c * x**2
        return np.exp(y)

    r_star_samples: list[float] = []
    curve_samples: list[np.ndarray] = []
    for _ in range(bs):
        s = rng.choice(idx, size=idx.size, replace=True)
        f = _fit_quadratic_loglog(r[s], tau[s])
        if int(f["fit_ok"]) != 1:
            continue
        a, b, c = float(f["a"]), float(f["b"]), float(f["c"])
        r_star_samples.append(float(f["r_star_km"]))
        curve_samples.append(_predict(a, b, c, r_grid))

    r_star_arr = np.array(r_star_samples, dtype=float)
    out_rstar = out.tables / "tau_r_star_bootstrap.csv"
    pd.DataFrame({"r_star_km": r_star_arr}).to_csv(out_rstar, index=False)

    curve = np.array(curve_samples, dtype=float) if curve_samples else np.empty((0, r_grid.size), dtype=float)
    if curve.size:
        lo = np.nanpercentile(curve, 2.5, axis=0)
        mid = np.nanpercentile(curve, 50, axis=0)
        hi = np.nanpercentile(curve, 97.5, axis=0)
        out_curve = out.tables / "tau_r_curve_ci.csv"
        pd.DataFrame({"r_km": r_grid, "tau_p50": mid, "tau_p025": lo, "tau_p975": hi}).to_csv(out_curve, index=False)
    else:
        out_curve = None

    # 把 bootstrap 的 r* 置信区间写回 fit 表，便于直接引用
    r_star_valid = r_star_arr[np.isfinite(r_star_arr) & (r_star_arr > 0)]
    if r_star_valid.size:
        fit_row.update(
            {
                "r_star_boot_p025_km": float(np.nanpercentile(r_star_valid, 2.5)),
                "r_star_boot_p50_km": float(np.nanpercentile(r_star_valid, 50)),
                "r_star_boot_p975_km": float(np.nanpercentile(r_star_valid, 97.5)),
                "n_boot_valid": int(r_star_valid.size),
            }
        )
        pd.DataFrame([fit_row]).to_csv(out_fit, index=False)

    # figures
    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        ax.scatter(r, tau, s=8, alpha=0.22, color=ps.OKABE_ITO["sky_blue"], linewidths=0, rasterized=True, label="tiles")
        if int(fit.get("fit_ok", 0)) == 1:
            y_fit = _predict(float(fit["a"]), float(fit["b"]), float(fit["c"]), r_grid)
            ax.plot(r_grid, y_fit, color=ps.OKABE_ITO["vermillion"], linewidth=2.2, label="quadratic fit")
        if out_curve is not None:
            ax.fill_between(r_grid, lo, hi, color=ps.OKABE_ITO["vermillion"], alpha=0.18, linewidth=0, label="bootstrap 95% CI")

        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Distance to epicenter r (km)")
        ax.set_ylabel(r"$\tau_i$ (hours, tile-level)")
        ax.set_title(r"Continuous $\tau(r)$ from tile-level exponential fits (08:00 windows)")
        ax.legend(frameon=False, ncol=2)
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "tau_vs_distance_continuous.png")
        plt.close(fig)

        # r* distribution
        if r_star_arr.size:
            fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
            ax.hist(r_star_arr[np.isfinite(r_star_arr) & (r_star_arr > 0)], bins=40, color=ps.OKABE_ITO["blue"], alpha=0.85)
            ax.set_xscale("log")
            ax.set_xlabel(r"$r^*$ (km)")
            ax.set_ylabel("Bootstrap count")
            ax.set_title(r"Bootstrap distribution of $r^*$ (argmin of fitted $\tau(r)$)")
            ps.despine(ax)
            fig.tight_layout()
            save_png_and_pdf(ps, fig, out.figures / "r_star_bootstrap_hist.png")
            plt.close(fig)

    readme = f"""# Continuous $\\tau(r)$ (tile-level)

目的：回应“距离带划分是否人为导致结论”的审稿风险。
做法：对每个 tile 拟合 $\\phi_i(t)=n_{{crisis}}/n_{{baseline}}$ 的指数恢复时间常数 $\\tau_i$，再在连续距离上拟合 $\\tau(r)$ 并给出 bootstrap 置信带与 $r^*$。

## 输入

- `{cfg.data_root}/population/*.csv`

## 关键口径

- 仅使用 PT {int(cfg.only_hour_pt):02d}:00 窗口（若 only_hour_pt=-1 则不过滤小时）
- tile universe：震前窗口（hours_since_quake<0）中 baseline 与 crisis 同时非空的 tiles
- $\\phi_i(t)=n_{{crisis}}/n_{{baseline}}$，并裁剪到 [{float(cfg.phi_clip_lo)}, {float(cfg.phi_clip_hi)}]
- 单 tile 指数拟合：线性化方法（尾部中位数估计 $\\phi_\\infty$）
- 连续拟合：$\\log \\tau = a + b\\log r + c(\\log r)^2$
- bootstrap：{int(cfg.bootstrap_samples)} 次（seed={int(cfg.seed)}）

## 产物

- `tables/tile_level_tau.csv`：每个 tile 的 $\\tau_i$ 与距离
- `tables/tau_r_fit_quadratic.csv`：连续 $\\tau(r)$ 拟合参数与 $r^*$
- `tables/tau_r_star_bootstrap.csv`：$r^*$ bootstrap 样本
- `tables/tau_r_curve_ci.csv`：$\\tau(r)$ 曲线的 bootstrap 置信带（若 bootstrap 成功）
- `figures/tau_vs_distance_continuous.*`
- `figures/r_star_bootstrap_hist.*`
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_tiles}")
    print(f"Done. Wrote: {out_fit}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("Data/Turkiye Turkey Earthquake Full Country Version Feb 8 2023"),
        help="数据根目录（包含 population/ 子目录）",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/tau_continuous_fit"), help="输出目录")
    parser.add_argument("--center-lat", type=float, default=None, help="灾难中心/震中纬度（默认使用脚本内置值）")
    parser.add_argument("--center-lon", type=float, default=None, help="灾难中心/震中经度（默认使用脚本内置值）")
    parser.add_argument("--t0-pt", type=str, default="2023-02-05 16:00", help="t=0 的 PT 时间戳")
    parser.add_argument("--only-hour-pt", type=int, default=8, help="仅保留该小时（PT）的窗口；-1 表示不过滤（默认 08:00）")
    parser.add_argument("--fit-min-hours", type=float, default=0.0, help="拟合窗口下界（默认 t>=0）")
    parser.add_argument("--fit-max-hours", type=float, default=None, help="拟合窗口上界（默认不限制）")
    parser.add_argument("--min-points", type=int, default=20, help="单 tile 拟合最少点数")
    parser.add_argument("--tail-frac", type=float, default=0.2, help="尾部比例（估计 phi_inf 用）")
    parser.add_argument("--phi-clip-lo", type=float, default=0.0, help="phi 裁剪下界")
    parser.add_argument("--phi-clip-hi", type=float, default=3.0, help="phi 裁剪上界")
    parser.add_argument("--intensity-recovery-threshold", type=float, default=0.95, help="强度恢复阈值：n_crisis/post / n_crisis_pre")
    parser.add_argument("--bootstrap-samples", type=int, default=1000, help="bootstrap 次数（r* 与 τ(r) CI）")
    parser.add_argument("--seed", type=int, default=7, help="随机种子")
    parser.add_argument("--max-files", type=int, default=None, help="只处理前 N 个窗口（用于冒烟测试）")
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
        fit_min_hours=float(args.fit_min_hours),
        fit_max_hours=float(args.fit_max_hours) if args.fit_max_hours is not None else None,
        min_points=int(args.min_points),
        tail_frac=float(args.tail_frac),
        phi_clip_lo=float(args.phi_clip_lo),
        phi_clip_hi=float(args.phi_clip_hi),
        intensity_recovery_threshold=float(args.intensity_recovery_threshold),
        bootstrap_samples=int(args.bootstrap_samples),
        seed=int(args.seed),
    )
    run(cfg, max_files=args.max_files)


if __name__ == "__main__":
    cli_main()
