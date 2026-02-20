"""
Figure 1: Universal Relaxation with Diverse Rates  (1 + 3 layout)
Row 0: (a) global map with hazard icons — full width
Row 1: (b) D(t) raw time series | (c) normalised log-log decay | (d) α vs D∞
"""
import sys, os
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from scipy.stats import spearmanr, theilslopes

from src.disaster.plot_style import (
    paper_style, OKABE_ITO, add_panel_label, save_figure, despine,
)

# ── paths ──────────────────────────────────────────────────────────────────
ROOT     = "outputs/cross_disaster_comparison"
TS_CSV   = f"{ROOT}/Dt_decay/tables/Dt_all_events.csv"
FLAGS_CSV = f"{ROOT}/Dt_decay/tables/Dt_routeB_sample_flags.csv"
OUT_DIR  = "Essay/figures"
OUT_PDF  = f"{OUT_DIR}/fig1_universal_relaxation.pdf"
OUT_PNG  = f"{OUT_DIR}/fig1_universal_relaxation.png"

# ── style constants ────────────────────────────────────────────────────────
DTYPE_COLOR = {
    "earthquake": OKABE_ITO["vermillion"],
    "hurricane":  OKABE_ITO["blue"],
    "typhoon":    OKABE_ITO["blue"],
    "flood":      OKABE_ITO["bluish_green"],
    "wildfire":   OKABE_ITO["orange"],
}
R2_THRESHOLD = 0.75

EVENT_COORDS = {
    "flooding_in_central_and_eastern_europe_sept_16_2024": (17.0, 50.0),
    "hurricane_beryl_across_quintana_roo_and_yucatan_mexico": (-87.0, 21.0),
    "hurricane_beryl_across_southeastern_texas_us": (-95.5, 29.5),
    "hurricane_beryl_pre_landfall_2024": (-61.0, 12.5),
    "hurricane_john_across_southeastern_guerrero_mexico": (-101.0, 16.5),
    "hurricane_john_southern_mexico_25_september_2024": (-103.0, 18.5),
    "hurricane_milton_across_florida_us": (-82.5, 28.0),
    "moldova_flooding_2024": (28.8, 47.0),
    "spain_flood": (-0.5, 39.5),
    "the_earthquake_across_central_mexico": (-98.5, 18.5),
    "the_flooding_across_bagmati_and_koshi_provinces_nepal": (86.0, 27.5),
    "the_flooding_across_eastern_bangladesh": (91.0, 24.0),
    "the_flooding_across_gujarat_india": (72.0, 22.0),
    "turkiye_earthquake_2023": (37.0, 37.2),
    "typhoon_yagi_across_northeastern_vietnam": (107.0, 21.5),
    "wildfires_in_boise_county_idaho_27_august_2024": (-115.5, 44.0),
}

REPR_SLUGS = [
    "turkiye_earthquake_2023",
    "hurricane_beryl_across_southeastern_texas_us",
    "the_flooding_across_bagmati_and_koshi_provinces_nepal",
    "typhoon_yagi_across_northeastern_vietnam",
    "spain_flood",
    "hurricane_john_across_southeastern_guerrero_mexico",
    "wildfires_in_boise_county_idaho_27_august_2024",
]
REPR_LABELS = {
    "turkiye_earthquake_2023":                               "Türkiye EQ",
    "hurricane_beryl_across_southeastern_texas_us":          "Beryl (TX)",
    "the_flooding_across_bagmati_and_koshi_provinces_nepal": "Nepal floods",
    "typhoon_yagi_across_northeastern_vietnam":              "Typhoon Yagi",
    "spain_flood":                                           "Spain floods",
    "hurricane_john_across_southeastern_guerrero_mexico":    "John (GUE)",
    "wildfires_in_boise_county_idaho_27_august_2024":        "Boise wildfire",
}

ICON_PATH = {
    "earthquake": "Essay/icons/earthquake.png",
    "hurricane":  "Essay/icons/hurricane.png",
    "typhoon":    "Essay/icons/hurricane.png",
    "flood":      "Essay/icons/flooded-house.png",
    "wildfire":   "Essay/icons/burning.png",
}
ICON_ZOOM     = 0.030
ICON_ZOOM_LEG = 0.022


