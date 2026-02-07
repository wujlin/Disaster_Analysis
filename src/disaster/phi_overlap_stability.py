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
    out_dir: Path
    slugs: tuple[str, ...] = ()
    min_hours: float | None = None
    max_hours: float | None = None


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _infer_slugs(output_root: Path) -> list[str]:
    slugs: list[str] = []
    for p in sorted(output_root.glob("*/phi_heatmap/tables/phi_rt_long.csv")):
        slugs.append(p.parents[2].name)
    return slugs


def _cv(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 2:
        return float("nan")
    mu = float(np.mean(x))
    sd = float(np.std(x, ddof=1))
    return float(sd / mu) if np.isfinite(mu) and mu != 0 else float("nan")


def _summarize_one(df: pd.DataFrame, *, slug: str) -> pd.DataFrame:
    need = {"hours_since_quake", "r_bin_km", "n_tiles_overlap"}
    missing = sorted(need - set(df.columns))
    if missing:
        raise SystemExit(f"{slug}: phi_rt_long 缺少列：{missing}")

    out = df.copy()
    out["hours_since_quake"] = pd.to_numeric(out["hours_since_quake"], errors="coerce")
    out["r_bin_km"] = pd.to_numeric(out["r_bin_km"], errors="coerce")
    out["n_tiles_overlap"] = pd.to_numeric(out["n_tiles_overlap"], errors="coerce")
    if "tile_overlap_ratio" in out.columns:
        out["tile_overlap_ratio"] = pd.to_numeric(out["tile_overlap_ratio"], errors="coerce")

    out = out.dropna(subset=["hours_since_quake", "r_bin_km"]).copy()

    agg_cols: dict[str, tuple[str, str]] = {
        "n_windows": ("hours_since_quake", "nunique"),
        "n_tiles_overlap_min": ("n_tiles_overlap", "min"),
        "n_tiles_overlap_mean": ("n_tiles_overlap", "mean"),
        "n_tiles_overlap_max": ("n_tiles_overlap", "max"),
        "n_tiles_overlap_std": ("n_tiles_overlap", "std"),
    }
    if "tile_overlap_ratio" in out.columns:
        agg_cols.update(
            {
                "tile_overlap_ratio_min": ("tile_overlap_ratio", "min"),
                "tile_overlap_ratio_mean": ("tile_overlap_ratio", "mean"),
                "tile_overlap_ratio_max": ("tile_overlap_ratio", "max"),
                "tile_overlap_ratio_std": ("tile_overlap_ratio", "std"),
            }
        )

    g = out.groupby("r_bin_km", sort=True, observed=True).agg(**agg_cols).reset_index()
    g.insert(0, "slug", str(slug))

    # CV（需要 numpy 更方便，按行计算）
    g["n_tiles_overlap_cv"] = np.nan
    if "tile_overlap_ratio_std" in g.columns:
        g["tile_overlap_ratio_cv"] = np.nan

    # 逐 r_bin 计算 CV（避免 groupby apply 的性能/兼容性问题）
    for idx, row in g.iterrows():
        rbin = float(row["r_bin_km"])
        sub = out[out["r_bin_km"] == rbin]
        g.loc[idx, "n_tiles_overlap_cv"] = _cv(sub["n_tiles_overlap"].to_numpy(dtype=float))
        if "tile_overlap_ratio" in sub.columns and "tile_overlap_ratio_cv" in g.columns:
            g.loc[idx, "tile_overlap_ratio_cv"] = _cv(sub["tile_overlap_ratio"].to_numpy(dtype=float))

    return g


def _plot_heatmap(
    df_long: pd.DataFrame,
    *,
    slug: str,
    out_path: Path,
    value_col: str,
    title: str,
) -> None:
    try:
        from disaster import plot_style as ps  # type: ignore
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        return

    tmp = df_long.copy()
    tmp["hours_since_quake"] = pd.to_numeric(tmp["hours_since_quake"], errors="coerce")
    tmp["r_bin_km"] = pd.to_numeric(tmp["r_bin_km"], errors="coerce")
    tmp[value_col] = pd.to_numeric(tmp[value_col], errors="coerce")
    tmp = tmp.dropna(subset=["hours_since_quake", "r_bin_km"]).copy()
    if tmp.empty:
        return

    pivot = tmp.pivot_table(index="r_bin_km", columns="hours_since_quake", values=value_col, aggfunc="first")
    pivot = pivot.sort_index(axis=0).sort_index(axis=1)
    z = pivot.to_numpy(dtype=float)
    if z.size == 0:
        return

    xs = pivot.columns.to_numpy(dtype=float)
    ys = pivot.index.to_numpy(dtype=float)
    if xs.size == 0 or ys.size == 0:
        return

    with ps.paper_style():
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        im = ax.imshow(z, origin="lower", aspect="auto", cmap="viridis")
        ax.set_title(f"{title}\n{slug}")
        ax.set_xlabel("hours_since_quake")
        ax.set_ylabel("r_bin_km")
        cb = fig.colorbar(im, ax=ax, shrink=0.92)
        cb.set_label(value_col)
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out_path)
        plt.close(fig)


