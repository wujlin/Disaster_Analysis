"""
Figure 1: Universal Recovery Dynamics  (2行布局)
第1行: (a) global map with hazard icons — 18-event event-level sample
中间:   shared legend
第2行: (b) D(t) raw time series
       (c) normalised log-log decay coloured by δ_near
       (d) α vs δ_near scatter + Theil-Sen trend
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
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image
import cartopy.crs as ccrs
from scipy.stats import spearmanr, theilslopes

from src.disaster.plot_style import (
    paper_style, OKABE_ITO, add_panel_label, save_figure, despine,
)

# ── paths ──────────────────────────────────────────────────────────────────
ROOT     = "outputs/cross_disaster_comparison"
DT_DIR   = f"{ROOT}/Dt_decay_unified_static_h8_gtfix_mtw5_mpp4"
TS_CSV   = f"{DT_DIR}/tables/Dt_all_events.csv"
FLAGS_CSV = f"{DT_DIR}/tables/Dt_routeB_sample_flags.csv"
OUT_DIR  = "Essay/figures"
OUT_PDF  = f"{OUT_DIR}/fig2_universal_relaxation.pdf"
OUT_PNG  = f"{OUT_DIR}/fig2_universal_relaxation.png"

# ── style constants ────────────────────────────────────────────────────────
DTYPE_COLOR = {
    "earthquake":     OKABE_ITO["vermillion"],
    "hurricane":      OKABE_ITO["blue"],
    "typhoon":        OKABE_ITO["blue"],
    "tropical_storm": OKABE_ITO["blue"],
    "flood":          OKABE_ITO["bluish_green"],
    "wildfire":       OKABE_ITO["orange"],
}
EVENT_COORDS = {
    "flooding_in_central_and_eastern_europe_sept_16_2024":         (17.0,   50.0),
    "hurricane_beryl_across_quintana_roo_and_yucatan_mexico":      (-87.0,  21.0),
    "hurricane_beryl_across_southeastern_texas_us":                (-95.5,  29.5),
    "hurricane_beryl_jamaica_western_caribbean_pre_landfall_2024_07_03": (-77.0, 18.1),
    "moldova_flooding_2024":                                       (28.8,   47.0),
    "park_fire_california_29_july_2024":                           (-121.0, 39.9),
    "spain_flood":                                                 (-0.5,   39.5),
    "the_flooding_across_bagmati_and_koshi_provinces_nepal":       (86.0,   27.5),
    "the_flooding_across_eastern_bangladesh":                      (91.0,   24.0),
    "the_flooding_across_gujarat_india":                           (72.0,   22.0),
    "the_flooding_across_rio_grande_do_sul_state_brazil":          (-51.2, -30.0),
    "the_wildfires_in_quito_pichincha_province_ecuador":           (-78.5,  -0.2),
    "tropical_storm_kristine_in_bicol_and_calabarzon_philippines": (123.5,  13.5),
    "tropical_storm_yagi_philippines_2_september_2024":            (121.5,  17.5),
    "turkiye_earthquake_2023":                                     (37.0,   37.2),
    "typhoon_krathon_across_taiwan":                               (120.3,  23.0),
    "typhoon_yagi_across_northeastern_vietnam":                    (107.0,  21.5),
    "wildfires_in_boise_county_idaho_27_august_2024":              (-115.5, 44.0),
}

REPR_SLUGS = [
    "the_flooding_across_bagmati_and_koshi_provinces_nepal",
    "hurricane_beryl_across_southeastern_texas_us",
    "tropical_storm_kristine_in_bicol_and_calabarzon_philippines",
    "typhoon_yagi_across_northeastern_vietnam",
    "turkiye_earthquake_2023",
    "spain_flood",
    "wildfires_in_boise_county_idaho_27_august_2024",
]
REPR_LABELS = {
    "the_flooding_across_bagmati_and_koshi_provinces_nepal":       "Nepal floods",
    "hurricane_beryl_across_southeastern_texas_us":                "Beryl (TX)",
    "tropical_storm_kristine_in_bicol_and_calabarzon_philippines": "Kristine (PH)",
    "typhoon_yagi_across_northeastern_vietnam":                    "Yagi (VN)",
    "turkiye_earthquake_2023":                                     "Türkiye EQ",
    "spain_flood":                                                 "Spain floods",
    "wildfires_in_boise_county_idaho_27_august_2024":              "Idaho wildfire",
}

ICON_PATH = {
    "earthquake":     "Essay/icons/earthquake.png",
    "hurricane":      "Essay/icons/hurricane.png",
    "typhoon":        "Essay/icons/hurricane.png",
    "tropical_storm": "Essay/icons/hurricane.png",
    "flood":          "Essay/icons/flooded-house.png",
    "wildfire":       "Essay/icons/burning.png",
}
ICON_ZOOM     = 0.022
ICON_ZOOM_LEG = 0.034
MAP_MIN_SEP_DEG = 6.0
LEGEND_ITEM_WIDTH = 0.235
LEGEND_ICON_X_OFFSET = 0.038
LEGEND_TEXT_X_OFFSET = 0.015
LEGEND_FONTSIZE = 7.5

MAP_MANUAL_OFFSET = {
    "hurricane_beryl_across_quintana_roo_and_yucatan_mexico":      (-2.2,  1.4),
    "hurricane_beryl_across_southeastern_texas_us":                ( 1.2,  2.0),
    "hurricane_beryl_jamaica_western_caribbean_pre_landfall_2024_07_03": (-1.4, -1.0),
    "the_flooding_across_rio_grande_do_sul_state_brazil":          ( 1.3, -0.6),
    "flooding_in_central_and_eastern_europe_sept_16_2024":         (-1.4,  0.8),
    "moldova_flooding_2024":                                       ( 1.0,  1.2),
    "spain_flood":                                                 (-1.2, -0.6),
    "the_flooding_across_bagmati_and_koshi_provinces_nepal":       (-1.1,  0.8),
    "the_flooding_across_eastern_bangladesh":                      ( 1.0, -0.7),
    "typhoon_krathon_across_taiwan":                               ( 1.2, -0.9),
}

def load_data():
    ts     = pd.read_csv(TS_CSV)
    flags  = pd.read_csv(FLAGS_CSV)
    sel    = flags[flags["route_b_selected"] == True].copy()
    return ts, sel


# ── panel helpers ──────────────────────────────────────────────────────────

def _load_icon_cache():
    cache = {}
    for dtype, path in ICON_PATH.items():
        try:
            cache[dtype] = np.array(Image.open(path).convert("RGBA"))
        except FileNotFoundError:
            cache[dtype] = None
    return cache


def _jitter_coords(coords_list, min_sep_deg=6.0):
    out = list(coords_list)
    n = len(out)
    for _ in range(8):
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


def panel_a(ax, sel):
    """World map with hazard icons for the 18-event event-level sample."""
    ax.set_extent([-135, 132, -10, 63], crs=ccrs.PlateCarree())
    ax.stock_img()
    proj = ccrs.PlateCarree()

    img_cache = _load_icon_cache()
    events = []
    for _, row in sel.iterrows():
        slug  = row["slug"]
        dtype = row["disaster_type"]
        if slug not in EVENT_COORDS:
            continue
        lon, lat = EVENT_COORDS[slug]
        dx, dy = MAP_MANUAL_OFFSET.get(slug, (0.0, 0.0))
        lon, lat = lon + dx, lat + dy
        events.append((slug, dtype, lon, lat))

    jittered = _jitter_coords([(e[2], e[3]) for e in events], min_sep_deg=MAP_MIN_SEP_DEG)

    for (slug, dtype, _, _), (lon, lat) in zip(events, jittered):
        img_arr  = img_cache.get(dtype)
        xy = proj.transform_point(lon, lat, ccrs.PlateCarree())
        if img_arr is not None:
            oimg = OffsetImage(img_arr, zoom=ICON_ZOOM)
            ab   = AnnotationBbox(oimg, xy, frameon=False, zorder=5)
            ax.add_artist(ab)
        else:
            ax.plot(xy[0], xy[1], "o",
                    color=DTYPE_COLOR.get(dtype, "gray"),
                    markersize=5, markeredgecolor="white", markeredgewidth=0.3,
                    zorder=5)

    ax.text(0.02, 0.06, f"$n = {len(sel)}$ events",
            transform=ax.transAxes, fontsize=8, va="bottom")
    return img_cache


def draw_icon_legend(fig, img_cache, y_icon=0.48):
    items = [
        ("Earthquake", "earthquake"),
        ("Hurricane / Typhoon / TS", "hurricane"),
        ("Flood", "flood"),
        ("Wildfire", "wildfire"),
    ]
    n = len(items)
    item_w = LEGEND_ITEM_WIDTH
    x_start = 0.50 - (n * item_w) / 2 + item_w / 2

    for k, (label, dtype) in enumerate(items):
        x_item = x_start + k * item_w
        img_arr = img_cache.get(dtype)
        if img_arr is not None:
            oimg = OffsetImage(img_arr, zoom=ICON_ZOOM_LEG)
            ab = AnnotationBbox(
                oimg,
                (x_item - LEGEND_ICON_X_OFFSET, y_icon),
                xycoords="figure fraction",
                frameon=False,
                zorder=10,
                box_alignment=(0.5, 0.5),
            )
            fig.add_artist(ab)
            fig.text(
                x_item + LEGEND_TEXT_X_OFFSET,
                y_icon,
                label,
                transform=fig.transFigure,
                fontsize=LEGEND_FONTSIZE,
                va="center",
                ha="left",
            )
        else:
            fig.text(
                x_item,
                y_icon,
                label,
                transform=fig.transFigure,
                fontsize=LEGEND_FONTSIZE,
                va="center",
                ha="center",
            )


def panel_b(ax, ts, sel):
    """D(t) raw time series for representative events."""
    legend_items = []
    for slug in REPR_SLUGS:
        sub = ts[ts["slug"] == slug].sort_values("t_hours")
        if sub.empty:
            continue
        row = sel[sel["slug"] == slug]
        if row.empty:
            continue
        t_peak = float(row["t_peak_hours"].iloc[0])
        dtype  = sub["disaster_type"].iloc[0]
        color  = DTYPE_COLOR.get(dtype, "gray")
        label  = REPR_LABELS.get(slug, slug)
        t_rel  = sub["t_hours"].values - t_peak
        d_vals = sub["D"].values
        line, = ax.plot(t_rel, d_vals, color=color, lw=1.4, alpha=0.9, label=label)
        legend_items.append((line, label))

    ax.axvline(0, color="black", lw=0.8, ls="--", alpha=0.4)
    ax.set_xlim(-48, 250)
    ax.set_ylim(bottom=0)
    ax.set_xlabel(r"$t - t_{\mathrm{peak}}$ (h)")
    ax.set_ylabel(r"$D(t)$")
    if legend_items:
        handles, labels = zip(*legend_items)
        ax.legend(
            handles,
            labels,
            fontsize=5.8,
            frameon=False,
            loc="upper right",
            ncol=2,
            handlelength=1.5,
            columnspacing=0.8,
            handletextpad=0.4,
            borderaxespad=0.3,
        )
    despine(ax)


def panel_c(ax, ts, sel):
    """Normalised log-log decay coloured by δ_near (18-event sample)."""
    dnear_vals = sel["near_delta_peak_windows_mean"].dropna().values
    vmax = max(abs(dnear_vals.min()), abs(dnear_vals.max()))
    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
    cmap = plt.get_cmap("RdBu_r")

    for _, row in sel.iterrows():
        slug   = row["slug"]
        t_peak = row["t_peak_hours"]
        dnear  = row["near_delta_peak_windows_mean"]
        D_peak = row["D_peak"]
        if pd.isna(dnear) or pd.isna(D_peak) or D_peak < 1e-8:
            continue
        color  = cmap(norm(dnear))
        sub    = ts[ts["slug"] == slug].sort_values("t_hours")
        sub    = sub[sub["t_hours"] >= t_peak].copy()
        sub["t_prime"] = sub["t_hours"] - t_peak
        sub["D_norm"]  = sub["D"] / D_peak
        sub = sub[(sub["t_prime"] > 0) & (sub["D_norm"] > 0)]
        if len(sub) < 2:
            continue
        ax.plot(sub["t_prime"], sub["D_norm"], color=color, lw=1.2, alpha=0.85)

    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel(r"$t'$ (h)"); ax.set_ylabel(r"$D / D_{\mathrm{peak}}$")
    ax.set_xlim(16, 500); ax.set_ylim(0.03, 2.5)

    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cb = plt.colorbar(sm, ax=ax, orientation="vertical",
                      fraction=0.035, pad=0.015, shrink=0.82)
    cb.set_label(r"$\delta_{\mathrm{near}}$", fontsize=8.8, labelpad=3)
    cb.ax.tick_params(labelsize=6)
    despine(ax)


def panel_d(ax, sel):
    """核心发现：事件级 α 与 δ_near 的负相关。"""
    x = sel["near_delta_peak_windows_mean"].values
    y = sel["alpha"].values

    res = theilslopes(y, x, 0.95)
    x_line = np.linspace(np.nanmin(x) - 0.05, np.nanmax(x) + 0.05, 100)
    ax.plot(
        x_line,
        res.slope * x_line + res.intercept,
        color="gray",
        ls="--",
        lw=1.2,
        alpha=0.8,
        zorder=1,
    )

    for _, row in sel.iterrows():
        xi = row["near_delta_peak_windows_mean"]
        yi = row["alpha"]
        ax.scatter(
            xi,
            yi,
            s=42,
            marker="o",
            facecolors="#7f7f7f",
            edgecolors="#7f7f7f",
            linewidths=0.8,
            alpha=0.95,
            zorder=3,
        )

    rho, pval = spearmanr(x, y)
    ax.text(
        0.97,
        0.97,
        fr"$\rho = {rho:.2f}$, $p = {pval:.3f}$",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=8.5,
    )
    ax.axhline(0, color="black", lw=0.5, alpha=0.3, ls=":")
    ax.axvline(0, color="black", lw=0.5, alpha=0.3, ls=":")
    ax.set_xlabel(r"$\delta_{\mathrm{near}}$")
    ax.set_ylabel(r"$\alpha$ (decay rate)", labelpad=2)
    despine(ax)


# ── main ───────────────────────────────────────────────────────────────────

def main():
    ts, sel = load_data()

    with paper_style():
        fig = plt.figure(figsize=(8.4, 6.35))
        gs  = gridspec.GridSpec(
            2, 3,
            figure=fig,
            height_ratios=[1.12, 1.0],
            hspace=0.44, wspace=0.46,
            left=0.08, right=0.97,
            top=0.94, bottom=0.11,
        )

        ax_a = fig.add_subplot(gs[0, :], projection=ccrs.PlateCarree())
        ax_b = fig.add_subplot(gs[1, 0])
        ax_c = fig.add_subplot(gs[1, 1])
        ax_d = fig.add_subplot(gs[1, 2])

        img_cache = panel_a(ax_a, sel)
        panel_b(ax_b, ts, sel)
        panel_c(ax_c, ts, sel)
        panel_d(ax_d, sel)

        add_panel_label(ax_a, "a", dy=8)
        add_panel_label(ax_b, "b", dy=8)
        add_panel_label(ax_c, "c", dy=8)
        add_panel_label(ax_d, "d", dy=8)

        draw_icon_legend(fig, img_cache, y_icon=0.50)

        os.makedirs(OUT_DIR, exist_ok=True)
        save_figure(fig, OUT_PDF)
        save_figure(fig, OUT_PNG, dpi=150)
        plt.close(fig)

    print(f"Saved: {OUT_PDF}, {OUT_PNG}")


if __name__ == "__main__":
    main()