def load_data():
    ts     = pd.read_csv(TS_CSV)
    flags  = pd.read_csv(FLAGS_CSV)
    flags16 = flags[flags["route_b_selected"] == True].copy()
    return ts, flags16


# ── panel helpers ──────────────────────────────────────────────────────────

def _load_icon_cache():
    cache = {}
    for dtype, path in ICON_PATH.items():
        try:
            cache[dtype] = np.array(Image.open(path).convert("RGBA"))
        except FileNotFoundError:
            cache[dtype] = None
    return cache


def _jitter_coords(coords_list, min_sep_deg=4.5):
    out = list(coords_list)
    n = len(out)
    for _ in range(3):
        for i in range(n):
            for j in range(i + 1, n):
                dx = out[i][0] - out[j][0]
                dy = out[i][1] - out[j][1]
                dist = np.sqrt(dx**2 + dy**2)
                if dist < min_sep_deg:
                    angle = np.arctan2(dy, dx) if dist > 0.1 else np.pi / 4 * (j - i)
                    shift = (min_sep_deg - dist) / 2 + 0.5
                    out[i] = (out[i][0] + shift * np.cos(angle),
                              out[i][1] + shift * np.sin(angle))
                    out[j] = (out[j][0] - shift * np.cos(angle),
                              out[j][1] - shift * np.sin(angle))
    return out


def panel_a(ax, flags16):
    """Full-width map — events from lat -8 to 65, lon -130 to 120."""
    ax.set_extent([-130, 120, -8, 62], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.LAND,      facecolor="#f5f5f5", edgecolor="none")
    ax.add_feature(cfeature.OCEAN,     facecolor="#e8f0f8", edgecolor="none")
    ax.add_feature(cfeature.COASTLINE, linewidth=0.4, color="#999999")
    ax.add_feature(cfeature.BORDERS,   linewidth=0.2, color="#cccccc", linestyle=":")

    img_cache = _load_icon_cache()
    slugs     = flags16["slug"].tolist()
    raw_coords = [(EVENT_COORDS.get(s, (0, 0))[0],
                   EVENT_COORDS.get(s, (0, 0))[1]) for s in slugs]
    jittered  = _jitter_coords(raw_coords, min_sep_deg=5.5)

    for i, (_, row) in enumerate(flags16.iterrows()):
        slug = row["slug"]
        if slug not in EVENT_COORDS:
            continue
        lon, lat = jittered[i]
        dtype    = row["disaster_type"]
        img_arr  = img_cache.get(dtype)
        if img_arr is not None:
            oimg = OffsetImage(img_arr, zoom=ICON_ZOOM)
            ab   = AnnotationBbox(oimg, (lon, lat),
                                  transform=ccrs.PlateCarree(),
                                  frameon=False, zorder=5)
            ax.add_artist(ab)
        else:
            ax.plot(lon, lat, "o", color=DTYPE_COLOR.get(dtype, "gray"),
                    markersize=6, markeredgecolor="white", markeredgewidth=0.4,
                    transform=ccrs.PlateCarree(), zorder=5)
    return img_cache


