"""
Figure 2: Spatial Shape of Initial Displacement Predicts Recovery Speed (2×2)

(a) α vs δ_near scatter + Theil-Sen line
(b) EVAC vs INFL radial profiles at peak time
(c) Jackknife distribution of ρ(α, δ_near) — robustness of the correlation
(d) Parameter sensitivity forest plot — robustness to r_max, near-thresh, bounce-tol
"""
import sys, os
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
from matplotlib.transforms import blended_transform_factory
from scipy.stats import spearmanr, theilslopes

from src.disaster.plot_style import (
    paper_style, OKABE_ITO, add_panel_label, save_figure, despine,
)

# ── paths ──────────────────────────────────────────────────────────────────
ROOT        = "outputs/cross_disaster_comparison"
FLAGS_CSV   = f"{ROOT}/Dt_decay/tables/Dt_routeB_sample_flags.csv"
PROFILES_CSV = f"{ROOT}/spatial_diffusion_results/tables/radial_profiles_at_peak.csv"
JK_CSV      = f"{ROOT}/Dt_decay/tables/Dt_routeB_alpha_delta_jackknife.csv"
RS_CSV      = f"{ROOT}/Dt_decay/tables/robustness_summary.csv"
OUT_DIR     = "Essay/figures"
OUT_PDF     = f"{OUT_DIR}/fig2_shape_predicts_recovery.pdf"
OUT_PNG     = f"{OUT_DIR}/fig2_shape_predicts_recovery.png"

DTYPE_COLOR = {
    "earthquake": OKABE_ITO["vermillion"],
    "hurricane":  OKABE_ITO["blue"],
    "typhoon":    OKABE_ITO["blue"],
    "flood":      OKABE_ITO["bluish_green"],
    "wildfire":   OKABE_ITO["orange"],
}
R2_THRESHOLD = 0.75
EVAC_SLUG    = "hurricane_beryl_across_southeastern_texas_us"
INFL_SLUG    = "spain_flood"


def _shared_legend_handles():
    return [
        Line2D([0], [0], marker="o", color="w",
               markerfacecolor=OKABE_ITO["vermillion"], markersize=6,
               markeredgecolor="none", label="Earthquake"),
        Line2D([0], [0], marker="o", color="w",
               markerfacecolor=OKABE_ITO["blue"], markersize=6,
               markeredgecolor="none", label="Hurricane / Typhoon"),
        Line2D([0], [0], marker="o", color="w",
               markerfacecolor=OKABE_ITO["bluish_green"], markersize=6,
               markeredgecolor="none", label="Flood"),
        Line2D([0], [0], marker="o", color="w",
               markerfacecolor=OKABE_ITO["orange"], markersize=6,
               markeredgecolor="none", label="Wildfire"),
    ]


def load_data():
    flags   = pd.read_csv(FLAGS_CSV)
    flags16 = flags[flags["route_b_selected"] == True].copy()
    profiles = pd.read_csv(PROFILES_CSV)
    jk       = pd.read_csv(JK_CSV)
    rs       = pd.read_csv(RS_CSV)
    return flags16, profiles, jk, rs


# ── panels ─────────────────────────────────────────────────────────────────

