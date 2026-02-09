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
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：scipy。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.plot_style import apply_paper_style, save_figure


@dataclass(frozen=True)
class EventRef:
    output_root: Path
    slug: str


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _parse_event_ref(s: str) -> EventRef:
    s = str(s).strip()
    if ":" not in s:
        raise SystemExit(f"--event 格式错误：{s}（期望 <output_root>:<slug>）")
    root, slug = s.split(":", 1)
    root_p = Path(root)
    if not root_p.exists():
        raise SystemExit(f"--event output_root 不存在：{root_p}")
    slug = slug.strip()
    if not slug:
        raise SystemExit(f"--event slug 为空：{s}")
    return EventRef(output_root=root_p, slug=slug)


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


def _load_metadata(output_root: Path, slug: str) -> tuple[str, str]:
    p = Path(output_root) / slug / "metadata.json"
    if not p.exists():
        return slug, slug.split("_", 1)[0]
    try:
        meta = json.loads(p.read_text(encoding="utf-8"))
        name = str(meta.get("name") or slug)
        event_type = str(meta.get("event_type") or slug.split("_", 1)[0])
        return name, event_type
    except Exception:
        return slug, slug.split("_", 1)[0]


def _load_phi_rt_long(output_root: Path, slug: str) -> pd.DataFrame:
    p = Path(output_root) / slug / "phi_heatmap" / "tables" / "phi_rt_long.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    for c in ["hours_since_quake", "r_bin_km", "phi_overlap", "phi_aggregate"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["hours_since_quake", "r_bin_km"]).copy()
    return df


