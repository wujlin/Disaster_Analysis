"""
Figure 3: Cross-Scale Universality — Subregion Data Collapse  (2×2)

Replaces the old PDE mechanism figure.  PDE quantitative prediction failed
(R² = -0.36 on n=18), so the cross-scale story is now told through data
collapse: ~1000 subregion-level decay trajectories, when rescaled, converge
onto a single master curve — confirming the same power-law functional form
at both event and subregion scales.

(a) Data collapse: D_norm vs τ for all qualified subregions, master curve overlay
(b) Master curve in log-log with R² and β annotation
(c) Per-event α_unit violin/box distributions — showing ICC structure
(d) Subregion power-law R² cumulative distribution — showing fit quality
"""
import sys, os
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.colors as mcolors
from matplotlib.lines import Line2D
from scipy.optimize import curve_fit

from src.disaster.plot_style import (
    paper_style, OKABE_ITO, add_panel_label, save_figure, despine,
)

# ── paths ──────────────────────────────────────────────────────────────────
ROOT     = "outputs/cross_disaster_comparison"
GEO_DIR  = f"{ROOT}/geo_unit_scale_unified_static_h8_gtfix_mtw5_mpp4/tables"
TS_CSV   = f"{GEO_DIR}/geo_unit_timeseries.csv"
FITS_CSV = f"{GEO_DIR}/geo_unit_fits.csv"
DT_FLAGS = f"{ROOT}/Dt_decay_unified_static_h8_gtfix_mtw5_mpp4/tables/Dt_routeB_sample_flags.csv"
OUT_DIR  = "Essay/figures"
OUT_PDF  = f"{OUT_DIR}/fig4_cross_scale_collapse.pdf"
OUT_PNG  = f"{OUT_DIR}/fig4_cross_scale_collapse.png"

# ── constants ─────────────────────────────────────────────────────────────
MIN_NMONO     = 4
MIN_R2        = 0.5
MIN_TAU_PTS   = 3
EXCLUDE_EQ    = True

DTYPE_COLOR = {
    "earthquake":     OKABE_ITO["vermillion"],
    "hurricane":      OKABE_ITO["blue"],
    "typhoon":        OKABE_ITO["blue"],
    "tropical_storm": OKABE_ITO["blue"],
    "flood":          OKABE_ITO["bluish_green"],
    "wildfire":       OKABE_ITO["orange"],
}

SHORT_LABELS = {
    "flooding_in_central_and_eastern_europe_sept_16_2024":         "EU Fl.",
    "hurricane_beryl_across_quintana_roo_and_yucatan_mexico":      "Beryl QR",
    "hurricane_beryl_across_southeastern_texas_us":                "Beryl TX",
    "hurricane_beryl_jamaica_western_caribbean_pre_landfall_2024_07_03": "Beryl JM",
    "moldova_flooding_2024":                                       "Moldova",
    "park_fire_california_29_july_2024":                           "Park Fire",
    "spain_flood":                                                 "Spain",
    "the_flooding_across_bagmati_and_koshi_provinces_nepal":       "Nepal",
    "the_flooding_across_eastern_bangladesh":                      "Bangladesh",
    "the_flooding_across_gujarat_india":                           "Gujarat",
    "the_flooding_across_rio_grande_do_sul_state_brazil":          "Rio Grande",
    "the_wildfires_in_quito_pichincha_province_ecuador":           "Quito",
    "tropical_storm_kristine_in_bicol_and_calabarzon_philippines": "Kristine",
    "tropical_storm_yagi_philippines_2_september_2024":            "Yagi PH",
    "turkiye_earthquake_2023":                                     "Türkiye",
    "typhoon_krathon_across_taiwan":                               "Krathon",
    "typhoon_yagi_across_northeastern_vietnam":                    "Yagi VN",
    "wildfires_in_boise_county_idaho_27_august_2024":              "Idaho",
}


def load_collapse_data(exclude_earthquake=True):
    """Load subregion timeseries, quality-filter, compute normalised decay."""
    ts   = pd.read_csv(TS_CSV)
    fits = pd.read_csv(FITS_CSV)

    # Quality filter
    fits_ok = fits[(fits["n_mono"] >= MIN_NMONO) &
                   (fits["r2_unit"] >= MIN_R2)].copy()

    merged = ts.merge(
        fits_ok[["slug", "geo_unit", "alpha_unit", "D_peak_unit",
                 "t_peak_h", "r2_unit", "n_mono"]],
        on=["slug", "geo_unit"], how="inner",
    )

    if exclude_earthquake:
        merged = merged[~merged["slug"].str.contains("earthquake")]

    # Post-peak decay
    merged["tau"] = merged["hours_since_t0"] - merged["t_peak_h"]
    decay = merged[merged["tau"] > 0].copy()
    decay["D_norm"] = decay["D"] / decay["D_peak_unit"]

    # Keep only subregions with enough decay points
    counts = decay.groupby(["slug", "geo_unit"]).size()
    valid  = counts[counts >= MIN_TAU_PTS].index
    decay  = decay.set_index(["slug", "geo_unit"]).loc[valid].reset_index()

    return decay, fits_ok


