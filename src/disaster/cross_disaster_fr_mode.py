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

from disaster.viz import save_png_and_pdf


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


def _svd_u1(
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
        return {"ok": 0, "reason": "empty_after_filter"}

    pivot = sub.pivot_table(index="r_bin_km", columns="hours_since_quake", values=value_col, aggfunc="first")
    pivot = pivot.sort_index(axis=0).sort_index(axis=1)
    r = pivot.index.to_numpy(dtype=float)
    t = pivot.columns.to_numpy(dtype=float)
    m = pivot.to_numpy(dtype=float)
    dev = m - 1.0

    if dev.size == 0:
        return {"ok": 0, "reason": "empty_matrix"}

    nan_frac = float(np.isnan(dev).sum() / dev.size)
    mode_used = "drop_complete" if bool(complete_only) else "fill_missing"
    r_used = r
    t_used = t
    dev_used = dev
    if bool(complete_only):
        ok_r = np.all(np.isfinite(dev), axis=1)
        ok_t = np.all(np.isfinite(dev), axis=0)
        dev_used = dev[np.where(ok_r)[0][:], :][:, np.where(ok_t)[0]]
        r_used = r[ok_r]
        t_used = t[ok_t]
        if dev_used.size == 0 or dev_used.shape[0] < 2 or dev_used.shape[1] < 2:
            return {"ok": 0, "reason": "insufficient_after_complete_filter", "nan_frac_raw": nan_frac}
    else:
        dev_used = np.where(np.isfinite(dev), dev, 0.0)

    if dev_used.shape[0] < 2 or dev_used.shape[1] < 2:
        return {"ok": 0, "reason": "insufficient_matrix_shape", "nan_frac_raw": nan_frac}

    u, s, vt = np.linalg.svd(dev_used, full_matrices=False)
    u, vt = _sign_fix(u, vt, 0)

    e = float(np.sum(np.square(s[np.isfinite(s)])))
    sigma1_energy = float((s[0] ** 2) / e) if s.size and np.isfinite(e) and e > 0 else float("nan")
    u1 = u[:, 0] if u.shape[1] else np.array([], dtype=float)
    if u1.size:
        norm = float(np.linalg.norm(u1))
        u1_norm = u1 / norm if np.isfinite(norm) and norm > 0 else u1 * float("nan")
    else:
        u1_norm = u1

    return {
        "ok": 1,
        "reason": "",
        "mode_used": str(mode_used),
        "nan_frac_raw": float(nan_frac),
        "sigma1_energy": float(sigma1_energy),
        "n_r_bins_used": int(dev_used.shape[0]),
        "n_time_used": int(dev_used.shape[1]),
        "r_used": np.asarray(r_used, dtype=float),
        "t_used": np.asarray(t_used, dtype=float),
        "u1": np.asarray(u1, dtype=float),
        "u1_norm": np.asarray(u1_norm, dtype=float),
    }


def _pairwise_corr(a: pd.DataFrame) -> pd.DataFrame:
    slugs = sorted(a["slug"].astype(str).unique().tolist())
    rows: list[dict] = []
    for i, si in enumerate(slugs):
        ai = a[a["slug"] == si][["r_bin_km", "u1_norm"]].copy()
        for sj in slugs[i + 1 :]:
            aj = a[a["slug"] == sj][["r_bin_km", "u1_norm"]].copy()
            m = ai.merge(aj, on="r_bin_km", how="inner", suffixes=("_i", "_j"))
            x = pd.to_numeric(m["u1_norm_i"], errors="coerce").to_numpy(dtype=float)
            y = pd.to_numeric(m["u1_norm_j"], errors="coerce").to_numpy(dtype=float)
            ok = np.isfinite(x) & np.isfinite(y)
            x = x[ok]
            y = y[ok]
            corr = float(np.corrcoef(x, y)[0, 1]) if x.size >= 3 else float("nan")
            rows.append({"slug_i": si, "slug_j": sj, "n_overlap_bins": int(x.size), "corr_u1_norm": float(corr)})
    return pd.DataFrame(rows)


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

    want = [str(s).strip() for s in slugs if str(s).strip()]
    if want and len(want) == 1 and want[0].lower() == "all":
        want = []
    if not want:
        want = sorted(refs.keys())
    exclude = {str(s).strip() for s in (exclude_slugs or []) if str(s).strip()}
    if exclude:
        want = [s for s in want if s not in exclude]

    value_col = str(value_col).strip()
    if value_col not in {"phi_overlap", "phi_aggregate"}:
        raise SystemExit(f"value_col 不支持：{value_col}")

    long_rows: list[dict] = []
    summary_rows: list[dict] = []
    for slug in want:
        if slug not in refs:
            continue
        ref = refs[slug]
        name, event_type = _load_metadata(ref.output_root, slug)
        df = _load_phi_rt_long(ref.output_root, slug)
        m = _svd_u1(
            df=df,
            value_col=value_col,
            r_max_km=float(r_max_km),
            time_min=time_min,
            time_max=time_max,
            complete_only=bool(complete_only),
        )
        ok = int(m.get("ok", 0))
        summary_rows.append(
            {
                "slug": str(slug),
                "name": str(name),
                "event_type": str(event_type),
                "output_root": str(ref.output_root),
                "ok": int(ok),
                "reason": str(m.get("reason", "")),
                "value_col": value_col,
                "r_max_km": float(r_max_km),
                "time_min": time_min,
                "time_max": time_max,
                "complete_only": int(bool(complete_only)),
                "mode_used": str(m.get("mode_used", "")),
                "nan_frac_raw": float(m.get("nan_frac_raw", float("nan"))),
                "sigma1_energy": float(m.get("sigma1_energy", float("nan"))),
                "n_r_bins_used": int(m.get("n_r_bins_used", 0)),
                "n_time_used": int(m.get("n_time_used", 0)),
            }
        )
        if ok != 1:
            continue
        r_used = np.asarray(m.get("r_used", np.array([], dtype=float)), dtype=float)
        u1 = np.asarray(m.get("u1", np.array([], dtype=float)), dtype=float)
        u1_norm = np.asarray(m.get("u1_norm", np.array([], dtype=float)), dtype=float)
        for ri, ui, un in zip(r_used.tolist(), u1.tolist(), u1_norm.tolist(), strict=False):
            long_rows.append(
                {
                    "slug": str(slug),
                    "r_bin_km": float(ri),
                    "u1": float(ui),
                    "u1_norm": float(un),
                    "sigma1_energy": float(m.get("sigma1_energy", float("nan"))),
                    "n_r_bins_used": int(m.get("n_r_bins_used", 0)),
                    "n_time_used": int(m.get("n_time_used", 0)),
                }
            )

    long_df = pd.DataFrame(long_rows)
    summary_df = pd.DataFrame(summary_rows).sort_values(["sigma1_energy"], ascending=False, kind="stable")
    long_df.to_csv(tabs / "fr_u1_long.csv", index=False)
    summary_df.to_csv(tabs / "fr_u1_summary.csv", index=False)

    corr_df = pd.DataFrame()
    if not long_df.empty:
        corr_df = _pairwise_corr(long_df)
        corr_df.to_csv(tabs / "fr_u1_pairwise_corr.csv", index=False)

    meta = {
        "n_events_scanned": int(len(want)),
        "n_ok": int((summary_df["ok"] == 1).sum()) if not summary_df.empty else 0,
        "roots": [str(p) for p in roots],
        "events": [f"{e.output_root}:{e.slug}" for e in events],
        "slugs": want,
        "exclude_slugs": sorted(exclude),
        "value_col": value_col,
        "r_max_km": float(r_max_km),
        "time_min": time_min,
        "time_max": time_max,
        "complete_only": int(bool(complete_only)),
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # figures (optional)
    try:
        from disaster import plot_style as ps  # type: ignore
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        return

    ok_sum = summary_df[summary_df["ok"] == 1].copy()
    if ok_sum.empty or long_df.empty:
        return

    ok_sum = ok_sum.sort_values("sigma1_energy", ascending=False, kind="stable")
    order = ok_sum["slug"].astype(str).tolist()
    pivot = long_df.pivot_table(index="slug", columns="r_bin_km", values="u1_norm", aggfunc="first").reindex(order)
    r_bins = pivot.columns.to_numpy(dtype=float)
    mat = pivot.to_numpy(dtype=float)

    vmax = float(np.nanmax(np.abs(mat))) if np.isfinite(np.nanmax(np.abs(mat))) else 1.0
    vmax = max(vmax, 1e-6)

    with ps.paper_style():
        fig, ax = plt.subplots(figsize=(min(10.5, 0.35 * len(r_bins) + 2.5), min(9.5, 0.35 * len(order) + 2.2)))
        im = ax.imshow(mat, aspect="auto", cmap="RdBu_r", vmin=-vmax, vmax=vmax, interpolation="nearest")
        ax.set_yticks(np.arange(len(order)))
        ax.set_yticklabels(order, fontsize=7)
        ax.set_xticks(np.arange(len(r_bins))[::2])
        ax.set_xticklabels([f"{int(x)}" for x in r_bins[::2]], rotation=0, fontsize=7)
        ax.set_xlabel("r_bin_km")
        ax.set_title(f"f(r)=u1(r) (normalized) heatmap; value_col={value_col}, r_max={float(r_max_km):.0f}km")
        ps.despine(ax)
        cb = fig.colorbar(im, ax=ax, shrink=0.9)
        cb.set_label("u1_norm")
        fig.tight_layout()
        save_png_and_pdf(ps, fig, figs / "fr_u1_norm_heatmap.png")
        plt.close(fig)


def cli_main() -> None:
    p = argparse.ArgumentParser(description="P2：提取 rank-1 空间模式 f(r)=u1(r) 并做跨事件一致性对比")
    p.add_argument("--root", type=Path, action="append", default=[], help="扫描的输出根目录（可多次提供）")
    p.add_argument("--event", type=str, action="append", default=[], help="额外事件：<output_root>:<slug>")
    p.add_argument("--out-dir", type=Path, default=Path("outputs/cross_disaster_comparison/fr_mode"))
    p.add_argument("--value-col", type=str, default="phi_overlap", choices=["phi_overlap", "phi_aggregate"])
    p.add_argument("--r-max-km", type=float, default=200.0)
    p.add_argument("--time-min", type=float, default=0.0)
    p.add_argument("--time-max", type=float, default=72.0)
    p.add_argument("--complete-only", action="store_true")
    p.add_argument("--slugs", type=str, nargs="*", default=[], help="可选：只跑指定 slugs（空或 all=自动发现）")
    p.add_argument("--exclude-slugs", type=str, nargs="*", default=[], help="可选：剔除指定 slugs")
    args = p.parse_args()

    if args.root:
        roots = [Path(x) for x in args.root]
    else:
        roots = [Path("outputs/_runs/trackpath/v3")]
        yagi_fix_root = Path("outputs/_runs/trackpath/v4_yagi_fix")
        if yagi_fix_root.exists():
            roots.append(yagi_fix_root)

    events = [_parse_event_ref(x) for x in (args.event or [])]

    run(
        roots=roots,
        events=events,
        out_dir=Path(args.out_dir),
        value_col=str(args.value_col),
        r_max_km=float(args.r_max_km),
        time_min=(float(args.time_min) if args.time_min is not None else None),
        time_max=(float(args.time_max) if args.time_max is not None else None),
        complete_only=bool(args.complete_only),
        slugs=list(args.slugs or []),
        exclude_slugs=list(args.exclude_slugs or []),
    )


if __name__ == "__main__":
    cli_main()
