from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from math import ceil
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e


@dataclass(frozen=True)
class EventRef:
    output_root: Path
    slug: str


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _discover_events(output_root: Path) -> list[EventRef]:
    root = Path(output_root)
    if not root.exists():
        return []
    out: list[EventRef] = []
    for d in sorted(root.iterdir(), key=lambda x: x.name):
        if not d.is_dir():
            continue
        if d.name.startswith("_"):
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
    need = {"hours_since_quake", "r_bin_km", "phi_overlap", "phi_aggregate"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise SystemExit(f"{p} 缺少列：{miss}")
    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df["r_bin_km"] = pd.to_numeric(df["r_bin_km"], errors="coerce")
    for c in ["phi_overlap", "phi_aggregate", "n_tiles_overlap"]:
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
        return {
            "ok": 0,
            "sigma1_energy": float("nan"),
            "n_r_bins_used": 0,
            "n_time_used": 0,
            "t_used": np.array([], dtype=float),
            "g1": np.array([], dtype=float),
        }

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
        return {
            "ok": 0,
            "sigma1_energy": float("nan"),
            "n_r_bins_used": int(dev_used.shape[0]),
            "n_time_used": int(dev_used.shape[1]),
            "t_used": np.asarray(t_used, dtype=float),
            "g1": np.array([], dtype=float),
            "mode_used": mode_used,
        }

    u, s, vt = np.linalg.svd(dev_used, full_matrices=False)
    u, vt = _sign_fix(u, vt, 0)
    frac = float((s[0] ** 2) / np.sum(np.square(s))) if s.size and float(np.sum(np.square(s))) > 0 else float("nan")
    v1 = vt[0, :] if vt.shape[0] else np.array([], dtype=float)
    g1 = float(s[0]) * v1 if s.size else np.array([], dtype=float)

    return {
        "ok": 1,
        "sigma1_energy": float(frac),
        "n_r_bins_used": int(dev_used.shape[0]),
        "n_time_used": int(dev_used.shape[1]),
        "t_used": np.asarray(t_used, dtype=float),
        "g1": np.asarray(g1, dtype=float),
        "mode_used": str(mode_used),
    }


def _fit_powerlaw(
    *,
    t: np.ndarray,
    y: np.ndarray,
    fit_mode: str,
    fit_tmin_hours: float,
    min_fit_points: int,
) -> dict:
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(t) & np.isfinite(y) & (t > 0) & (y > 0)
    t0 = t[ok]
    y0 = y[ok]
    if t0.size == 0:
        return {"fit_ok": 0}

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
        return {
            "fit_ok": 0,
            "fit_mode": fit_mode,
            "t_start": float(t_start),
            "n_fit": int(t1.size),
        }

    x = np.log(t1)
    yy = np.log(y1)
    slope, intercept = np.polyfit(x, yy, deg=1)
    yy_hat = slope * x + intercept
    ss_res = float(np.sum(np.square(yy - yy_hat)))
    ss_tot = float(np.sum(np.square(yy - float(np.mean(yy)))))
    r2 = float(1.0 - ss_res / ss_tot) if np.isfinite(ss_tot) and ss_tot > 0 else float("nan")

    return {
        "fit_ok": 1,
        "fit_mode": fit_mode,
        "t_start": float(t_start),
        "n_fit": int(t1.size),
        "alpha": float(-slope),
        "logA": float(intercept),
        "r2_loglog": float(r2),
        "t_fit_min": float(np.min(t1)),
        "t_fit_max": float(np.max(t1)),
    }


def run(
    *,
    roots: list[Path],
    events: list[EventRef],
    out_dir: Path,
    value_col: str,
    r_max_km: float,
    time_min: float | None,
    time_max: float | None,
    complete_only: bool,
    sigma1_threshold: float,
    fit_mode: str,
    fit_tmin_hours: float,
    min_fit_points: int,
    slugs: list[str],
    exclude_slugs: list[str],
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

    value_col = str(value_col).strip()
    if value_col not in {"phi_overlap", "phi_aggregate"}:
        raise SystemExit(f"value_col 不支持：{value_col}")

    ts_rows: list[dict] = []
    fit_rows: list[dict] = []
    want = [str(s).strip() for s in (slugs or []) if str(s).strip()]
    if want and len(want) == 1 and want[0].lower() == "all":
        want = []
    if not want:
        want = sorted(refs.keys())
    exclude = {str(s).strip() for s in (exclude_slugs or []) if str(s).strip()}
    if exclude:
        want = [s for s in want if s not in exclude]

    for slug in want:
        ref = refs[slug]
        name, event_type = _load_metadata(ref.output_root, ref.slug)
        df = _load_phi_rt_long(ref.output_root, ref.slug)

        m = _svd_g1(
            df=df,
            value_col=value_col,
            r_max_km=float(r_max_km),
            time_min=time_min,
            time_max=time_max,
            complete_only=bool(complete_only),
        )
        t = np.asarray(m.get("t_used", np.array([], dtype=float)), dtype=float)
        g1 = np.asarray(m.get("g1", np.array([], dtype=float)), dtype=float)
        sig1 = float(m.get("sigma1_energy", float("nan")))
        ok = int(m.get("ok", 0))

        if ok and t.size and g1.size and t.size == g1.size:
            abs_g1 = np.abs(g1)
            i_peak = int(np.nanargmax(abs_g1)) if abs_g1.size else -1
            t_peak = float(t[i_peak]) if i_peak >= 0 else float("nan")
            g1_peak = float(g1[i_peak]) if i_peak >= 0 else float("nan")
            abs_peak = float(abs_g1[i_peak]) if i_peak >= 0 else float("nan")
            for ti, gi, ai in zip(t.tolist(), g1.tolist(), abs_g1.tolist(), strict=False):
                ts_rows.append(
                    {
                        "slug": str(slug),
                        "name": str(name),
                        "event_type": str(event_type),
                        "hours_since_quake": float(ti),
                        "g1": float(gi),
                        "abs_g1": float(ai),
                        "sigma1_energy": float(sig1),
                        "r_max_km": float(r_max_km),
                        "mode_used": str(m.get("mode_used", "")),
                    }
                )
        else:
            t_peak = float("nan")
            g1_peak = float("nan")
            abs_peak = float("nan")

        fit = {"fit_ok": 0}
        if ok and np.isfinite(sig1) and float(sig1) >= float(sigma1_threshold) and t.size and g1.size:
            fit = _fit_powerlaw(
                t=t,
                y=np.abs(g1),
                fit_mode=str(fit_mode),
                fit_tmin_hours=float(fit_tmin_hours),
                min_fit_points=int(min_fit_points),
            )

        fit_rows.append(
            {
                "slug": str(slug),
                "name": str(name),
                "event_type": str(event_type),
                "output_root": str(ref.output_root),
                "value_col": value_col,
                "r_max_km": float(r_max_km),
                "time_min": time_min,
                "time_max": time_max,
                "complete_only": int(bool(complete_only)),
                "sigma1_energy": float(sig1),
                "n_r_bins_used": int(m.get("n_r_bins_used", 0)),
                "n_time_used": int(m.get("n_time_used", 0)),
                "t_peak": float(t_peak),
                "g1_peak": float(g1_peak),
                "abs_g1_peak": float(abs_peak),
                **fit,
            }
        )

    ts_df = pd.DataFrame(ts_rows)
    fit_df = pd.DataFrame(fit_rows).sort_values(["sigma1_energy"], ascending=False, kind="stable")
    ts_df.to_csv(tabs / "g1_timeseries_long.csv", index=False)
    fit_df.to_csv(tabs / "g1_powerlaw_fits.csv", index=False)

    meta = {
        "n_events": int(len(want)),
        "value_col": value_col,
        "r_max_km": float(r_max_km),
        "time_min": time_min,
        "time_max": time_max,
        "complete_only": int(bool(complete_only)),
        "sigma1_threshold": float(sigma1_threshold),
        "fit_mode": str(fit_mode),
        "fit_tmin_hours": float(fit_tmin_hours),
        "min_fit_points": int(min_fit_points),
        "roots": [str(r) for r in roots],
        "events": [f"{str(e.output_root)}:{e.slug}" for e in events],
        "slugs": want,
        "exclude_slugs": sorted(exclude),
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # figures (optional)
    try:
        from disaster import plot_style as ps  # type: ignore
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        return

    sel = fit_df[(pd.to_numeric(fit_df["sigma1_energy"], errors="coerce") >= float(sigma1_threshold))].copy()
    sel = sel.sort_values("sigma1_energy", ascending=False, kind="stable")
    if sel.empty or ts_df.empty:
        return

    slugs = sel["slug"].tolist()
    n = len(slugs)
    ncols = 3
    nrows = int(ceil(n / ncols))
    with ps.paper_style():
        fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(3.2 * ncols, 2.45 * nrows), squeeze=False)
        for i, slug in enumerate(slugs):
            ax = axes[i // ncols][i % ncols]
            sub = ts_df[ts_df["slug"] == slug].copy()
            sub = sub.sort_values("hours_since_quake")
            x = pd.to_numeric(sub["hours_since_quake"], errors="coerce").to_numpy(dtype=float)
            y = pd.to_numeric(sub["abs_g1"], errors="coerce").to_numpy(dtype=float)
            ok = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
            x = x[ok]
            y = y[ok]
            ax.scatter(x / 24.0, y, s=18, color=ps.OKABE_ITO["blue"], alpha=0.85, linewidths=0, rasterized=True)

            row = sel[sel["slug"] == slug].iloc[0].to_dict()
            if int(row.get("fit_ok", 0)) == 1 and np.isfinite(float(row.get("alpha", np.nan))) and np.isfinite(float(row.get("logA", np.nan))):
                alpha = float(row["alpha"])
                logA = float(row["logA"])
                t_start = float(row.get("t_start", np.nan))
                xx = np.linspace(max(np.nanmin(x), t_start), np.nanmax(x), 120)
                yy = np.exp(logA) * np.power(xx, -alpha)
                ax.plot(xx / 24.0, yy, color=ps.OKABE_ITO["vermillion"], lw=2.0, alpha=0.9)
                ax.set_title(f"{slug}\nα={alpha:.2f}, R²={float(row.get('r2_loglog', np.nan)):.2f}", fontsize=9)
            else:
                ax.set_title(slug, fontsize=9)

            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.set_xlabel("t (days)")
            ax.set_ylabel("|g1(t)|")
            ps.despine(ax)

        # hide unused axes
        for j in range(n, nrows * ncols):
            axes[j // ncols][j % ncols].axis("off")

        fig.tight_layout()
        fig.savefig(figs / "g1_abs_powerlaw_fits.png", dpi=220)
        fig.savefig(figs / "g1_abs_powerlaw_fits.pdf")
        plt.close(fig)


def cli_main() -> None:
    p = argparse.ArgumentParser(description="Q3：对 δ(r,t)=φ(r,t)-1 的 rank-1 时间振幅 g1(t) 做幂律拟合（跨事件）")
    p.add_argument("--root", type=Path, action="append", default=None)
    p.add_argument("--event", type=str, action="append", default=None, help="额外指定单个事件：<output_root>:<slug>（可重复）")
    p.add_argument("--out-dir", type=Path, default=Path("outputs/cross_disaster_comparison/rank1_dynamics"))
    p.add_argument("--value-col", type=str, default="phi_overlap", choices=["phi_overlap", "phi_aggregate"])
    p.add_argument("--slugs", type=str, nargs="*", default=[], help="可选：只跑指定 slugs（空或 all=自动发现）")
    p.add_argument("--exclude-slugs", type=str, nargs="*", default=[], help="可选：剔除指定 slugs")
    p.add_argument("--r-max-km", type=float, default=200.0)
    p.add_argument("--time-min", type=float, default=None)
    p.add_argument("--time-max", type=float, default=None)
    p.add_argument("--complete-only", action="store_true")
    p.add_argument("--sigma1-threshold", type=float, default=0.90)
    p.add_argument("--fit-mode", type=str, default="from_peak", choices=["from_peak", "from_tmin"])
    p.add_argument("--fit-tmin-hours", type=float, default=24.0)
    p.add_argument("--min-fit-points", type=int, default=6)
    args = p.parse_args()

    if args.root:
        roots = [Path(x) for x in args.root]
    else:
        roots = [Path("outputs/_runs/trackpath/v3")]
        yagi_fix_root = Path("outputs/_runs/trackpath/v4_yagi_fix")
        if yagi_fix_root.exists():
            roots.append(yagi_fix_root)

    if args.event:
        events = [_parse_event_ref(x) for x in args.event]
    else:
        events = []
        default_turkey = Path("outputs") / "turkiye_earthquake_2023" / "phi_heatmap" / "tables" / "phi_rt_long.csv"
        if default_turkey.exists():
            events.append(EventRef(output_root=Path("outputs"), slug="turkiye_earthquake_2023"))

    run(
        roots=roots,
        events=events,
        out_dir=Path(args.out_dir),
        value_col=str(args.value_col),
        slugs=list(args.slugs or []),
        exclude_slugs=list(args.exclude_slugs or []),
        r_max_km=float(args.r_max_km),
        time_min=(float(args.time_min) if args.time_min is not None else None),
        time_max=(float(args.time_max) if args.time_max is not None else None),
        complete_only=bool(args.complete_only),
        sigma1_threshold=float(args.sigma1_threshold),
        fit_mode=str(args.fit_mode),
        fit_tmin_hours=float(args.fit_tmin_hours),
        min_fit_points=int(args.min_fit_points),
    )


if __name__ == "__main__":
    cli_main()
