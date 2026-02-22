"""
Supplementary Figures S1–S5 for SI.

S1: Individual D(t) panels (4×4 grid)
S2: Robustness parameter sweeps (r_near, R_max)
S3: Leave-one-out jackknife distribution
S4: PDE parameter search heatmap (copy from existing)
S5: Profile gallery (copy from existing)
"""
import sys
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy.stats import spearmanr
from src.disaster.plot_style import (
    paper_style, OKABE_ITO, add_panel_label, save_figure, despine,
)
import shutil
from pathlib import Path

ROOT = "outputs/cross_disaster_comparison"
TS_CSV       = f"{ROOT}/Dt_decay/tables/Dt_all_events.csv"
FLAGS_CSV    = f"{ROOT}/Dt_decay/tables/Dt_routeB_sample_flags.csv"
NEAR_CSV     = f"{ROOT}/Dt_decay/tables/robustness_near_thresh.csv"
RMAX_CSV     = f"{ROOT}/Dt_decay/tables/robustness_r_max.csv"
JACK_CSV     = f"{ROOT}/Dt_decay/tables/Dt_routeB_alpha_delta_jackknife.csv"
PROFILES_CSV = f"{ROOT}/spatial_diffusion_results/tables/radial_profiles_at_peak.csv"

OUT_DIR = Path("Essay/figures_supp")
OUT_DIR.mkdir(parents=True, exist_ok=True)

DTYPE_COLOR = {
    "earthquake": OKABE_ITO["vermillion"],
    "hurricane":  OKABE_ITO["blue"],
    "typhoon":    OKABE_ITO["blue"],
    "flood":      OKABE_ITO["bluish_green"],
    "wildfire":   OKABE_ITO["orange"],
}

SHORT_LABELS = {
    "flooding_in_central_and_eastern_europe_sept_16_2024": "EU Floods",
    "hurricane_beryl_across_quintana_roo_and_yucatan_mexico": "Beryl (QR)",
    "hurricane_beryl_across_southeastern_texas_us": "Beryl (TX)",
    "hurricane_beryl_pre_landfall_2024": "Beryl (pre)",
    "hurricane_john_across_southeastern_guerrero_mexico": "John (GUE)",
    "hurricane_john_southern_mexico_25_september_2024": "John (SM)",
    "hurricane_milton_across_florida_us": "Milton (FL)",
    "moldova_flooding_2024": "Moldova",
    "spain_flood": "Spain Floods",
    "the_earthquake_across_central_mexico": "Mexico EQ",
    "the_flooding_across_bagmati_and_koshi_provinces_nepal": "Nepal Floods",
    "the_flooding_across_eastern_bangladesh": "Bangladesh",
    "the_flooding_across_gujarat_india": "Gujarat",
    "turkiye_earthquake_2023": "Turkiye EQ",
    "typhoon_yagi_across_northeastern_vietnam": "Yagi (VN)",
    "wildfires_in_boise_county_idaho_27_august_2024": "Idaho Fire",
}


def figS1_individual_panels():
    """4×4 grid of individual D(t) time series."""
    ts = pd.read_csv(TS_CSV)
    flags = pd.read_csv(FLAGS_CSV)
    flags16 = flags[flags["route_b_selected"] == True].copy()
    slugs = flags16.sort_values("alpha", ascending=False)["slug"].tolist()

    with paper_style():
        fig, axes = plt.subplots(4, 4, figsize=(8, 7))
        fig.subplots_adjust(hspace=0.55, wspace=0.35,
                            left=0.07, right=0.97, top=0.95, bottom=0.06)

        for idx, (ax, slug) in enumerate(zip(axes.flat, slugs)):
            sub = ts[ts["slug"] == slug].copy().sort_values("t_hours")
            row = flags16[flags16["slug"] == slug].iloc[0]
            t_peak = row["t_peak_hours"]
            dtype = row["disaster_type"]
            alpha_val = row["alpha"]
            color = DTYPE_COLOR.get(dtype, "gray")
            label = SHORT_LABELS.get(slug, slug[:15])

            # Pre-peak shading
            ax.axvspan(sub["t_hours"].min() - t_peak, 0,
                       alpha=0.06, color="gray", zorder=0)
            ax.plot(sub["t_hours"] - t_peak, sub["D"],
                    color=color, lw=1.5, alpha=0.9)
            ax.axvline(0, color="black", lw=0.5, ls="--", alpha=0.4)

            ax.set_title(f"{label} ({dtype[:2].upper()}, "
                         fr"$\alpha={alpha_val:.2f}$)",
                         fontsize=7.5, pad=2)
            ax.tick_params(labelsize=6.5)
            ax.set_ylim(bottom=0)
            despine(ax)

            if idx >= 12:
                ax.set_xlabel(r"$t - t_{\mathrm{peak}}$ (h)", fontsize=7.5)
            if idx % 4 == 0:
                ax.set_ylabel(r"$D(t)$", fontsize=7.5)

        # Blank unused panels (if any)
        for ax in axes.flat[len(slugs):]:
            ax.set_visible(False)

        save_figure(fig, OUT_DIR / "figS1_individual_panels.pdf")
        save_figure(fig, OUT_DIR / "figS1_individual_panels.png", dpi=150)
        plt.close(fig)
    print("Saved: figS1_individual_panels")


