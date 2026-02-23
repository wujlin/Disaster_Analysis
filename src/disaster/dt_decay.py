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

try:
    from scipy.optimize import curve_fit
    from scipy.stats import spearmanr, theilslopes
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：scipy。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e


@dataclass(frozen=True)
class EventRef:
    output_root: Path
    slug: str


def _is_missing_text(x: object) -> bool:
    if x is None:
        return True
    s = str(x).strip()
    return s == "" or s.lower() == "nan"


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _safe_float(x: object) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except Exception:
        return None


def _short_name(slug: str) -> str:
    """
    生成用于图注/标注的短名（不追求完美，保证确定性和可读性）。
    """
    s = str(slug).strip().lower()
    if not s:
        return ""
    if s == "turkiye_earthquake_2023":
        return "turkiye"
    if s.startswith("park_fire_california"):
        return "park_fire2"
    if s.startswith("park_fire_2024"):
        return "park_fire1"
    if s.startswith("park_fire_"):
        return "park_fire"
    if s.startswith("moldova_"):
        return "moldova"
    if s.startswith("line_fire_"):
        return "line_fire"
    if s.startswith("wildfires_in_boise"):
        return "boise_fire"

    tokens = s.split("_")
    storm_name = ""
    if s.startswith("hurricane_") and len(tokens) >= 2:
        storm_name = tokens[1]
    elif s.startswith("typhoon_") and len(tokens) >= 2:
        storm_name = tokens[1]
    elif s.startswith("tropical_storm_") and len(tokens) >= 3:
        storm_name = tokens[2]

    # geographic hints (last match wins)
    geo_map = {
        "texas": "tx",
        "florida": "fl",
        "puerto": "pr",
        "rico": "pr",
        "quintana": "qr",
        "yucatan": "yuc",
        "mexico": "mx",
        "guerrero": "gue",
        "taiwan": "tw",
        "vietnam": "vn",
        "philippines": "ph",
        "nepal": "np",
        "bangladesh": "bd",
        "gujarat": "gj",
        "quito": "quito",
        "guinea": "gn",
        "nigeria": "ng",
        "moldova": "md",
        "colombia": "co",
        "california": "ca",
    }
    geo = ""
    for t in tokens:
        if t in geo_map:
            geo = geo_map[t]

    if storm_name:
        if storm_name == "melissa" and "aftermath" in tokens:
            return "melissa_aft"
        if "pre" in tokens and "landfall" in tokens:
            return f"{storm_name}_pre"
        if storm_name == "john":
            if "guerrero" in tokens:
                return "john_gue"
            if "southern" in tokens and "mexico" in tokens:
                return "john_sm"
        if storm_name == "beryl":
            if "texas" in tokens:
                return "beryl_tx"
            if "quintana" in tokens:
                return "beryl_qr"
        if storm_name == "yagi":
            if "vietnam" in tokens:
                return "yagi_vn"
            if "philippines" in tokens:
                return "yagi_ph"
        if storm_name == "kristine":
            return "kristine_ph"
        if storm_name == "enteng":
            return "enteng_ph"
        if storm_name == "debby":
            return "debby_pre"
        if storm_name == "krathon":
            return "krathon_tw"
        if storm_name == "helene":
            return "helene_pre"
        if storm_name == "milton":
            return "milton_fl"
        if storm_name == "ernesto":
            return "ernesto_pr"
        if geo:
            return f"{storm_name}_{geo}"
        return storm_name

    # floods / wildfires: try a stable keyword
    if s.startswith("the_flooding_across_") and "nepal" in tokens:
        return "nepal_fld"
    if s.startswith("the_flooding_across_") and "bangladesh" in tokens:
        return "bangladesh_fld"
    if s.startswith("the_flooding_across_") and "gujarat" in tokens:
        return "gujarat_fld"
    if s.startswith("the_wildfires_in_quito"):
        return "quito_fire"

    # fallback: keep it short but unique-ish
    return s[:22]


def _load_config(path: Path | None) -> tuple[dict[str, object], dict[str, object], Path | None]:
    if path is None:
        return {}, {}, None
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"未找到配置文件：{p}")
    suffix = p.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError as exc:
            raise SystemExit(f"读取 YAML 需要 PyYAML：{p}（请先安装 pyyaml）") from exc
        try:
            cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SystemExit(f"配置文件不是合法 YAML：{p}") from exc
    else:
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SystemExit(f"配置文件不是合法 JSON：{p}") from exc
    if not isinstance(cfg, dict):
        raise SystemExit(f"配置文件必须是 JSON object：{p}")
    params = cfg.get("params", cfg)
    if not isinstance(params, dict):
        raise SystemExit(f"配置文件中的 params 必须是 object：{p}")
    return dict(params), dict(cfg), p


def _load_catalog_exclude_reasons(catalog: Path | None) -> dict[str, str]:
    if catalog is None:
        return {}
    p = Path(catalog)
    if not p.exists():
        raise SystemExit(f"--catalog 指定文件不存在：{p}")
    df = pd.read_csv(p)
    if "slug" not in df.columns:
        raise SystemExit(f"catalog 缺少 slug 列：{p}")
    if "exclude_reason" not in df.columns:
        return {}
    out: dict[str, str] = {}
    for row in df.to_dict(orient="records"):
        slug = str(row.get("slug", "")).strip()
        reason = str(row.get("exclude_reason", "")).strip()
        if not slug or _is_missing_text(reason):
            continue
        out[slug] = reason
    return out


def _load_catalog_slugs(catalog: Path | None) -> list[str]:
    if catalog is None:
        return []
    p = Path(catalog)
    if not p.exists():
        raise SystemExit(f"--catalog 指定文件不存在：{p}")
    df = pd.read_csv(p)
    if "slug" not in df.columns:
        raise SystemExit(f"catalog 缺少 slug 列：{p}")
    slugs = [str(s).strip() for s in df["slug"].tolist() if str(s).strip()]
    return sorted(dict.fromkeys(slugs))


def _discover_events(output_root: Path) -> list[EventRef]:
    root = Path(output_root)
    if not root.exists():
        return []
    out: list[EventRef] = []
    for d in sorted(root.iterdir(), key=lambda x: x.name):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        p = d / "phi_heatmap" / "tables" / "phi_rt_long.csv"
        if p.exists():
            out.append(EventRef(output_root=root, slug=d.name))
    return out


def _parse_event_ref(s: str) -> EventRef:
    s = str(s).strip()
    if ":" not in s:
        raise SystemExit(f"--event 需要形如 <output_root>:<slug>，但收到：{s}")
    root_s, slug = s.split(":", 1)
    root = Path(root_s).expanduser()
    slug = str(slug).strip()
    if not slug:
        raise SystemExit(f"--event 的 slug 为空：{s}")
    return EventRef(output_root=root, slug=slug)


def _load_metadata(output_root: Path, slug: str) -> tuple[str, str]:
    meta_p = Path(output_root) / slug / "metadata.json"
    if meta_p.exists():
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            name = str(meta.get("name") or slug)
            event_type = str(meta.get("event_type") or slug.split("_", 1)[0])
            return name, event_type
        except Exception:
            pass
    return slug, slug.split("_", 1)[0]


