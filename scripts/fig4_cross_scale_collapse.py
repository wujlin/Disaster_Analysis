"""
Figure 4: Geo-unit recovery heterogeneity and event-level consistency.

(a) Per-event alpha_unit distributions across all geo-unit fits
(b) Event-level alpha vs median alpha_unit
(c) CDF of geo-unit power-law fit R^2
"""
import os
import sys

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, ".")

from src.disaster.plot_style import (
    OKABE_ITO,
    add_panel_label,
    despine,
    paper_style,
    save_figure,
)


ROOT = "outputs/cross_disaster_comparison"
GEO_DIR = f"{ROOT}/geo_unit_scale_unified_static_h8_gtfix_mtw5_mpp4/tables"
FITS_CSV = f"{GEO_DIR}/geo_unit_fits.csv"
DT_FLAGS = f"{ROOT}/Dt_decay_unified_static_h8_gtfix_mtw5_mpp4/tables/Dt_routeB_sample_flags.csv"
OUT_DIR = "Essay/figures"
OUT_PDF = f"{OUT_DIR}/fig4_cross_scale_collapse.pdf"
OUT_PNG = f"{OUT_DIR}/fig4_cross_scale_collapse.png"
EXCLUDE_EQ = False


SHORT_LABELS = {
    "flooding_in_central_and_eastern_europe_sept_16_2024": "EU Fl.",
    "hurricane_beryl_across_quintana_roo_and_yucatan_mexico": "Beryl QR",
    "hurricane_beryl_across_southeastern_texas_us": "Beryl TX",
    "hurricane_beryl_jamaica_western_caribbean_pre_landfall_2024_07_03": "Beryl JM",
    "moldova_flooding_2024": "Moldova",
    "park_fire_california_29_july_2024": "Park Fire",
    "spain_flood": "Spain",
    "the_flooding_across_bagmati_and_koshi_provinces_nepal": "Nepal",
    "the_flooding_across_gujarat_india": "Gujarat",
    "the_flooding_across_rio_grande_do_sul_state_brazil": "Rio Grande",
    "the_wildfires_in_quito_pichincha_province_ecuador": "Quito",
    "tropical_storm_kristine_in_bicol_and_calabarzon_philippines": "Kristine",
    "tropical_storm_yagi_philippines_2_september_2024": "Yagi PH",
    "turkiye_earthquake_2023": "Türkiye",
    "typhoon_krathon_across_taiwan": "Krathon",
    "typhoon_yagi_across_northeastern_vietnam": "Yagi VN",
}

LABEL_OFFSETS = {
    "flooding_in_central_and_eastern_europe_sept_16_2024": (4, -6),
    "the_flooding_across_gujarat_india": (4, 4),
    "typhoon_krathon_across_taiwan": (4, -10),
    "spain_flood": (4, -2),
    "turkiye_earthquake_2023": (4, 6),
    "the_wildfires_in_quito_pichincha_province_ecuador": (4, 2),
}


def load_geo_unit_data(exclude_earthquake=False):
    fits = pd.read_csv(FITS_CSV)
    flags = pd.read_csv(DT_FLAGS)

    if exclude_earthquake:
        fits = fits[~fits["slug"].str.contains("earthquake")]

    event_alpha = flags[flags["route_b_selected"] == True][["slug", "alpha"]].copy()
    if exclude_earthquake:
        event_alpha = event_alpha[~event_alpha["slug"].str.contains("earthquake")]

    return fits, event_alpha


def panel_a(ax, fits_all, exclude_earthquake=False):
    if exclude_earthquake:
        fits_all = fits_all[~fits_all["slug"].str.contains("earthquake")]

    event_medians = fits_all.groupby("slug")["alpha_unit"].median().sort_values()
    event_order = event_medians.index.tolist()
    event_labels = [SHORT_LABELS.get(slug, slug[:10]) for slug in event_order]
    data = [fits_all[fits_all["slug"] == slug]["alpha_unit"].dropna().values for slug in event_order]

    keep = [(values, label) for values, label in zip(data, event_labels) if len(values) >= 3]
    if not keep:
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes, ha="center", va="center")
        despine(ax)
        return

    data, event_labels = zip(*keep)
    ax.boxplot(
        data,
        vert=False,
        widths=0.6,
        patch_artist=True,
        showfliers=False,
        medianprops=dict(color="black", lw=1.2),
        boxprops=dict(facecolor=OKABE_ITO["sky_blue"], alpha=0.5, edgecolor="gray", lw=0.5),
        whiskerprops=dict(color="gray", lw=0.8),
        capprops=dict(color="gray", lw=0.8),
    )
    ax.set_yticklabels(event_labels, fontsize=6.2)
    ax.set_xlabel(r"Geo-unit $\alpha_{\mathrm{unit}}$")
    ax.axvline(0, color="black", lw=0.5, ls=":", alpha=0.4)
    despine(ax)


