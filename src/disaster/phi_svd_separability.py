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
class Config:
    output_root: Path
    slug: str
    out_dir: Path
    value_col: str = "phi_overlap"  # phi_aggregate | phi_overlap
    dev_mode: str = "signed"  # signed | abs | raw
    time_min: float | None = None
    time_max: float | None = None
    min_tiles_overlap: int = 0
    complete_only: bool = True  # True: drop any NaN rows/cols; False: fill NaN with 0 (on dev)


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _load_phi_rt_long(output_root: Path, slug: str) -> pd.DataFrame:
    p = output_root / slug / "phi_heatmap" / "tables" / "phi_rt_long.csv"
    if not p.exists():
        raise FileNotFoundError(f"未找到：{p}")
    df = pd.read_csv(p)
    need = {"hours_since_quake", "r_bin_km", "phi_aggregate", "phi_overlap"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise SystemExit(f"{p} 缺少列：{miss}")
    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df["r_bin_km"] = pd.to_numeric(df["r_bin_km"], errors="coerce")
    for c in ["phi_aggregate", "phi_overlap", "n_tiles_overlap"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["hours_since_quake", "r_bin_km"]).copy()
    return df


def _svd_energy_frac1(s: np.ndarray) -> float:
    s = np.asarray(s, dtype=float)
    if s.size == 0 or not np.isfinite(s[0]):
        return float("nan")
    e = np.sum(np.square(s[np.isfinite(s)]))
    if not np.isfinite(e) or e <= 0:
        return float("nan")
    return float((s[0] ** 2) / e)


def run(cfg: Config) -> None:
    out_dir = Path(cfg.out_dir)
    tabs = out_dir / "tables"
    figs = out_dir / "figures"
    _ensure_dir(tabs)
    _ensure_dir(figs)

    df = _load_phi_rt_long(Path(cfg.output_root), str(cfg.slug))

    value_col = str(cfg.value_col).strip()
    if value_col not in {"phi_aggregate", "phi_overlap"}:
        raise SystemExit(f"value_col 不支持：{value_col}（仅支持 phi_aggregate/phi_overlap）")

    dev_mode = str(cfg.dev_mode).strip().lower() or "signed"
    if dev_mode not in {"signed", "abs", "raw"}:
        raise SystemExit(f"dev_mode 不支持：{cfg.dev_mode}（仅支持 signed/abs/raw）")

    if cfg.time_min is not None:
        df = df[df["hours_since_quake"] >= float(cfg.time_min)].copy()
    if cfg.time_max is not None:
        df = df[df["hours_since_quake"] <= float(cfg.time_max)].copy()

    if int(cfg.min_tiles_overlap) > 0:
        if "n_tiles_overlap" not in df.columns:
            raise SystemExit("min_tiles_overlap>0 需要 phi_rt_long 中包含 n_tiles_overlap")
        keep_r = (
            df.groupby("r_bin_km", observed=True)["n_tiles_overlap"]
            .mean()
            .reset_index()
            .rename(columns={"n_tiles_overlap": "n_tiles_overlap_mean"})
        )
        keep_r = keep_r[pd.to_numeric(keep_r["n_tiles_overlap_mean"], errors="coerce") >= float(cfg.min_tiles_overlap)].copy()
        df = df[df["r_bin_km"].isin(set(pd.to_numeric(keep_r["r_bin_km"], errors="coerce").dropna().astype(float).tolist()))].copy()

    if df.empty:
        raise SystemExit("过滤后数据为空（请检查 time_min/time_max/min_tiles_overlap）")

    pivot = df.pivot_table(index="r_bin_km", columns="hours_since_quake", values=value_col, aggfunc="first")
    pivot = pivot.sort_index(axis=0).sort_index(axis=1)
    m = pivot.to_numpy(dtype=float)

    if dev_mode == "raw":
        dev = m
        fill_value = 1.0
    else:
        dev = m - 1.0
        if dev_mode == "abs":
            dev = np.abs(dev)
        fill_value = 0.0

    mode_used = "drop_complete" if bool(cfg.complete_only) else "fill_missing"
    nan_frac = float(np.isnan(dev).sum() / dev.size) if dev.size else float("nan")

    # complete matrix
    dev_used = dev
    r_used = pivot.index.to_numpy(dtype=float)
    t_used = pivot.columns.to_numpy(dtype=float)
    if bool(cfg.complete_only):
        ok_r = np.all(np.isfinite(dev), axis=1)
        ok_t = np.all(np.isfinite(dev), axis=0)
        dev_used = dev[np.where(ok_r)[0][:], :][:, np.where(ok_t)[0]]
        r_used = r_used[ok_r]
        t_used = t_used[ok_t]
        if dev_used.size == 0 or dev_used.shape[0] < 2 or dev_used.shape[1] < 2:
            mode_used = "fill_missing_fallback"
            dev_used = np.where(np.isfinite(dev), dev, float(fill_value))
            r_used = pivot.index.to_numpy(dtype=float)
            t_used = pivot.columns.to_numpy(dtype=float)
    else:
        dev_used = np.where(np.isfinite(dev), dev, float(fill_value))

    # SVD
    u, s, vt = np.linalg.svd(dev_used, full_matrices=False)
    frac1 = _svd_energy_frac1(s)
    sigma1 = float(s[0]) if s.size else float("nan")

    # rank-1 reconstruction relative error
    denom = float(np.linalg.norm(dev_used))
    if dev_used.size and s.size and np.isfinite(denom) and denom > 0:
        rank1 = (s[0] * np.outer(u[:, 0], vt[0, :])).astype(float)
        rel_err = float(np.linalg.norm(dev_used - rank1) / denom)
    else:
        rel_err = float("nan")

    spec_rows = []
    e = np.square(s)
    e_sum = float(np.sum(e)) if e.size else float("nan")
    cum = 0.0
    for k, sv in enumerate(s.tolist(), start=1):
        ev = float(sv) ** 2
        cum += ev
        spec_rows.append(
            {
                "k": int(k),
                "sigma": float(sv),
                "energy_frac": float(ev / e_sum) if np.isfinite(e_sum) and e_sum > 0 else float("nan"),
                "energy_cum": float(cum / e_sum) if np.isfinite(e_sum) and e_sum > 0 else float("nan"),
            }
        )
    pd.DataFrame(spec_rows).to_csv(tabs / "svd_spectrum.csv", index=False)

    summary = {
        "slug": str(cfg.slug),
        "value_col": value_col,
        "dev_mode": dev_mode,
        "time_min": cfg.time_min,
        "time_max": cfg.time_max,
        "min_tiles_overlap": int(cfg.min_tiles_overlap),
        "complete_only": int(bool(cfg.complete_only)),
        "mode_used": str(mode_used),
        "n_r_bins_used": int(dev_used.shape[0]),
        "n_time_used": int(dev_used.shape[1]),
        "nan_frac_raw_matrix": float(nan_frac),
        "sigma1": float(sigma1),
        "sigma1_energy_frac": float(frac1),
        "rank1_rel_error": float(rel_err),
        "singular_values": json.dumps([float(x) for x in s.tolist()[:12]], ensure_ascii=False),
    }
    pd.DataFrame([summary]).to_csv(tabs / "svd_separability_summary.csv", index=False)
    (out_dir / "metadata.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # plot spectrum (optional)
    try:
        from disaster import plot_style as ps  # type: ignore
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        print(f"Done. Wrote: {tabs / 'svd_separability_summary.csv'}")
        return

    with ps.paper_style():
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_HALF)
        ks = np.arange(1, int(len(s)) + 1, dtype=int)
        ax.plot(ks, s, marker="o", ms=4, lw=1.5, color=ps.OKABE_ITO["blue"])
        ax.set_xlabel("k")
        ax.set_ylabel("singular value σ_k")
        ax.set_title(f"SVD spectrum: {cfg.slug}\nσ1 energy frac={frac1:.3f}, mode={mode_used}")
        ax.set_yscale("log" if np.nanmax(s) / max(np.nanmin(s[np.isfinite(s)]), 1e-12) > 50 else "linear")
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, figs / "svd_spectrum.png")
        plt.close(fig)

    print(f"Done. Wrote: {tabs / 'svd_separability_summary.csv'}")