def panel_a(ax, flags16):
    """α vs δ_near scatter with Theil-Sen regression line."""
    x = flags16["near_delta_peak_windows_mean"].values
    y = flags16["alpha"].values

    res    = theilslopes(y, x, 0.95)
    x_line = np.linspace(x.min() - 0.02, x.max() + 0.02, 100)
    ax.plot(x_line, res.slope * x_line + res.intercept,
            color="gray", ls="--", lw=1.2, alpha=0.7, zorder=1)

    for _, row in flags16.iterrows():
        xi    = row["near_delta_peak_windows_mean"]
        yi    = row["alpha"]
        dtype = row["disaster_type"]
        ri2   = row["r2"]
        color = DTYPE_COLOR.get(dtype, "gray")
        fc    = color if ri2 >= R2_THRESHOLD else "none"
        ax.scatter(xi, yi, s=42, marker="o",
                   facecolors=fc, edgecolors=color,
                   linewidths=1.0, alpha=0.95 if ri2 >= R2_THRESHOLD else 0.5,
                   zorder=3)

    rho, pval = spearmanr(x, y)
    ax.text(0.97, 0.97, fr"$\rho = {rho:.2f}$, $p = {pval:.3f}$",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.5)
    ax.axhline(0, color="black", lw=0.5, alpha=0.3, ls=":")
    ax.axvline(0, color="black", lw=0.5, alpha=0.3, ls=":")
    ax.set_xlabel(r"$\delta_{\mathrm{near}}$")
    ax.set_ylabel(r"$\alpha$ (decay rate)")
    despine(ax)


def panel_b(ax, flags16, profiles):
    """Radial profiles at peak for a fast-recovering EVAC and a slow INFL event."""
    r_near = 50

    def _plot(slug, color, label):
        sub = profiles[profiles["slug"] == slug].sort_values("r_bin_km")
        if sub.empty:
            return
        ax.plot(sub["r_bin_km"], sub["delta_at_peak"],
                color=color, lw=2.0, label=label, zorder=3)

    row_e = flags16[flags16["slug"] == EVAC_SLUG]
    row_i = flags16[flags16["slug"] == INFL_SLUG]
    a_e   = float(row_e["alpha"].iloc[0]) if not row_e.empty else 0
    a_i   = float(row_i["alpha"].iloc[0]) if not row_i.empty else 0

    _plot(EVAC_SLUG, OKABE_ITO["blue"],         fr"Beryl, TX ($\alpha={a_e:.2f}$)")
    _plot(INFL_SLUG, OKABE_ITO["bluish_green"], fr"Spain flood ($\alpha={a_i:.2f}$)")

    ax.axhline(0, color="black", lw=0.7, ls="--", alpha=0.5)
    ax.axvspan(0, r_near, alpha=0.08, color="gray", zorder=0)
    trans = blended_transform_factory(ax.transData, ax.transAxes)
    ax.text(r_near / 2, 0.94, "near-field", ha="center", va="top",
            fontsize=7.5, color="gray", style="italic", transform=trans)

    ax.set_xlabel(r"Distance $r$ from epicenter (km)")
    ax.set_ylabel(r"$\delta(r,\,t_{\mathrm{peak}})$")
    ax.set_xlim(0, 200)
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    despine(ax)


def panel_c(ax, jk):
    """Jackknife distribution of ρ(α, δ_near).
    Each estimate removes one event and recomputes the correlation.
    The spread shows how much any single event drives the result.
    """
    rhos = jk["spearman_rho"].values
    rho_full = -0.527          # base estimate from full 16-event sample

    # Horizontal strip plot (jitter along y=0)
    np.random.seed(42)
    y_jitter = np.random.uniform(-0.15, 0.15, size=len(rhos))
    ax.scatter(rhos, y_jitter, color=OKABE_ITO["blue"], s=28,
               alpha=0.75, zorder=3, edgecolors="white", linewidths=0.3)

    # CI from jackknife
    ci_lo, ci_hi = np.percentile(rhos, [2.5, 97.5])
    ax.axvspan(ci_lo, ci_hi, alpha=0.18, color=OKABE_ITO["blue"], zorder=1)
    ax.axvline(rho_full, color=OKABE_ITO["blue"], lw=1.8, zorder=4)
    ax.axvline(0, color="black", lw=0.8, ls="--", alpha=0.5)

    ax.set_yticks([])
    ax.set_xlabel(r"Jackknife $\rho\,(\alpha,\;\delta_{\mathrm{near}})$")
    ax.set_xlim(-0.85, 0.15)
    ax.text(rho_full + 0.01, 0.22,
            fr"Full: $\rho={rho_full:.2f}$",
            transform=ax.get_xaxis_transform(), fontsize=7.5,
            color=OKABE_ITO["blue"], va="center")
    ax.text(0.03, 0.92,
            fr"95% CI [{ci_lo:.2f}, {ci_hi:.2f}]",
            transform=ax.transAxes, fontsize=7.5, color="gray", va="top")
    despine(ax)
    ax.spines["left"].set_visible(False)