def _load_phi_rt_long(output_root: Path, slug: str) -> pd.DataFrame:
    p = Path(output_root) / slug / "phi_heatmap" / "tables" / "phi_rt_long.csv"
    if not p.exists():
        raise FileNotFoundError(f"未找到：{p}")
    df = pd.read_csv(p)
    need = {"hours_since_quake", "r_bin_km", "phi_overlap", "n_tiles_overlap"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise SystemExit(f"{p} 缺少列：{miss}")
    for c in ["hours_since_quake", "r_bin_km", "phi_overlap", "n_tiles_overlap"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["hours_since_quake", "r_bin_km", "phi_overlap", "n_tiles_overlap"]).copy()
    return df


def _compute_dt_timeseries(
    df: pd.DataFrame,
    *,
    r_max_km: float,
    near_r_km: float,
    min_tiles_overlap: int,
    min_r_bins: int,
    min_near_bins: int,
) -> pd.DataFrame:
    sub = df.copy()
    sub = sub[(sub["r_bin_km"] <= float(r_max_km)) & (sub["n_tiles_overlap"] >= float(min_tiles_overlap))].copy()
    if sub.empty:
        return pd.DataFrame(columns=["hours_since_quake", "D", "near_delta", "n_r_bins"])
    sub["delta"] = sub["phi_overlap"] - 1.0

    rows: list[dict] = []
    for t, g in sub.groupby("hours_since_quake", sort=True):
        if g.shape[0] < int(min_r_bins):
            continue
        D = float(np.mean(np.abs(pd.to_numeric(g["delta"], errors="coerce").to_numpy(dtype=float))))
        near = g[g["r_bin_km"] <= float(near_r_km)]["delta"].to_numpy(dtype=float)
        near = near[np.isfinite(near)]
        near_delta = float(np.mean(near)) if near.size >= int(min_near_bins) else float("nan")
        rows.append({"hours_since_quake": float(t), "D": float(D), "near_delta": float(near_delta), "n_r_bins": int(g.shape[0])})

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("hours_since_quake", kind="stable").reset_index(drop=True)
    return out


def _median_step_hours(ts: pd.DataFrame) -> float:
    if ts is None or ts.empty or "hours_since_quake" not in ts.columns:
        return float("nan")
    h = pd.to_numeric(ts["hours_since_quake"], errors="coerce").to_numpy(dtype=float)
    h = h[np.isfinite(h)]
    if h.size < 2:
        return float("nan")
    h = np.sort(h)
    dh = np.diff(h)
    dh = dh[np.isfinite(dh) & (dh > 0)]
    if dh.size == 0:
        return float("nan")
    return float(np.median(dh))


def _daily_average_if_high_freq(ts: pd.DataFrame, *, high_freq_thresh_h: float = 16.0) -> tuple[pd.DataFrame, float, int]:
    """
    仅当时间步长较高频（如 8h）时，按日做平均，抑制日内周期。
    返回：(处理后序列, 原始中位步长, 是否做了日均值[0/1])。
    """
    if ts is None or ts.empty:
        return ts.copy(), float("nan"), 0
    med_step = _median_step_hours(ts)
    if not np.isfinite(med_step) or med_step >= float(high_freq_thresh_h):
        return ts.copy(), float(med_step), 0

    tmp = ts.copy()
    h = pd.to_numeric(tmp["hours_since_quake"], errors="coerce").to_numpy(dtype=float)
    tmp = tmp[np.isfinite(h)].copy()
    if tmp.empty:
        return pd.DataFrame(columns=list(ts.columns)), float(med_step), 0
    tmp["hours_since_quake"] = pd.to_numeric(tmp["hours_since_quake"], errors="coerce")
    tmp = tmp.dropna(subset=["hours_since_quake"]).copy()
    tmp["day_idx"] = np.floor(tmp["hours_since_quake"].to_numpy(dtype=float) / 24.0).astype(int)

    out = (
        tmp.groupby("day_idx", sort=True, as_index=False)
        .agg(
            hours_since_quake=("hours_since_quake", "mean"),
            D=("D", "mean"),
            near_delta=("near_delta", "mean"),
            n_r_bins=("n_r_bins", "mean"),
        )
        .sort_values("hours_since_quake", kind="stable")
        .reset_index(drop=True)
    )
    out["n_r_bins"] = pd.to_numeric(out["n_r_bins"], errors="coerce").round().astype("Int64")
    return out, float(med_step), 1


def _pick_peak(ts: pd.DataFrame, *, peak_min_hours: float | None, peak_max_hours: float | None) -> tuple[float, float]:
    if ts.empty:
        return float("nan"), float("nan")
    sub = ts.copy()
    if peak_min_hours is not None:
        sub = sub[pd.to_numeric(sub["hours_since_quake"], errors="coerce") >= float(peak_min_hours)].copy()
    if peak_max_hours is not None:
        sub = sub[pd.to_numeric(sub["hours_since_quake"], errors="coerce") <= float(peak_max_hours)].copy()
    if sub.empty:
        sub = ts.copy()
    i = int(pd.to_numeric(sub["D"], errors="coerce").idxmax())
    row = ts.loc[i]
    return float(row["hours_since_quake"]), float(row["D"])


def _classify_event(
    ts: pd.DataFrame,
    *,
    D_peak: float,
    D_peak_min: float | None,
    D_peak_snr: float | None,
    snr_threshold: float | None,
    min_time_windows: int,
    peak_frac: float,
    near_thresh: float,
) -> tuple[str, float]:
    """
    返回：(event_type, near_delta_mean_over_peak_windows)
    event_type ∈ {EVAC, INFL, LOW_SIGNAL, EXCLUDED_SHORT, NEUTRAL}
    """
    if ts.empty:
        return "EXCLUDED_SHORT", float("nan")
    if int(ts.shape[0]) < int(min_time_windows):
        return "EXCLUDED_SHORT", float("nan")
    if not np.isfinite(float(D_peak)):
        return "LOW_SIGNAL", float("nan")
    if D_peak_min is not None and np.isfinite(float(D_peak_min)) and float(D_peak) < float(D_peak_min):
        return "LOW_SIGNAL", float("nan")
    if snr_threshold is not None and np.isfinite(float(snr_threshold)):
        if D_peak_snr is None or (not np.isfinite(float(D_peak_snr))) or float(D_peak_snr) < float(snr_threshold):
            return "LOW_SIGNAL", float("nan")

    cut = float(peak_frac) * float(D_peak)
    peak_w = ts[pd.to_numeric(ts["D"], errors="coerce") >= float(cut)].copy()
    near = pd.to_numeric(peak_w["near_delta"], errors="coerce").to_numpy(dtype=float)
    near = near[np.isfinite(near)]
    near_mean = float(np.mean(near)) if near.size else float("nan")

    if np.isfinite(near_mean) and near_mean < -float(near_thresh):
        return "EVAC", float(near_mean)
    if np.isfinite(near_mean) and near_mean > float(near_thresh):
        return "INFL", float(near_mean)
    return "NEUTRAL", float(near_mean)


def _monotone_decay_segment(
    post: pd.DataFrame,
    *,
    tol_up: float,
) -> pd.DataFrame:
    """
    给定 post-peak 序列（按 t' 升序），返回“首次反弹即截断”的单调衰减段。
    允许小幅波动：D_{i+1} <= D_i * tol_up 视为继续。
    """
    if post.empty:
        return post.copy()
    post = post.sort_values("t_prime_h", kind="stable").reset_index(drop=True)
    keep_idx = [0]
    for i in range(post.shape[0] - 1):
        di = float(post.loc[i, "D_norm"])
        dj = float(post.loc[i + 1, "D_norm"])
        if not (np.isfinite(di) and np.isfinite(dj)):
            break
        if dj <= di * float(tol_up):
            keep_idx.append(i + 1)
            continue
        break
    return post.loc[keep_idx].copy().reset_index(drop=True)


def _fit_powerlaw_loglog(t: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """
    拟合 y = A * t^{-alpha} 的 log-log OLS；返回 (alpha, logA, r2)。
    """
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(t) & np.isfinite(y) & (t > 0) & (y > 0)
    t1 = t[ok]
    y1 = y[ok]
    if t1.size < 3:
        return float("nan"), float("nan"), float("nan")
    x = np.log(t1)
    yy = np.log(y1)
    slope, intercept = np.polyfit(x, yy, deg=1)
    yy_hat = slope * x + intercept
    ss_res = float(np.sum(np.square(yy - yy_hat)))
    ss_tot = float(np.sum(np.square(yy - float(np.mean(yy))))) if yy.size else float("nan")
    r2 = float(1.0 - ss_res / ss_tot) if np.isfinite(ss_tot) and ss_tot > 0 else float("nan")
    alpha = float(-slope)
    logA = float(intercept)
    return alpha, logA, r2


def _bic_from_sse(*, sse: float, n: int, k: int) -> float:
    if n <= 0 or k <= 0 or not np.isfinite(sse):
        return float("nan")
    sse = float(max(sse, 1e-12))
    return float(n * np.log(sse / float(n)) + float(k) * np.log(float(n)))


def _fit_models_bic(
    t: np.ndarray,
    y: np.ndarray,
) -> dict:
    """
    在 real space 上拟合三模型，并返回 BIC 与参数。
    """
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(t) & np.isfinite(y) & (t > 0) & (y > 0)
    tt = t[ok]
    yy = y[ok]
    if tt.size < 3:
        return {"ok": 0}

    def f_powerlaw(t_in: np.ndarray, A: float, alpha: float) -> np.ndarray:
        return A * np.power(np.asarray(t_in, dtype=float), -alpha)

    def f_exp(t_in: np.ndarray, A: float, tau: float) -> np.ndarray:
        return A * np.exp(-np.asarray(t_in, dtype=float) / tau)

    def f_strexp(t_in: np.ndarray, A: float, tau: float, beta: float) -> np.ndarray:
        return A * np.exp(-np.power(np.asarray(t_in, dtype=float) / tau, beta))

    # initial guesses
    A0 = float(np.nanmax(yy)) if yy.size else 1.0
    A0 = float(np.clip(A0, 0.1, 5.0))
    t_med = float(np.nanmedian(tt)) if tt.size else 48.0
    t_med = float(t_med) if np.isfinite(t_med) and t_med > 0 else 48.0
    alpha0 = 0.5
    tau0 = float(np.clip(t_med, 1.0, 2000.0))
    beta0 = 1.0

    out: dict[str, object] = {"ok": 1, "n_pts": int(tt.size)}

    # power-law
    try:
        popt, _ = curve_fit(
            f_powerlaw,
            tt,
            yy,
            p0=(A0, alpha0),
            bounds=([0.0, -1.0], [5.0, 3.0]),
            maxfev=20000,
        )
        A_p, alpha_p = float(popt[0]), float(popt[1])
        y_hat = f_powerlaw(tt, A_p, alpha_p)
        sse = float(np.sum(np.square(yy - y_hat)))
        out.update({"BIC_power": _bic_from_sse(sse=sse, n=int(tt.size), k=2), "A_power": A_p, "alpha_power": alpha_p})
    except Exception:
        out.update({"BIC_power": float("nan"), "A_power": float("nan"), "alpha_power": float("nan")})

    # exponential
    try:
        popt, _ = curve_fit(
            f_exp,
            tt,
            yy,
            p0=(A0, tau0),
            bounds=([0.0, 1.0], [5.0, 2000.0]),
            maxfev=20000,
        )
        A_e, tau_e = float(popt[0]), float(popt[1])
        y_hat = f_exp(tt, A_e, tau_e)
        sse = float(np.sum(np.square(yy - y_hat)))
        out.update({"BIC_exp": _bic_from_sse(sse=sse, n=int(tt.size), k=2), "A_exp": A_e, "tau_exp": tau_e})
    except Exception:
        out.update({"BIC_exp": float("nan"), "A_exp": float("nan"), "tau_exp": float("nan")})

    # stretched exponential
    try:
        popt, _ = curve_fit(
            f_strexp,
            tt,
            yy,
            p0=(A0, tau0, beta0),
            bounds=([0.0, 1.0, 0.01], [5.0, 2000.0, 3.0]),
            maxfev=40000,
        )
        A_s, tau_s, beta_s = float(popt[0]), float(popt[1]), float(popt[2])
        y_hat = f_strexp(tt, A_s, tau_s, beta_s)
        sse = float(np.sum(np.square(yy - y_hat)))
        out.update(
            {"BIC_strexp": _bic_from_sse(sse=sse, n=int(tt.size), k=3), "A_strexp": A_s, "tau_strexp": tau_s, "beta_strexp": beta_s}
        )
    except Exception:
        out.update({"BIC_strexp": float("nan"), "A_strexp": float("nan"), "tau_strexp": float("nan"), "beta_strexp": float("nan")})

    return out


def _tau50(t_prime_h: np.ndarray, y: np.ndarray) -> tuple[float, int]:
    t_prime_h = np.asarray(t_prime_h, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(t_prime_h) & np.isfinite(y) & (t_prime_h > 0)
    t1 = t_prime_h[ok]
    y1 = y[ok]
    if t1.size == 0:
        return float("nan"), 0
    idx = np.where(y1 <= 0.5)[0]
    if idx.size:
        return float(t1[int(idx[0])]), 0
    return float(np.max(t1)), 1


def run(
    *,
    output_root: Path,
    out_dir: Path,
    catalog: Path | None,
    slugs: list[str],
    exclude_slugs: list[str],
    r_max_km: float,
    near_r_km: float,
    min_tiles_overlap: int,
    min_r_bins: int,
    min_near_bins: int,
    peak_min_hours: float | None,
    peak_max_hours: float | None,
    D_peak_min: float | None,
    snr_threshold: float | None,
    min_time_windows: int,
    min_post_peak_steps: int,
    peak_frac: float,
    near_thresh: float,
    fit_method: str,
    fit_min_tprime_hours: float,
    mono_tol_up: float,
    route_b_min_n_mono: int,
    route_b_low_r2_threshold: float,
    route_b_exclude_slugs: list[str],
    catalog_exclude_reasons: dict[str, str] | None,
    route_b_teach_highlight_slugs: list[str],
    config_json_path: Path | None,
    config_payload: dict[str, object] | None,
) -> None:
    output_root = Path(output_root)
    out_dir = Path(out_dir)
    tabs = out_dir / "tables"
    figs = out_dir / "figures"
    _ensure_dir(tabs)
    _ensure_dir(figs)

    refs = {r.slug: r for r in _discover_events(output_root)}
    want = [str(s).strip() for s in (slugs or []) if str(s).strip()]
    if want and len(want) == 1 and want[0].lower() == "all":
        want = []
    catalog_slugs = _load_catalog_slugs(catalog) if catalog is not None else []
    if not want:
        if catalog_slugs:
            want = [s for s in catalog_slugs if s in refs]
        else:
            want = sorted(refs.keys())
    exclude = {str(s).strip() for s in (exclude_slugs or []) if str(s).strip()}
    if exclude:
        want = [s for s in want if s not in exclude]
    catalog_exclude_reasons = dict(catalog_exclude_reasons or {})
    route_b_exclude_from_catalog = set(catalog_exclude_reasons.keys())
    route_b_exclude_from_cli = {str(x).strip() for x in (route_b_exclude_slugs or []) if str(x).strip()}
    route_b_exclude = route_b_exclude_from_catalog | route_b_exclude_from_cli

    all_rows: list[dict] = []
    summary_rows: list[dict] = []
    fit_rows: list[dict] = []
    bic_rows: list[dict] = []
    collapse_rows: list[dict] = []

    for slug in want:
        if slug not in refs:
            continue
        ref = refs[slug]
        name, disaster_type = _load_metadata(ref.output_root, slug)
        df = _load_phi_rt_long(ref.output_root, slug)

        ts_raw = _compute_dt_timeseries(
            df,
            r_max_km=float(r_max_km),
            near_r_km=float(near_r_km),
            min_tiles_overlap=int(min_tiles_overlap),
            min_r_bins=int(min_r_bins),
            min_near_bins=int(min_near_bins),
        )
        n_time_windows_raw = int(ts_raw.shape[0])
        ts, median_step_hours_raw, daily_avg_applied = _daily_average_if_high_freq(ts_raw, high_freq_thresh_h=16.0)

        t_peak, D_peak = _pick_peak(ts, peak_min_hours=peak_min_hours, peak_max_hours=peak_max_hours)
        baseline = ts[pd.to_numeric(ts["hours_since_quake"], errors="coerce") <= 0].copy() if not ts.empty else pd.DataFrame()
        baseline_std = float(np.nanstd(pd.to_numeric(baseline["D"], errors="coerce").to_numpy(dtype=float), ddof=1)) if not baseline.empty else float("nan")
        D_peak_snr = (
            float(D_peak) / float(baseline_std)
            if np.isfinite(float(D_peak)) and np.isfinite(float(baseline_std)) and float(baseline_std) > 0
            else float("nan")
        )
        event_type, near_mean = _classify_event(
            ts,
            D_peak=float(D_peak),
            D_peak_min=(float(D_peak_min) if D_peak_min is not None else None),
            D_peak_snr=(float(D_peak_snr) if np.isfinite(float(D_peak_snr)) else None),
            snr_threshold=(float(snr_threshold) if snr_threshold is not None else None),
            min_time_windows=int(min_time_windows),
            peak_frac=float(peak_frac),
            near_thresh=float(near_thresh),
        )

        # per-time rows
        if not ts.empty and np.isfinite(float(D_peak)) and float(D_peak) > 0:
            ts2 = ts.copy()
            ts2["t_hours"] = pd.to_numeric(ts2["hours_since_quake"], errors="coerce")
            ts2["D_peak"] = float(D_peak)
            ts2["t_peak_hours"] = float(t_peak)
            ts2["D_norm"] = ts2["D"].to_numpy(dtype=float) / float(D_peak)
            ts2["short_name"] = _short_name(slug)
            ts2["slug"] = str(slug)
            ts2["name"] = str(name)
            ts2["disaster_type"] = str(disaster_type)
            ts2["event_type"] = str(event_type)
            for r in ts2.to_dict(orient="records"):
                all_rows.append(r)

        # summary row
        summary_rows.append(
            {
                "slug": str(slug),
                "short_name": _short_name(slug),
                "name": str(name),
                "disaster_type": str(disaster_type),
                "output_root": str(ref.output_root),
                "n_time_windows": int(ts.shape[0]),
                "n_time_windows_raw": int(n_time_windows_raw),
                "median_step_hours_raw": float(median_step_hours_raw),
                "daily_avg_applied": int(daily_avg_applied),
                "t_peak_hours": float(t_peak),
                "D_peak": float(D_peak),
                "event_type": str(event_type),
                "near_delta_peak_windows_mean": float(near_mean),
                "D_inf": float("nan"),
                "D_baseline_std": float(baseline_std),
                "D_peak_snr": float(D_peak_snr),
            }
        )

        # post-peak arrays for fits
        if ts.empty or not np.isfinite(float(t_peak)) or not np.isfinite(float(D_peak)) or float(D_peak) <= 0:
            continue
        if event_type in {"EXCLUDED_SHORT"}:
            continue

        post = ts.copy()
        post = post[pd.to_numeric(post["hours_since_quake"], errors="coerce") > float(t_peak)].copy()
        post = post.sort_values("hours_since_quake", kind="stable").reset_index(drop=True)
        post["t_prime_h"] = pd.to_numeric(post["hours_since_quake"], errors="coerce") - float(t_peak)
        post["D_norm"] = pd.to_numeric(post["D"], errors="coerce") / float(D_peak)
        post_fit = post[pd.to_numeric(post["t_prime_h"], errors="coerce") >= float(fit_min_tprime_hours)].copy()

        D_inf = float("nan")
        if not post.empty:
            tail_n = max(1, int(post.shape[0] // 3))
            tail = pd.to_numeric(post["D_norm"], errors="coerce").to_numpy(dtype=float)
            if tail_n > 0:
                tail = tail[-tail_n:]
            tail = tail[np.isfinite(tail)]
            if tail.size:
                D_inf = float(np.mean(tail))
        summary_rows[-1]["D_inf"] = float(D_inf)

        # 拟合段：full_post_peak | monotone_truncated（均在 t' >= fit_min_tprime_hours 上进行）
        if str(fit_method) == "full_post_peak":
            fit_seg = post_fit[["t_prime_h", "D_norm"]].copy() if not post_fit.empty else pd.DataFrame()
        elif str(fit_method) == "monotone_truncated":
            fit_seg = _monotone_decay_segment(post_fit[["t_prime_h", "D_norm"]].copy(), tol_up=float(mono_tol_up)) if not post_fit.empty else pd.DataFrame()
        else:
            raise SystemExit(f"不支持的 fit_method：{fit_method}（仅支持 full_post_peak / monotone_truncated）")
        alpha, logA, r2 = _fit_powerlaw_loglog(
            pd.to_numeric(fit_seg["t_prime_h"], errors="coerce").to_numpy(dtype=float) if not fit_seg.empty else np.array([], dtype=float),
            pd.to_numeric(fit_seg["D_norm"], errors="coerce").to_numpy(dtype=float) if not fit_seg.empty else np.array([], dtype=float),
        )
        fit_rows.append(
            {
                "slug": str(slug),
                "short_name": _short_name(slug),
                "disaster_type": str(disaster_type),
                "event_type": str(event_type),
                "D_peak": float(D_peak),
                "t_peak_hours": float(t_peak),
                "fit_method": str(fit_method),
                "fit_min_tprime_hours": float(fit_min_tprime_hours),
                "n_mono": int(fit_seg.shape[0]) if fit_seg is not None else 0,
                "n_post_fit": int(post_fit.shape[0]),
                "n_total_post": int(post.shape[0]),
                "alpha": float(alpha),
                "logA": float(logA),
                "r2": float(r2),
                "t_decay_start": float(pd.to_numeric(fit_seg["t_prime_h"], errors="coerce").min()) if fit_seg is not None and not fit_seg.empty else float("nan"),
                "t_decay_end": float(pd.to_numeric(fit_seg["t_prime_h"], errors="coerce").max()) if fit_seg is not None and not fit_seg.empty else float("nan"),
                "D_inf": float(D_inf),
                "D_inf_abs": float(D_inf * D_peak) if np.isfinite(D_inf) and np.isfinite(float(D_peak)) else float("nan"),
            }
        )

        # Task 3: BIC compare on selected fit segment（与 alpha 拟合口径一致）
        bic = (
            _fit_models_bic(
                pd.to_numeric(fit_seg["t_prime_h"], errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(fit_seg["D_norm"], errors="coerce").to_numpy(dtype=float),
            )
            if fit_seg is not None and not fit_seg.empty
            else {"ok": 0, "n_pts": 0}
        )
        Bp = float(bic.get("BIC_power", float("nan")))
        Be = float(bic.get("BIC_exp", float("nan")))
        Bs = float(bic.get("BIC_strexp", float("nan")))
        finite = [x for x in [Bp, Be, Bs] if np.isfinite(float(x))]
        best = float(min(finite)) if finite else float("nan")
        best_model = ""
        if np.isfinite(best):
            if np.isfinite(Bp) and abs(Bp - best) < 1e-9:
                best_model = "power_law"
            elif np.isfinite(Be) and abs(Be - best) < 1e-9:
                best_model = "exponential"
            elif np.isfinite(Bs) and abs(Bs - best) < 1e-9:
                best_model = "stretched_exp"
        bic_rows.append(
            {
                "slug": str(slug),
                "short_name": _short_name(slug),
                "disaster_type": str(disaster_type),
                "event_type": str(event_type),
                "fit_method": str(fit_method),
                "n_pts": int(bic.get("n_pts", int(fit_seg.shape[0]) if fit_seg is not None else 0)),
                "best_model": str(best_model),
                "BIC_power": float(Bp),
                "BIC_exp": float(Be),
                "BIC_strexp": float(Bs),
                "dBIC_power": float(Bp - best) if np.isfinite(Bp) and np.isfinite(best) else float("nan"),
                "dBIC_exp": float(Be - best) if np.isfinite(Be) and np.isfinite(best) else float("nan"),
                "dBIC_strexp": float(Bs - best) if np.isfinite(Bs) and np.isfinite(best) else float("nan"),
                "alpha_power": float(bic.get("alpha_power", float("nan"))),
                "tau_exp": float(bic.get("tau_exp", float("nan"))),
                "tau_strexp": float(bic.get("tau_strexp", float("nan"))),
                "beta_strexp": float(bic.get("beta_strexp", float("nan"))),
            }
        )

        # Task 4: tau_50 for collapse（无 post 时写 NaN）
        tau50, lower_bound = (
            _tau50(
                pd.to_numeric(post["t_prime_h"], errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(post["D_norm"], errors="coerce").to_numpy(dtype=float),
            )
            if not post.empty
            else (float("nan"), 0)
        )
        collapse_rows.append(
            {
                "slug": str(slug),
                "short_name": _short_name(slug),
                "disaster_type": str(disaster_type),
                "event_type": str(event_type),
                "t_peak_hours": float(t_peak),
                "D_peak": float(D_peak),
                "fit_method": str(fit_method),
                "tau50_h": float(tau50),
                "tau50_lower_bound": int(lower_bound),
            }
        )

    # tables
    dt_df = pd.DataFrame(all_rows)
    summary_df = pd.DataFrame(summary_rows)
    fits_df = pd.DataFrame(fit_rows)
    bic_df = pd.DataFrame(bic_rows)
    collapse_df = pd.DataFrame(collapse_rows)

    dt_df.to_csv(tabs / "Dt_all_events.csv", index=False)
    summary_df.to_csv(tabs / "Dt_event_summary.csv", index=False)
    fits_df.to_csv(tabs / "Dt_powerlaw_fits.csv", index=False)
    bic_df.to_csv(tabs / "Dt_model_bic.csv", index=False)
    collapse_df.to_csv(tabs / "Dt_tau50.csv", index=False)

    # Route B sample and correlation stats
    route_b_sample_df = pd.DataFrame()
    route_b_stats_df = pd.DataFrame()
    route_b_jackknife_df = pd.DataFrame()
    route_b_jackknife_summary_df = pd.DataFrame()
    route_b_r2_strata_df = pd.DataFrame()
    route_b_alpha_dinf_df = pd.DataFrame()
    if not fits_df.empty and not summary_df.empty:
        route_b_sample_df = fits_df.merge(
            summary_df[
                [
                    "slug",
                    "near_delta_peak_windows_mean",
                    "short_name",
                    "event_type",
                    "D_inf",
                    "n_time_windows",
                    "D_peak",
                    "D_peak_snr",
                ]
            ],
            on=["slug", "short_name", "event_type"],
            how="left",
            suffixes=("", "_summary"),
        )
        route_b_sample_df["n_mono"] = pd.to_numeric(route_b_sample_df["n_mono"], errors="coerce")
        route_b_sample_df["alpha"] = pd.to_numeric(route_b_sample_df["alpha"], errors="coerce")
        route_b_sample_df["r2"] = pd.to_numeric(route_b_sample_df["r2"], errors="coerce")
        route_b_sample_df["near_delta_peak_windows_mean"] = pd.to_numeric(route_b_sample_df["near_delta_peak_windows_mean"], errors="coerce")
        route_b_sample_df["D_inf"] = pd.to_numeric(route_b_sample_df["D_inf"], errors="coerce")
        route_b_sample_df["n_post_fit"] = pd.to_numeric(route_b_sample_df["n_post_fit"], errors="coerce")
        route_b_sample_df["n_time_windows"] = pd.to_numeric(route_b_sample_df["n_time_windows"], errors="coerce")
        route_b_sample_df["D_peak"] = pd.to_numeric(route_b_sample_df["D_peak"], errors="coerce")
        route_b_sample_df["D_peak_snr"] = pd.to_numeric(route_b_sample_df["D_peak_snr"], errors="coerce")

        route_b_sample_df["catalog_exclude_reason"] = route_b_sample_df["slug"].astype(str).map(catalog_exclude_reasons).fillna("")
        route_b_sample_df["route_b_exclude_via_catalog"] = route_b_sample_df["slug"].astype(str).isin(route_b_exclude_from_catalog)
        route_b_sample_df["route_b_exclude_via_cli"] = route_b_sample_df["slug"].astype(str).isin(route_b_exclude_from_cli)

        route_b_sample_df["quality_short_windows"] = route_b_sample_df["n_time_windows"] < float(min_time_windows)
        route_b_sample_df["quality_short_post_peak"] = route_b_sample_df["n_post_fit"] < float(min_post_peak_steps)
        route_b_sample_df["quality_low_signal"] = (
            (route_b_sample_df["D_peak"] < float(D_peak_min))
            if D_peak_min is not None
            else False
        )
        route_b_sample_df["quality_low_snr"] = (
            (route_b_sample_df["D_peak_snr"] < float(snr_threshold))
            if snr_threshold is not None
            else False
        )
        route_b_sample_df["quality_missing_near_delta"] = route_b_sample_df["near_delta_peak_windows_mean"].isna()
        route_b_sample_df["analysis_n_mono_lt_threshold"] = route_b_sample_df["n_mono"] < float(route_b_min_n_mono)
        route_b_sample_df["analysis_alpha_nan"] = route_b_sample_df["alpha"].isna()
        route_b_sample_df["data_quality_ok"] = ~(
            route_b_sample_df["quality_short_windows"]
            | route_b_sample_df["quality_short_post_peak"]
            | route_b_sample_df["quality_low_signal"]
            | route_b_sample_df["quality_low_snr"]
            | route_b_sample_df["quality_missing_near_delta"]
        )
        route_b_sample_df["analysis_applicability_ok"] = ~(
            route_b_sample_df["analysis_n_mono_lt_threshold"] | route_b_sample_df["analysis_alpha_nan"]
        )
        route_b_sample_df["route_b_base_ok"] = route_b_sample_df["data_quality_ok"] & route_b_sample_df["analysis_applicability_ok"]
        route_b_sample_df["route_b_excluded_slug"] = route_b_sample_df["slug"].astype(str).isin(route_b_exclude)
        route_b_sample_df["route_b_low_r2"] = (
            route_b_sample_df["r2"].notna() & (route_b_sample_df["r2"] < float(route_b_low_r2_threshold))
        )
        route_b_sample_df["route_b_selected"] = (
            route_b_sample_df["route_b_base_ok"]
            & (~route_b_sample_df["route_b_excluded_slug"])
        )
        route_b_sample_df["route_b_selected_plot"] = (
            route_b_sample_df["route_b_selected"] & (~route_b_sample_df["route_b_low_r2"])
        )
        drop_reason_primary: list[str] = []
        drop_reason_class: list[str] = []
        for row in route_b_sample_df.to_dict(orient="records"):
            if bool(row.get("route_b_selected", False)):
                drop_reason_primary.append("selected")
                drop_reason_class.append("selected")
                continue
            if bool(row.get("route_b_excluded_slug", False)):
                if bool(row.get("route_b_exclude_via_catalog", False)):
                    drop_reason_primary.append("manual_exclude_catalog")
                else:
                    drop_reason_primary.append("manual_exclude_cli")
                drop_reason_class.append("manual_exclude")
                continue
            if bool(row.get("quality_short_windows", False)):
                drop_reason_primary.append("data_quality_short_windows")
                drop_reason_class.append("data_quality")
                continue
            if bool(row.get("quality_short_post_peak", False)):
                drop_reason_primary.append("data_quality_short_post_peak")
                drop_reason_class.append("data_quality")
                continue
            if bool(row.get("quality_low_signal", False)):
                drop_reason_primary.append("data_quality_low_signal")
                drop_reason_class.append("data_quality")
                continue
            if bool(row.get("quality_low_snr", False)):
                drop_reason_primary.append("data_quality_low_snr")
                drop_reason_class.append("data_quality")
                continue
            if bool(row.get("quality_missing_near_delta", False)):
                drop_reason_primary.append("data_quality_missing_near_delta")
                drop_reason_class.append("data_quality")
                continue
            if bool(row.get("analysis_n_mono_lt_threshold", False)):
                drop_reason_primary.append("analysis_n_mono_lt_threshold")
                drop_reason_class.append("analysis_applicability")
                continue
            if bool(row.get("analysis_alpha_nan", False)):
                drop_reason_primary.append("analysis_alpha_nan")
                drop_reason_class.append("analysis_applicability")
                continue
            drop_reason_primary.append("other")
            drop_reason_class.append("other")
        route_b_sample_df["drop_reason_primary"] = drop_reason_primary
        route_b_sample_df["drop_reason_class"] = drop_reason_class

        ss = route_b_sample_df[route_b_sample_df["route_b_selected"]].copy()
        rho, pval = (float("nan"), float("nan"))
        if ss.shape[0] >= 3:
            rho, pval = spearmanr(
                pd.to_numeric(ss["near_delta_peak_windows_mean"], errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(ss["alpha"], errors="coerce").to_numpy(dtype=float),
            )
            rho, pval = float(rho), float(pval)

        route_b_stats_df = pd.DataFrame(
            [
                {
                    "n_total_fits": int(route_b_sample_df.shape[0]),
                    "n_base_ok": int(route_b_sample_df["route_b_base_ok"].sum()),
                    "n_selected": int(route_b_sample_df["route_b_selected"].sum()),
                    "n_selected_plot": int(route_b_sample_df["route_b_selected_plot"].sum()),
                    "spearman_rho": float(rho),
                    "spearman_p": float(pval),
                    "min_n_mono": int(route_b_min_n_mono),
                    "min_post_peak_steps": int(min_post_peak_steps),
                    "fit_method": str(fit_method),
                    "fit_min_tprime_hours": float(fit_min_tprime_hours),
                    "low_r2_threshold": float(route_b_low_r2_threshold),
                    "excluded_slugs": ";".join(sorted(route_b_exclude)),
                    "excluded_slugs_from_catalog": ";".join(sorted(route_b_exclude_from_catalog)),
                    "excluded_slugs_from_cli": ";".join(sorted(route_b_exclude_from_cli)),
                }
            ]
        )

        # Leave-one-out jackknife
        jk_rows: list[dict] = []
        if ss.shape[0] >= 4:
            for removed_slug in ss["slug"].astype(str).tolist():
                tmp = ss[ss["slug"].astype(str) != str(removed_slug)].copy()
                if tmp.shape[0] < 3:
                    continue
                rho_jk, p_jk = spearmanr(
                    pd.to_numeric(tmp["near_delta_peak_windows_mean"], errors="coerce").to_numpy(dtype=float),
                    pd.to_numeric(tmp["alpha"], errors="coerce").to_numpy(dtype=float),
                )
                jk_rows.append(
                    {
                        "removed_slug": str(removed_slug),
                        "n_after_remove": int(tmp.shape[0]),
                        "spearman_rho": float(rho_jk),
                        "spearman_p": float(p_jk),
                    }
                )
        route_b_jackknife_df = pd.DataFrame(jk_rows)
        if not route_b_jackknife_df.empty:
            rho_arr = pd.to_numeric(route_b_jackknife_df["spearman_rho"], errors="coerce").to_numpy(dtype=float)
            p_arr = pd.to_numeric(route_b_jackknife_df["spearman_p"], errors="coerce").to_numpy(dtype=float)
            rho_arr = rho_arr[np.isfinite(rho_arr)]
            p_arr = p_arr[np.isfinite(p_arr)]
            route_b_jackknife_summary_df = pd.DataFrame(
                [
                    {
                        "n_jackknife": int(len(rho_arr)),
                        "rho_median": float(np.nanmedian(rho_arr)) if len(rho_arr) else float("nan"),
                        "rho_ci2p5": float(np.nanpercentile(rho_arr, 2.5)) if len(rho_arr) else float("nan"),
                        "rho_ci97p5": float(np.nanpercentile(rho_arr, 97.5)) if len(rho_arr) else float("nan"),
                        "p_median": float(np.nanmedian(p_arr)) if len(p_arr) else float("nan"),
                        "p_ci2p5": float(np.nanpercentile(p_arr, 2.5)) if len(p_arr) else float("nan"),
                        "p_ci97p5": float(np.nanpercentile(p_arr, 97.5)) if len(p_arr) else float("nan"),
                    }
                ]
            )

        # R² 分层稳健性
        strata_rows: list[dict] = []
        for thr in [0.0, 0.8]:
            tmp = ss[pd.to_numeric(ss["r2"], errors="coerce") >= float(thr)].copy()
            rho_t, p_t = (float("nan"), float("nan"))
            if tmp.shape[0] >= 3:
                rho_t, p_t = spearmanr(
                    pd.to_numeric(tmp["near_delta_peak_windows_mean"], errors="coerce").to_numpy(dtype=float),
                    pd.to_numeric(tmp["alpha"], errors="coerce").to_numpy(dtype=float),
                )
                rho_t, p_t = float(rho_t), float(p_t)
            strata_rows.append(
                {
                    "r2_threshold": float(thr),
                    "n": int(tmp.shape[0]),
                    "spearman_rho": float(rho_t),
                    "spearman_p": float(p_t),
                }
            )
        route_b_r2_strata_df = pd.DataFrame(strata_rows)

        # D_inf 补充：alpha 与 D_inf 是否相关
        dinf_rows: list[dict] = []
        for tag, q in [("selected", ss), ("selected_r2_ge_0p8", ss[pd.to_numeric(ss["r2"], errors="coerce") >= 0.8].copy())]:
            q2 = q[pd.to_numeric(q["D_inf"], errors="coerce").notna()].copy()
            rho_d, p_d = (float("nan"), float("nan"))
            if q2.shape[0] >= 3:
                rho_d, p_d = spearmanr(
                    pd.to_numeric(q2["alpha"], errors="coerce").to_numpy(dtype=float),
                    pd.to_numeric(q2["D_inf"], errors="coerce").to_numpy(dtype=float),
                )
                rho_d, p_d = float(rho_d), float(p_d)
            dinf_rows.append(
                {
                    "subset": str(tag),
                    "n": int(q2.shape[0]),
                    "spearman_rho_alpha_vs_Dinf": float(rho_d),
                    "spearman_p_alpha_vs_Dinf": float(p_d),
                }
            )
        route_b_alpha_dinf_df = pd.DataFrame(dinf_rows)

    route_b_sample_df.to_csv(tabs / "Dt_routeB_sample_flags.csv", index=False)
    route_b_stats_df.to_csv(tabs / "Dt_routeB_alpha_delta_spearman.csv", index=False)
    route_b_jackknife_df.to_csv(tabs / "Dt_routeB_alpha_delta_jackknife.csv", index=False)
    route_b_jackknife_summary_df.to_csv(tabs / "Dt_routeB_alpha_delta_jackknife_summary.csv", index=False)
    route_b_r2_strata_df.to_csv(tabs / "Dt_routeB_alpha_delta_r2_strata.csv", index=False)
    route_b_alpha_dinf_df.to_csv(tabs / "Dt_routeB_alpha_dinf_spearman.csv", index=False)

    # collapse quality table
    bins = [(0.0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, 2.5), (2.5, 3.0)]
    q_rows: list[dict] = []
    if not dt_df.empty and not collapse_df.empty:
        # build post-peak normalized time for each event
        dt_post = dt_df.copy()
        dt_post = dt_post[pd.to_numeric(dt_post["hours_since_quake"], errors="coerce") > pd.to_numeric(dt_post["t_peak_hours"], errors="coerce")].copy()
        dt_post["t_prime_h"] = pd.to_numeric(dt_post["hours_since_quake"], errors="coerce") - pd.to_numeric(dt_post["t_peak_hours"], errors="coerce")
        dt_post = dt_post.merge(collapse_df[["slug", "tau50_h", "tau50_lower_bound"]], on="slug", how="left")
        dt_post["t_tilde"] = pd.to_numeric(dt_post["t_prime_h"], errors="coerce") / pd.to_numeric(dt_post["tau50_h"], errors="coerce")
        dt_post["D_norm"] = pd.to_numeric(dt_post["D_norm"], errors="coerce")

        def _group_quality(group_name: str, want_types: set[str] | None) -> None:
            g = dt_post.copy()
            if want_types is not None:
                g = g[g["event_type"].astype(str).isin(want_types)].copy()
            for lo, hi in bins:
                vals: list[float] = []
                for slug, sub in g.groupby("slug", sort=False):
                    x = pd.to_numeric(sub["t_tilde"], errors="coerce").to_numpy(dtype=float)
                    y = pd.to_numeric(sub["D_norm"], errors="coerce").to_numpy(dtype=float)
                    m = np.isfinite(x) & np.isfinite(y) & (x >= lo) & (x < hi)
                    if np.sum(m) == 0:
                        continue
                    vals.append(float(np.mean(y[m])))
                vals_arr = np.asarray(vals, dtype=float)
                n = int(np.sum(np.isfinite(vals_arr)))
                mean = float(np.nanmean(vals_arr)) if n else float("nan")
                std = float(np.nanstd(vals_arr, ddof=1)) if n >= 2 else float("nan")
                cv = float(std / mean) if np.isfinite(std) and np.isfinite(mean) and mean != 0 else float("nan")
                if n < 3:
                    quality = "insufficient"
                    cv = float("nan")
                elif np.isfinite(cv):
                    if cv < 0.3:
                        quality = "good"
                    elif cv < 0.5:
                        quality = "medium"
                    else:
                        quality = "bad"
                else:
                    quality = ""
                q_rows.append(
                    {
                        "group": group_name,
                        "bin_lo": float(lo),
                        "bin_hi": float(hi),
                        "n_events": int(n),
                        "mean_Dnorm": float(mean),
                        "std_Dnorm": float(std),
                        "cv": float(cv),
                        "quality": str(quality),
                    }
                )

        _group_quality("all", None)
        _group_quality("EVAC", {"EVAC"})
        _group_quality("INFL", {"INFL"})

    q_df = pd.DataFrame(q_rows)
    q_df.to_csv(tabs / "Dt_collapse_quality.csv", index=False)

    # figures (optional)
    try:
        from disaster import plot_style as ps  # type: ignore
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        meta = {
            "output_root": str(output_root),
            "n_events": int(len(want)),
            "r_max_km": float(r_max_km),
            "near_r_km": float(near_r_km),
            "min_tiles_overlap": int(min_tiles_overlap),
            "min_r_bins": int(min_r_bins),
            "min_near_bins": int(min_near_bins),
        }
        (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    # palette: EVAC red, INFL blue, others gray
    color_map = {"EVAC": ps.OKABE_ITO["vermillion"], "INFL": ps.OKABE_ITO["blue"], "LOW_SIGNAL": ps.OKABE_ITO["gray"], "NEUTRAL": ps.OKABE_ITO["gray"]}

    # Fig 1 (teaching): 灰色底图 + 2-4条代表性高亮，仅用于解释 D(t') 与 α
    if not dt_df.empty and not route_b_sample_df.empty:
        base_sample = route_b_sample_df.copy()
        plot_slugs = set(base_sample.loc[base_sample["route_b_base_ok"], "slug"].astype(str).tolist())
        pass_df = base_sample[base_sample["route_b_selected_plot"]].copy()

        # 高亮事件：优先使用显式指定，否则自动取低/中/高 alpha 三个代表
        highlight_slugs: list[str] = []
        manual = [str(s).strip() for s in (route_b_teach_highlight_slugs or []) if str(s).strip()]
        if manual:
            highlight_slugs = [s for s in manual if s in set(pass_df["slug"].astype(str).tolist())]
        else:
            tmp = pass_df.copy().sort_values("alpha", kind="stable")
            if not tmp.empty:
                low = str(tmp.iloc[0]["slug"])
                mid = str(tmp.iloc[int(len(tmp) // 2)]["slug"])
                high = str(tmp.iloc[-1]["slug"])
                seen = set()
                for s in [low, mid, high]:
                    if s not in seen:
                        highlight_slugs.append(s)
                        seen.add(s)

        highlight_colors = ["#d55e00", "#0072b2", "#009e73", "#cc79a7"]
        color_by_slug = {slug: highlight_colors[i % len(highlight_colors)] for i, slug in enumerate(highlight_slugs)}

        d = dt_df.copy()
        d = d[pd.to_numeric(d["hours_since_quake"], errors="coerce") > pd.to_numeric(d["t_peak_hours"], errors="coerce")].copy()
        d["t_prime_h"] = pd.to_numeric(d["hours_since_quake"], errors="coerce") - pd.to_numeric(d["t_peak_hours"], errors="coerce")
        d = d[(pd.to_numeric(d["t_prime_h"], errors="coerce") > 0) & (pd.to_numeric(d["D_norm"], errors="coerce") > 0)].copy()

        with ps.paper_style():
            fig, ax = plt.subplots(figsize=(7.2, 4.8))
            for slug, sub in d.groupby("slug", sort=False):
                slug = str(slug)
                if plot_slugs and slug not in plot_slugs:
                    continue

                sub = sub.sort_values("t_prime_h", kind="stable")
                x = pd.to_numeric(sub["t_prime_h"], errors="coerce").to_numpy(dtype=float)
                y = pd.to_numeric(sub["D_norm"], errors="coerce").to_numpy(dtype=float)
                ok = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
                x = x[ok]
                y = y[ok]
                if x.size < 3:
                    continue

                mono = _monotone_decay_segment(pd.DataFrame({"t_prime_h": x, "D_norm": y}), tol_up=float(mono_tol_up))
                mx = pd.to_numeric(mono["t_prime_h"], errors="coerce").to_numpy(dtype=float)
                my = pd.to_numeric(mono["D_norm"], errors="coerce").to_numpy(dtype=float)
                m_ok = np.isfinite(mx) & np.isfinite(my) & (mx > 0) & (my > 0)
                mx = mx[m_ok]
                my = my[m_ok]
                if mx.size < 3:
                    continue

                # 背景：全部基础样本统一浅灰
                ax.plot(mx, my, color="#bfbfbf", alpha=0.55, lw=1.2)

                # 高亮：仅代表事件画拟合与 alpha 标注
                if slug in color_by_slug:
                    c = color_by_slug[slug]
                    ax.plot(mx, my, color=c, alpha=0.98, lw=2.2)
                    ax.scatter(mx, my, s=16, color=c, alpha=0.9, linewidths=0, rasterized=True)
                    alpha, logA, _ = _fit_powerlaw_loglog(mx, my)
                    if np.isfinite(alpha) and np.isfinite(logA):
                        xx = np.geomspace(max(float(np.min(mx)), 1e-3), max(float(np.max(mx)), float(np.min(mx)) * 1.01), 80)
                        yy = np.exp(float(logA)) * np.power(xx, -float(alpha))
                        ax.plot(xx, yy, color=c, alpha=0.95, lw=1.8, ls="--")
                        lbl = str(base_sample.loc[base_sample["slug"].astype(str) == slug, "short_name"].iloc[0]) if np.any(base_sample["slug"].astype(str) == slug) else slug
                        ax.text(float(xx[-1]), float(yy[-1]), f"{lbl}: α={alpha:.2f}", fontsize=7, color=c, ha="left", va="center", alpha=0.95)

            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_xlim(left=20.0)
            ax.set_xlabel("t' = t - t_peak (hours)")
            ax.set_ylabel("D(t') / D_peak")
            ax.set_title("Dt decay (log-log): monotone segment and slope α")
            ps.despine(ax)
            fig.tight_layout()
            ps.save_figure(fig, figs / "Dt_decay_all_events_loglog.png", dpi=220)
            ps.save_figure(fig, figs / "Dt_decay_all_events_loglog.pdf")
            plt.close(fig)

    # Fig 1b: Route B 核心散点（alpha vs delta_near）
    if not route_b_sample_df.empty:
        import matplotlib.colors as mcolors

        ss = route_b_sample_df[route_b_sample_df["route_b_selected"]].copy()
        ex = route_b_sample_df[(route_b_sample_df["route_b_base_ok"]) & (~route_b_sample_df["route_b_selected"])].copy()

        if not ss.empty:
            with ps.paper_style():
                fig, ax = plt.subplots(figsize=(6.0, 4.6))

                x = pd.to_numeric(ss["near_delta_peak_windows_mean"], errors="coerce").to_numpy(dtype=float)
                y = pd.to_numeric(ss["alpha"], errors="coerce").to_numpy(dtype=float)
                keep = np.isfinite(x) & np.isfinite(y)
                x = x[keep]
                y = y[keep]
                ss_plot = ss.loc[keep].copy()

                vmax = float(max(abs(float(np.nanmin(x))), abs(float(np.nanmax(x))), 1e-6)) if x.size else 1.0
                cmap = plt.get_cmap("RdBu")
                norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)

                for _, r in ss_plot.iterrows():
                    xv = float(r["near_delta_peak_windows_mean"])
                    yv = float(r["alpha"])
                    c = cmap(norm(xv))
                    ax.scatter(xv, yv, s=40, color=c, alpha=0.92, linewidths=0)
                    ax.text(xv, yv, str(r.get("short_name", "")), fontsize=7, ha="left", va="bottom", alpha=0.9)

                if not ex.empty:
                    exx = pd.to_numeric(ex["near_delta_peak_windows_mean"], errors="coerce").to_numpy(dtype=float)
                    exy = pd.to_numeric(ex["alpha"], errors="coerce").to_numpy(dtype=float)
                    k2 = np.isfinite(exx) & np.isfinite(exy)
                    if np.any(k2):
                        ax.scatter(exx[k2], exy[k2], s=46, color="#9b9b9b", marker="x", alpha=0.9, linewidths=1.3)
                        for _, r in ex.loc[k2].iterrows():
                            ax.text(float(r["near_delta_peak_windows_mean"]), float(r["alpha"]), str(r.get("short_name", "")), fontsize=7, color="#666666", ha="left", va="bottom", alpha=0.85)

                rho, pval = (float("nan"), float("nan"))
                if ss_plot.shape[0] >= 3:
                    rho, pval = spearmanr(
                        pd.to_numeric(ss_plot["near_delta_peak_windows_mean"], errors="coerce").to_numpy(dtype=float),
                        pd.to_numeric(ss_plot["alpha"], errors="coerce").to_numpy(dtype=float),
                    )
                    rho, pval = float(rho), float(pval)

                if ss_plot.shape[0] >= 3:
                    slope, intercept, _, _ = theilslopes(
                        pd.to_numeric(ss_plot["alpha"], errors="coerce").to_numpy(dtype=float),
                        pd.to_numeric(ss_plot["near_delta_peak_windows_mean"], errors="coerce").to_numpy(dtype=float),
                        0.95,
                    )
                    xmin = float(np.nanmin(pd.to_numeric(ss_plot["near_delta_peak_windows_mean"], errors="coerce").to_numpy(dtype=float)))
                    xmax = float(np.nanmax(pd.to_numeric(ss_plot["near_delta_peak_windows_mean"], errors="coerce").to_numpy(dtype=float)))
                    xx = np.linspace(xmin, xmax, 100)
                    yy = float(intercept) + float(slope) * xx
                    ax.plot(xx, yy, color="#333333", lw=1.6, ls="--", alpha=0.8)

                ax.axvline(0.0, color="#666666", lw=1.0, ls=":", alpha=0.6)
                ax.set_xlabel("δ_near")
                ax.set_ylabel("α")
                ax.set_title("Route B: α vs δ_near")
                ax.text(0.02, 0.98, f"Spearman ρ={rho:.3f}, p={pval:.3f}", transform=ax.transAxes, ha="left", va="top", fontsize=9)

                sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
                sm.set_array([])
                cbar = fig.colorbar(sm, ax=ax, pad=0.02, shrink=0.92)
                cbar.set_label("δ_near")

                ps.despine(ax)
                fig.tight_layout()
                ps.save_figure(fig, figs / "Dt_alpha_vs_delta_routeB.png", dpi=220)
                ps.save_figure(fig, figs / "Dt_alpha_vs_delta_routeB.pdf")
                plt.close(fig)

    # Fig 1c: Route B 补充（alpha vs D_inf）
    if not route_b_sample_df.empty:
        ss_d = route_b_sample_df[route_b_sample_df["route_b_selected"]].copy()
        ss_d = ss_d[pd.to_numeric(ss_d["D_inf"], errors="coerce").notna()].copy()
        if ss_d.shape[0] >= 3:
            with ps.paper_style():
                fig, ax = plt.subplots(figsize=(5.6, 4.2))
                x = pd.to_numeric(ss_d["D_inf"], errors="coerce").to_numpy(dtype=float)
                y = pd.to_numeric(ss_d["alpha"], errors="coerce").to_numpy(dtype=float)
                k = np.isfinite(x) & np.isfinite(y)
                x = x[k]
                y = y[k]
                ss_d = ss_d.loc[k].copy()
                ax.scatter(x, y, s=36, color="#4c78a8", alpha=0.85, linewidths=0)
                for _, r in ss_d.iterrows():
                    ax.text(float(r["D_inf"]), float(r["alpha"]), str(r.get("short_name", "")), fontsize=7, ha="left", va="bottom", alpha=0.85)
                rho_d, p_d = spearmanr(x, y)
                ax.text(0.02, 0.98, f"Spearman ρ={float(rho_d):.3f}, p={float(p_d):.3f}", transform=ax.transAxes, ha="left", va="top", fontsize=9)
                ax.set_xlabel("D_inf")
                ax.set_ylabel("α")
                ax.set_title("Route B: α vs D_inf")
                ps.despine(ax)
                fig.tight_layout()
                ps.save_figure(fig, figs / "Dt_alpha_vs_Dinf_routeB.png", dpi=220)
                ps.save_figure(fig, figs / "Dt_alpha_vs_Dinf_routeB.pdf")
                plt.close(fig)

    # Fig 2 已停用：离散EVAC/INFL分组图不再作为主线输出（保留连续变量散点 Fig 1b）。

    # Fig 3: collapse plots
    if not dt_df.empty and not collapse_df.empty:
        dt_post = dt_df.copy()
        dt_post = dt_post[pd.to_numeric(dt_post["hours_since_quake"], errors="coerce") > pd.to_numeric(dt_post["t_peak_hours"], errors="coerce")].copy()
        dt_post["t_prime_h"] = pd.to_numeric(dt_post["hours_since_quake"], errors="coerce") - pd.to_numeric(dt_post["t_peak_hours"], errors="coerce")
        dt_post = dt_post.merge(collapse_df[["slug", "tau50_h", "tau50_lower_bound"]], on="slug", how="left")
        dt_post["t_tilde"] = pd.to_numeric(dt_post["t_prime_h"], errors="coerce") / pd.to_numeric(dt_post["tau50_h"], errors="coerce")
        dt_post = dt_post[(pd.to_numeric(dt_post["t_tilde"], errors="coerce") >= 0) & (pd.to_numeric(dt_post["t_tilde"], errors="coerce") <= 3.2)].copy()

        def _plot_collapse(df_in: pd.DataFrame, out_name: str, title: str) -> None:
            if df_in.empty:
                return
            with ps.paper_style():
                fig, ax = plt.subplots(figsize=(6.4, 3.9))
                for slug, sub in df_in.groupby("slug", sort=False):
                    et = str(sub["event_type"].iloc[0])
                    c = color_map.get(et, ps.OKABE_ITO["gray"])
                    x = pd.to_numeric(sub["t_tilde"], errors="coerce").to_numpy(dtype=float)
                    y = pd.to_numeric(sub["D_norm"], errors="coerce").to_numpy(dtype=float)
                    ok = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
                    x = x[ok]
                    y = y[ok]
                    if x.size < 2:
                        continue
                    ax.scatter(x, y, s=10, alpha=0.35, color=c, linewidths=0, rasterized=True)
                ax.set_xscale("linear")
                ax.set_yscale("log")
                ax.set_xlabel("t' / tau50")
                ax.set_ylabel("D(t') / D_peak")
                ax.set_title(title)
                ps.despine(ax)
                fig.tight_layout()
                ps.save_figure(fig, figs / f"{out_name}.png", dpi=220)
                ps.save_figure(fig, figs / f"{out_name}.pdf")
                plt.close(fig)

        _plot_collapse(dt_post, "Dt_collapse_all", "Collapse: all events")

    # Fig 4: panels of D(t) absolute (linear) + peak + mono segment highlight
    if not dt_df.empty:
        # build per-event mono segments in original time coordinates
        mono_map: dict[str, tuple[float, float]] = {}
        d_inf_abs_map: dict[str, float] = {}
        if not fits_df.empty:
            for _, r in fits_df.iterrows():
                slug = str(r.get("slug", ""))
                t_peak_h = _safe_float(r.get("t_peak_hours"))
                t0 = _safe_float(r.get("t_decay_start"))
                t1 = _safe_float(r.get("t_decay_end"))
                d_inf_abs = _safe_float(r.get("D_inf_abs"))
                if slug and d_inf_abs is not None and np.isfinite(d_inf_abs):
                    d_inf_abs_map[slug] = float(d_inf_abs)
                if not slug or t_peak_h is None or t0 is None or t1 is None:
                    continue
                mono_map[slug] = (float(t_peak_h + t0), float(t_peak_h + t1))

        panel_df = dt_df.copy()
        panel_df["hours_since_quake"] = pd.to_numeric(panel_df["hours_since_quake"], errors="coerce")
        panel_df["D"] = pd.to_numeric(panel_df["D"], errors="coerce")
        panel_df = panel_df.dropna(subset=["hours_since_quake", "D"]).copy()
        slugs_order = summary_df.sort_values(["D_peak"], ascending=False, kind="stable")["slug"].astype(str).tolist() if not summary_df.empty else sorted(panel_df["slug"].astype(str).unique().tolist())

        n = len(slugs_order)
        ncols = 6
        nrows = int(np.ceil(n / ncols)) if n else 1
        with ps.paper_style():
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(3.1 * ncols, 2.0 * nrows), squeeze=False)
            for i, slug in enumerate(slugs_order):
                ax = axes[i // ncols][i % ncols]
                sub = panel_df[panel_df["slug"] == slug].sort_values("hours_since_quake", kind="stable")
                x = sub["hours_since_quake"].to_numpy(dtype=float)
                y = sub["D"].to_numpy(dtype=float)
                et = str(sub["event_type"].iloc[0]) if not sub.empty else ""
                c = color_map.get(et, ps.OKABE_ITO["gray"])
                ax.plot(x, y, color=c, lw=1.7, marker="o", ms=3.2, alpha=0.9)
                # peak marker
                try:
                    t_peak = float(sub["t_peak_hours"].iloc[0])
                    D_peak = float(sub["D_peak"].iloc[0])
                    ax.scatter([t_peak], [D_peak], s=28, color="black", zorder=5)
                except Exception:
                    pass
                # mono segment highlight
                if slug in mono_map:
                    a, b = mono_map[slug]
                    ax.axvspan(a, b, color=c, alpha=0.12, lw=0)
                # D_inf 水平线（尾部 1/3 的归一化均值再还原到 D 量纲）
                if slug in d_inf_abs_map:
                    ax.axhline(float(d_inf_abs_map[slug]), color="black", lw=1.0, ls="--", alpha=0.4)
                ax.set_title(str(sub["short_name"].iloc[0]) if not sub.empty else slug, fontsize=9)
                ax.set_xlabel("t (h)")
                ax.set_ylabel("D")
                ps.despine(ax)
            for j in range(n, nrows * ncols):
                axes[j // ncols][j % ncols].axis("off")
            fig.tight_layout()
            ps.save_figure(fig, figs / "Dt_timeseries_panels.png", dpi=220)
            ps.save_figure(fig, figs / "Dt_timeseries_panels.pdf")
            plt.close(fig)

    meta = {
        "output_root": str(output_root),
        "catalog": (str(catalog) if catalog is not None else ""),
        "config_json": (str(config_json_path) if config_json_path is not None else ""),
        "config_payload": dict(config_payload or {}),
        "n_events": int(len(want)),
        "r_max_km": float(r_max_km),
        "near_r_km": float(near_r_km),
        "min_tiles_overlap": int(min_tiles_overlap),
        "min_r_bins": int(min_r_bins),
        "min_near_bins": int(min_near_bins),
        "peak_min_hours": (float(peak_min_hours) if peak_min_hours is not None else None),
        "peak_max_hours": (float(peak_max_hours) if peak_max_hours is not None else None),
        "D_peak_min": (float(D_peak_min) if D_peak_min is not None else None),
        "snr_threshold": (float(snr_threshold) if snr_threshold is not None else None),
        "min_time_windows": int(min_time_windows),
        "min_post_peak_steps": int(min_post_peak_steps),
        "fit_method": str(fit_method),
        "fit_min_tprime_hours": float(fit_min_tprime_hours),
        "peak_frac": float(peak_frac),
        "near_thresh": float(near_thresh),
        "mono_tol_up": float(mono_tol_up),
        "route_b_min_n_mono": int(route_b_min_n_mono),
        "route_b_low_r2_threshold": float(route_b_low_r2_threshold),
        "route_b_exclude_slugs": sorted(route_b_exclude),
        "route_b_exclude_slugs_from_catalog": sorted(route_b_exclude_from_catalog),
        "route_b_exclude_slugs_from_cli": sorted(route_b_exclude_from_cli),
        "route_b_catalog_exclude_reasons": {k: catalog_exclude_reasons[k] for k in sorted(catalog_exclude_reasons)},
        "route_b_teach_highlight_slugs": [str(x).strip() for x in (route_b_teach_highlight_slugs or []) if str(x).strip()],
        "slugs": want,
        "exclude_slugs": sorted(exclude),
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def cli_main() -> None:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", type=Path, default=None)
    pre.add_argument("--config-json", type=Path, default=None)
    pre_args, _ = pre.parse_known_args()
    cfg_path = pre_args.config if pre_args.config is not None else pre_args.config_json
    cfg_params, cfg_payload, cfg_loaded_path = _load_config(cfg_path)

    def _cfg(name: str, default: object) -> object:
        return cfg_params.get(name, default)

    def _cfg_path(name: str, default: Path | None) -> Path | None:
        v = cfg_params.get(name, default)
        if v is None:
            return None
        return Path(str(v))

    def _cfg_list(name: str, default: list[str]) -> list[str]:
        v = cfg_params.get(name, default)
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x) for x in v]
        return [str(v)]

    p = argparse.ArgumentParser(description="SVD-free: 计算 D(t) 并做衰减拟合/模型比较/坍缩与可视化")
    p.add_argument("--config", type=Path, default=(pre_args.config if pre_args.config is not None else cfg_loaded_path), help="配置文件（推荐，支持 JSON/YAML）")
    p.add_argument("--config-json", type=Path, default=pre_args.config_json, help="阈值配置 JSON（可选，CLI 参数优先于配置）")
    p.add_argument("--catalog", type=Path, default=_cfg_path("catalog", None), help="可选：用于读取 exclude_reason 的 catalog")
    p.add_argument("--use-catalog-exclude-reason", type=int, choices=[0, 1], default=int(_cfg("use_catalog_exclude_reason", 1)))

    p.add_argument("--output-root", type=Path, default=_cfg_path("output_root", Path("outputs")), help="输入根目录：包含 <slug>/phi_heatmap/tables/phi_rt_long.csv")
    p.add_argument("--out-dir", type=Path, default=_cfg_path("out_dir", Path("outputs/cross_disaster_comparison/Dt_decay")))
    p.add_argument("--slugs", type=str, nargs="*", default=_cfg_list("slugs", []), help="可选：只跑指定 slugs（空或 all=自动发现）")
    p.add_argument("--exclude-slugs", type=str, nargs="*", default=_cfg_list("exclude_slugs", []), help="可选：剔除指定 slugs")

    p.add_argument("--r-max-km", type=float, default=float(_cfg("r_max_km", 200.0)))
    p.add_argument("--near-r-km", type=float, default=float(_cfg("near_r_km", 50.0)))
    p.add_argument("--min-tiles-overlap", type=int, default=int(_cfg("min_tiles_overlap", 3)))
    p.add_argument("--min-r-bins", type=int, default=int(_cfg("min_r_bins", 5)))
    p.add_argument("--min-near-bins", type=int, default=int(_cfg("min_near_bins", 2)))

    p.add_argument("--peak-min-hours", type=float, default=_cfg("peak_min_hours", None), help="peak 搜索的最小 t（小时）。默认不限制（允许灾前 peak）。")
    p.add_argument("--peak-max-hours", type=float, default=_cfg("peak_max_hours", None))
    p.add_argument("--D-peak-min", type=float, default=_cfg("D_peak_min", 0.03))
    p.add_argument("--snr-threshold", type=float, default=_cfg("snr_threshold", None))
    p.add_argument("--min-time-windows", type=int, default=int(_cfg("min_time_windows", 5)))
    p.add_argument("--min-post-peak-steps", type=int, default=int(_cfg("min_post_peak_steps", 4)))
    p.add_argument("--peak-frac", type=float, default=float(_cfg("peak_frac", 0.5)))
    p.add_argument("--near-thresh", type=float, default=float(_cfg("near_thresh", 0.02)))
    p.add_argument("--fit-method", type=str, choices=["full_post_peak", "monotone_truncated"], default=str(_cfg("fit_method", "monotone_truncated")))
    p.add_argument("--fit-min-tprime-hours", type=float, default=float(_cfg("fit_min_tprime_hours", 0.0)))

    p.add_argument("--mono-tol-up", type=float, default=float(_cfg("mono_tol_up", 1.05)), help="单调衰减段允许的上升比例（默认 1.05=5%%）")
    p.add_argument("--route-b-min-n-mono", type=int, default=int(_cfg("route_b_min_n_mono", 3)), help="Route B: 基础样本最小单调段点数")
    p.add_argument("--route-b-low-r2-threshold", type=float, default=float(_cfg("route_b_low_r2_threshold", 0.60)), help="Route B: 低R²阈值（低于该值的事件在图中置灰）")
    p.add_argument(
        "--route-b-exclude-slugs",
        type=str,
        nargs="*",
        default=_cfg_list("route_b_exclude_slugs", []),
        help="Route B: 额外手动排除的事件 slugs（建议改由 catalog.exclude_reason 管理）",
    )
    p.add_argument(
        "--route-b-teach-highlight-slugs",
        type=str,
        nargs="*",
        default=_cfg_list("route_b_teach_highlight_slugs", []),
        help="教学版log-log高亮事件（默认自动选低/中/高 alpha）",
    )

    args = p.parse_args()
    config_path_runtime = args.config if args.config is not None else args.config_json
    cfg_payload_used = cfg_payload if config_path_runtime is not None else {}
    catalog_exclude_reasons = {}
    if int(args.use_catalog_exclude_reason) == 1 and args.catalog is not None:
        catalog_exclude_reasons = _load_catalog_exclude_reasons(Path(args.catalog))

    run(
        output_root=Path(args.output_root),
        out_dir=Path(args.out_dir),
        catalog=(Path(args.catalog) if args.catalog is not None else None),
        slugs=list(args.slugs or []),
        exclude_slugs=list(args.exclude_slugs or []),
        r_max_km=float(args.r_max_km),
        near_r_km=float(args.near_r_km),
        min_tiles_overlap=int(args.min_tiles_overlap),
        min_r_bins=int(args.min_r_bins),
        min_near_bins=int(args.min_near_bins),
        peak_min_hours=args.peak_min_hours,
        peak_max_hours=(float(args.peak_max_hours) if args.peak_max_hours is not None else None),
        D_peak_min=(float(args.D_peak_min) if args.D_peak_min is not None else None),
        snr_threshold=(float(args.snr_threshold) if args.snr_threshold is not None else None),
        min_time_windows=int(args.min_time_windows),
        min_post_peak_steps=int(args.min_post_peak_steps),
        peak_frac=float(args.peak_frac),
        near_thresh=float(args.near_thresh),
        fit_method=str(args.fit_method),
        fit_min_tprime_hours=float(args.fit_min_tprime_hours),
        mono_tol_up=float(args.mono_tol_up),
        route_b_min_n_mono=int(args.route_b_min_n_mono),
        route_b_low_r2_threshold=float(args.route_b_low_r2_threshold),
        route_b_exclude_slugs=list(args.route_b_exclude_slugs or []),
        catalog_exclude_reasons=dict(catalog_exclude_reasons),
        route_b_teach_highlight_slugs=list(args.route_b_teach_highlight_slugs or []),
        config_json_path=(Path(config_path_runtime) if config_path_runtime is not None else None),
        config_payload=cfg_payload_used,
    )


if __name__ == "__main__":
    cli_main()