def cli_main() -> None:
    p = argparse.ArgumentParser(description="对 φ(r,t) 矩阵做 SVD：评估 rank-1 可分离性（σ1 能量占比）")
    p.add_argument("--output-root", type=Path, required=True, help="包含 <slug>/phi_heatmap/... 的目录")
    p.add_argument("--slug", type=str, required=True)
    p.add_argument("--out-dir", type=Path, default=Path("outputs/_tmp_phi_svd"))
    p.add_argument("--value-col", type=str, default="phi_overlap", choices=["phi_aggregate", "phi_overlap"])
    p.add_argument("--dev-mode", type=str, default="signed", choices=["signed", "abs", "raw"])
    p.add_argument("--time-min", type=float, default=None)
    p.add_argument("--time-max", type=float, default=None)
    p.add_argument("--min-tiles-overlap", type=int, default=0)
    p.add_argument("--complete-only", action="store_true", help="只用完全无缺失的 r×t 子矩阵；否则用 fill_missing_fallback")
    args = p.parse_args()

    run(
        Config(
            output_root=Path(args.output_root),
            slug=str(args.slug),
            out_dir=Path(args.out_dir),
            value_col=str(args.value_col),
            dev_mode=str(args.dev_mode),
            time_min=(float(args.time_min) if args.time_min is not None else None),
            time_max=(float(args.time_max) if args.time_max is not None else None),
            min_tiles_overlap=int(args.min_tiles_overlap),
            complete_only=bool(args.complete_only),
        )
    )


if __name__ == "__main__":
    cli_main()

