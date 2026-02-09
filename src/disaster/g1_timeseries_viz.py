from __future__ import annotations

import argparse
from math import ceil
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _load_series(path: Path) -> pd.DataFrame:
    if not Path(path).exists():
        raise FileNotFoundError(f"未找到：{path}")
    df = pd.read_csv(path)
    need = {"slug", "hours_since_quake", "g1", "abs_g1"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise SystemExit(f"{path} 缺少列：{miss}")
    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df["g1"] = pd.to_numeric(df["g1"], errors="coerce")
    df["abs_g1"] = pd.to_numeric(df["abs_g1"], errors="coerce")
    df = df.dropna(subset=["slug", "hours_since_quake", "g1", "abs_g1"]).copy()
    return df


def run(*, input_csv: Path, out_dir: Path, slugs: list[str], max_cols: int) -> None:
    out_dir = Path(out_dir)
    tabs = out_dir / "tables"
    figs = out_dir / "figures"
    _ensure_dir(tabs)
    _ensure_dir(figs)

    df = _load_series(Path(input_csv))
    want = [str(s).strip() for s in slugs if str(s).strip()]
    if not want:
        raise SystemExit("--slugs 为空")

    sub = df[df["slug"].astype(str).isin(set(want))].copy()
    if sub.empty:
        raise SystemExit(f"未找到任何指定 slug 的 g1 记录：{want}")

    sub["t_days"] = sub["hours_since_quake"].to_numpy(dtype=float) / 24.0
    sub = sub.sort_values(["slug", "hours_since_quake"], kind="stable")
    sub.to_csv(tabs / "g1_timeseries_selected.csv", index=False)

    # figures (optional)
    try:
        from disaster import plot_style as ps  # type: ignore
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        return

    want = [s for s in want if s in set(sub["slug"].astype(str).unique().tolist())]
    n = len(want)
    ncols = int(max(1, max_cols))
    nrows = int(ceil(n / ncols))

    with ps.paper_style():
        fig, axes = plt.subplots(
            nrows=nrows,
            ncols=ncols,
            figsize=(3.9 * ncols, 2.9 * nrows),
            squeeze=False,
            constrained_layout=True,
        )
        for i, slug in enumerate(want):
            ax = axes[i // ncols][i % ncols]
            s = sub[sub["slug"] == slug].copy()
            x = pd.to_numeric(s["t_days"], errors="coerce").to_numpy(dtype=float)
            y_signed = pd.to_numeric(s["g1"], errors="coerce").to_numpy(dtype=float)
            y_abs = pd.to_numeric(s["abs_g1"], errors="coerce").to_numpy(dtype=float)

            ax.plot(x, y_signed, color=ps.OKABE_ITO["blue"], lw=1.8, marker="o", ms=3.5, label="g1(t)")
            ax.axhline(0, color=ps.OKABE_ITO["gray"], lw=1.0, ls="--", alpha=0.7)
            ax2 = ax.twinx()
            ok = np.isfinite(y_abs) & (y_abs > 0)
            ax2.plot(x[ok], y_abs[ok], color=ps.OKABE_ITO["vermillion"], lw=1.6, marker="s", ms=3.0, alpha=0.85, label="|g1(t)|")
            ax2.set_yscale("log")

            ax.set_title(str(slug), fontsize=9)
            ax.set_xlabel("t (days since t0)")
            ax.set_ylabel("g1(t)")
            ax2.set_ylabel("|g1(t)| (log)")
            ps.despine(ax)
            ax2.spines["top"].set_visible(False)

        # hide unused
        for j in range(n, nrows * ncols):
            axes[j // ncols][j % ncols].axis("off")

        fig.savefig(figs / "g1_timeseries_selected.png", dpi=220)
        fig.savefig(figs / "g1_timeseries_selected.pdf")
        plt.close(fig)


def cli_main() -> None:
    p = argparse.ArgumentParser(description="可视化指定事件的 g1(t) 原始曲线（含 |g1| 对数轴）")
    p.add_argument(
        "--input-csv",
        type=Path,
        default=Path("outputs/cross_disaster_comparison/rank1_dynamics_sigma070_min4/tables/g1_timeseries_long.csv"),
        help="cross_disaster_rank1_dynamics 生成的 g1_timeseries_long.csv",
    )
    p.add_argument("--out-dir", type=Path, default=Path("outputs/cross_disaster_comparison/g1_timeseries_viz"))
    p.add_argument("--slugs", type=str, nargs="*", default=[], help="要画的 slugs（空则报错）")
    p.add_argument("--max-cols", type=int, default=2, help="多事件拼图列数（默认 2）")
    args = p.parse_args()

    run(input_csv=Path(args.input_csv), out_dir=Path(args.out_dir), slugs=list(args.slugs or []), max_cols=int(args.max_cols))


if __name__ == "__main__":
    cli_main()

