"""
Supplementary Figures S1–S5 for SI.

S1: Individual D(t) panels (5×4 grid, up to 18 events)
S2: Leave-one-out jackknife bar chart
S3: α vs D_∞ scatter (validation that α captures real recovery)
S4: Profile gallery (radial δ at peak, if available)
S5: Gao baseline ΔBIC(PL−Exp) forest plot
"""
import sys
sys.path.insert(0, ".")

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy.stats import spearmanr, theilslopes
from src.disaster.plot_style import (
    paper_style, OKABE_ITO, add_panel_label, save_figure, despine,
)
from pathlib import Path

ROOT     = "outputs/cross_disaster_comparison"
DT_DIR   = f"{ROOT}/Dt_decay_unified_static_h8_gtfix_mtw5_mpp4"
TS_CSV   = f"{DT_DIR}/tables/Dt_all_events.csv"
FLAGS_CSV = f"{DT_DIR}/tables/Dt_routeB_sample_flags.csv"
JACK_CSV  = f"{DT_DIR}/tables/Dt_routeB_alpha_delta_jackknife.csv"
GAO_CSV   = f"{ROOT}/gao_baseline_unified_static_h8_gtfix_mtw5_mpp4/model_comparison.csv"

# Radial profiles: try new path first, fall back to old
PROFILES_CSV_NEW = f"{ROOT}/spatial_diffusion_unified_static_h8_gtfix_mtw5_mpp4/tables/radial_profiles_at_peak.csv"
PROFILES_CSV_OLD = f"{ROOT}/spatial_diffusion_results/tables/radial_profiles_at_peak.csv"

OUT_DIR = Path("Essay/figures_supp")
OUT_DIR.mkdir(parents=True, exist_ok=True)

DTYPE_COLOR = {
    "earthquake":     OKABE_ITO["vermillion"],
    "hurricane":      OKABE_ITO["blue"],
    "typhoon":        OKABE_ITO["blue"],
    "tropical_storm": OKABE_ITO["blue"],
    "flood":          OKABE_ITO["bluish_green"],
    "wildfire":       OKABE_ITO["orange"],
}

SHORT_LABELS = {
    "flooding_in_central_and_eastern_europe_sept_16_2024":         "EU Floods",
    "hurricane_beryl_across_quintana_roo_and_yucatan_mexico":      "Beryl (QR)",
    "hurricane_beryl_across_southeastern_texas_us":                "Beryl (TX)",
    "hurricane_beryl_jamaica_western_caribbean_pre_landfall_2024_07_03": "Beryl (JM)",
    "moldova_flooding_2024":                                       "Moldova",
    "park_fire_california_29_july_2024":                           "Park Fire",
    "spain_flood":                                                 "Spain Floods",
    "the_flooding_across_bagmati_and_koshi_provinces_nepal":       "Nepal Floods",
    "the_flooding_across_eastern_bangladesh":                      "Bangladesh",
    "the_flooding_across_gujarat_india":                           "Gujarat",
    "the_flooding_across_rio_grande_do_sul_state_brazil":          "Rio Grande (BR)",
    "the_wildfires_in_quito_pichincha_province_ecuador":           "Quito Fire",
    "tropical_storm_kristine_in_bicol_and_calabarzon_philippines": "Kristine (PH)",
    "tropical_storm_yagi_philippines_2_september_2024":            "Yagi (PH)",
    "turkiye_earthquake_2023":                                     "Türkiye EQ",
    "typhoon_krathon_across_taiwan":                               "Krathon (TW)",
    "typhoon_yagi_across_northeastern_vietnam":                    "Yagi (VN)",
    "wildfires_in_boise_county_idaho_27_august_2024":              "Idaho Fire",
}