def figS2_robustness_sweeps():
    """Parameter sensitivity: (a) r_near sweep, (b) R_max sweep."""
    flags = pd.read_csv(FLAGS_CSV)
    flags16 = flags[flags["route_b_selected"] == True].copy()
    profiles = pd.read_csv(PROFILES_CSV)
    rmax_df = pd.read_csv(RMAX_CSV)

    # --- Panel (a): r_near sweep ---
    # Recompute δ_near from radial profiles at different r_near thresholds
    r_near_values = [10, 25, 50, 75, 100, 125, 150]
    rho_near = []
    for r_near in r_near_values:
        deltas, alphas = [], []
        for _, row in flags16.iterrows():
            slug = row["slug"]
            alpha = row["alpha"]
            if pd.isna(alpha):
                continue
            sub = profiles[(profiles["slug"] == slug) &
                           (profiles["r_bin_km"] <= r_near)]
            if sub.empty:
                continue
            deltas.append(sub["delta_at_peak"].mean())
            alphas.append(alpha)
        if len(deltas) >= 5:
            rho, p = spearmanr(alphas, deltas)
            rho_near.append({"r_near": r_near, "rho": rho, "p": p, "n": len(deltas)})
    rho_near = pd.DataFrame(rho_near)

    # --- Panel (b): R_max sweep ---
    rho_rmax = []
    for rv in sorted(rmax_df["r_max_km"].unique()):
        sub = rmax_df[rmax_df["r_max_km"] == rv][["slug", "alpha"]].rename(
            columns={"alpha": "alpha_rmax"})
        merged = sub.merge(
            flags16[["slug", "near_delta_peak_windows_mean"]], on="slug", how="inner")
        merged = merged.dropna(subset=["alpha_rmax"])
        if len(merged) < 5:
            continue
        rho, p = spearmanr(merged["alpha_rmax"],
                           merged["near_delta_peak_windows_mean"])
        rho_rmax.append({"r_max": rv, "rho": rho, "p": p, "n": len(merged)})
    rho_rmax = pd.DataFrame(rho_rmax)

    rho_sig = 0.496  # |ρ| at p=0.05 for n≈16

    with paper_style():
        fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(6.5, 2.8))
        fig.subplots_adjust(wspace=0.40, left=0.12, right=0.97,
                            top=0.90, bottom=0.20)

        if not rho_near.empty:
            ax_a.plot(rho_near["r_near"], rho_near["rho"],
                      "o-", color=OKABE_ITO["blue"], lw=1.5, markersize=5)
            ax_a.axhline(-rho_sig, color="gray", ls="--", lw=0.8, alpha=0.6,
                         label=r"$p = 0.05$ threshold")
            ax_a.axhline(0, color="black", ls=":", lw=0.5, alpha=0.4)
            ax_a.set_xlabel(r"$r_{\mathrm{near}}$ (km)")
            ax_a.set_ylabel(r"$\rho(\alpha,\,\delta_{\mathrm{near}})$")
            ax_a.legend(fontsize=7, frameon=False, loc="lower right")
        despine(ax_a)

        if not rho_rmax.empty:
            ax_b.plot(rho_rmax["r_max"], rho_rmax["rho"],
                      "o-", color=OKABE_ITO["bluish_green"], lw=1.5, markersize=5)
            ax_b.axhline(-rho_sig, color="gray", ls="--", lw=0.8, alpha=0.6)
            ax_b.axhline(0, color="black", ls=":", lw=0.5, alpha=0.4)
            ax_b.set_xlabel(r"$R_{\max}$ (km)")
            ax_b.set_ylabel(r"$\rho(\alpha,\,\delta_{\mathrm{near}})$")
        despine(ax_b)

        add_panel_label(ax_a, "a", dy=8)
        add_panel_label(ax_b, "b", dy=8)

        save_figure(fig, OUT_DIR / "figS2_robustness_sweeps.pdf")
        save_figure(fig, OUT_DIR / "figS2_robustness_sweeps.png", dpi=150)
        plt.close(fig)
    print("Saved: figS2_robustness_sweeps")