def _power_law(t, C, beta):
    return C * np.power(t, -beta)


# ── panel functions ────────────────────────────────────────────────────────

def panel_a(ax, decay):
    """Data collapse: D_norm vs τ for all subregions, semi-transparent.
    Master curve overlay in black."""
    events = decay["slug"].unique()
    cmap   = plt.cm.tab20(np.linspace(0, 1, max(len(events), 2)))

    for i, slug in enumerate(sorted(events)):
        sub = decay[decay["slug"] == slug]
        for _, g in sub.groupby("geo_unit"):
            g = g.sort_values("tau")
            ax.plot(g["tau"], g["D_norm"], color=cmap[i % len(cmap)],
                    lw=0.3, alpha=0.08, zorder=1)

    # Bin-averaged master curve
    tau_vals  = decay["tau"].values
    dnorm_vals = decay["D_norm"].values
    valid = (tau_vals > 0) & (dnorm_vals > 0) & np.isfinite(tau_vals) & np.isfinite(dnorm_vals)
    tau_v, dn_v = tau_vals[valid], dnorm_vals[valid]

    bins = np.logspace(np.log10(tau_v.min()), np.log10(tau_v.max()), 30)
    bin_idx = np.digitize(tau_v, bins)
    t_med, d_med, d_q25, d_q75 = [], [], [], []
    for b in range(1, len(bins)):
        mask = bin_idx == b
        if mask.sum() >= 5:
            t_med.append(np.median(tau_v[mask]))
            d_med.append(np.median(dn_v[mask]))
            d_q25.append(np.percentile(dn_v[mask], 25))
            d_q75.append(np.percentile(dn_v[mask], 75))

    t_med = np.array(t_med)
    d_med = np.array(d_med)
    d_q25 = np.array(d_q25)
    d_q75 = np.array(d_q75)

    ax.fill_between(t_med, d_q25, d_q75, color="black", alpha=0.12, zorder=2)
    ax.plot(t_med, d_med, color="black", lw=2.0, zorder=3, label="Master curve")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(r"$\tau$ (h since subregion peak)")
    ax.set_ylabel(r"$D / D_{\mathrm{peak}}$")
    ax.set_xlim(1, 500)
    ax.set_ylim(0.01, 3)

    n_units  = decay.groupby(["slug", "geo_unit"]).ngroups
    n_events = decay["slug"].nunique()
    ax.text(0.97, 0.97, f"$n = {n_units}$ units, {n_events} events",
            transform=ax.transAxes, ha="right", va="top", fontsize=7.5)
    ax.legend(fontsize=7, frameon=False, loc="lower left")
    despine(ax)


