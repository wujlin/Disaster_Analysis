"""
Figure 4: Amplitude Effect and Two-Dimensional Prediction Framework
2-panel: (a) α vs D_peak scatter | (b) 2D framework δ_near × D_peak coloured by α.
Shared hazard-type legend at figure bottom.
"""
import sys, os
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
from matplotlib.lines import Line2D
from scipy.stats import spearmanr, theilslopes
from src.disaster.plot_style import (
    paper_style, OKABE_ITO, add_panel_label, save_figure, despine,
)

ROOT = "outputs/cross_disaster_comparison"
FLAGS_CSV = f"{ROOT}/Dt_decay/tables/Dt_routeB_sample_flags.csv"
OUT_DIR = "Essay/figures"
OUT_PDF = f"{OUT_DIR}/fig4_amplitude_orthogonality.pdf"
OUT_PNG = f"{OUT_DIR}/fig4_amplitude_orthogonality.png"

DTYPE_COLOR = {
    "earthquake": OKABE_ITO["vermillion"],
    "hurricane":  OKABE_ITO["blue"],
    "typhoon":    OKABE_ITO["blue"],
    "flood":      OKABE_ITO["bluish_green"],
    "wildfire":   OKABE_ITO["orange"],
}

R2_THRESHOLD = 0.75
PAD = 0.04  # unified absolute padding for both axes in panel (b)


def _shared_legend_handles():
    return [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=OKABE_ITO["vermillion"],
               markersize=6, markeredgecolor="none", label="Earthquake"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=OKABE_ITO["blue"],
               markersize=6, markeredgecolor="none", label="Hurricane / Typhoon"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=OKABE_ITO["bluish_green"],
               markersize=6, markeredgecolor="none", label="Flood"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=OKABE_ITO["orange"],
               markersize=6, markeredgecolor="none", label="Wildfire"),
    ]


def load_data():
    flags = pd.read_csv(FLAGS_CSV)
    return flags[flags["route_b_selected"] == True].copy()


def panel_a(ax, flags16):
    """α vs D_peak scatter with Theil-Sen line. Stat in upper right."""
    x = flags16["D_peak"].values
    y = flags16["alpha"].values

    res = theilslopes(y, x, 0.95)
    x_line = np.linspace(x.min() - PAD, x.max() + PAD, 100)
    ax.plot(x_line, res.slope * x_line + res.intercept,
            color="gray", ls="--", lw=1.2, alpha=0.7, zorder=1)

    for _, row in flags16.iterrows():
        xi = row["D_peak"]
        yi = row["alpha"]
        dtype = row["disaster_type"]
        ri2 = row["r2"]
        color = DTYPE_COLOR.get(dtype, "gray")
        fc = color if ri2 >= R2_THRESHOLD else "none"
        ax.scatter(xi, yi, s=42, marker="o",
                   facecolors=fc, edgecolors=color,
                   linewidths=1.0,
                   alpha=0.95 if ri2 >= R2_THRESHOLD else 0.5, zorder=3)

    rho, pval = spearmanr(x, y)
    ax.text(0.97, 0.97,
            fr"$\rho = +{rho:.2f}$, $p = {pval:.3f}$",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.5)

    ax.set_xlabel(r"$D_{\mathrm{peak}}$")
    ax.set_ylabel(r"$\alpha$ (decay rate)")
    despine(ax)


def panel_b(ax, flags16):
    """2D framework: δ_near × D_peak, coloured by α."""
    x = flags16["near_delta_peak_windows_mean"].values
    y = flags16["D_peak"].values
    alpha_vals = flags16["alpha"].values

    vmin, vmax = alpha_vals.min(), alpha_vals.max()
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    cmap = plt.get_cmap("plasma")

    for _, row in flags16.iterrows():
        xi = row["near_delta_peak_windows_mean"]
        yi = row["D_peak"]
        ai = row["alpha"]
        color = cmap(norm(ai))
        ax.scatter(xi, yi, color=color, s=55, marker="o",
                   edgecolors="white", linewidths=0.5, zorder=4)

    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cb = plt.colorbar(sm, ax=ax, orientation="vertical",
                      fraction=0.05, pad=0.04, shrink=0.85)
    cb.set_label(r"Decay rate $\alpha$", fontsize=9)
    cb.ax.tick_params(labelsize=8)

    # Median quadrant lines
    ax.axvline(np.median(x), color="gray", lw=0.8, ls=":", alpha=0.5)
    ax.axhline(np.median(y), color="gray", lw=0.8, ls=":", alpha=0.5)

    # Unified absolute padding
    ax.set_xlim(x.min() - PAD, x.max() + PAD)
    ax.set_ylim(y.min() - PAD, y.max() + PAD)
    ax.set_xlabel(r"$\delta_{\mathrm{near}}$")
    ax.set_ylabel(r"$D_{\mathrm{peak}}$")
    despine(ax)


def main():
    flags16 = load_data()

    with paper_style():
        fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(6.5, 2.8))
        fig.subplots_adjust(wspace=0.45, left=0.10, right=0.94,
                            top=0.90, bottom=0.28)

        panel_a(ax_a, flags16)
        panel_b(ax_b, flags16)

        add_panel_label(ax_a, "a", dy=8)
        add_panel_label(ax_b, "b", dy=8)

        fig.legend(handles=_shared_legend_handles(),
                   loc="lower center", bbox_to_anchor=(0.5, 0.02),
                   ncol=4, fontsize=7.5, frameon=False,
                   handlelength=1, handletextpad=0.3, columnspacing=1.2)

        os.makedirs(OUT_DIR, exist_ok=True)
        save_figure(fig, OUT_PDF)
        save_figure(fig, OUT_PNG, dpi=150)
        plt.close(fig)

    print(f"Saved: {OUT_PDF}, {OUT_PNG}")


if __name__ == "__main__":
    main()