def figS3_jackknife():
    """Jackknife distribution of ρ(α, δ_near)."""
    jack = pd.read_csv(JACK_CSV)

    with paper_style():
        fig, ax = plt.subplots(figsize=(4, 3))
        fig.subplots_adjust(left=0.15, right=0.95, top=0.93, bottom=0.18)

        y_pos = np.arange(len(jack))
        colors = [OKABE_ITO["sky_blue"]] * len(jack)

        ax.barh(y_pos, jack["spearman_rho"], height=0.7, color=colors,
                edgecolor="white", lw=0.5)

        # Full-sample line
        full_rho = -0.526
        ax.axvline(full_rho, color=OKABE_ITO["vermillion"], lw=2, ls="--",
                   label=fr"Full sample $\rho = {full_rho:.3f}$")
        ax.axvline(0, color="black", lw=0.8, ls=":", alpha=0.5)

        # Labels
        short = [SHORT_LABELS.get(s, s[:12]) for s in jack["removed_slug"]]
        ax.set_yticks(y_pos)
        ax.set_yticklabels(short, fontsize=7)
        ax.set_xlabel(r"$\rho(\alpha,\,\delta_{\mathrm{near}})$ after removal")
        ax.legend(fontsize=8, frameon=False, loc="lower left")
        despine(ax)

        save_figure(fig, OUT_DIR / "figS3_jackknife.pdf")
        save_figure(fig, OUT_DIR / "figS3_jackknife.png", dpi=150)
        plt.close(fig)
    print("Saved: figS3_jackknife")


def figS4_copy_heatmap():
    """Copy existing PDE heatmap from analysis outputs."""
    src = Path(f"{ROOT}/spatial_diffusion_results/figures/pde_param_heatmap.png")
    dst = OUT_DIR / "figS4_pde_param_heatmap.png"
    if src.exists():
        shutil.copy2(src, dst)
        print(f"Copied: {src} -> {dst}")
    else:
        print(f"Warning: {src} not found")


def figS5_profile_gallery():
    """Radial profile gallery at peak for all 16 events."""
    profiles = pd.read_csv(PROFILES_CSV)
    flags = pd.read_csv(FLAGS_CSV)
    flags16 = flags[flags["route_b_selected"] == True].copy()
    slugs = flags16.sort_values("alpha", ascending=False)["slug"].tolist()

    with paper_style():
        fig, axes = plt.subplots(4, 4, figsize=(8, 6.5))
        fig.subplots_adjust(hspace=0.55, wspace=0.35,
                            left=0.07, right=0.97, top=0.95, bottom=0.07)

        for idx, (ax, slug) in enumerate(zip(axes.flat, slugs)):
            sub = profiles[profiles["slug"] == slug].copy()
            if sub.empty:
                ax.text(0.5, 0.5, "No data", transform=ax.transAxes,
                        ha="center", va="center", fontsize=7)
                despine(ax)
                continue
            sub = sub.sort_values("r_bin_km")
            row = flags16[flags16["slug"] == slug].iloc[0]
            dtype = row["disaster_type"]
            alpha_val = row["alpha"]
            color = DTYPE_COLOR.get(dtype, "gray")
            label = SHORT_LABELS.get(slug, slug[:15])

            ax.plot(sub["r_bin_km"], sub["delta_at_peak"],
                    color=color, lw=1.5, alpha=0.9)
            ax.axhline(0, color="black", lw=0.5, ls="--", alpha=0.4)
            ax.axvspan(0, 50, alpha=0.06, color="gray", zorder=0)
            ax.set_title(f"{label} " + fr"($\alpha={alpha_val:.2f}$)",
                         fontsize=7.5, pad=2)
            ax.tick_params(labelsize=6.5)
            despine(ax)

            if idx >= 12:
                ax.set_xlabel(r"$r$ (km)", fontsize=7.5)
            if idx % 4 == 0:
                ax.set_ylabel(r"$\delta(r,\,t_{\mathrm{peak}})$", fontsize=7.5)

        for ax in axes.flat[len(slugs):]:
            ax.set_visible(False)

        save_figure(fig, OUT_DIR / "figS5_profile_gallery.pdf")
        save_figure(fig, OUT_DIR / "figS5_profile_gallery.png", dpi=150)
        plt.close(fig)
    print("Saved: figS5_profile_gallery")


def main():
    figS1_individual_panels()
    figS2_robustness_sweeps()
    figS3_jackknife()
    figS4_copy_heatmap()
    figS5_profile_gallery()
    print("\nAll supplementary figures done.")


if __name__ == "__main__":
    main()