def run(cfg: Config) -> None:
    out = Path(cfg.out_dir)
    tabs = out / "tables"
    figs = out / "figures"
    _ensure_dir(tabs)
    _ensure_dir(figs)

    slugs = list(cfg.slugs) if cfg.slugs else _infer_slugs(Path(cfg.output_root))
    if not slugs:
        raise SystemExit(f"未找到任何 phi_rt_long.csv：{cfg.output_root}")

    rows: list[pd.DataFrame] = []
    summary_rows: list[dict] = []
    for slug in slugs:
        p = Path(cfg.output_root) / slug / "phi_heatmap" / "tables" / "phi_rt_long.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if "hours_since_quake" not in df.columns:
            continue

        df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
        df = df[df["hours_since_quake"].notna()].copy()
        if cfg.min_hours is not None:
            df = df[df["hours_since_quake"] >= float(cfg.min_hours)].copy()
        if cfg.max_hours is not None:
            df = df[df["hours_since_quake"] <= float(cfg.max_hours)].copy()
        if df.empty:
            continue

        by_r = _summarize_one(df, slug=str(slug))
        rows.append(by_r)

        n_time = int(df["hours_since_quake"].nunique())
        n_r = int(by_r.shape[0])
        summary_rows.append(
            {
                "slug": str(slug),
                "n_time_windows": int(n_time),
                "n_r_bins": int(n_r),
                "n_tiles_overlap_cv_mean": float(np.nanmean(pd.to_numeric(by_r["n_tiles_overlap_cv"], errors="coerce").to_numpy(dtype=float))),
                "n_tiles_overlap_cv_p95": float(np.nanpercentile(pd.to_numeric(by_r["n_tiles_overlap_cv"], errors="coerce").to_numpy(dtype=float), 95))
                if n_r
                else float("nan"),
            }
        )

        _plot_heatmap(
            df,
            slug=str(slug),
            out_path=figs / f"{slug}__n_tiles_overlap_heatmap.png",
            value_col="n_tiles_overlap",
            title="n_tiles_overlap by (r,t)",
        )
        if "tile_overlap_ratio" in df.columns:
            _plot_heatmap(
                df,
                slug=str(slug),
                out_path=figs / f"{slug}__tile_overlap_ratio_heatmap.png",
                value_col="tile_overlap_ratio",
                title="tile_overlap_ratio by (r,t)",
            )

    out_df = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    out_df.to_csv(tabs / "overlap_stability_by_rbin.csv", index=False)
    pd.DataFrame(summary_rows).to_csv(tabs / "overlap_stability_summary.csv", index=False)

    meta = {
        "output_root": str(Path(cfg.output_root)),
        "slugs": slugs,
        "min_hours": cfg.min_hours,
        "max_hours": cfg.max_hours,
    }
    (out / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Done. Wrote: {tabs / 'overlap_stability_by_rbin.csv'}")


def cli_main() -> None:
    p = argparse.ArgumentParser(description="诊断 phi_overlap 的 tile overlap 时序稳定性（composition effect 检查）")
    p.add_argument("--output-root", type=Path, required=True, help="包含 <slug>/phi_heatmap/... 的目录")
    p.add_argument("--out-dir", type=Path, default=Path("outputs/_tmp_phi_overlap_stability"))
    p.add_argument("--slug", type=str, nargs="*", default=None, help="只分析指定 slug（可多个；默认自动扫描 output-root）")
    p.add_argument("--min-hours", type=float, default=None)
    p.add_argument("--max-hours", type=float, default=None)
    args = p.parse_args()

    run(
        Config(
            output_root=Path(args.output_root),
            out_dir=Path(args.out_dir),
            slugs=tuple(str(s) for s in (args.slug or ())),
            min_hours=float(args.min_hours) if args.min_hours is not None else None,
            max_hours=float(args.max_hours) if args.max_hours is not None else None,
        )
    )


if __name__ == "__main__":
    cli_main()

