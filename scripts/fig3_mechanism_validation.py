"""
Figure 3: Why Spatial Geometry Determines Recovery Speed (2×2)

Mechanism validation via four independent lines of evidence, none of which
relies on the 2-parameter PDE quantitative prediction (which fails R²<0).

(a) Synthetic profiles: α_pred vs |δ_near| under controlled diffusion
(b) Counterfactual dot plot: removing shape or diffusion kills the signal
(c) Cross-scale consistency: event-level δ_near → α significant,
    subregion-level δ_unit → α_unit NOT significant (spatial mechanism)
(d) Exemplar radial profiles: steep (fast) vs shallow (slow) shape contrast
"""
import sys, os
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
from matplotlib.transforms import blended_transform_factory
from scipy.stats import spearmanr

from src.disaster.plot_style import (
    paper_style, OKABE_ITO, add_panel_label, save_figure, despine,
)

# ── paths ──────────────────────────────────────────────────────────────────
ROOT    = "outputs/cross_disaster_comparison"
SD_DIR  = f"{ROOT}/spatial_diffusion_unified_static_h8_gtfix_mtw5_mpp4/tables"
DT_DIR  = f"{ROOT}/Dt_decay_unified_static_h8_gtfix_mtw5_mpp4/tables"
GEO_DIR = f"{ROOT}/geo_unit_scale_unified_static_h8_gtfix_mtw5_mpp4/tables"

SYNTH_CSV = f"{SD_DIR}/analytic_predictions_synthetic.csv"
CF_CSV    = f"{SD_DIR}/counterfactual_results.csv"
BOOT_CSV  = f"{SD_DIR}/simulation_bootstrap.csv"
PROF_CSV  = f"{SD_DIR}/radial_profiles_at_peak.csv"
FLAGS_CSV = f"{DT_DIR}/Dt_routeB_sample_flags.csv"
MIX_CSV   = f"{GEO_DIR}/mixed_effects_alpha_unit.csv"

OUT_DIR = "Essay/figures"
OUT_PDF = f"{OUT_DIR}/fig3_mechanism_validation.pdf"
OUT_PNG = f"{OUT_DIR}/fig3_mechanism_validation.png"

DTYPE_COLOR = {
    "earthquake":     OKABE_ITO["vermillion"],
    "hurricane":      OKABE_ITO["blue"],
    "typhoon":        OKABE_ITO["blue"],
    "tropical_storm": OKABE_ITO["blue"],
    "flood":          OKABE_ITO["bluish_green"],
    "wildfire":       OKABE_ITO["orange"],
}

SYNTH_CLASS_COLOR = {
    "EVAC":  OKABE_ITO["blue"],
    "INFL":  OKABE_ITO["vermillion"],
    "MIXED": OKABE_ITO["gray"],
}

EVAC_SLUG = "hurricane_beryl_across_southeastern_texas_us"
INFL_SLUG = "spain_flood"


def load_data():
    synth = pd.read_csv(SYNTH_CSV)
    cf    = pd.read_csv(CF_CSV)
    boot  = pd.read_csv(BOOT_CSV)
    prof  = pd.read_csv(PROF_CSV)
    flags = pd.read_csv(FLAGS_CSV)
    sel   = flags[flags["route_b_selected"] == True].copy()
    mix   = pd.read_csv(MIX_CSV)
    return synth, cf, boot, prof, sel, mix


# ── panels ─────────────────────────────────────────────────────────────────

def panel_a(ax, synth):
    """Synthetic profiles: α_pred vs |δ_near| under controlled diffusion.
    Demonstrates causal relationship in silico."""
    x = synth["delta_near"].abs().values
    y = synth["alpha_predicted"].values
    classes = synth["profile_class"].values

    for xi, yi, cls, label in zip(x, y, classes, synth["profile_label"]):
        col = SYNTH_CLASS_COLOR.get(cls, "gray")
        ax.scatter(xi, yi, color=col, s=60, zorder=4,
                   edgecolors="white", linewidths=0.5)
        ax.annotate(label, (xi, yi), textcoords="offset points",
                    xytext=(5, 4), fontsize=5.5, color=col,
                    annotation_clip=False)

    rho, pval = spearmanr(x, y)
    ax.text(0.03, 0.97,
            fr"$\rho = {rho:.2f}$, $p = {pval:.3f}$"
            "\n(controlled diffusion)",
            transform=ax.transAxes, ha="left", va="top", fontsize=7.5,
            linespacing=1.5)

    ax.set_xlabel(r"$|\delta_{\mathrm{near}}|$ (synthetic)")
    ax.set_ylabel(r"$\alpha_{\mathrm{pred}}$ (from PDE)")

    handles = [Line2D([0], [0], marker="o", color="w",
                      markerfacecolor=c, markersize=6, label=l)
               for l, c in [("EVAC", OKABE_ITO["blue"]),
                             ("INFL", OKABE_ITO["vermillion"]),
                             ("MIXED", OKABE_ITO["gray"])]]
    ax.legend(handles=handles, fontsize=6.5, frameon=False, loc="lower right")
    despine(ax)