def figS1_individual_panels():
    """5×4 grid of individual D(t) time series for up to 18 events."""
    ts = pd.read_csv(TS_CSV)
    flags = pd.read_csv(FLAGS_CSV)
    sel = flags[flags["route_b_selected"] == True].copy()
    slugs = sel.sort_values("alpha", ascending=False)["slug"].tolist()

    n_cols, n_rows = 4, 5

    with paper_style():
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(8.5, 8.5))
        fig.subplots_adjust(hspace=0.55, wspace=0.35,
                            left=0.07, right=0.97, top=0.95, bottom=0.05)

        for idx, (ax, slug) in enumerate(zip(axes.flat, slugs)):
            sub = ts[ts["slug"] == slug].copy().sort_values("t_hours")
            row = sel[sel["slug"] == slug].iloc[0]
            t_peak = row["t_peak_hours"]
            dtype = row["disaster_type"]
            alpha_val = row["alpha"]
            r2_val = row["r2"]
            color = DTYPE_COLOR.get(dtype, "gray")
            label = SHORT_LABELS.get(slug, slug[:15])

            ax.axvspan(sub["t_hours"].min() - t_peak, 0,
                       alpha=0.06, color="gray", zorder=0)
            ax.plot(sub["t_hours"] - t_peak, sub["D"],
                    color=color, lw=1.5, alpha=0.9)
            ax.axvline(0, color="black", lw=0.5, ls="--", alpha=0.4)

            alpha_str = f"{alpha_val:.2f}" if pd.notna(alpha_val) else "—"
            r2_str = f"{r2_val:.2f}" if pd.notna(r2_val) else "—"
            ax.set_title(f"{label}\n"
                         fr"$\alpha={alpha_str}$, $R^2={r2_str}$",
                         fontsize=6.5, pad=2)
            ax.tick_params(labelsize=6)
            ax.set_ylim(bottom=0)
            despine(ax)

            if idx >= (n_rows - 1) * n_cols:
                ax.set_xlabel(r"$t - t_{\mathrm{peak}}$ (h)", fontsize=7)
            if idx % n_cols == 0:
                ax.set_ylabel(r"$D(t)$", fontsize=7)

        for ax in axes.flat[len(slugs):]:
            ax.set_visible(False)

        save_figure(fig, OUT_DIR / "figS1_individual_panels.pdf")
        save_figure(fig, OUT_DIR / "figS1_individual_panels.png", dpi=150)
        plt.close(fig)
    print("Saved: figS1_individual_panels")


def figS2_jackknife():
    """Jackknife leave-one-out bar chart for ρ(α, δ_near)."""
    jack = pd.read_csv(JACK_CSV)
    flags = pd.read_csv(FLAGS_CSV)
    sel = flags[flags["route_b_selected"] == True].copy()

    # Compute full-sample ρ from the authoritative event-level sample
    x_full = sel["near_delta_peak_windows_mean"].values
    y_full = sel["alpha"].values
    full_rho, _ = spearmanr(x_full, y_full)

    with paper_style():
        fig, ax = plt.subplots(figsize=(5, 4.5))
        fig.subplots_adjust(left=0.25, right=0.95, top=0.93, bottom=0.12)

        y_pos = np.arange(len(jack))
        colors = [OKABE_ITO["sky_blue"]] * len(jack)

        ax.barh(y_pos, jack["spearman_rho"], height=0.7, color=colors,
                edgecolor="white", lw=0.5)

        ax.axvline(full_rho, color=OKABE_ITO["vermillion"], lw=2, ls="--",
                   label=fr"Full sample $\rho = {full_rho:.3f}$")
        ax.axvline(0, color="black", lw=0.8, ls=":", alpha=0.5)

        short = [SHORT_LABELS.get(s, s[:12]) for s in jack["removed_slug"]]
        ax.set_yticks(y_pos)
        ax.set_yticklabels(short, fontsize=6.5)
        ax.set_xlabel(r"$\rho(\alpha,\,\delta_{\mathrm{near}})$ after removal")
        ax.legend(fontsize=7.5, frameon=False, loc="lower left")
        despine(ax)

        save_figure(fig, OUT_DIR / "figS2_jackknife.pdf")
        save_figure(fig, OUT_DIR / "figS2_jackknife.png", dpi=150)
        plt.close(fig)
    print("Saved: figS2_jackknife")


