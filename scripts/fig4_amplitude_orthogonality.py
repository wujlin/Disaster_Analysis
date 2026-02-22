"""
Figure 4: Amplitude Effect and Two-Dimensional Prediction Framework (2×2)

(a) α vs D_peak scatter + Theil-Sen line
(b) 2D framework: δ_near × D_peak coloured by α
(c) Partial correlations for δ_near — stability across socioeconomic controls
(d) Partial correlations for D_peak — stability across socioeconomic controls
"""
import sys, os
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
from scipy.stats import spearmanr, theilslopes

from src.disaster.plot_style import (
    paper_style, OKABE_ITO, add_panel_label, save_figure, despine,
)

# ── paths ──────────────────────────────────────────────────────────────────
ROOT       = "outputs/cross_disaster_comparison"
FLAGS_CSV  = f"{ROOT}/Dt_decay/tables/Dt_routeB_sample_flags.csv"
EXT_DIR    = f"{ROOT}/external_covariates/tables"
PC_DN_CSV  = f"{EXT_DIR}/partial_spearman_delta_near_alpha.csv"
PC_DP_CSV  = f"{EXT_DIR}/partial_spearman_dpeak_alpha.csv"
OUT_DIR    = "Essay/figures"
OUT_PDF    = f"{OUT_DIR}/fig4_amplitude_orthogonality.pdf"
OUT_PNG    = f"{OUT_DIR}/fig4_amplitude_orthogonality.png"

DTYPE_COLOR = {
    "earthquake": OKABE_ITO["vermillion"],
    "hurricane":  OKABE_ITO["blue"],
    "typhoon":    OKABE_ITO["blue"],
    "flood":      OKABE_ITO["bluish_green"],
    "wildfire":   OKABE_ITO["orange"],
}
R2_THRESHOLD = 0.75
PAD = 0.04


def _shared_legend_handles():
    return [
        Line2D([0],[0], marker="o", color="w",
               markerfacecolor=OKABE_ITO["vermillion"], markersize=6,
               markeredgecolor="none", label="Earthquake"),
        Line2D([0],[0], marker="o", color="w",
               markerfacecolor=OKABE_ITO["blue"], markersize=6,
               markeredgecolor="none", label="Hurricane / Typhoon"),
        Line2D([0],[0], marker="o", color="w",
               markerfacecolor=OKABE_ITO["bluish_green"], markersize=6,
               markeredgecolor="none", label="Flood"),
        Line2D([0],[0], marker="o", color="w",
               markerfacecolor=OKABE_ITO["orange"], markersize=6,
               markeredgecolor="none", label="Wildfire"),
    ]


def load_data():
    flags  = pd.read_csv(FLAGS_CSV)
    flags16 = flags[flags["route_b_selected"] == True].copy()
    pc_dn  = pd.read_csv(PC_DN_CSV)
    pc_dp  = pd.read_csv(PC_DP_CSV)
    return flags16, pc_dn, pc_dp


# ── panels ─────────────────────────────────────────────────────────────────

def panel_a(ax, flags16):
    """α vs D_peak scatter with Theil-Sen line."""
    x = flags16["D_peak"].values
    y = flags16["alpha"].values

    res    = theilslopes(y, x, 0.95)
    x_line = np.linspace(x.min() - PAD, x.max() + PAD, 100)
    ax.plot(x_line, res.slope * x_line + res.intercept,
            color="gray", ls="--", lw=1.2, alpha=0.7, zorder=1)

    for _, row in flags16.iterrows():
        xi    = row["D_peak"]
        yi    = row["alpha"]
        dtype = row["disaster_type"]
        ri2   = row["r2"]
        color = DTYPE_COLOR.get(dtype, "gray")
        fc    = color if ri2 >= R2_THRESHOLD else "none"
        ax.scatter(xi, yi, s=42, marker="o",
                   facecolors=fc, edgecolors=color, linewidths=1.0,
                   alpha=0.95 if ri2 >= R2_THRESHOLD else 0.5, zorder=3)

    rho, pval = spearmanr(x, y)
    ax.text(0.97, 0.97, fr"$\rho = +{rho:.2f}$, $p = {pval:.3f}$",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.5)
    ax.set_xlabel(r"$D_{\mathrm{peak}}$")
    ax.set_ylabel(r"$\alpha$ (decay rate)")
    despine(ax)