def panel_b(ax, decay):
    """Master curve power-law fit in log-log with R² and β."""
    tau_vals  = decay["tau"].values
    dnorm_vals = decay["D_norm"].values
    valid = (tau_vals > 0) & (dnorm_vals > 0) & np.isfinite(tau_vals) & np.isfinite(dnorm_vals)
    tau_v, dn_v = tau_vals[valid], dnorm_vals[valid]

    # Bin-averaged for fitting
    bins = np.logspace(np.log10(tau_v.min()), np.log10(tau_v.max()), 40)
    bin_idx = np.digitize(tau_v, bins)
    t_fit, d_fit = [], []
    for b in range(1, len(bins)):
        mask = bin_idx == b
        if mask.sum() >= 5:
            t_fit.append(np.median(tau_v[mask]))
            d_fit.append(np.median(dn_v[mask]))

    t_fit = np.array(t_fit)
    d_fit = np.array(d_fit)

    # Power-law fit on binned medians
    try:
        popt, _ = curve_fit(_power_law, t_fit, d_fit,
                            p0=[1.0, 0.3], bounds=([0, -1], [100, 5]))
        C_fit, beta_fit = popt
        d_pred = _power_law(t_fit, *popt)
        ss_res = np.sum((d_fit - d_pred) ** 2)
        ss_tot = np.sum((d_fit - np.mean(d_fit)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    except Exception:
        C_fit, beta_fit, r2 = 1.0, 0.3, 0.0

    # Plot binned data + fit
    ax.scatter(t_fit, d_fit, color=OKABE_ITO["blue"], s=20, zorder=3,
               edgecolors="white", linewidths=0.3)
    t_smooth = np.logspace(np.log10(t_fit.min()), np.log10(t_fit.max()), 100)
    ax.plot(t_smooth, _power_law(t_smooth, C_fit, beta_fit),
            color="black", lw=1.5, ls="--", zorder=4)

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(r"$\tau$ (h)")
    ax.set_ylabel(r"$D / D_{\mathrm{peak}}$ (binned median)")
    ax.text(0.97, 0.97,
            fr"$\beta = {beta_fit:.2f}$, $R^2 = {r2:.2f}$"
            "\n"
            fr"$D/D_p = {C_fit:.2f}\,\tau^{{-{beta_fit:.2f}}}$",
            transform=ax.transAxes, ha="right", va="top", fontsize=7.5,
            linespacing=1.5)
    despine(ax)


def panel_c(ax, fits_ok, exclude_earthquake=True):
    """Per-event α_unit distributions (boxplots) — showing ICC structure."""
    if exclude_earthquake:
        fits_ok = fits_ok[~fits_ok["slug"].str.contains("earthquake")]

    # Order by median α
    event_medians = fits_ok.groupby("slug")["alpha_unit"].median().sort_values()
    event_order = event_medians.index.tolist()
    event_labels = [SHORT_LABELS.get(s, s[:10]) for s in event_order]

    data = [fits_ok[fits_ok["slug"] == s]["alpha_unit"].dropna().values
            for s in event_order]
    # Filter out events with too few points
    keep = [(d, l) for d, l in zip(data, event_labels) if len(d) >= 3]
    if not keep:
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes,
                ha="center", va="center")
        despine(ax)
        return
    data, event_labels = zip(*keep)

    bp = ax.boxplot(data, vert=False, widths=0.6, patch_artist=True,
                    showfliers=False,
                    medianprops=dict(color="black", lw=1.2),
                    boxprops=dict(facecolor=OKABE_ITO["sky_blue"], alpha=0.5,
                                  edgecolor="gray", lw=0.5),
                    whiskerprops=dict(color="gray", lw=0.8),
                    capprops=dict(color="gray", lw=0.8))

    ax.set_yticklabels(event_labels, fontsize=5.5)
    ax.set_xlabel(r"$\alpha_{\mathrm{unit}}$")
    ax.axvline(0, color="black", lw=0.5, ls=":", alpha=0.4)

    # ICC annotation
    all_alpha = fits_ok["alpha_unit"].dropna()
    grand_mean = all_alpha.mean()
    event_means = fits_ok.groupby("slug")["alpha_unit"].mean()
    event_counts = fits_ok.groupby("slug")["alpha_unit"].count()
    ss_between = np.sum(event_counts.values * (event_means.values - grand_mean) ** 2)
    ss_total   = np.sum((all_alpha.values - grand_mean) ** 2)
    icc_approx = ss_between / ss_total if ss_total > 0 else 0

    ax.text(0.97, 0.06, f"ICC ≈ {icc_approx:.2f}",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=7.5, color="gray")
    despine(ax)


def panel_d(ax, fits_ok, exclude_earthquake=True):
    """Subregion power-law R² cumulative distribution."""
    if exclude_earthquake:
        fits_ok = fits_ok[~fits_ok["slug"].str.contains("earthquake")]

    r2_all = fits_ok["r2_unit"].dropna().values
    r2_sorted = np.sort(r2_all)
    cdf = np.arange(1, len(r2_sorted) + 1) / len(r2_sorted)

    ax.plot(r2_sorted, cdf, color=OKABE_ITO["blue"], lw=1.8)
    ax.axvline(0.5, color="gray", ls="--", lw=0.8, alpha=0.6)
    ax.axvline(0.7, color="gray", ls=":", lw=0.8, alpha=0.6)

    pct_05 = np.mean(r2_all >= 0.5) * 100
    pct_07 = np.mean(r2_all >= 0.7) * 100
    ax.text(0.52, 0.15, fr"$R^2 \geq 0.5$: {pct_05:.0f}%",
            transform=ax.transAxes, fontsize=7.5, color="gray")
    ax.text(0.52, 0.05, fr"$R^2 \geq 0.7$: {pct_07:.0f}%",
            transform=ax.transAxes, fontsize=7.5, color="gray")

    ax.set_xlabel(r"Subregion power-law $R^2$")
    ax.set_ylabel("CDF")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    despine(ax)


# ── main ───────────────────────────────────────────────────────────────────

def main():
    decay, fits_ok = load_collapse_data(exclude_earthquake=EXCLUDE_EQ)

    with paper_style():
        fig = plt.figure(figsize=(7.0, 5.4))
        gs  = gridspec.GridSpec(
            2, 2,
            figure=fig,
            hspace=0.52, wspace=0.55,
            left=0.09, right=0.97,
            top=0.93, bottom=0.12,
        )
        ax_a = fig.add_subplot(gs[0, 0])
        ax_b = fig.add_subplot(gs[0, 1])
        ax_c = fig.add_subplot(gs[1, 0])
        ax_d = fig.add_subplot(gs[1, 1])

        panel_a(ax_a, decay)
        panel_b(ax_b, decay)
        panel_c(ax_c, fits_ok, exclude_earthquake=EXCLUDE_EQ)
        panel_d(ax_d, fits_ok, exclude_earthquake=EXCLUDE_EQ)

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