def panel_b(ax, cf, boot):
    """Counterfactual dot plot: ρ(α_pred, δ_near) under different scenarios."""
    scenarios = [
        ("observed_empirical",                     r"Observed $\rho(\alpha, \delta_{\rm near})$",
         OKABE_ITO["blue"]),
        ("pde_predicted",                          "PDE baseline",
         OKABE_ITO["sky_blue"]),
        ("counterfactual_shuffle_profiles",        "Shuffled profiles",
         OKABE_ITO["gray"]),
        ("counterfactual_no_diffusion_Ds0",        r"No diffusion ($D_s=0$)",
         OKABE_ITO["gray"]),
        ("counterfactual_uniform_profile_only_c0", r"Uniform ($c_0$ only)",
         OKABE_ITO["gray"]),
    ]
    y_pos = np.arange(len(scenarios))[::-1]

    # Bootstrap CI for PDE baseline
    boot_rhos = boot["rho_alpha_pred_vs_delta_near"].values
    boot_ci = np.percentile(boot_rhos, [2.5, 97.5])

    for i, (key, label, color) in enumerate(scenarios):
        row = cf[cf["scenario"] == key]
        if row.empty:
            continue
        rho_val = float(row["rho"].iloc[0])
        yi = y_pos[i]

        if key == "observed_empirical":
            ax.scatter(rho_val, yi, color=color, s=70, marker="D",
                       edgecolors="white", linewidths=0.5, zorder=5)
        elif key == "pde_predicted":
            ax.errorbar(rho_val, yi,
                        xerr=[[rho_val - boot_ci[0]], [boot_ci[1] - rho_val]],
                        fmt="o", color=color, ms=7, capsize=3,
                        capthick=1.0, elinewidth=1.2, zorder=4)
        elif key == "counterfactual_shuffle_profiles":
            note = str(row["note"].iloc[0]) if "note" in row.columns else ""
            ci_lo, ci_hi = -0.5, 0.5
            if "95%CI=[" in note:
                ci_str = note.split("95%CI=[")[1].split("]")[0]
                ci_lo, ci_hi = map(float, ci_str.split(","))
            ax.errorbar(rho_val, yi,
                        xerr=[[rho_val - ci_lo], [ci_hi - rho_val]],
                        fmt="o", color=color, ms=7, capsize=3,
                        capthick=1.0, elinewidth=1.2, zorder=4)
        else:
            ax.scatter(rho_val, yi, color=color, s=55, marker="s",
                       edgecolors="white", linewidths=0.5, zorder=4)

    ax.axvline(0, color="black", lw=0.8, ls="--", alpha=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels([s[1] for s in scenarios], fontsize=6.5)
    ax.set_xlabel(r"$\rho$")
    ax.set_xlim(-0.85, 0.55)
    ax.tick_params(axis="y", length=0)
    despine(ax)
    ax.spines["left"].set_visible(False)


def panel_c(ax, sel, mix):
    """Cross-scale consistency: event-level δ_near→α vs subregion δ_unit→α_unit.

    The spatial mechanism predicts that δ_near (spatial average = gradient proxy)
    predicts α, but δ_unit (local point value) does NOT predict α_unit.
    Both predictions are confirmed by data.
    """
    # Event-level
    sel_plot = sel[sel["route_b_selected_plot"] == True]
    rho_event, p_event = spearmanr(
        sel_plot["near_delta_peak_windows_mean"].values,
        sel_plot["alpha"].values,
    )

    # Subregion-level
    row_delta = mix[mix["predictor"] == "delta_peak_unit"]
    if not row_delta.empty:
        beta_sub = float(row_delta["coef"].iloc[0])
        p_sub = float(row_delta["p"].iloc[0])
    else:
        beta_sub, p_sub = 0.0, 1.0

    # Paired bar chart
    labels = [r"Event-level" "\n" r"$\delta_{\rm near} \to \alpha$",
              r"Subregion-level" "\n" r"$\delta_{\rm unit} \to \alpha_{\rm unit}$"]
    x_pos = [0, 1]

    # Use -log10(p) as effect strength indicator, capped
    def _neg_log_p(p):
        return min(-np.log10(max(p, 1e-10)), 5)

    heights = [_neg_log_p(p_event), _neg_log_p(p_sub)]
    colors = [OKABE_ITO["blue"] if p_event < 0.05 else OKABE_ITO["gray"],
              OKABE_ITO["blue"] if p_sub < 0.05 else OKABE_ITO["gray"]]

    bars = ax.bar(x_pos, heights, width=0.5, color=colors, alpha=0.8,
                  edgecolor="white", linewidth=0.8)

    # p=0.05 threshold
    threshold = _neg_log_p(0.05)
    ax.axhline(threshold, color="black", ls="--", lw=0.8, alpha=0.6)
    ax.text(1.05, threshold, "$p = 0.05$", fontsize=7, color="gray",
            va="center", transform=ax.get_yaxis_transform())

    # Annotations
    ax.text(0, heights[0] + 0.15,
            fr"$\rho = {rho_event:.2f}$" "\n" fr"$p = {p_event:.3f}$",
            ha="center", fontsize=7, color=colors[0])
    ax.text(1, heights[1] + 0.15,
            fr"$\beta = {beta_sub:.2f}$" "\n" fr"$p = {p_sub:.3f}$",
            ha="center", fontsize=7, color=colors[1])

    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels, fontsize=7.5)
    ax.set_ylabel(r"$-\log_{10}(p)$")
    ax.set_ylim(0, max(heights) + 0.8)

    ax.text(0.5, 0.97,
            "Spatial mechanism:\ngradient predicts, local value does not",
            transform=ax.transAxes, ha="center", va="top",
            fontsize=6.5, color="gray", style="italic", linespacing=1.3)
    despine(ax)