def panel_b(ax, flags16):
    """2D joint prediction space: δ_near × D_peak coloured by α."""
    x          = flags16["near_delta_peak_windows_mean"].values
    y          = flags16["D_peak"].values
    alpha_vals = flags16["alpha"].values

    norm = mcolors.Normalize(vmin=alpha_vals.min(), vmax=alpha_vals.max())
    cmap = plt.get_cmap("plasma")

    for _, row in flags16.iterrows():
        xi  = row["near_delta_peak_windows_mean"]
        yi  = row["D_peak"]
        ai  = row["alpha"]
        col = cmap(norm(ai))
        ax.scatter(xi, yi, color=col, s=55, marker="o",
                   edgecolors="white", linewidths=0.5, zorder=4)

    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cb = plt.colorbar(sm, ax=ax, orientation="vertical",
                      fraction=0.05, pad=0.04, shrink=0.85)
    cb.set_label(r"Decay rate $\alpha$", fontsize=9)
    cb.ax.tick_params(labelsize=8)

    ax.axvline(np.median(x), color="gray", lw=0.8, ls=":", alpha=0.5)
    ax.axhline(np.median(y), color="gray", lw=0.8, ls=":", alpha=0.5)
    ax.set_xlim(x.min() - PAD, x.max() + PAD)
    ax.set_ylim(y.min() - PAD, y.max() + PAD)
    ax.set_xlabel(r"$\delta_{\mathrm{near}}$")
    ax.set_ylabel(r"$D_{\mathrm{peak}}$")
    despine(ax)


def _partial_corr_forest(ax, pc_df, predictor_label, color, x_center,
                         title_offset=-0.02):
    """Generic forest plot for partial correlation data.

    pc_df has columns: pair, rho, p, n
    pair examples: 'delta_near vs alpha (raw)', 'delta_near vs alpha | HDI', ...
    """
    # Build a cleaner label for each row
    label_map = {
        "(raw)":                   "Raw",
        "| HDI":                   "| HDI",
        "| GDP_per_capita_PPP":    "| GDP/cap",
        "| INFORM_risk":           "| INFORM risk",
        "| INFORM_lack_coping":    "| INFORM coping",
        "| INFORM_vulnerability":  "| INFORM vuln.",
        "| HDI+delta_near":        r"| HDI+$\delta_{\rm near}$",
        "| INFORM_lack_coping+delta_near": r"| INFORM+$\delta_{\rm near}$",
        "| GDP_per_capita_PPP+delta_near": r"| GDP+$\delta_{\rm near}$",
    }

    labels = []
    rhos   = []
    pvals  = []
    for _, row in pc_df.iterrows():
        pair = str(row["pair"])
        for key, clean in label_map.items():
            if key in pair:
                labels.append(clean)
                rhos.append(row["rho"])
                pvals.append(row["p"])
                break

    y_pos = np.arange(len(labels))[::-1]

    for i, (yi, rho, pv) in enumerate(zip(y_pos, rhos, pvals)):
        col  = color if pv < 0.05 else "gray"
        mker = "o" if pv < 0.05 else "D"
        ax.scatter(rho, yi, color=col, s=50, marker=mker,
                   edgecolors="white", linewidths=0.4, zorder=4)

    # Vertical reference line at x_center (the raw ρ)
    ax.axvline(x_center, color=color, lw=0.8, ls="--", alpha=0.5)
    ax.axvline(0, color="black", lw=0.7, ls=":", alpha=0.4)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_xlabel(fr"Partial $\rho$ ({predictor_label})")
    ax.tick_params(axis="y", length=0)
    despine(ax)
    ax.spines["left"].set_visible(False)


def panel_c(ax, pc_dn):
    """Partial correlations for δ_near → α, controlling for socioeconomic vars."""
    _partial_corr_forest(ax, pc_dn,
                         predictor_label=r"$\delta_{\mathrm{near}}$",
                         color=OKABE_ITO["blue"],
                         x_center=-0.527)
    ax.set_xlim(-0.80, 0.10)


def panel_d(ax, pc_dp):
    """Partial correlations for D_peak → α, controlling for socioeconomic vars."""
    _partial_corr_forest(ax, pc_dp,
                         predictor_label=r"$D_{\mathrm{peak}}$",
                         color=OKABE_ITO["vermillion"],
                         x_center=0.600)
    ax.set_xlim(0.20, 0.90)


# ── main ───────────────────────────────────────────────────────────────────

def main():
    flags16, pc_dn, pc_dp = load_data()

    with paper_style():
        fig = plt.figure(figsize=(6.8, 5.0))
        gs  = gridspec.GridSpec(
            2, 2,
            figure=fig,
            hspace=0.52, wspace=0.56,
            left=0.10, right=0.95,
            top=0.93, bottom=0.18,
        )
        ax_a = fig.add_subplot(gs[0, 0])
        ax_b = fig.add_subplot(gs[0, 1])
        ax_c = fig.add_subplot(gs[1, 0])
        ax_d = fig.add_subplot(gs[1, 1])

        panel_a(ax_a, flags16)
        panel_b(ax_b, flags16)
        panel_c(ax_c, pc_dn)
        panel_d(ax_d, pc_dp)

        add_panel_label(ax_a, "a", dy=8)
        add_panel_label(ax_b, "b", dy=8)
        add_panel_label(ax_c, "c", dy=8)
        add_panel_label(ax_d, "d", dy=8)

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