def figS3_alpha_vs_dinf():
    """α vs D_∞ scatter — validates α as a meaningful recovery indicator."""
    flags = pd.read_csv(FLAGS_CSV)
    sel = flags[flags["route_b_selected"] == True].copy()

    x = sel["alpha"].values
    y = sel["D_inf"].values
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]

    with paper_style():
        fig, ax = plt.subplots(figsize=(4.5, 3.5))
        fig.subplots_adjust(left=0.15, right=0.95, top=0.93, bottom=0.15)

        res = theilslopes(y, x, 0.95)
        x_line = np.linspace(x.min() - 0.05, x.max() + 0.05, 100)
        ax.plot(x_line, res.slope * x_line + res.intercept,
                color="gray", ls="--", lw=1.2, alpha=0.7, zorder=1)

        for _, row in sel.iterrows():
            xi   = row["alpha"]
            yi   = row["D_inf"]
            if not (np.isfinite(xi) and np.isfinite(yi)):
                continue
            dtype = row["disaster_type"]
            ri2   = row["r2"]
            color = DTYPE_COLOR.get(dtype, "gray")
            fc    = color if ri2 >= 0.75 else "none"
            ax.scatter(xi, yi, s=42, marker="o",
                       facecolors=fc, edgecolors=color,
                       linewidths=1.0, alpha=0.95 if ri2 >= 0.75 else 0.5,
                       zorder=3)

        rho, pval = spearmanr(x, y)
        ax.text(0.97, 0.97,
                fr"$\rho = {rho:.2f}$, $p = {pval:.3f}$",
                transform=ax.transAxes, ha="right", va="top", fontsize=8.5)
        ax.set_xlabel(r"$\alpha$ (decay rate)")
        ax.set_ylabel(r"$D_\infty$ (residual displacement)")

        handles = []
        for label, dtype in [("EQ", "earthquake"), ("Hurr./Typh./TS", "hurricane"),
                              ("Flood", "flood"), ("Wildfire", "wildfire")]:
            c = DTYPE_COLOR.get(dtype, "gray")
            handles.append(Line2D([0], [0], marker="o", color="none",
                                  markerfacecolor=c, markeredgecolor=c,
                                  markersize=5, label=label))
        ax.legend(handles=handles, fontsize=7, loc="lower left",
                  frameon=False, ncol=2)
        despine(ax)

        save_figure(fig, OUT_DIR / "figS3_alpha_vs_dinf.pdf")
        save_figure(fig, OUT_DIR / "figS3_alpha_vs_dinf.png", dpi=150)
        plt.close(fig)
    print("Saved: figS3_alpha_vs_dinf")


