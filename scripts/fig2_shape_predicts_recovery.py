"""
Figure 2: Spatial Shape of Initial Displacement Predicts Recovery Speed
2-panel: (a) α vs δ_near scatter  |  (b) contrasting radial profiles at peak.
Shared hazard-type legend at figure bottom.
"""
import sys, os
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.transforms import blended_transform_factory
from scipy.stats import spearmanr, theilslopes
from src.disaster.plot_style import (
    paper_style, OKABE_ITO, add_panel_label, save_figure, despine,
)

ROOT = "outputs/cross_disaster_comparison"
FLAGS_CSV = f"{ROOT}/Dt_decay/tables/Dt_routeB_sample_flags.csv"
PROFILES_CSV = f"{ROOT}/spatial_diffusion_results/tables/radial_profiles_at_peak.csv"
OUT_DIR = "Essay/figures"
OUT_PDF = f"{OUT_DIR}/fig2_shape_predicts_recovery.pdf"
OUT_PNG = f"{OUT_DIR}/fig2_shape_predicts_recovery.png"

DTYPE_COLOR = {
    "earthquake": OKABE_ITO["vermillion"],
    "hurricane":  OKABE_ITO["blue"],
    "typhoon":    OKABE_ITO["blue"],
    "flood":      OKABE_ITO["bluish_green"],
    "wildfire":   OKABE_ITO["orange"],
}

R2_THRESHOLD = 0.75
EVAC_SLUG = "hurricane_beryl_across_southeastern_texas_us"
INFL_SLUG = "spain_flood"


def _shared_legend_handles():
    """4-item hazard-type legend handles (reused across figures)."""
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
    flags16 = flags[flags["route_b_selected"] == True].copy()
    profiles = pd.read_csv(PROFILES_CSV)
    return flags16, profiles


def panel_a(ax, flags16):
    """α vs δ_near scatter with Theil-Sen line."""
    x = flags16["near_delta_peak_windows_mean"].values
    y = flags16["alpha"].values

    res = theilslopes(y, x, 0.95)
    x_line = np.linspace(x.min() - 0.02, x.max() + 0.02, 100)
    ax.plot(x_line, res.slope * x_line + res.intercept,
            color="gray", ls="--", lw=1.2, alpha=0.7, zorder=1)

    for _, row in flags16.iterrows():
        xi = row["near_delta_peak_windows_mean"]
        yi = row["alpha"]
        dtype = row["disaster_type"]
        ri2 = row["r2"]
        color = DTYPE_COLOR.get(dtype, "gray")
        fc = color if ri2 >= R2_THRESHOLD else "none"
        alpha_pt = 0.95 if ri2 >= R2_THRESHOLD else 0.5
        ax.scatter(xi, yi, s=42, marker="o",
                   facecolors=fc, edgecolors=color,
                   linewidths=1.0, alpha=alpha_pt, zorder=3)

    rho, pval = spearmanr(x, y)
    ax.text(0.97, 0.97,
            fr"$\rho = {rho:.2f}$, $p = {pval:.3f}$",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.5)

    ax.axhline(0, color="black", lw=0.5, alpha=0.3, ls=":")
    ax.axvline(0, color="black", lw=0.5, alpha=0.3, ls=":")
    ax.set_xlabel(r"$\delta_{\mathrm{near}}$")
    ax.set_ylabel(r"$\alpha$ (decay rate)")
    despine(ax)


def panel_b(ax, flags16, profiles):
    """Radial profiles at peak: EVAC vs INFL events."""
    r_near = 50

    def _plot_profile(slug, color, label):
        sub = profiles[profiles["slug"] == slug].copy()
        if sub.empty:
            return
        sub = sub.sort_values("r_bin_km")
        ax.plot(sub["r_bin_km"], sub["delta_at_peak"],
                color=color, lw=2.0, label=label, zorder=3)

    row_evac = flags16[flags16["slug"] == EVAC_SLUG]
    row_infl = flags16[flags16["slug"] == INFL_SLUG]
    a_evac = float(row_evac["alpha"].iloc[0]) if not row_evac.empty else 0
    a_infl = float(row_infl["alpha"].iloc[0]) if not row_infl.empty else 0

    _plot_profile(EVAC_SLUG, OKABE_ITO["blue"],
                  fr"Beryl, TX ($\alpha={a_evac:.2f}$)")
    _plot_profile(INFL_SLUG, OKABE_ITO["bluish_green"],
                  fr"Spain flood ($\alpha={a_infl:.2f}$)")

    ax.axhline(0, color="black", lw=0.7, ls="--", alpha=0.5)
    ax.axvspan(0, r_near, alpha=0.08, color="gray", zorder=0)

    ax.set_xlabel(r"Distance $r$ from epicenter (km)")
    ax.set_ylabel(r"$\delta(r,\,t_{\mathrm{peak}})$")
    ax.set_xlim(0, 200)
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    despine(ax)

    # "near-field" label in blended coords (data x, axes y)
    trans = blended_transform_factory(ax.transData, ax.transAxes)
    ax.text(r_near / 2, 0.93, "near-field",
            ha="center", va="top", fontsize=7.5, color="gray",
            style="italic", transform=trans)


def main():
    flags16, profiles = load_data()

    with paper_style():
        fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(6.5, 2.8))
        fig.subplots_adjust(wspace=0.40, left=0.10, right=0.97,
                            top=0.90, bottom=0.28)

        panel_a(ax_a, flags16)
        panel_b(ax_b, flags16, profiles)

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
