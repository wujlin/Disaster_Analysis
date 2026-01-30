from __future__ import annotations

from pathlib import Path

import numpy as np

from disaster.geo import distance_bin_labels


def default_distance_bin_color_map(ps, labels: list[str]) -> dict[str, str]:
    palette = [
        ps.OKABE_ITO["vermillion"],
        ps.OKABE_ITO["orange"],
        ps.OKABE_ITO["bluish_green"],
        ps.OKABE_ITO["sky_blue"],
        ps.OKABE_ITO["blue"],
        ps.OKABE_ITO["gray"],
    ]
    return {label: palette[i % len(palette)] for i, label in enumerate(labels)}


def save_png_and_pdf(ps, fig, png_path: Path, *, png_dpi: int = 200) -> None:
    ps.save_figure(fig, png_path, dpi=png_dpi)
    ps.save_figure(fig, png_path.with_suffix(".pdf"))


def plot_zscore_heatmap(df, output_path: Path, title: str, *, cfg, ps) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
    sc = ax.scatter(
        df["lon"].to_numpy(),
        df["lat"].to_numpy(),
        c=df["z_score"].to_numpy(),
        s=6,
        alpha=0.8,
        cmap="RdBu_r",
        vmin=-4,
        vmax=4,
        linewidths=0,
        rasterized=True,
    )
    ax.scatter(
        [cfg.epicenter_lon],
        [cfg.epicenter_lat],
        s=80,
        c=ps.OKABE_ITO["yellow"],
        edgecolors="black",
        linewidths=1.0,
        zorder=5,
    )
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(title)
    ps.despine(ax)
    cb = fig.colorbar(sc, ax=ax, shrink=0.88)
    cb.set_label(r"$z$-score (clipped to [-4, 4])")
    fig.tight_layout()
    save_png_and_pdf(ps, fig, output_path)
    plt.close(fig)


def plot_relaxation_curves(
    ts,
    *,
    y_col: str,
    y_std_col: str,
    y_n_col: str,
    output_path: Path,
    title: str,
    cfg,
    ps,
    band_alpha: float = 0.18,
) -> None:
    import matplotlib.pyplot as plt

    labels = distance_bin_labels(cfg.distance_bins_km)
    color_map = default_distance_bin_color_map(ps, labels)

    fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
    for dist_bin, sub in ts.groupby("distance_bin", sort=False, observed=True):
        sub = sub.sort_values("hours_since_quake")
        n = sub[y_n_col].to_numpy(dtype=float)
        se = sub[y_std_col].to_numpy(dtype=float) / np.sqrt(np.where(n > 0, n, np.nan))

        x = sub["hours_since_quake"].to_numpy(dtype=float)
        y = sub[y_col].to_numpy(dtype=float)
        color = color_map.get(str(dist_bin), ps.OKABE_ITO["gray"])

        ax.plot(x, y, marker="o", color=color, label=str(dist_bin))
        ax.fill_between(x, y - se, y + se, color=color, alpha=band_alpha, linewidth=0)

    ax.axvline(0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
    ax.axhline(0, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.6)
    ax.set_xlabel("Hours since earthquake (PT windows)")
    ax.set_ylabel(y_col)
    ax.set_title(title)
    ps.despine(ax)

    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3, frameon=False)
    fig.subplots_adjust(bottom=0.28)
    save_png_and_pdf(ps, fig, output_path)
    plt.close(fig)