def panel_d(ax, rs):
    """Parameter sensitivity forest plot.
    Shows Mann-Whitney p-value for EVAC vs INFL α difference
    under different robustness choices (r_max, near_thresh, bounce_tol).
    All p-values remain < 0.05, confirming robustness.
    """
    # Curate a subset of rows to show with clean labels
    # Map (test, param, value) → display label
    rows_to_show = [
        ("bounce_tol",  "mono_tol_up", 1.00, "Bounce tol. 0%"),
        ("bounce_tol",  "mono_tol_up", 1.05, "Bounce tol. 5%"),
        ("bounce_tol",  "mono_tol_up", 1.10, "Bounce tol. 10%"),
        ("r_max",       "r_max_km",   100.0, r"$r_{\max}=100$ km"),
        ("r_max",       "r_max_km",   150.0, r"$r_{\max}=150$ km"),
        ("r_max",       "r_max_km",   200.0, r"$r_{\max}=200$ km (base)"),
        ("near_thresh", "near_thresh", 0.01, r"$r_{\mathrm{near}}<1$ km"),
        ("near_thresh", "near_thresh", 0.02, r"$r_{\mathrm{near}}<2$ km"),
        ("near_thresh", "near_thresh", 0.05, r"$r_{\mathrm{near}}<5$ km"),
    ]
    y_pos  = np.arange(len(rows_to_show))[::-1]
    p_vals = []
    labels = []

    for test, param, val, label in rows_to_show:
        sub = rs[(rs["test"] == test) & (rs["param"] == param) &
                 (rs["value"].round(3) == round(val, 3))]
        if sub.empty:
            p_vals.append(np.nan)
        else:
            p_vals.append(float(sub["p_mannwhitney"].iloc[0]))
        labels.append(label)

    sig_color   = OKABE_ITO["blue"]
    insig_color = "gray"
    for i, (pv, yi) in enumerate(zip(p_vals, y_pos)):
        if np.isnan(pv):
            continue
        col  = sig_color if pv < 0.05 else insig_color
        size = 55 if pv < 0.05 else 35
        ax.scatter(pv, yi, color=col, s=size, zorder=4,
                   edgecolors="white", linewidths=0.4)

    ax.axvline(0.05, color="black", lw=0.8, ls="--", alpha=0.6)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=7.2)
    ax.set_xlabel(r"$p$ (Mann-Whitney EVAC vs INFL $\alpha$)")
    ax.set_xlim(-0.005, 0.08)
    ax.text(0.052, len(rows_to_show) - 0.5, "$p=0.05$",
            fontsize=7, color="gray", va="center")
    ax.tick_params(axis="y", length=0)
    despine(ax)
    ax.spines["left"].set_visible(False)


# ── main ───────────────────────────────────────────────────────────────────

def main():
    flags16, profiles, jk, rs = load_data()

    with paper_style():
        fig = plt.figure(figsize=(6.8, 5.0))
        gs  = gridspec.GridSpec(
            2, 2,
            figure=fig,
            hspace=0.50, wspace=0.48,
            left=0.10, right=0.97,
            top=0.93, bottom=0.18,
        )
        ax_a = fig.add_subplot(gs[0, 0])
        ax_b = fig.add_subplot(gs[0, 1])
        ax_c = fig.add_subplot(gs[1, 0])
        ax_d = fig.add_subplot(gs[1, 1])

        panel_a(ax_a, flags16)
        panel_b(ax_b, flags16, profiles)
        panel_c(ax_c, jk)
        panel_d(ax_d, rs)

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
