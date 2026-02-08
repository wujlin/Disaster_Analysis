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
    from scipy.stats import pearsonr, spearmanr
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：scipy。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e


@dataclass(frozen=True)
class EventRef:
    output_root: Path
    slug: str


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _svd_energy_frac1(s: np.ndarray) -> float:
    s = np.asarray(s, dtype=float)
    if s.size == 0 or not np.isfinite(s[0]):
        return float("nan")
    e = np.sum(np.square(s[np.isfinite(s)]))
    if not np.isfinite(e) or e <= 0:
        return float("nan")
    return float((s[0] ** 2) / e)


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


def _max_r_where_tiles_ge(df: pd.DataFrame, *, tiles_thr: float) -> float:
    if "n_tiles_overlap" not in df.columns:
        return float("nan")
    g = df.groupby("r_bin_km", observed=True)["n_tiles_overlap"].mean().reset_index()
    g["r_bin_km"] = pd.to_numeric(g["r_bin_km"], errors="coerce")
    g["n_tiles_overlap"] = pd.to_numeric(g["n_tiles_overlap"], errors="coerce")
    g = g.dropna(subset=["r_bin_km", "n_tiles_overlap"]).sort_values("r_bin_km")
    ok = g[g["n_tiles_overlap"] >= float(tiles_thr)]
    if ok.empty:
        return float("nan")
    return float(ok["r_bin_km"].max())


def _svd_sigma1_energy(
    *,
    df: pd.DataFrame,
    value_col: str,
    r_max_km: float,
    time_min: float | None,
    time_max: float | None,
    complete_only: bool,
) -> dict:
    sub = df.copy()
    if np.isfinite(r_max_km):
        sub = sub[pd.to_numeric(sub["r_bin_km"], errors="coerce") <= float(r_max_km)].copy()
    if time_min is not None:
        sub = sub[pd.to_numeric(sub["hours_since_quake"], errors="coerce") >= float(time_min)].copy()
    if time_max is not None:
        sub = sub[pd.to_numeric(sub["hours_since_quake"], errors="coerce") <= float(time_max)].copy()

    pivot = sub.pivot_table(index="r_bin_km", columns="hours_since_quake", values=value_col, aggfunc="first")
    pivot = pivot.sort_index(axis=0).sort_index(axis=1)
    m = pivot.to_numpy(dtype=float)
    dev = m - 1.0
    S = float(np.nanmax(np.abs(dev))) if dev.size else float("nan")
    nan_frac = float(np.isnan(dev).sum() / dev.size) if dev.size else float("nan")

    mode_used = "drop_complete" if bool(complete_only) else "fill_missing"
    dev_used = dev
    if bool(complete_only):
        ok_r = np.all(np.isfinite(dev), axis=1)
        ok_t = np.all(np.isfinite(dev), axis=0)
        dev_used = dev[np.where(ok_r)[0][:], :][:, np.where(ok_t)[0]]
        if dev_used.size == 0 or dev_used.shape[0] < 2 or dev_used.shape[1] < 2:
            mode_used = "fill_missing_fallback"
            dev_used = np.where(np.isfinite(dev), dev, 0.0)
    else:
        dev_used = np.where(np.isfinite(dev), dev, 0.0)

    s = np.linalg.svd(dev_used, full_matrices=False, compute_uv=False)
    frac1 = _svd_energy_frac1(s)
    denom = float(np.linalg.norm(dev_used))
    if dev_used.size and s.size and np.isfinite(denom) and denom > 0:
        # rank-1 error（只需要 σ1、u1、v1 会更快，但这里数据很小，直接算即可）
        u, s2, vt = np.linalg.svd(dev_used, full_matrices=False)
        rank1 = (s2[0] * np.outer(u[:, 0], vt[0, :])).astype(float)
        rel_err = float(np.linalg.norm(dev_used - rank1) / denom)
    else:
        rel_err = float("nan")

    return {
        "sigma1_energy": float(frac1),
        "rank1_rel_error": float(rel_err),
        "S_max_abs_delta": float(S),
        "mode_used": str(mode_used),
        "n_r_bins_raw": int(pivot.shape[0]),
        "n_time_raw": int(pivot.shape[1]),
        "n_r_bins_used": int(dev_used.shape[0]),
        "n_time_used": int(dev_used.shape[1]),
        "nan_frac_raw_matrix": float(nan_frac),
    }