def panel_b(ax, ts, flags16):
    """D(t) raw time series for 6 representative events."""
    curves = {}
    for slug in REPR_SLUGS:
        sub = ts[ts["slug"] == slug].sort_values("t_hours")
        if sub.empty:
            continue
        row = flags16[flags16["slug"] == slug]
        if row.empty:
            continue
        t_peak = float(row["t_peak_hours"].iloc[0])
        dtype  = sub["disaster_type"].iloc[0]
        color  = DTYPE_COLOR.get(dtype, "gray")
        label  = REPR_LABELS.get(slug, slug)
        t_rel  = sub["t_hours"].values - t_peak
        d_vals = sub["D"].values
        ax.plot(t_rel, d_vals, color=color, lw=1.6, alpha=0.9)
        curves[slug] = (t_rel, d_vals, color, label)

    ax.axvline(0, color="black", lw=0.8, ls="--", alpha=0.4)
    ax.set_xlim(-48, 250)
    ax.set_ylim(bottom=0)
    ax.set_xlabel(r"$t - t_{\mathrm{peak}}$ (h)")
    ax.set_ylabel(r"$D(t)$")

    offsets_pt = {
        "turkiye_earthquake_2023":                               (6,   2),
        "hurricane_beryl_across_southeastern_texas_us":          (6,  -8),
        "the_flooding_across_bagmati_and_koshi_provinces_nepal": (6,  -8),
        "typhoon_yagi_across_northeastern_vietnam":              (6,   8),
        "spain_flood":                                           (6,   8),
        "hurricane_john_across_southeastern_guerrero_mexico":    (6,   6),
        "wildfires_in_boise_county_idaho_27_august_2024":        (6, -10),
    }
    for slug, (t_rel, d_vals, color, label) in curves.items():
        mask = t_rel <= 240
        if mask.sum() < 2:
            continue
        idx = np.where(mask)[0][-1]
        dx, dy = offsets_pt.get(slug, (6, 0))
        ax.annotate(label, xy=(t_rel[idx], d_vals[idx]),
                    xytext=(dx, dy), textcoords="offset points",
                    fontsize=6.5, color=color, va="center",
                    annotation_clip=True)
    despine(ax)


def panel_c(ax, ts, flags16):
    """Normalised log-log decay coloured by δ_near (all 16 events)."""
    dnear_vals = flags16["near_delta_peak_windows_mean"].values
    vmax = max(abs(dnear_vals.min()), abs(dnear_vals.max()))
    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
    cmap = plt.get_cmap("RdBu_r")

    for _, row in flags16.iterrows():
        slug   = row["slug"]
        t_peak = row["t_peak_hours"]
        dnear  = row["near_delta_peak_windows_mean"]
        D_peak = row["D_peak"]
        color  = cmap(norm(dnear))
        sub    = ts[ts["slug"] == slug].sort_values("t_hours")
        sub    = sub[sub["t_hours"] >= t_peak].copy()
        sub["t_prime"] = sub["t_hours"] - t_peak
        sub["D_norm"]  = sub["D"] / D_peak
        sub = sub[(sub["t_prime"] > 0) & (sub["D_norm"] > 0)]
        if len(sub) < 2:
            continue
        ax.plot(sub["t_prime"], sub["D_norm"], color=color, lw=1.4, alpha=0.85)

    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel(r"$t'$ (h)"); ax.set_ylabel(r"$D_{\mathrm{norm}}(t')$")
    ax.set_xlim(16, 400); ax.set_ylim(0.05, 2.5)
    ax.text(0.97, 0.97, r"$\alpha \in [-0.02,\; 1.14]$",
            transform=ax.transAxes, ha="right", va="top", fontsize=8)

    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cb = plt.colorbar(sm, ax=ax, orientation="vertical",
                      fraction=0.04, pad=0.03, shrink=0.85)
    cb.set_label(r"$\delta_{\mathrm{near}}$", fontsize=9)
    cb.ax.tick_params(labelsize=7)
    despine(ax)


