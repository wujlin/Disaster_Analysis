from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`。") from e

try:
    from scipy.stats import spearmanr
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：scipy。请先运行 `pip install -r requirements.txt`。") from e

from disaster.cross_disaster_phi_tau import load_catalog
from disaster.geo import haversine_km
from disaster.population_io import load_population_file, parse_window_start_pt, resolve_subdir


@dataclass(frozen=True)
class GeoUnitConfig:
    catalog: Path
    output_root: Path
    dt_flags_csv: Path
    out_dir: Path
    use_route_b_selected: int = 1
    selected_slugs: tuple[str, ...] = ()
    exclude_slugs: tuple[str, ...] = ()
    require_all_events: int = 1
    quadkey_level: int = 10
    min_hours: float = -16.0
    max_hours: float = 832.0
    min_tiles_per_unit: int = 5
    min_time_windows: int = 6
    peak_min_hours: float = 0.0
    peak_max_hours: float = 168.0
    fit_min_tprime_hours: float = 24.0
    min_mono_points: int = 3
    mono_tol_up: float = 1.05
    min_fit_r2: float = 0.0


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _safe_ts(x: object) -> pd.Timestamp | None:
    if x is None:
        return None
    s = str(x).strip()
    if not s or s.lower() == "nan":
        return None
    ts = pd.to_datetime(s, errors="coerce")
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts)


def _safe_float(x: object) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except Exception:
        return None


def _parse_list_arg(raw: str) -> tuple[str, ...]:
    s = str(raw or "").strip()
    if not s:
        return ()
    return tuple(x.strip() for x in s.split(",") if x.strip())


def _load_selected_slugs(flags_csv: Path, use_route_b_selected: int) -> list[str]:
    if not flags_csv.exists():
        raise FileNotFoundError(f"未找到 Dt flags：{flags_csv}")
    df = pd.read_csv(flags_csv)
    if "slug" not in df.columns:
        raise ValueError(f"{flags_csv} 缺少 slug 列")
    if int(use_route_b_selected) == 1:
        if "route_b_selected" not in df.columns:
            raise ValueError(f"{flags_csv} 缺少 route_b_selected 列")
        df = df[df["route_b_selected"].astype(bool)].copy()
    slugs = sorted(df["slug"].astype(str).str.strip().tolist())
    if not slugs:
        raise ValueError("筛选后无事件（请检查 Dt_routeB_sample_flags.csv）")
    return slugs


def _load_event_runtime(output_root: Path, slug: str) -> dict:
    meta_p = output_root / slug / "metadata.json"
    if not meta_p.exists():
        raise FileNotFoundError(f"缺少事件 metadata：{meta_p}")
    meta = json.loads(meta_p.read_text(encoding="utf-8"))

    t0 = _safe_ts(meta.get("t0_pt"))
    lat = _safe_float(meta.get("center_lat"))
    lon = _safe_float(meta.get("center_lon"))
    hour = int(meta.get("only_hour_pt", 8))
    if t0 is None:
        raise ValueError(f"{slug}: metadata 缺少有效 t0_pt")
    if lat is None or lon is None:
        raise ValueError(f"{slug}: metadata 缺少有效 center_lat/center_lon")
    return {
        "t0_pt": t0,
        "center_lat": float(lat),
        "center_lon": float(lon),
        "only_hour_pt": int(hour),
    }


def _list_population_windows(data_root: Path, only_hour_pt: int) -> list[tuple[pd.Timestamp, Path]]:
    pop_dir = resolve_subdir(data_root, "population")
    files = sorted(pop_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"population 目录为空：{pop_dir}")
    rows: list[tuple[pd.Timestamp, Path]] = []
    for p in files:
        ts = parse_window_start_pt(p)
        if int(ts.hour) != int(only_hour_pt):
            continue
        rows.append((pd.Timestamp(ts), p))
    rows.sort(key=lambda x: x[0])
    if not rows:
        raise FileNotFoundError(f"未找到 hour={only_hour_pt} 的 population 文件：{pop_dir}")
    return rows


def _aggregate_geo_units(
    path: Path,
    *,
    slug: str,
    window_pt: pd.Timestamp,
    hours_since_t0: float,
    quadkey_level: int,
    min_tiles_per_unit: int,
    center_lat: float,
    center_lon: float,
) -> pd.DataFrame:
    df = load_population_file(path)
    need = {"quadkey", "lat", "lon", "n_baseline", "n_crisis"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise ValueError(f"{slug}: {path.name} 缺少列 {miss}")

    qk = df["quadkey"].astype("string")
    nb = pd.to_numeric(df["n_baseline"], errors="coerce")
    nc = pd.to_numeric(df["n_crisis"], errors="coerce")
    la = pd.to_numeric(df["lat"], errors="coerce")
    lo = pd.to_numeric(df["lon"], errors="coerce")

    mask = qk.notna() & (qk.astype(str).str.len() >= int(quadkey_level)) & np.isfinite(nb) & np.isfinite(nc) & np.isfinite(la) & np.isfinite(lo) & (nb > 0)
    sub = pd.DataFrame(
        {
            "geo_unit": qk.astype(str).str.slice(0, int(quadkey_level)),
            "lat": la,
            "lon": lo,
            "n_baseline": nb,
            "n_crisis": nc,
            "quadkey": qk.astype(str),
        }
    )
    sub = sub[mask].copy()
    if sub.empty:
        return pd.DataFrame(
            columns=[
                "slug",
                "geo_unit",
                "window_start_pt",
                "hours_since_t0",
                "lat",
                "lon",
                "distance_km",
                "n_tiles",
                "n_baseline_sum",
                "n_crisis_sum",
                "phi",
                "delta",
                "D",
            ]
        )

    g = (
        sub.groupby("geo_unit", sort=False, observed=True)
        .agg(
            lat=("lat", "mean"),
            lon=("lon", "mean"),
            n_tiles=("quadkey", "nunique"),
            n_baseline_sum=("n_baseline", "sum"),
            n_crisis_sum=("n_crisis", "sum"),
        )
        .reset_index()
    )
    g = g[g["n_tiles"] >= int(min_tiles_per_unit)].copy()
    if g.empty:
        return g

    g["phi"] = pd.to_numeric(g["n_crisis_sum"], errors="coerce") / pd.to_numeric(g["n_baseline_sum"], errors="coerce")
    g["delta"] = g["phi"] - 1.0
    g["D"] = np.abs(g["delta"])
    g["distance_km"] = haversine_km(
        pd.to_numeric(g["lat"], errors="coerce").to_numpy(dtype=float),
        pd.to_numeric(g["lon"], errors="coerce").to_numpy(dtype=float),
        float(center_lat),
        float(center_lon),
    )
    g["slug"] = str(slug)
    g["window_start_pt"] = str(pd.Timestamp(window_pt))
    g["hours_since_t0"] = float(hours_since_t0)
    return g[
        [
            "slug",
            "geo_unit",
            "window_start_pt",
            "hours_since_t0",
            "lat",
            "lon",
            "distance_km",
            "n_tiles",
            "n_baseline_sum",
            "n_crisis_sum",
            "phi",
            "delta",
            "D",
        ]
    ].copy()


def _fit_powerlaw_loglog(t: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    ok = np.isfinite(t) & np.isfinite(y) & (t > 0) & (y > 0)
    tt = np.asarray(t[ok], dtype=float)
    yy = np.asarray(y[ok], dtype=float)
    if tt.size < 3:
        return float("nan"), float("nan"), float("nan")
    x = np.log(tt)
    ly = np.log(yy)
    slope, intercept = np.polyfit(x, ly, deg=1)
    pred = slope * x + intercept
    ss_res = float(np.sum((ly - pred) ** 2))
    ss_tot = float(np.sum((ly - float(np.mean(ly))) ** 2))
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")
    return float(-slope), float(intercept), float(r2)


def _monotone_segment(post: pd.DataFrame, tol_up: float) -> pd.DataFrame:
    if post.empty:
        return post.copy()
    post = post.sort_values("t_prime_h", kind="stable").reset_index(drop=True)
    keep = [0]
    for i in range(post.shape[0] - 1):
        d0 = float(post.loc[i, "D_norm"])
        d1 = float(post.loc[i + 1, "D_norm"])
        if not (np.isfinite(d0) and np.isfinite(d1)):
            break
        if d1 <= d0 * float(tol_up):
            keep.append(i + 1)
            continue
        break
    return post.loc[keep].copy().reset_index(drop=True)


def _safe_spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, float, int]:
    xx = np.asarray(x, dtype=float)
    yy = np.asarray(y, dtype=float)
    ok = np.isfinite(xx) & np.isfinite(yy)
    xx = xx[ok]
    yy = yy[ok]
    if xx.size < 4:
        return float("nan"), float("nan"), int(xx.size)
    rho, p = spearmanr(xx, yy)
    return float(rho), float(p), int(xx.size)


def run(cfg: GeoUnitConfig) -> None:
    out = Path(cfg.out_dir)
    tabs = out / "tables"
    _ensure_dir(tabs)

    specs = {s.slug: s for s in load_catalog(Path(cfg.catalog))}
    base_slugs = _load_selected_slugs(Path(cfg.dt_flags_csv), int(cfg.use_route_b_selected))
    if cfg.selected_slugs:
        selected = [s for s in base_slugs if s in set(cfg.selected_slugs)]
    else:
        selected = list(base_slugs)
    if cfg.exclude_slugs:
        ex = set(cfg.exclude_slugs)
        selected = [s for s in selected if s not in ex]
    if not selected:
        raise ValueError("最终无可分析事件（selected/exclude 过滤后为空）")

    all_rows: list[pd.DataFrame] = []
    diag_rows: list[dict] = []
    failed: list[str] = []

    for slug in selected:
        try:
            if slug not in specs:
                raise ValueError(f"{slug}: catalog 中不存在")
            spec = specs[slug]
            runtime = _load_event_runtime(Path(cfg.output_root), slug)
            windows = _list_population_windows(Path(spec.data_root), int(runtime["only_hour_pt"]))

            unit_frames: list[pd.DataFrame] = []
            for ts, p in windows:
                hs = float((pd.Timestamp(ts) - runtime["t0_pt"]).total_seconds() / 3600.0)
                if hs < float(cfg.min_hours) or hs > float(cfg.max_hours):
                    continue
                gg = _aggregate_geo_units(
                    p,
                    slug=slug,
                    window_pt=ts,
                    hours_since_t0=hs,
                    quadkey_level=int(cfg.quadkey_level),
                    min_tiles_per_unit=int(cfg.min_tiles_per_unit),
                    center_lat=float(runtime["center_lat"]),
                    center_lon=float(runtime["center_lon"]),
                )
                if not gg.empty:
                    unit_frames.append(gg)

            if not unit_frames:
                raise ValueError(f"{slug}: 未得到任何 geo_unit 时序（检查时间窗口与 min_tiles_per_unit）")

            event_long = pd.concat(unit_frames, ignore_index=True)
            event_long["event_type"] = str(spec.event_type)
            event_long["name"] = str(spec.name)
            all_rows.append(event_long)
            diag_rows.append(
                {
                    "slug": slug,
                    "status": "ok",
                    "n_rows": int(event_long.shape[0]),
                    "n_geo_units": int(event_long["geo_unit"].nunique()),
                    "n_windows": int(event_long["hours_since_t0"].nunique()),
                    "message": "ok",
                }
            )
        except Exception as e:
            failed.append(slug)
            diag_rows.append(
                {
                    "slug": slug,
                    "status": "failed",
                    "n_rows": 0,
                    "n_geo_units": 0,
                    "n_windows": 0,
                    "message": f"{type(e).__name__}:{e}",
                }
            )

    diag_df = pd.DataFrame(diag_rows).sort_values(["status", "slug"], kind="stable").reset_index(drop=True)
    diag_df.to_csv(tabs / "event_processing_diagnostics.csv", index=False)

    if int(cfg.require_all_events) == 1 and failed:
        raise ValueError(f"事件处理失败（strict 模式）：{sorted(failed)}。详见 {tabs/'event_processing_diagnostics.csv'}")

    if not all_rows:
        raise ValueError("没有可用事件通过预处理")

    long_df = pd.concat(all_rows, ignore_index=True)
    long_df = long_df.sort_values(["slug", "geo_unit", "hours_since_t0"], kind="stable").reset_index(drop=True)
    long_df.to_csv(tabs / "geo_unit_timeseries.csv", index=False)

    fit_rows: list[dict] = []
    fit_diag_rows: list[dict] = []
    for (slug, geo_unit), g in long_df.groupby(["slug", "geo_unit"], sort=False, observed=True):
        g = g.sort_values("hours_since_t0", kind="stable").copy()
        h = pd.to_numeric(g["hours_since_t0"], errors="coerce").to_numpy(dtype=float)
        D = pd.to_numeric(g["D"], errors="coerce").to_numpy(dtype=float)
        delta = pd.to_numeric(g["delta"], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(h) & np.isfinite(D) & np.isfinite(delta)
        h, D, delta = h[ok], D[ok], delta[ok]
        if h.size < int(cfg.min_time_windows):
            fit_diag_rows.append({"slug": slug, "geo_unit": geo_unit, "reason": "short_series", "n_time_windows": int(h.size)})
            continue

        peak_mask = (h >= float(cfg.peak_min_hours)) & (h <= float(cfg.peak_max_hours))
        if not np.any(peak_mask):
            fit_diag_rows.append({"slug": slug, "geo_unit": geo_unit, "reason": "no_peak_window", "n_time_windows": int(h.size)})
            continue
        p_idx_local = int(np.argmax(D[peak_mask]))
        peak_candidates = np.where(peak_mask)[0]
        p_idx = int(peak_candidates[p_idx_local])
        t_peak = float(h[p_idx])
        D_peak = float(D[p_idx])
        delta_peak = float(delta[p_idx])
        if not np.isfinite(D_peak) or D_peak <= 0:
            fit_diag_rows.append({"slug": slug, "geo_unit": geo_unit, "reason": "bad_peak", "n_time_windows": int(h.size)})
            continue

        post_mask = h > t_peak
        if not np.any(post_mask):
            fit_diag_rows.append({"slug": slug, "geo_unit": geo_unit, "reason": "no_post_peak", "n_time_windows": int(h.size)})
            continue

        hp = h[post_mask]
        Dp = D[post_mask]
        t_prime = hp - t_peak
        keep = t_prime >= float(cfg.fit_min_tprime_hours)
        hp = hp[keep]
        Dp = Dp[keep]
        t_prime = t_prime[keep]
        if t_prime.size < int(cfg.min_mono_points):
            fit_diag_rows.append({"slug": slug, "geo_unit": geo_unit, "reason": "short_post_peak", "n_time_windows": int(h.size)})
            continue

        post_df = pd.DataFrame({"hours_since_t0": hp, "t_prime_h": t_prime, "D_norm": Dp / D_peak})
        mono = _monotone_segment(post_df, tol_up=float(cfg.mono_tol_up))
        if mono.shape[0] < int(cfg.min_mono_points):
            fit_diag_rows.append({"slug": slug, "geo_unit": geo_unit, "reason": "short_mono", "n_time_windows": int(h.size)})
            continue

        alpha, logA, r2 = _fit_powerlaw_loglog(
            mono["t_prime_h"].to_numpy(dtype=float),
            mono["D_norm"].to_numpy(dtype=float),
        )
        if not np.isfinite(alpha):
            fit_diag_rows.append({"slug": slug, "geo_unit": geo_unit, "reason": "fit_fail", "n_time_windows": int(h.size)})
            continue
        if np.isfinite(float(cfg.min_fit_r2)) and np.isfinite(r2) and r2 < float(cfg.min_fit_r2):
            fit_diag_rows.append({"slug": slug, "geo_unit": geo_unit, "reason": "low_r2", "n_time_windows": int(h.size)})
            continue

        fit_rows.append(
            {
                "slug": slug,
                "geo_unit": geo_unit,
                "alpha_unit": float(alpha),
                "logA_unit": float(logA),
                "r2_unit": float(r2),
                "n_mono": int(mono.shape[0]),
                "t_peak_h": float(t_peak),
                "D_peak_unit": float(D_peak),
                "delta_peak_unit": float(delta_peak),
                "distance_km": float(pd.to_numeric(g["distance_km"], errors="coerce").mean()),
                "n_tiles_median": float(pd.to_numeric(g["n_tiles"], errors="coerce").median()),
                "n_windows_total": int(h.size),
            }
        )

    fit_df = pd.DataFrame(fit_rows)
    fit_diag_df = pd.DataFrame(fit_diag_rows)
    if fit_diag_df.empty:
        fit_diag_df = pd.DataFrame(columns=["slug", "geo_unit", "reason", "n_time_windows"])
    fit_diag_df.to_csv(tabs / "geo_unit_fit_diagnostics.csv", index=False)

    if fit_df.empty:
        raise ValueError("geo-unit 拟合结果为空（请检查参数阈值）")
    fit_df = fit_df.sort_values(["slug", "geo_unit"], kind="stable").reset_index(drop=True)
    fit_df.to_csv(tabs / "geo_unit_fits.csv", index=False)

    event_corr_rows: list[dict] = []
    for slug, sub in fit_df.groupby("slug", sort=False):
        x_alpha = sub["alpha_unit"].to_numpy(dtype=float)
        rho_delta, p_delta, n_delta = _safe_spearman(x_alpha, sub["delta_peak_unit"].to_numpy(dtype=float))
        rho_dpeak, p_dpeak, n_dpeak = _safe_spearman(x_alpha, sub["D_peak_unit"].to_numpy(dtype=float))
        rho_dist, p_dist, n_dist = _safe_spearman(x_alpha, sub["distance_km"].to_numpy(dtype=float))
        event_corr_rows.append(
            {
                "slug": slug,
                "n_units_fit": int(sub.shape[0]),
                "rho_alpha_vs_delta_peak_unit": float(rho_delta),
                "p_alpha_vs_delta_peak_unit": float(p_delta),
                "n_alpha_vs_delta_peak_unit": int(n_delta),
                "rho_alpha_vs_D_peak_unit": float(rho_dpeak),
                "p_alpha_vs_D_peak_unit": float(p_dpeak),
                "n_alpha_vs_D_peak_unit": int(n_dpeak),
                "rho_alpha_vs_distance_km": float(rho_dist),
                "p_alpha_vs_distance_km": float(p_dist),
                "n_alpha_vs_distance_km": int(n_dist),
            }
        )
    event_corr_df = pd.DataFrame(event_corr_rows).sort_values("slug", kind="stable").reset_index(drop=True)
    event_corr_df.to_csv(tabs / "event_unit_correlations.csv", index=False)

    # pooled correlations
    pooled_rows: list[dict] = []
    rho, p, n = _safe_spearman(fit_df["alpha_unit"].to_numpy(dtype=float), fit_df["delta_peak_unit"].to_numpy(dtype=float))
    pooled_rows.append({"scope": "pooled_raw", "pair": "alpha_vs_delta_peak_unit", "rho": float(rho), "p": float(p), "n": int(n)})
    rho, p, n = _safe_spearman(fit_df["alpha_unit"].to_numpy(dtype=float), fit_df["D_peak_unit"].to_numpy(dtype=float))
    pooled_rows.append({"scope": "pooled_raw", "pair": "alpha_vs_D_peak_unit", "rho": float(rho), "p": float(p), "n": int(n)})
    rho, p, n = _safe_spearman(fit_df["alpha_unit"].to_numpy(dtype=float), fit_df["distance_km"].to_numpy(dtype=float))
    pooled_rows.append({"scope": "pooled_raw", "pair": "alpha_vs_distance_km", "rho": float(rho), "p": float(p), "n": int(n)})

    dm = fit_df.copy()
    for col in ["alpha_unit", "delta_peak_unit", "D_peak_unit", "distance_km"]:
        dm[f"{col}_demean"] = pd.to_numeric(dm[col], errors="coerce") - pd.to_numeric(dm.groupby("slug")[col].transform("mean"), errors="coerce")

    rho, p, n = _safe_spearman(dm["alpha_unit_demean"].to_numpy(dtype=float), dm["delta_peak_unit_demean"].to_numpy(dtype=float))
    pooled_rows.append({"scope": "within_event_demean", "pair": "alpha_vs_delta_peak_unit", "rho": float(rho), "p": float(p), "n": int(n)})
    rho, p, n = _safe_spearman(dm["alpha_unit_demean"].to_numpy(dtype=float), dm["D_peak_unit_demean"].to_numpy(dtype=float))
    pooled_rows.append({"scope": "within_event_demean", "pair": "alpha_vs_D_peak_unit", "rho": float(rho), "p": float(p), "n": int(n)})
    rho, p, n = _safe_spearman(dm["alpha_unit_demean"].to_numpy(dtype=float), dm["distance_km_demean"].to_numpy(dtype=float))
    pooled_rows.append({"scope": "within_event_demean", "pair": "alpha_vs_distance_km", "rho": float(rho), "p": float(p), "n": int(n)})

    pooled_df = pd.DataFrame(pooled_rows)
    pooled_df.to_csv(tabs / "pooled_unit_correlations.csv", index=False)

    avail_rows: list[dict] = []
    fit_count = fit_df.groupby("slug", observed=True).size().to_dict()
    for slug in selected:
        row = diag_df[diag_df["slug"] == slug]
        status = str(row.iloc[0]["status"]) if not row.empty else "missing"
        avail_rows.append(
            {
                "slug": slug,
                "preprocess_status": status,
                "n_units_fit": int(fit_count.get(slug, 0)),
                "selected": True,
            }
        )
    avail_df = pd.DataFrame(avail_rows)
    avail_df.to_csv(tabs / "analysis_availability.csv", index=False)

    missing_fit = sorted(avail_df.loc[avail_df["n_units_fit"] <= 0, "slug"].astype(str).tolist())
    if int(cfg.require_all_events) == 1 and missing_fit:
        raise ValueError(f"存在事件无可用 geo-unit 拟合结果：{missing_fit}。详见 {tabs/'analysis_availability.csv'}")

    meta = {
        "catalog": str(cfg.catalog),
        "output_root": str(cfg.output_root),
        "dt_flags_csv": str(cfg.dt_flags_csv),
        "n_selected_events": int(len(selected)),
        "n_preprocess_ok_events": int((diag_df["status"] == "ok").sum()) if not diag_df.empty else 0,
        "n_fit_events": int((avail_df["n_units_fit"] > 0).sum()) if not avail_df.empty else 0,
        "quadkey_level": int(cfg.quadkey_level),
        "min_tiles_per_unit": int(cfg.min_tiles_per_unit),
        "min_hours": float(cfg.min_hours),
        "max_hours": float(cfg.max_hours),
        "fit_min_tprime_hours": float(cfg.fit_min_tprime_hours),
        "min_mono_points": int(cfg.min_mono_points),
        "mono_tol_up": float(cfg.mono_tol_up),
    }
    (out / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# Geo-unit Scale Analysis (Quadkey L{cfg.quadkey_level})

本实验在 Route B 事件集合上，将 L14 tile 通过 `quadkey[:{cfg.quadkey_level}]` 聚合为子区域（geo-unit），在子区域尺度复现恢复动力学分析。

## 口径（与主分析一致）
- 指标：`phi = sum(n_crisis) / sum(n_baseline)`，`D = |phi - 1|`
- 峰后拟合：`t' >= {cfg.fit_min_tprime_hours}h`，单调段（首次反弹截断，`tol_up={cfg.mono_tol_up}`），log-log 斜率 `alpha_unit`
- 严格模式：`require_all_events={cfg.require_all_events}`（有缺失即报错）