def _sign_fix(u: np.ndarray, vt: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    u = np.asarray(u, dtype=float)
    vt = np.asarray(vt, dtype=float)
    if k < 0 or k >= u.shape[1]:
        return u, vt
    s = float(np.nansum(u[:, k]))
    if np.isfinite(s) and s < 0:
        u[:, k] *= -1.0
        vt[k, :] *= -1.0
    return u, vt


def _svd_g1(
    *,
    df: pd.DataFrame,
    value_col: str,
    r_max_km: float,
    time_min: float | None,
    time_max: float | None,
    complete_only: bool,
) -> dict:
    sub = df.copy()
    if np.isfinite(float(r_max_km)):
        sub = sub[pd.to_numeric(sub["r_bin_km"], errors="coerce") <= float(r_max_km)].copy()
    if time_min is not None:
        sub = sub[pd.to_numeric(sub["hours_since_quake"], errors="coerce") >= float(time_min)].copy()
    if time_max is not None:
        sub = sub[pd.to_numeric(sub["hours_since_quake"], errors="coerce") <= float(time_max)].copy()
    if sub.empty:
        return {"ok": 0}

    pivot = sub.pivot_table(index="r_bin_km", columns="hours_since_quake", values=value_col, aggfunc="first")
    pivot = pivot.sort_index(axis=0).sort_index(axis=1)
    r = pivot.index.to_numpy(dtype=float)
    t = pivot.columns.to_numpy(dtype=float)
    m = pivot.to_numpy(dtype=float)
    dev = m - 1.0

    r_used = r
    t_used = t
    dev_used = dev
    mode_used = "drop_complete" if bool(complete_only) else "fill_missing"
    if bool(complete_only):
        ok_r = np.all(np.isfinite(dev), axis=1)
        ok_t = np.all(np.isfinite(dev), axis=0)
        dev_used = dev[np.where(ok_r)[0][:], :][:, np.where(ok_t)[0]]
        r_used = r[ok_r]
        t_used = t[ok_t]
        if dev_used.size == 0 or dev_used.shape[0] < 2 or dev_used.shape[1] < 2:
            mode_used = "fill_missing_fallback"
            dev_used = np.where(np.isfinite(dev), dev, 0.0)
            r_used = r
            t_used = t
    else:
        dev_used = np.where(np.isfinite(dev), dev, 0.0)

    if dev_used.size == 0 or dev_used.shape[0] < 2 or dev_used.shape[1] < 2:
        return {"ok": 0, "mode_used": mode_used}

    u, s, vt = np.linalg.svd(dev_used, full_matrices=False)
    u, vt = _sign_fix(u, vt, 0)
    e = float(np.sum(np.square(s[np.isfinite(s)])))
    frac = float((s[0] ** 2) / e) if s.size and np.isfinite(e) and e > 0 else float("nan")
    v1 = vt[0, :] if vt.shape[0] else np.array([], dtype=float)
    g1 = float(s[0]) * v1 if s.size else np.array([], dtype=float)

    return {
        "ok": 1,
        "sigma1_energy": float(frac),
        "mode_used": str(mode_used),
        "t_used": np.asarray(t_used, dtype=float),
        "g1": np.asarray(g1, dtype=float),
        "n_r_bins_used": int(dev_used.shape[0]),
        "n_time_used": int(dev_used.shape[1]),
    }


def _bic_from_sse(*, sse: float, n: int, k: int) -> float:
    if n <= 0 or k <= 0 or not np.isfinite(sse):
        return float("nan")
    sse = float(max(sse, 1e-12))
    return float(n * np.log(sse / float(n)) + float(k) * np.log(float(n)))


def _fit_line(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    slope, intercept = np.polyfit(x, y, deg=1)
    y_hat = slope * x + intercept
    ss_res = float(np.sum(np.square(y - y_hat)))
    ss_tot = float(np.sum(np.square(y - float(np.mean(y))))) if y.size else float("nan")
    r2 = float(1.0 - ss_res / ss_tot) if np.isfinite(ss_tot) and ss_tot > 0 else float("nan")
    return float(slope), float(intercept), float(r2)


def _select_fit_range(t: np.ndarray, y: np.ndarray, *, fit_mode: str, fit_tmin_hours: float, min_fit_points: int) -> tuple[np.ndarray, np.ndarray, float]:
    ok = np.isfinite(t) & np.isfinite(y) & (t > 0) & (y > 0)
    t0 = np.asarray(t[ok], dtype=float)
    y0 = np.asarray(y[ok], dtype=float)
    if t0.size == 0:
        return np.array([]), np.array([]), float("nan")

    fit_mode = str(fit_mode).strip()
    if fit_mode not in {"from_peak", "from_tmin"}:
        raise SystemExit(f"--fit-mode 不支持：{fit_mode}（仅支持 from_peak/from_tmin）")

    if fit_mode == "from_peak":
        i = int(np.argmax(y0))
        t_start = float(t0[i])
    else:
        t_start = float(fit_tmin_hours)

    m = t0 >= t_start
    t1 = t0[m]
    y1 = y0[m]
    if t1.size < int(min_fit_points):
        return np.array([]), np.array([]), float(t_start)
    return t1, y1, float(t_start)


def _fit_powerlaw(t: np.ndarray, y: np.ndarray) -> dict:
    x = np.log(t)
    yy = np.log(y)
    slope, intercept, r2 = _fit_line(x, yy)
    yy_hat = slope * x + intercept
    sse = float(np.sum(np.square(yy - yy_hat)))
    return {"fit_ok": 1, "alpha": float(-slope), "logA": float(intercept), "tau": float("nan"), "beta": float("nan"), "sse_log": float(sse), "r2_log": float(r2), "k": 2}


def _fit_exponential(t: np.ndarray, y: np.ndarray) -> dict:
    x = t
    yy = np.log(y)
    slope, intercept, r2 = _fit_line(x, yy)
    yy_hat = slope * x + intercept
    sse = float(np.sum(np.square(yy - yy_hat)))
    tau = float(-1.0 / slope) if np.isfinite(slope) and slope != 0 else float("nan")
    return {"fit_ok": 1, "alpha": float("nan"), "logA": float(intercept), "tau": float(tau), "beta": float("nan"), "sse_log": float(sse), "r2_log": float(r2), "k": 2}


def _fit_stretched_exp(t: np.ndarray, y: np.ndarray) -> dict:
    tt = np.asarray(t, dtype=float)
    yy = np.asarray(np.log(y), dtype=float)

    def f_log(t_in: np.ndarray, logA: float, log_tau: float, beta: float) -> np.ndarray:
        tau = np.exp(log_tau)
        return logA - np.power(np.asarray(t_in, dtype=float) / tau, beta)

    logA0 = float(np.nanmax(yy)) if yy.size else 0.0
    log_tau0 = float(np.log(np.nanmedian(tt))) if tt.size and np.nanmedian(tt) > 0 else 0.0
    p0 = (logA0, log_tau0, 1.0)
    bounds = ([-np.inf, -np.inf, 0.1], [np.inf, np.inf, 5.0])
    try:
        popt, _ = curve_fit(f_log, tt, yy, p0=p0, bounds=bounds, maxfev=20000)
        logA, log_tau, beta = float(popt[0]), float(popt[1]), float(popt[2])
        yy_hat = f_log(tt, logA, log_tau, beta)
        sse = float(np.sum(np.square(yy - yy_hat)))
        ss_tot = float(np.sum(np.square(yy - float(np.mean(yy))))) if yy.size else float("nan")
        r2 = float(1.0 - sse / ss_tot) if np.isfinite(ss_tot) and ss_tot > 0 else float("nan")
        return {
            "fit_ok": 1,
            "alpha": float("nan"),
            "logA": float(logA),
            "tau": float(np.exp(log_tau)),
            "beta": float(beta),
            "sse_log": float(sse),
            "r2_log": float(r2),
            "k": 3,
        }
    except Exception:
        return {"fit_ok": 0}


def run(
    *,
    roots: list[Path],
    events: list[EventRef],
    slugs: list[str],
    exclude_slugs: list[str],
    out_dir: Path,
    value_col: str,
    r_max_km: float,
    time_min: float | None,
    time_max: float | None,
    complete_only: bool,
    fit_mode: str,
    fit_tmin_hours: float,
    min_fit_points: int,
    skip_figures: bool,
    max_plot_panels: int,
) -> None:
    out_dir = Path(out_dir)
    tabs = out_dir / "tables"
    figs = out_dir / "figures"
    _ensure_dir(tabs)
    _ensure_dir(figs)

    refs: dict[str, EventRef] = {}
    for root in roots:
        for ref in _discover_events(root):
            refs[ref.slug] = ref
    for ref in events:
        refs[ref.slug] = ref
    if not refs:
        raise SystemExit("未发现任何可用事件（请检查 --root/--event）")

    want = [str(s).strip() for s in slugs if str(s).strip()]
    if want and len(want) == 1 and want[0].lower() == "all":
        want = []
    if not want:
        want = sorted(refs.keys())

    exclude = {str(s).strip() for s in (exclude_slugs or []) if str(s).strip()}
    if exclude:
        want = [s for s in want if s not in exclude]
    if not want:
        raise SystemExit("筛选后 slugs 为空（请检查 --slugs/--exclude-slugs）")

    value_col = str(value_col).strip()
    if value_col not in {"phi_overlap", "phi_aggregate"}:
        raise SystemExit(f"value_col 不支持：{value_col}")

    all_fit_rows: list[dict] = []
    best_rows: list[dict] = []
    series_rows: list[dict] = []

    for slug in want:
        if slug not in refs:
            raise SystemExit(f"未找到 slug：{slug}（请检查 --root/--event 扫描范围）")
        ref = refs[slug]
        name, event_type = _load_metadata(ref.output_root, slug)
        df = _load_phi_rt_long(ref.output_root, slug)

        m = _svd_g1(
            df=df,
            value_col=value_col,
            r_max_km=float(r_max_km),
            time_min=time_min,
            time_max=time_max,
            complete_only=bool(complete_only),
        )
        if int(m.get("ok", 0)) != 1:
            best_rows.append(
                {
                    "slug": slug,
                    "name": name,
                    "event_type": event_type,
                    "output_root": str(ref.output_root),
                    "fit_ok": 0,
                    "reason": "svd_failed_or_empty",
                }
            )
            continue

        t = np.asarray(m.get("t_used", np.array([], dtype=float)), dtype=float)
        g1 = np.asarray(m.get("g1", np.array([], dtype=float)), dtype=float)
        y = np.abs(g1)

        t_fit, y_fit, t_start = _select_fit_range(t, y, fit_mode=str(fit_mode), fit_tmin_hours=float(fit_tmin_hours), min_fit_points=int(min_fit_points))
        if t_fit.size == 0:
            best_rows.append(
                {
                    "slug": slug,
                    "name": name,
                    "event_type": event_type,
                    "output_root": str(ref.output_root),
                    "fit_ok": 0,
                    "reason": "insufficient_fit_points",
                    "t_start": float(t_start),
                }
            )
            continue

        for ti, yi in zip(t.tolist(), y.tolist(), strict=False):
            series_rows.append(
                {
                    "slug": slug,
                    "name": name,
                    "event_type": event_type,
                    "hours_since_quake": float(ti),
                    "abs_g1": float(yi),
                    "sigma1_energy": float(m.get("sigma1_energy", float("nan"))),
                    "mode_used": str(m.get("mode_used", "")),
                }
            )

        fits = {
            "power_law": _fit_powerlaw(t_fit, y_fit),
            "exponential": _fit_exponential(t_fit, y_fit),
            "stretched_exp": _fit_stretched_exp(t_fit, y_fit),
        }
        for model, fr in fits.items():
            if int(fr.get("fit_ok", 0)) != 1:
                continue
            n = int(t_fit.size)
            k = int(fr.get("k", 0))
            sse = float(fr.get("sse_log", float("nan")))
            bic = _bic_from_sse(sse=sse, n=n, k=k)
            all_fit_rows.append(
                {
                    "slug": slug,
                    "name": name,
                    "event_type": event_type,
                    "output_root": str(ref.output_root),
                    "value_col": value_col,
                    "r_max_km": float(r_max_km),
                    "time_min": time_min,
                    "time_max": time_max,
                    "complete_only": int(bool(complete_only)),
                    "sigma1_energy": float(m.get("sigma1_energy", float("nan"))),
                    "mode_used": str(m.get("mode_used", "")),
                    "fit_mode": str(fit_mode),
                    "t_start": float(t_start),
                    "n_fit": int(n),
                    "t_fit_min": float(np.min(t_fit)),
                    "t_fit_max": float(np.max(t_fit)),
                    "model": str(model),
                    "k_params": int(k),
                    "bic_log": float(bic),
                    "sse_log": float(sse),
                    "r2_log": float(fr.get("r2_log", float("nan"))),
                    "alpha": float(fr.get("alpha", float("nan"))),
                    "tau": float(fr.get("tau", float("nan"))),
                    "beta": float(fr.get("beta", float("nan"))),
                    "logA": float(fr.get("logA", float("nan"))),
                }
            )

        sub = pd.DataFrame([r for r in all_fit_rows if r["slug"] == slug])
        if sub.empty:
            best_rows.append({"slug": slug, "name": name, "event_type": event_type, "output_root": str(ref.output_root), "fit_ok": 0, "reason": "all_models_failed"})
            continue
        sub = sub.sort_values("bic_log", ascending=True, kind="stable")
        best = sub.iloc[0].to_dict()
        best_rows.append(
            {
                "slug": slug,
                "name": name,
                "event_type": event_type,
                "output_root": str(ref.output_root),
                "fit_ok": 1,
                "best_model": str(best.get("model", "")),
                "best_bic_log": float(best.get("bic_log", float("nan"))),
                "best_alpha": float(best.get("alpha", float("nan"))),
                "best_tau": float(best.get("tau", float("nan"))),
                "best_beta": float(best.get("beta", float("nan"))),
                "best_logA": float(best.get("logA", float("nan"))),
                "n_fit": int(best.get("n_fit", 0)),
                "t_start": float(best.get("t_start", float("nan"))),
                "sigma1_energy": float(best.get("sigma1_energy", float("nan"))),
            }
        )

    fit_df = pd.DataFrame(all_fit_rows)
    best_df = pd.DataFrame(best_rows)
    series_df = pd.DataFrame(series_rows)
    fit_df.to_csv(tabs / "g1_model_bic.csv", index=False)
    best_df.to_csv(tabs / "g1_model_bic_summary.csv", index=False)
    series_df.to_csv(tabs / "g1_abs_series.csv", index=False)

    meta = {
        "roots": [str(p) for p in roots],
        "events": [f"{e.output_root}:{e.slug}" for e in events],
        "slugs": want,
        "exclude_slugs": sorted(exclude),
        "value_col": value_col,
        "r_max_km": float(r_max_km),
        "time_min": time_min,
        "time_max": time_max,
        "complete_only": int(bool(complete_only)),
        "fit_mode": str(fit_mode),
        "fit_tmin_hours": float(fit_tmin_hours),
        "min_fit_points": int(min_fit_points),
        "skip_figures": int(bool(skip_figures)),
        "max_plot_panels": int(max_plot_panels),
    }

    if bool(skip_figures):
        (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    if int(max_plot_panels) > 0 and len(want) > int(max_plot_panels):
        meta = {**meta, "figures_skipped_reason": f"too_many_slugs({len(want)})"}
        (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    # Plot: for each slug, show data + best-fit curves for all models (if available).
    apply_paper_style()
    import matplotlib.pyplot as plt

    n_panels = len(want)
    fig, axes = plt.subplots(1, n_panels, figsize=(3.2 * max(n_panels, 1), 2.6), constrained_layout=True)
    if n_panels == 1:
        axes = [axes]
    for ax, slug in zip(axes, want, strict=False):
        sub_s = series_df[series_df["slug"] == slug].copy()
        if sub_s.empty:
            ax.set_title(slug)
            ax.text(0.5, 0.5, "no data", ha="center", va="center", transform=ax.transAxes)
            continue
        t = pd.to_numeric(sub_s["hours_since_quake"], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(sub_s["abs_g1"], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(t) & np.isfinite(y) & (t > 0) & (y > 0)
        t = t[ok]
        y = y[ok]
        if t.size:
            ax.scatter(t, y, s=12, color="black", alpha=0.75, label="|g1|")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("t (hours)")
        ax.set_ylabel("|g1(t)|")
        ax.set_title(slug)

        sub_f = fit_df[fit_df["slug"] == slug].copy()
        if sub_f.empty or t.size == 0:
            continue
        t_start = float(pd.to_numeric(sub_f["t_start"], errors="coerce").dropna().min()) if "t_start" in sub_f.columns else float("nan")
        if np.isfinite(t_start):
            ax.axvline(t_start, color="#777777", lw=1.2, ls="--", alpha=0.8)

        t_grid = np.geomspace(max(float(np.min(t)), 1e-3), float(np.max(t)), 200)
        for model, color in [("power_law", "#0072B2"), ("exponential", "#D55E00"), ("stretched_exp", "#009E73")]:
            mrow = sub_f[sub_f["model"] == model].head(1)
            if mrow.empty:
                continue
            r = mrow.iloc[0]
            logA = float(r.get("logA", float("nan")))
            if model == "power_law":
                alpha = float(r.get("alpha", float("nan")))
                if np.isfinite(alpha) and np.isfinite(logA):
                    y_hat = np.exp(logA) * np.power(t_grid, -alpha)
                else:
                    continue
            elif model == "exponential":
                tau = float(r.get("tau", float("nan")))
                if np.isfinite(tau) and tau > 0 and np.isfinite(logA):
                    y_hat = np.exp(logA) * np.exp(-t_grid / tau)
                else:
                    continue
            else:
                tau = float(r.get("tau", float("nan")))
                beta = float(r.get("beta", float("nan")))
                if np.isfinite(tau) and tau > 0 and np.isfinite(beta) and beta > 0 and np.isfinite(logA):
                    y_hat = np.exp(logA) * np.exp(-np.power(t_grid / tau, beta))
                else:
                    continue
            ax.plot(t_grid, y_hat, color=color, lw=2.0, alpha=0.9, label=model)
        ax.legend(frameon=False)

    save_figure(fig, figs / "g1_model_comparison.png")
    save_figure(fig, figs / "g1_model_comparison.pdf")
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_default_roots_and_events() -> tuple[list[Path], list[EventRef]]:
    meta_p = Path("outputs/cross_disaster_comparison/svd_separability/metadata.json")
    if not meta_p.exists():
        return [Path("outputs/_runs/trackpath/v3"), Path("outputs/_runs/trackpath/v4_yagi_fix")], [EventRef(Path("outputs"), "turkiye_earthquake_2023")]
    try:
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
    except Exception:
        return [Path("outputs/_runs/trackpath/v3"), Path("outputs/_runs/trackpath/v4_yagi_fix")], [EventRef(Path("outputs"), "turkiye_earthquake_2023")]
    roots = [Path(p) for p in meta.get("roots", []) if str(p).strip()]
    events = []
    for s in meta.get("events", []) or []:
        try:
            events.append(_parse_event_ref(str(s)))
        except SystemExit:
            continue
    return roots, events


def cli_main() -> None:
    parser = argparse.ArgumentParser(description="对指定事件的 |g1(t)| 做模型族比较（power-law/exponential/stretched-exp）并输出 BIC 表")
    parser.add_argument("--root", type=Path, action="append", default=[], help="扫描的输出根目录（可多次提供）")
    parser.add_argument("--event", type=str, action="append", default=[], help="额外事件：<output_root>:<slug>")
    parser.add_argument("--slugs", type=str, nargs="*", default=[], help="要比较的事件 slugs（空或 all=自动发现）")
    parser.add_argument("--exclude-slugs", type=str, nargs="*", default=[], help="可选：从 slugs 中剔除的事件")
    parser.add_argument("--out-dir", type=Path, default=Path("outputs/cross_disaster_comparison/g1_model_comparison_tier1"), help="输出目录")
    parser.add_argument("--value-col", type=str, default="phi_overlap", choices=["phi_overlap", "phi_aggregate"])
    parser.add_argument("--r-max-km", type=float, default=200.0)
    parser.add_argument("--time-min", type=float, default=None)
    parser.add_argument("--time-max", type=float, default=None)
    parser.add_argument("--complete-only", type=int, default=1, choices=[0, 1])
    parser.add_argument("--fit-mode", type=str, default="from_peak", choices=["from_peak", "from_tmin"])
    parser.add_argument("--fit-tmin-hours", type=float, default=24.0)
    parser.add_argument("--min-fit-points", type=int, default=4)
    parser.add_argument("--skip-figures", action="store_true", help="只输出表，不出图")
    parser.add_argument("--max-plot-panels", type=int, default=6, help="超过该数量时自动跳过出图（默认 6；0=不限制）")
    args = parser.parse_args()

    if args.root:
        roots = [Path(p) for p in args.root]
        events = [_parse_event_ref(s) for s in (args.event or [])]
    else:
        roots, events = _load_default_roots_and_events()
        if args.event:
            events = events + [_parse_event_ref(s) for s in args.event]

    run(
        roots=roots,
        events=events,
        slugs=list(args.slugs or []),
        exclude_slugs=list(args.exclude_slugs or []),
        out_dir=Path(args.out_dir),
        value_col=str(args.value_col),
        r_max_km=float(args.r_max_km),
        time_min=args.time_min,
        time_max=args.time_max,
        complete_only=bool(int(args.complete_only)),
        fit_mode=str(args.fit_mode),
        fit_tmin_hours=float(args.fit_tmin_hours),
        min_fit_points=int(args.min_fit_points),
        skip_figures=bool(args.skip_figures),
        max_plot_panels=int(args.max_plot_panels),
    )


if __name__ == "__main__":
    cli_main()