def panel_d(ax, flags16):
    """α vs D_∞ scatter — validates α as a meaningful recovery indicator.
    D_∞ = normalised residual displacement (0 = full return, 1 = no return).
    ρ = −0.703, p = 0.002 (full 16-event sample).
    """
    x = flags16["alpha"].values
    y = flags16["D_inf"].values
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]

    # Theil–Sen robust regression line
    res = theilslopes(y, x, 0.95)
    x_line = np.linspace(x.min() - 0.05, x.max() + 0.05, 100)
    ax.plot(x_line, res.slope * x_line + res.intercept,
            color="gray", ls="--", lw=1.2, alpha=0.7, zorder=1)

    for _, row in flags16.iterrows():
        xi   = row["alpha"]
        yi   = row["D_inf"]
        if not (np.isfinite(xi) and np.isfinite(yi)):
            continue
        dtype = row["disaster_type"]
        ri2   = row["r2"]
        color = DTYPE_COLOR.get(dtype, "gray")
        fc    = color if ri2 >= R2_THRESHOLD else "none"
        ax.scatter(xi, yi, s=42, marker="o",
                   facecolors=fc, edgecolors=color,
                   linewidths=1.0, alpha=0.95 if ri2 >= R2_THRESHOLD else 0.5,
                   zorder=3)

    rho, pval = spearmanr(x, y)
    ax.text(0.97, 0.97,
            fr"$\rho = {rho:.2f}$, $p = {pval:.3f}$",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.5)

    ax.set_xlabel(r"$\alpha$ (decay rate)")
    ax.set_ylabel(r"$D_\infty$ (resid.)")

    handles = []
    for label, dtype in [("EQ", "earthquake"), ("Hurr./Typh.", "hurricane"),
                          ("Flood", "flood"), ("Wildfire", "wildfire")]:
        c = DTYPE_COLOR.get(dtype, "gray")
        handles.append(Line2D([0], [0], marker="o", color="none",
                              markerfacecolor=c, markeredgecolor=c,
                              markersize=5, label=label))
    ax.legend(handles=handles, fontsize=5.5, loc="lower left",
              frameon=False, handletextpad=0.2, columnspacing=0.6,
              ncol=2, borderaxespad=0.3)
    despine(ax)


def _draw_figure_legend(fig, img_cache, y_icon=0.47):
    """Horizontal icon legend between map row and data row."""
    items = [
        ("Earthquake",          "earthquake"),
        ("Hurricane / Typhoon", "hurricane"),
        ("Flood",               "flood"),
        ("Wildfire",            "wildfire"),
    ]
    n      = len(items)
    item_w = 0.22
    x_start = 0.50 - (n * item_w) / 2 + item_w / 2

    for k, (label, dtype) in enumerate(items):
        x_item  = x_start + k * item_w
        img_arr = img_cache.get(dtype)
        if img_arr is not None:
            oimg = OffsetImage(img_arr, zoom=ICON_ZOOM_LEG)
            ab = AnnotationBbox(oimg, (x_item - 0.025, y_icon),
                                xycoords="figure fraction",
                                frameon=False, zorder=10, box_alignment=(0.5, 0.5))
            fig.add_artist(ab)
        fig.text(x_item + 0.005, y_icon, label, transform=fig.transFigure,
                 fontsize=6.5, va="center", ha="left")


# ── main ───────────────────────────────────────────────────────────────────

def main():
    ts, flags16 = load_data()

    with paper_style():
        fig = plt.figure(figsize=(7.2, 5.4))
        gs  = gridspec.GridSpec(
            2, 3,
            figure=fig,
            height_ratios=[1.15, 1.0],
            hspace=0.55, wspace=0.68,
            left=0.09, right=0.97,
            top=0.94, bottom=0.10,
        )
        # Row 0: map spans all 3 columns
        ax_a = fig.add_subplot(gs[0, :], projection=ccrs.PlateCarree())
        # Row 1: three data panels
        ax_b = fig.add_subplot(gs[1, 0])
        ax_c = fig.add_subplot(gs[1, 1])
        ax_d = fig.add_subplot(gs[1, 2])

        img_cache = panel_a(ax_a, flags16)
        panel_b(ax_b, ts, flags16)
        panel_c(ax_c, ts, flags16)
        panel_d(ax_d, flags16)

        add_panel_label(ax_a, "a", dy=8)
        add_panel_label(ax_b, "b", dy=8)
        add_panel_label(ax_c, "c", dy=8)
        add_panel_label(ax_d, "d", dy=8)

        _draw_figure_legend(fig, img_cache)

        os.makedirs(OUT_DIR, exist_ok=True)
        save_figure(fig, OUT_PDF)
        save_figure(fig, OUT_PNG, dpi=150)
        plt.close(fig)

    print(f"Saved: {OUT_PDF}, {OUT_PNG}")


if __name__ == "__main__":
    main()