def panel_b(ax, fits_all, event_alpha, exclude_earthquake=False):
    fits_plot = fits_all.copy()
    if exclude_earthquake:
        fits_plot = fits_plot[~fits_plot["slug"].str.contains("earthquake")]

    unit_med = fits_plot.groupby("slug")["alpha_unit"].median().reset_index()
    unit_med = unit_med.rename(columns={"alpha_unit": "alpha_unit_median"})
    merged = event_alpha.merge(unit_med, on="slug", how="inner").dropna()

    if merged.empty:
        ax.text(0.5, 0.5, "No overlap events", transform=ax.transAxes, ha="center", va="center", fontsize=8, color="gray")
        despine(ax)
        return

    for _, row in merged.iterrows():
        ax.scatter(
            row["alpha"],
            row["alpha_unit_median"],
            s=42,
            color="0.4",
            edgecolors="white",
            linewidths=0.4,
            zorder=3,
        )
        ax.annotate(
            SHORT_LABELS.get(row["slug"], row["slug"][:10]),
            (row["alpha"], row["alpha_unit_median"]),
            textcoords="offset points",
            xytext=LABEL_OFFSETS.get(row["slug"], (4, 2)),
            fontsize=5.5,
            alpha=0.8,
        )

    x = merged["alpha"].values
    y = merged["alpha_unit_median"].values
    if len(merged) >= 3:
        coef = np.polyfit(x, y, 1)
        xx = np.linspace(x.min(), x.max(), 100)
        ax.plot(xx, coef[0] * xx + coef[1], color="gray", ls="--", lw=1.0, zorder=2)

    ax.set_xlabel(r"Event-level $\alpha$")
    ax.set_ylabel(r"Median $\alpha_{\mathrm{unit}}$")
    despine(ax)


def panel_c(ax, fits_all, exclude_earthquake=False):
    if exclude_earthquake:
        fits_all = fits_all[~fits_all["slug"].str.contains("earthquake")]

    r2_all = fits_all["r2_unit"].dropna().values
    r2_sorted = np.sort(r2_all)
    cdf = np.arange(1, len(r2_sorted) + 1) / len(r2_sorted)

    ax.plot(r2_sorted, cdf, color=OKABE_ITO["blue"], lw=1.8)
    ax.axvline(0.5, color="gray", ls="--", lw=0.8, alpha=0.6)
    ax.axvline(0.7, color="gray", ls=":", lw=0.8, alpha=0.6)
    ax.set_xlabel(r"Geo-unit power-law fit $R^2$")
    ax.set_ylabel("CDF")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    despine(ax)


def main():
    fits_all, event_alpha = load_geo_unit_data(exclude_earthquake=EXCLUDE_EQ)

    with paper_style():
        fig = plt.figure(figsize=(7.0, 4.7))
        gs = gridspec.GridSpec(
            2,
            2,
            figure=fig,
            hspace=0.42,
            wspace=0.48,
            left=0.10,
            right=0.97,
            top=0.93,
            bottom=0.12,
        )
        ax_a = fig.add_subplot(gs[:, 0])
        ax_b = fig.add_subplot(gs[0, 1])
        ax_c = fig.add_subplot(gs[1, 1])

        panel_a(ax_a, fits_all, exclude_earthquake=EXCLUDE_EQ)
        panel_b(ax_b, fits_all, event_alpha, exclude_earthquake=EXCLUDE_EQ)
        panel_c(ax_c, fits_all, exclude_earthquake=EXCLUDE_EQ)

        add_panel_label(ax_a, "a", dy=8)
        add_panel_label(ax_b, "b", dy=8)
        add_panel_label(ax_c, "c", dy=8)

        os.makedirs(OUT_DIR, exist_ok=True)
        save_figure(fig, OUT_PDF)
        save_figure(fig, OUT_PNG, dpi=150)
        plt.close(fig)

    print(f"Saved: {OUT_PDF}, {OUT_PNG}")


if __name__ == "__main__":
    main()
