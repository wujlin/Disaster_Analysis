from __future__ import annotations

import argparse
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
    input_csv: Path
    output_dir: Path
    base_boundaries_km: tuple[float, ...] = (25.0, 50.0, 100.0, 200.0)
    jitter_sigma: float = 0.25
    n_schemes: int = 200
    seed: int = 7
    min_edge_km: float = 5.0
    max_edge_km: float = 800.0


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _jittered_edges(rng: np.random.Generator, base: np.ndarray, *, sigma: float, lo: float, hi: float) -> np.ndarray:
    # log-normal jitter + sort
    edges = base * np.exp(rng.normal(0.0, float(sigma), size=base.size))
    edges = np.clip(edges, float(lo), float(hi))
    edges = np.unique(np.sort(edges))
    return edges


def run(cfg: Config) -> None:
    if not cfg.input_csv.exists():
        raise FileNotFoundError(f"未找到输入：{cfg.input_csv}")

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

    df = pd.read_csv(cfg.input_csv)
    required = {"distance_km", "tau_hours"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"输入缺少列：{missing}（来自 {cfg.input_csv}）")

    r = pd.to_numeric(df["distance_km"], errors="coerce").to_numpy(dtype=float)
    tau = pd.to_numeric(df["tau_hours"], errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(r) & np.isfinite(tau) & (r >= 0) & (tau > 0)
    r = r[mask]
    tau = tau[mask]
    if r.size < 1000:
        raise SystemExit("有效 tiles 太少，无法做 binning 敏感性分析。")

    rng = np.random.default_rng(int(cfg.seed))
    base = np.array(cfg.base_boundaries_km, dtype=float)

    rows: list[dict] = []
    for sid in range(int(cfg.n_schemes)):
        edges = _jittered_edges(
            rng,
            base,
            sigma=float(cfg.jitter_sigma),
            lo=float(cfg.min_edge_km),
            hi=float(cfg.max_edge_km),
        )
        if edges.size < 2:
            continue
        bins = np.concatenate([[0.0], edges, [np.inf]])
        lo = bins[:-1]
        hi = bins[1:]

        medians: list[float] = []
        counts: list[int] = []
        for a, b in zip(lo, hi, strict=False):
            m = (r >= float(a)) & (r < float(b))
            counts.append(int(np.sum(m)))
            medians.append(float(np.nanmedian(tau[m])) if np.any(m) else float("nan"))

        med = np.array(medians, dtype=float)
        cnt = np.array(counts, dtype=int)
        valid = np.isfinite(med) & (cnt >= 50)
        if not np.any(valid):
            continue
        win = int(np.nanargmin(np.where(valid, med, np.nan)))
        win_lo = float(lo[win])
        win_hi = float(hi[win]) if np.isfinite(hi[win]) else float("nan")
        if np.isfinite(win_hi) and win_hi > win_lo:
            win_mid = float(np.sqrt(win_lo * win_hi)) if win_lo > 0 else float(win_hi / 2.0)
        else:
            win_mid = float(win_lo)

        rows.append(
            {
                "scheme_id": int(sid),
                "edges_km": ",".join([f"{x:.2f}" for x in edges.tolist()]),
                "winner_lo_km": win_lo,
                "winner_hi_km": win_hi,
                "winner_mid_km": win_mid,
                "winner_median_tau_hours": float(med[win]),
                "winner_n_tiles": int(cnt[win]),
            }
        )

    if not rows:
        raise SystemExit("没有生成任何有效的 binning scheme 结果（请降低最小 tiles 数阈值或增大样本）。")

    res = pd.DataFrame(rows)
    out_csv = out.tables / "binning_sensitivity_winner_bins.csv"
    res.to_csv(out_csv, index=False)

    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        mids = pd.to_numeric(res["winner_mid_km"], errors="coerce").to_numpy(dtype=float)
        mids = mids[np.isfinite(mids) & (mids > 0)]
        ax.hist(mids, bins=40, color=ps.OKABE_ITO["bluish_green"], alpha=0.85)
        ax.set_xscale("log")
        ax.set_xlabel("Winner bin mid distance (km)")
        ax.set_ylabel("Count")
        ax.set_title("Binning sensitivity: which distance range minimizes median $\\tau_i$?")
        for x in cfg.base_boundaries_km:
            ax.axvline(float(x), color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.0, alpha=0.6)
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "winner_mid_distance_hist.png")
        plt.close(fig)

    readme = f"""# Binning Sensitivity (tile-level $\\tau_i$)

目的：验证“50–100km 恢复最快”是否只是人为分箱产物。
方法：在 `base={list(cfg.base_boundaries_km)}` 的基础上对边界做 log-normal jitter，重复 {int(cfg.n_schemes)} 次。
每个 scheme 用各 bin 内 **median $\\tau_i$** 找 winner bin，并统计 winner 的距离分布。

## 输入

- `{cfg.input_csv}`（来自 `scripts/tau_continuous_fit.py` 的 `tile_level_tau.csv`）

## 输出

- `tables/binning_sensitivity_winner_bins.csv`
- `figures/winner_mid_distance_hist.*`
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_csv}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=Path("outputs/tau_continuous_fit/tables/tile_level_tau.csv"),
        help="tile-level τ 表",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/binning_sensitivity_tau"), help="输出目录")
    parser.add_argument("--n-schemes", type=int, default=200, help="binning scheme 数量")
    parser.add_argument("--jitter-sigma", type=float, default=0.25, help="log-space jitter 强度")
    parser.add_argument("--seed", type=int, default=7, help="随机种子")
    parser.add_argument("--min-edge-km", type=float, default=5.0, help="bin 边界最小值")
    parser.add_argument("--max-edge-km", type=float, default=800.0, help="bin 边界最大值")
    args = parser.parse_args()

    cfg = Config(
        input_csv=args.input_csv,
        output_dir=args.output_dir,
        n_schemes=int(args.n_schemes),
        jitter_sigma=float(args.jitter_sigma),
        seed=int(args.seed),
        min_edge_km=float(args.min_edge_km),
        max_edge_km=float(args.max_edge_km),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()