def panel_d(ax, prof, sel):
    """Exemplar radial profiles: steep gradient (fast) vs shallow (slow)."""
    r_near = 50

    sel_plot = sel[sel["route_b_selected_plot"] == True]
    row_e = sel_plot[sel_plot["slug"] == EVAC_SLUG]
    row_i = sel_plot[sel_plot["slug"] == INFL_SLUG]
    a_e = float(row_e["alpha"].iloc[0]) if not row_e.empty else 0
    a_i = float(row_i["alpha"].iloc[0]) if not row_i.empty else 0

    for slug, color, label_fmt in [
        (EVAC_SLUG, OKABE_ITO["blue"],
         fr"Beryl TX ($\alpha={a_e:.2f}$, steep)"),
        (INFL_SLUG, OKABE_ITO["bluish_green"],
         fr"Spain flood ($\alpha={a_i:.2f}$, shallow)"),
    ]:
        sub = prof[prof["slug"] == slug].sort_values("r_bin_km")
        if sub.empty:
            continue
        ax.plot(sub["r_bin_km"], sub["delta_at_peak"],
                color=color, lw=2.0, label=label_fmt, zorder=3)

    ax.axhline(0, color="black", lw=0.7, ls="--", alpha=0.5)
    ax.axvspan(0, r_near, alpha=0.08, color="gray", zorder=0)
    trans = blended_transform_factory(ax.transData, ax.transAxes)
    ax.text(r_near / 2, 0.94, "near-field", ha="center", va="top",
            fontsize=7, color="gray", style="italic", transform=trans)

    ax.set_xlabel(r"Distance $r$ from center (km)")
    ax.set_ylabel(r"$\delta(r,\,t_{\mathrm{peak}})$")
    ax.set_xlim(0, 200)
    ax.legend(fontsize=7, frameon=False, loc="upper right")

    ax.annotate("", xy=(25, -0.25), xytext=(25, -0.05),
                arrowprops=dict(arrowstyle="->", color=OKABE_ITO["blue"],
                                lw=1.5), annotation_clip=False)
    ax.text(30, -0.16, "steep\ngradient", fontsize=6,
            color=OKABE_ITO["blue"], va="center")
    despine(ax)


# ── main ───────────────────────────────────────────────────────────────────

def main():
    synth, cf, boot, prof, sel, mix = load_data()

    with paper_style():
        fig = plt.figure(figsize=(7.0, 5.2))
        gs = gridspec.GridSpec(
            2, 2,
            figure=fig,
            hspace=0.56, wspace=0.52,
            left=0.09, right=0.97,
            top=0.93, bottom=0.12,
        )
        ax_a = fig.add_subplot(gs[0, 0])
        ax_b = fig.add_subplot(gs[0, 1])
        ax_c = fig.add_subplot(gs[1, 0])
        ax_d = fig.add_subplot(gs[1, 1])

        panel_a(ax_a, synth)
        panel_b(ax_b, cf, boot)
        panel_c(ax_c, sel, mix)
        panel_d(ax_d, prof, sel)

        add_panel_label(ax_a, "a", dy=8)
        add_panel_label(ax_b, "b", dy=8)
        add_panel_label(ax_c, "c", dy=8)
        add_panel_label(ax_d, "d", dy=8)

        os.makedirs(OUT_DIR, exist_ok=True)
        save_figure(fig, OUT_PDF)
        save_figure(fig, OUT_PNG, dpi=150)
        plt.close(fig)

    print(f"Saved: {OUT_PDF}, {OUT_PNG}")


if __name__ == "__main__":
    main()