## 关键输出
- `tables/geo_unit_timeseries.csv`：子区域时间序列
- `tables/geo_unit_fits.csv`：子区域拟合参数（alpha/D_peak/delta_peak/distance）
- `tables/event_unit_correlations.csv`：事件内相关
- `tables/pooled_unit_correlations.csv`：跨事件汇总相关（含去均值版本）
- `tables/event_processing_diagnostics.csv`：预处理诊断
- `tables/geo_unit_fit_diagnostics.csv`：拟合失败原因
- `tables/analysis_availability.csv`：事件可用性
"""
    (out / "README.md").write_text(readme, encoding="utf-8")


def cli_main() -> None:
    p = argparse.ArgumentParser(description="Quadkey 子区域尺度恢复动力学分析（Route B 口径）")
    p.add_argument("--catalog", type=Path, required=True, help="跨灾害 catalog（建议使用 WSA remap 后版本）")
    p.add_argument("--output-root", type=Path, default=Path("outputs"), help="事件输出根目录（读取 outputs/<slug>/metadata.json）")
    p.add_argument(
        "--dt-flags-csv",
        type=Path,
        default=Path("outputs/cross_disaster_comparison/Dt_decay/tables/Dt_routeB_sample_flags.csv"),
        help="Route B 样本标记表",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("outputs/cross_disaster_comparison/geo_unit_scale"),
        help="输出目录",
    )
    p.add_argument("--use-route-b-selected", type=int, default=1, choices=[0, 1])
    p.add_argument("--selected-slugs", type=str, default="", help="逗号分隔；空=按 flags 自动选择")
    p.add_argument("--exclude-slugs", type=str, default="", help="逗号分隔")
    p.add_argument("--require-all-events", type=int, default=1, choices=[0, 1], help="1=严格模式，任何事件失败即报错")
    p.add_argument("--quadkey-level", type=int, default=10, help="子区域层级（建议 10）")
    p.add_argument("--min-hours", type=float, default=-16.0)
    p.add_argument("--max-hours", type=float, default=832.0)
    p.add_argument("--min-tiles-per-unit", type=int, default=5)
    p.add_argument("--min-time-windows", type=int, default=6)
    p.add_argument("--peak-min-hours", type=float, default=0.0)
    p.add_argument("--peak-max-hours", type=float, default=168.0)
    p.add_argument("--fit-min-tprime-hours", type=float, default=24.0)
    p.add_argument("--min-mono-points", type=int, default=3)
    p.add_argument("--mono-tol-up", type=float, default=1.05)
    p.add_argument("--min-fit-r2", type=float, default=0.0, help="子区域 alpha 拟合最小 R2（默认不过滤）")
    args = p.parse_args()

    cfg = GeoUnitConfig(
        catalog=Path(args.catalog),
        output_root=Path(args.output_root),
        dt_flags_csv=Path(args.dt_flags_csv),
        out_dir=Path(args.out_dir),
        use_route_b_selected=int(args.use_route_b_selected),
        selected_slugs=_parse_list_arg(args.selected_slugs),
        exclude_slugs=_parse_list_arg(args.exclude_slugs),
        require_all_events=int(args.require_all_events),
        quadkey_level=int(args.quadkey_level),
        min_hours=float(args.min_hours),
        max_hours=float(args.max_hours),
        min_tiles_per_unit=int(args.min_tiles_per_unit),
        min_time_windows=int(args.min_time_windows),
        peak_min_hours=float(args.peak_min_hours),
        peak_max_hours=float(args.peak_max_hours),
        fit_min_tprime_hours=float(args.fit_min_tprime_hours),
        min_mono_points=int(args.min_mono_points),
        mono_tol_up=float(args.mono_tol_up),
        min_fit_r2=float(args.min_fit_r2),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()