def _corr(x: np.ndarray, y: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x = x[ok]
    y = y[ok]
    if x.size < 5:
        return {"n": int(x.size), "spearman_rho": float("nan"), "spearman_p": float("nan"), "pearson_r": float("nan"), "pearson_p": float("nan")}
    rho, p_s = spearmanr(x, y)
    r, p_p = pearsonr(x, y)
    return {"n": int(x.size), "spearman_rho": float(rho), "spearman_p": float(p_s), "pearson_r": float(r), "pearson_p": float(p_p)}


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


def run(
    *,
    roots: list[Path],
    events: list[EventRef],
    out_dir: Path,
    value_col: str,
    r_max_list: list[float],
    time_min: float | None,
    time_max: float | None,
    complete_only: bool,
    tiles_thr: float,
) -> None:
    out_dir = Path(out_dir)
    tabs = out_dir / "tables"
    figs = out_dir / "figures"
    _ensure_dir(tabs)
    _ensure_dir(figs)

    # collect refs (later ones override)
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

    # per-event tile-threshold r_max
    thr_rows: list[dict] = []
    df_cache: dict[str, pd.DataFrame] = {}
    meta_cache: dict[str, tuple[str, str]] = {}
    for slug, ref in refs.items():
        df = _load_phi_rt_long(ref.output_root, ref.slug)
        df_cache[slug] = df
        meta_cache[slug] = _load_metadata(ref.output_root, ref.slug)
        thr_rows.append(
            {
                "slug": slug,
                "event_type": meta_cache[slug][1],
                "output_root": str(ref.output_root),
                "tiles_thr": float(tiles_thr),
                "r_max_km_tiles_ge_thr": _max_r_where_tiles_ge(df, tiles_thr=float(tiles_thr)),
            }
        )
    thr_df = pd.DataFrame(thr_rows).sort_values("r_max_km_tiles_ge_thr", ascending=True, kind="stable")
    thr_df.to_csv(tabs / "rmax_by_tiles_threshold.csv", index=False)
    r_common = float(np.nanmin(pd.to_numeric(thr_df["r_max_km_tiles_ge_thr"], errors="coerce").to_numpy(dtype=float)))
    if not np.isfinite(r_common):
        r_common = float("nan")

    # sweep
    sweep_rows: list[dict] = []
    for r_max_km in r_max_list:
        for slug, ref in refs.items():
            name, event_type = meta_cache[slug]
            m = _svd_sigma1_energy(
                df=df_cache[slug],
                value_col=value_col,
                r_max_km=float(r_max_km),
                time_min=time_min,
                time_max=time_max,
                complete_only=bool(complete_only),
            )
            sweep_rows.append(
                {
                    "slug": slug,
                    "name": name,
                    "event_type": event_type,
                    "output_root": str(ref.output_root),
                    "value_col": value_col,
                    "r_max_km": float(r_max_km),
                    "time_min": time_min,
                    "time_max": time_max,
                    **m,
                }
            )
        if np.isfinite(r_common):
            # 记录“按 tiles 阈值的最大公约距离”的参照行（不重算，单独标注）
            pass

    sweep_df = pd.DataFrame(sweep_rows).sort_values(["r_max_km", "sigma1_energy"], ascending=[True, False], kind="stable")
    sweep_df.to_csv(tabs / "svd_sigma1_rmax_sweep.csv", index=False)

    # correlations per r_max
    corr_rows: list[dict] = []
    for r_max_km in r_max_list:
        sub = sweep_df[sweep_df["r_max_km"] == float(r_max_km)].copy()
        y = pd.to_numeric(sub["sigma1_energy"], errors="coerce").to_numpy(dtype=float)
        n_r = pd.to_numeric(sub["n_r_bins_used"], errors="coerce").to_numpy(dtype=float)
        n_t = pd.to_numeric(sub["n_time_used"], errors="coerce").to_numpy(dtype=float)
        size = n_r * n_t
        corr_rows.append({"r_max_km": float(r_max_km), "x": "n_r_bins_used", **_corr(n_r, y)})
        corr_rows.append({"r_max_km": float(r_max_km), "x": "n_time_used", **_corr(n_t, y)})
        corr_rows.append({"r_max_km": float(r_max_km), "x": "matrix_size", **_corr(size, y)})
    pd.DataFrame(corr_rows).to_csv(tabs / "sigma1_vs_dimension_corr.csv", index=False)

    # rank stability (Spearman across events between r_max)
    r_vals = [float(x) for x in r_max_list]
    mat = []
    for i, ri in enumerate(r_vals):
        row = []
        yi = sweep_df[sweep_df["r_max_km"] == ri].set_index("slug")["sigma1_energy"]
        yi = pd.to_numeric(yi, errors="coerce")
        for rj in r_vals:
            yj = sweep_df[sweep_df["r_max_km"] == rj].set_index("slug")["sigma1_energy"]
            yj = pd.to_numeric(yj, errors="coerce")
            common = sorted(set(yi.index) & set(yj.index))
            a = yi.loc[common].to_numpy(dtype=float)
            b = yj.loc[common].to_numpy(dtype=float)
            ok = np.isfinite(a) & np.isfinite(b)
            if np.sum(ok) < 5:
                row.append(float("nan"))
            else:
                rho, _ = spearmanr(a[ok], b[ok])
                row.append(float(rho))
        mat.append(row)
    stab = pd.DataFrame(mat, index=[f"rmax_{int(r)}" for r in r_vals], columns=[f"rmax_{int(r)}" for r in r_vals])
    stab.to_csv(tabs / "sigma1_rank_stability_spearman.csv", index=True)

    meta = {
        "n_events": int(len(refs)),
        "value_col": value_col,
        "r_max_list": r_vals,
        "time_min": time_min,
        "time_max": time_max,
        "complete_only": int(bool(complete_only)),
        "tiles_thr": float(tiles_thr),
        "r_common_tiles_ge_thr": float(r_common),
        "roots": [str(r) for r in roots],
        "events": [f"{str(e.output_root)}:{e.slug}" for e in events],
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # quick plot: sigma1 vs r_max for a few key slugs (optional)
    try:
        from disaster import plot_style as ps  # type: ignore
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        return

    key_slugs = [
        "hurricane_beryl_across_southeastern_texas_us",
        "hurricane_beryl_across_quintana_roo_and_yucatan_mexico",
        "hurricane_john_southern_mexico_25_september_2024",
        "turkiye_earthquake_2023",
    ]
    with ps.paper_style():
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_HALF)
        for slug in key_slugs:
            sub = sweep_df[sweep_df["slug"] == slug].copy()
            if sub.empty:
                continue
            sub = sub.sort_values("r_max_km")
            ax.plot(
                sub["r_max_km"].to_numpy(dtype=float),
                sub["sigma1_energy"].to_numpy(dtype=float),
                marker="o",
                lw=2.0,
                ms=4,
                label=slug,
            )
        ax.set_xlabel("r_max (km)")
        ax.set_ylabel(r"$\sigma_1^2/\sum_k\sigma_k^2$")
        ax.set_title("σ1 energy vs r_max (selected events)")
        ax.legend(frameon=False, fontsize=7)
        ps.despine(ax)
        fig.tight_layout()
        fig.savefig(figs / "sigma1_vs_rmax_selected.png", dpi=220)
        fig.savefig(figs / "sigma1_vs_rmax_selected.pdf")
        plt.close(fig)


def cli_main() -> None:
    p = argparse.ArgumentParser(description="Q2: σ1 对 r_max/矩阵维度的敏感性分析（跨事件）")
    p.add_argument("--root", type=Path, action="append", default=None)
    p.add_argument("--event", type=str, action="append", default=None)
    p.add_argument("--out-dir", type=Path, default=Path("outputs/cross_disaster_comparison/svd_sensitivity"))
    p.add_argument("--value-col", type=str, default="phi_overlap", choices=["phi_overlap", "phi_aggregate"])
    p.add_argument("--r-max-km", type=float, nargs="*", default=[100.0, 200.0, 300.0, 500.0])
    p.add_argument("--time-min", type=float, default=None)
    p.add_argument("--time-max", type=float, default=None)
    p.add_argument("--complete-only", action="store_true", help="仅用完全无缺失的 r×t 子矩阵；否则用填充 0")
    p.add_argument("--tiles-thr", type=float, default=50.0, help="用于计算每事件 r_max 的 tiles 阈值（n_tiles_overlap 均值）")
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
        r_max_list=[float(x) for x in (args.r_max_km or [])],
        time_min=(float(args.time_min) if args.time_min is not None else None),
        time_max=(float(args.time_max) if args.time_max is not None else None),
        complete_only=bool(args.complete_only),
        tiles_thr=float(args.tiles_thr),
    )


if __name__ == "__main__":
    cli_main()