def figS4_profile_gallery():
    """Radial profile gallery at peak for all selected events."""
    profiles = None
    for p in [PROFILES_CSV_NEW, PROFILES_CSV_OLD]:
        if os.path.exists(p):
            profiles = pd.read_csv(p)
            print(f"Loaded profiles from: {p}")
            break

    if profiles is None:
        print("WARNING: radial_profiles_at_peak.csv not found; skipping figS4.")
        return

    flags = pd.read_csv(FLAGS_CSV)
    sel = flags[flags["route_b_selected"] == True].copy()
    slugs = sel.sort_values("alpha", ascending=False)["slug"].tolist()

    n_cols, n_rows = 4, 5

    with paper_style():
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(8.5, 8))
        fig.subplots_adjust(hspace=0.55, wspace=0.35,
                            left=0.07, right=0.97, top=0.95, bottom=0.06)

        for idx, (ax, slug) in enumerate(zip(axes.flat, slugs)):
            sub = profiles[profiles["slug"] == slug].copy()
            if sub.empty:
                ax.text(0.5, 0.5, "No data", transform=ax.transAxes,
                        ha="center", va="center", fontsize=7)
                despine(ax)
                continue
            sub = sub.sort_values("r_bin_km")
            row = sel[sel["slug"] == slug].iloc[0]
            dtype = row["disaster_type"]
            alpha_val = row["alpha"]
            color = DTYPE_COLOR.get(dtype, "gray")
            label = SHORT_LABELS.get(slug, slug[:15])

            ax.plot(sub["r_bin_km"], sub["delta_at_peak"],
                    color=color, lw=1.5, alpha=0.9)
            ax.axhline(0, color="black", lw=0.5, ls="--", alpha=0.4)
            ax.axvspan(0, 50, alpha=0.06, color="gray", zorder=0)

            alpha_str = f"{alpha_val:.2f}" if pd.notna(alpha_val) else "—"
            ax.set_title(f"{label} " + fr"($\alpha={alpha_str}$)",
                         fontsize=7, pad=2)
            ax.tick_params(labelsize=6)
            despine(ax)

            if idx >= (n_rows - 1) * n_cols:
                ax.set_xlabel(r"$r$ (km)", fontsize=7)
            if idx % n_cols == 0:
                ax.set_ylabel(r"$\delta(r,\,t_{\mathrm{peak}})$", fontsize=7)

        for ax in axes.flat[len(slugs):]:
            ax.set_visible(False)

        save_figure(fig, OUT_DIR / "figS4_profile_gallery.pdf")
        save_figure(fig, OUT_DIR / "figS4_profile_gallery.png", dpi=150)
        plt.close(fig)
    print("Saved: figS4_profile_gallery")


def figS5_gao_delta_bic():
    """Gao baseline: ΔBIC (Power Law - Exponential) forest."""
    if not Path(GAO_CSV).exists():
        print("WARNING: missing model_comparison.csv; skip figS5.")
        return

    gao = pd.read_csv(GAO_CSV)
    flags = pd.read_csv(FLAGS_CSV)
    sel = flags[flags["route_b_selected"] == True][["slug", "disaster_type"]].copy()
    merged = gao.merge(sel, on="slug", how="inner")
    merged["dBIC_PL_Exp"] = merged["M1_power_law_bic"] - merged["M2_exponential_bic"]
    merged = merged.sort_values("dBIC_PL_Exp")
    merged["label"] = merged["slug"].map(SHORT_LABELS).fillna(merged["slug"].str[:12])

    with paper_style():
        fig, ax = plt.subplots(figsize=(5.2, 4.8))
        fig.subplots_adjust(left=0.36, right=0.96, top=0.93, bottom=0.14)
        y = np.arange(len(merged))
        ax.axvspan(-2, 2, alpha=0.10, color="gray", zorder=0)
        ax.axvline(0, color="black", lw=0.8, ls=":", alpha=0.5)
        for pos, row in enumerate(merged.itertuples(index=False)):
            c = DTYPE_COLOR.get(row.disaster_type, "gray")
            ax.scatter(row.dBIC_PL_Exp, y[pos], color=c, s=28,
                       edgecolors="white", linewidths=0.3, zorder=4)
        ax.set_yticks(y)
        ax.set_yticklabels(merged["label"].values, fontsize=6)
        ax.set_xlabel(r"$\Delta$BIC (Power Law $-$ Exponential)")
        ax.tick_params(axis="y", length=0)
        ax.text(0.97, 0.97, "PL preferred ←  → Exp preferred",
                transform=ax.transAxes, ha="right", va="top", fontsize=6.5, color="gray")
        despine(ax)
        ax.spines["left"].set_visible(False)
        save_figure(fig, OUT_DIR / "figS5_gao_delta_bic.pdf")
        save_figure(fig, OUT_DIR / "figS5_gao_delta_bic.png", dpi=150)
        plt.close(fig)
    print("Saved: figS5_gao_delta_bic")


def main():
    figS1_individual_panels()
    figS2_jackknife()
    figS3_alpha_vs_dinf()
    figS4_profile_gallery()
    figS5_gao_delta_bic()
    print("\nAll supplementary figures done.")


if __name__ == "__main__":
    main()
