from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.cross_disaster_phi_tau import load_catalog
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    catalog: Path
    output_root: Path
    output_dir: Path
    min_hours: float = -16.0
    max_hours: float = 832.0
    max_distance_km: float = 500.0
    phi_vmin: float = 0.6
    phi_vmax: float = 1.6


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _load_matrix(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    df = pd.read_csv(path)
    if "r_bin_km" not in df.columns:
        raise SystemExit(f"{path} 缺少列：r_bin_km")
    r = pd.to_numeric(df["r_bin_km"], errors="coerce").to_numpy(dtype=float)
    cols = [c for c in df.columns if c != "r_bin_km"]
    t: list[float] = []
    for c in cols:
        try:
            t.append(float(c))
        except Exception:
            t.append(float("nan"))
    times = np.array(t, dtype=float)
    z = df[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    return r, times, z


def run(cfg: Config) -> None:
    specs = load_catalog(cfg.catalog)
    _ensure_dir(cfg.output_dir)
    _ensure_dir(cfg.output_dir / "figures")

    mats: list[dict] = []
    for spec in specs:
        p = cfg.output_root / spec.slug / "phi_heatmap" / "tables" / "phi_rt_matrix.csv"
        if not p.exists():
            print(f"[phi_heatmap_panel] skip missing: {p}")
            continue
        r, times, z = _load_matrix(p)
        mats.append({"slug": spec.slug, "name": spec.name, "event_type": spec.event_type, "r": r, "t": times, "z": z})

    if not mats:
        raise SystemExit("没有可用的 heatmap matrix（请先运行 scripts/cross_disaster_phi_heatmap.py）")

    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    n = len(mats)
    ncols = 2 if n > 1 else 1
    nrows = int(np.ceil(n / ncols))

    with ps.paper_style():
        import matplotlib.pyplot as plt
        from matplotlib.colors import TwoSlopeNorm

        fig_w = ps.FIGSIZE_FULL[0]
        fig_h = ps.FIGSIZE_FULL[1] * (1.3 if nrows == 2 else 1.05)
        fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(fig_w, fig_h), sharex=True, sharey=True)
        axes = np.array(axes).reshape(-1)

        norm = TwoSlopeNorm(vmin=float(cfg.phi_vmin), vcenter=1.0, vmax=float(cfg.phi_vmax))
        last_im = None
        panel_labels = list("abcdefghijklmnopqrstuvwxyz")

        for i, ax in enumerate(axes):
            if i >= n:
                ax.axis("off")
                continue
            item = mats[i]
            z = np.array(item["z"], dtype=float)

            last_im = ax.imshow(
                z,
                origin="lower",
                aspect="auto",
                cmap="RdBu_r",
                norm=norm,
                extent=[float(cfg.min_hours) - 4.0, float(cfg.max_hours) + 4.0, 0.0, float(cfg.max_distance_km)],
            )
            ax.axvline(0.0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.1, alpha=0.7)
            ax.set_title(f"{item['slug']} ({item['event_type']})", fontsize=10)
            ps.add_panel_label(ax, panel_labels[i])
            ps.despine(ax)

        for ax in axes:
            ax.set_xlabel("Hours since event")
            ax.set_ylabel("r (km)")

        # ticks
        xt = np.array([-16, 0, 160, 320, 480, 640, 800], dtype=float)
        xt = xt[(xt >= float(cfg.min_hours)) & (xt <= float(cfg.max_hours))]
        if xt.size:
            for ax in axes:
                ax.set_xticks(xt)
                ax.set_xticklabels([f"{int(x)}" for x in xt])

        yt = np.array([0, 100, 200, 300, 400, 500], dtype=float)
        yt = yt[(yt >= 0) & (yt <= float(cfg.max_distance_km))]
        if yt.size:
            for ax in axes:
                ax.set_yticks(yt)
                ax.set_yticklabels([f"{int(y)}" for y in yt])

        if last_im is not None:
            cb = fig.colorbar(last_im, ax=axes.tolist(), shrink=0.92, pad=0.02)
            cb.set_label(r"$\phi_{agg}$")

        fig.suptitle(r"Cross-disaster $\phi_{agg}(r,t)$ heatmaps (shared scale)", y=0.98)
        fig.subplots_adjust(left=0.08, right=0.96, bottom=0.10, top=0.90, wspace=0.18, hspace=0.28)
        save_png_and_pdf(ps, fig, cfg.output_dir / "figures" / "phi_heatmap_panel.png")
        plt.close(fig)

    readme = f"""# Cross-disaster Heatmap Panel (Task 4)

把各灾害的 `outputs/<slug>/phi_heatmap/tables/phi_rt_matrix.csv` 放到同一张图里对比（统一色标）。

## 输入

- catalog: `{cfg.catalog}`
- per-disaster heatmap: `outputs/<slug>/phi_heatmap/`（需先跑 `scripts/cross_disaster_phi_heatmap.py`）

## 输出

- `figures/phi_heatmap_panel.*`
"""
    (cfg.output_dir / "README.md").write_text(readme, encoding="utf-8")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog.csv"), help="灾难配置表（CSV）")
    parser.add_argument("--output-root", type=Path, default=Path("outputs"), help="outputs 根目录（含 <slug>/phi_heatmap/）")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/cross_disaster_comparison/phi_heatmap_comparison"),
        help="输出目录",
    )
    parser.add_argument("--min-hours", type=float, default=-16.0, help="x 轴最小值（默认 -16）")
    parser.add_argument("--max-hours", type=float, default=832.0, help="x 轴最大值（默认 832）")
    parser.add_argument("--max-distance-km", type=float, default=500.0, help="y 轴最大距离（默认 500）")
    parser.add_argument("--phi-vmin", type=float, default=0.6, help="色标 vmin（默认 0.6）")
    parser.add_argument("--phi-vmax", type=float, default=1.6, help="色标 vmax（默认 1.6）")
    args = parser.parse_args()

    cfg = Config(
        catalog=args.catalog,
        output_root=args.output_root,
        output_dir=args.output_dir,
        min_hours=float(args.min_hours),
        max_hours=float(args.max_hours),
        max_distance_km=float(args.max_distance_km),
        phi_vmin=float(args.phi_vmin),
        phi_vmax=float(args.phi_vmax),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()
