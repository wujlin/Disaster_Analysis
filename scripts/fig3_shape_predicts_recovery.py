"""
Figure 2: Why Spatial Geometry Determines Recovery Speed (2×2)

(a) 径向廓线对比：steep-fast vs shallow-slow
(b) 合成实验：|δ_near| 与 α_pred 的单调关系（受控扩散）
(c) 反事实检验：去掉空间形状/扩散后相关性消失
(d) 跨尺度一致性：事件级显著 vs 子区域级不显著（forest风格）
"""
import sys
import os
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy.stats import spearmanr

from src.disaster.plot_style import (
    paper_style, OKABE_ITO, add_panel_label, save_figure, despine,
)

# ── paths ──────────────────────────────────────────────────────────────────
ROOT     = "outputs/cross_disaster_comparison"
DT_DIR   = f"{ROOT}/Dt_decay_unified_static_h8_gtfix_mtw5_mpp4/tables"
SD_DIR   = f"{ROOT}/spatial_diffusion_unified_static_h8_gtfix_mtw5_mpp4/tables"
GEO_DIR  = f"{ROOT}/geo_unit_scale_unified_static_h8_gtfix_mtw5_mpp4/tables"

FLAGS_CSV = f"{DT_DIR}/Dt_routeB_sample_flags.csv"
JACK_CSV  = f"{DT_DIR}/Dt_routeB_alpha_delta_jackknife.csv"
SYNTH_CSV = f"{SD_DIR}/analytic_predictions_synthetic.csv"
CF_CSV    = f"{SD_DIR}/counterfactual_results.csv"
BOOT_CSV  = f"{SD_DIR}/simulation_bootstrap.csv"
PROF_CSV  = f"{SD_DIR}/radial_profiles_at_peak.csv"
MIX_CSV   = f"{GEO_DIR}/mixed_effects_alpha_unit.csv"

OUT_DIR = "Essay/figures"
OUT_PDF = f"{OUT_DIR}/fig3_shape_predicts_recovery.pdf"
OUT_PNG = f"{OUT_DIR}/fig3_shape_predicts_recovery.png"

SYNTH_CLASS_COLOR = {
    "EVAC":  OKABE_ITO["blue"],
    "INFL":  OKABE_ITO["vermillion"],
    "MIXED": OKABE_ITO["gray"],
}

EVAC_SLUG = "hurricane_beryl_across_southeastern_texas_us"
INFL_SLUG = "spain_flood"


def load_data():
    flags = pd.read_csv(FLAGS_CSV)
    sel = flags[flags["route_b_selected"] == True].copy()
    jack = pd.read_csv(JACK_CSV)

    synth = pd.read_csv(SYNTH_CSV) if os.path.exists(SYNTH_CSV) else None
    cf = pd.read_csv(CF_CSV) if os.path.exists(CF_CSV) else None
    boot = pd.read_csv(BOOT_CSV) if os.path.exists(BOOT_CSV) else None
    prof = pd.read_csv(PROF_CSV) if os.path.exists(PROF_CSV) else None
    mix = pd.read_csv(MIX_CSV) if os.path.exists(MIX_CSV) else None
    return sel, jack, synth, cf, boot, prof, mix


def panel_a(ax, prof, sel):
    """径向廓线只出现一次：直接展示空间几何差异。"""
    if prof is None:
        ax.text(0.5, 0.5, "Missing radial_profiles_at_peak.csv",
                transform=ax.transAxes, ha="center", va="center",
                fontsize=8, color="gray")
        despine(ax)
        return

    r_near = 50
    row_e = sel[sel["slug"] == EVAC_SLUG]
    row_i = sel[sel["slug"] == INFL_SLUG]
    a_e = float(row_e["alpha"].iloc[0]) if not row_e.empty else np.nan
    a_i = float(row_i["alpha"].iloc[0]) if not row_i.empty else np.nan

    for slug, color, label in [
        (EVAC_SLUG, OKABE_ITO["blue"], f"Beryl TX ($\\alpha={a_e:.2f}$)"),
        (INFL_SLUG, OKABE_ITO["bluish_green"], f"Spain flood ($\\alpha={a_i:.2f}$)"),
    ]:
        sub = prof[prof["slug"] == slug].sort_values("r_bin_km")
        if sub.empty:
            continue
        ax.plot(sub["r_bin_km"], sub["delta_at_peak"], color=color, lw=2.0, label=label)

    ax.axhline(0, color="black", lw=0.7, ls="--", alpha=0.5)
    ax.axvspan(0, r_near, alpha=0.08, color="gray")
    ax.text(r_near / 2, 0.95, "near-field", transform=ax.get_xaxis_transform(),
            ha="center", va="top", fontsize=6.8, color="gray")
    ax.set_xlim(0, 200)
    ax.set_xlabel(r"Distance $r$ from center (km)")
    ax.set_ylabel(r"$\delta(r,\,t_{\mathrm{peak}})$")
    ax.legend(fontsize=7.4, frameon=False, loc="upper right")
    ax.tick_params(labelsize=8)
    despine(ax)


def panel_b(ax, synth):
    """受控合成实验：提供因果链证据。"""
    if synth is None:
        ax.text(0.5, 0.5, "Missing analytic_predictions_synthetic.csv",
                transform=ax.transAxes, ha="center", va="center",
                fontsize=8, color="gray")
        despine(ax)
        return

    x = synth["delta_near"].abs().values
    y = synth["alpha_predicted"].values
    classes = synth["profile_class"].values

    for xi, yi, cls in zip(x, y, classes):
        ax.scatter(
            xi, yi,
            color=SYNTH_CLASS_COLOR.get(cls, "gray"),
            s=55, edgecolors="white", linewidths=0.5, zorder=3,
        )

    ax.set_xlabel(r"$|\delta_{\mathrm{near}}|$ (synthetic)")
    ax.set_ylabel(r"$\alpha_{\mathrm{pred}}$")

    handles = []
    for name in ["EVAC", "INFL", "MIXED"]:
        handles.append(plt.Line2D(
            [0], [0], marker="o", color="w",
            markerfacecolor=SYNTH_CLASS_COLOR[name], markeredgecolor="none",
            markersize=6, label=name,
        ))
    ax.legend(handles=handles, fontsize=7.0, frameon=False, loc="lower right")
    ax.tick_params(labelsize=8)
    despine(ax)


def _parse_note_ci(note: str):
    if not isinstance(note, str) or "95%CI=[" not in note:
        return np.nan, np.nan
    try:
        ci_str = note.split("95%CI=[", 1)[1].split("]", 1)[0]
        lo, hi = ci_str.split(",")
        return float(lo), float(hi)
    except Exception:
        return np.nan, np.nan


def panel_c(ax, cf, boot):
    """反事实必要性证据：baseline 保留信号，反事实削弱/消失。"""
    if cf is None:
        ax.text(0.5, 0.5, "Missing counterfactual_results.csv",
                transform=ax.transAxes, ha="center", va="center",
                fontsize=8, color="gray")
        despine(ax)
        return

    plot_items = [
        ("observed_empirical", "Observed"),
        ("pde_predicted", "PDE baseline"),
        ("counterfactual_shuffle_profiles", "Shuffle"),
        ("counterfactual_no_diffusion_Ds0", "No diffusion"),
        ("counterfactual_uniform_profile_only_c0", "Uniform profile"),
    ]
    ys = np.arange(len(plot_items))[::-1]

    boot_ci = (np.nan, np.nan)
    if boot is not None and "rho_alpha_pred_vs_delta_near" in boot.columns:
        vals = boot["rho_alpha_pred_vs_delta_near"].dropna().values
        if len(vals) > 10:
            boot_ci = np.percentile(vals, [2.5, 97.5])

    for idx, (scenario, label) in enumerate(plot_items):
        row = cf[cf["scenario"] == scenario]
        if row.empty:
            continue
        rho = float(row["rho"].iloc[0])
        yi = ys[idx]

        if scenario == "observed_empirical":
            ax.scatter(rho, yi, color=OKABE_ITO["blue"], s=70, marker="D",
                       edgecolors="white", linewidths=0.5, zorder=4)
        elif scenario == "pde_predicted":
            if np.isfinite(boot_ci[0]) and np.isfinite(boot_ci[1]):
                ax.errorbar(
                    rho, yi,
                    xerr=[[rho - boot_ci[0]], [boot_ci[1] - rho]],
                    fmt="o", ms=7, color=OKABE_ITO["sky_blue"],
                    capsize=3, elinewidth=1.2, zorder=4,
                )
            else:
                ax.scatter(rho, yi, color=OKABE_ITO["sky_blue"], s=55, zorder=4)
        elif scenario == "counterfactual_shuffle_profiles":
            note = row["note"].iloc[0] if "note" in row.columns else ""
            ci_lo, ci_hi = _parse_note_ci(note)
            if np.isfinite(ci_lo) and np.isfinite(ci_hi):
                ax.errorbar(
                    rho, yi,
                    xerr=[[rho - ci_lo], [ci_hi - rho]],
                    fmt="o", ms=7, color=OKABE_ITO["gray"],
                    capsize=3, elinewidth=1.2, zorder=4,
                )
            else:
                ax.scatter(rho, yi, color=OKABE_ITO["gray"], s=55, zorder=4)
        else:
            ax.scatter(rho, yi, color=OKABE_ITO["gray"], s=55, marker="s",
                       edgecolors="white", linewidths=0.4, zorder=4)

    ax.axvline(0, color="black", lw=0.8, ls="--", alpha=0.5)
    ax.set_yticks(ys)
    ax.set_yticklabels([v for _, v in plot_items], fontsize=7.3)
    ax.set_xlabel(r"Effect size ($\rho$)")
    ax.set_xlim(-0.85, 0.55)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", labelsize=8)
    despine(ax)
    ax.spines["left"].set_visible(False)


def panel_d(ax, sel, jack, mix):
    """跨尺度一致性：统一 forest 语言，而不是 -log10(p) 柱图。"""
    rho, p_event = spearmanr(
        sel["near_delta_peak_windows_mean"].values,
        sel["alpha"].values,
    )
    ci_event = [np.nan, np.nan]
    if jack is not None and "spearman_rho" in jack.columns:
        vals = jack["spearman_rho"].dropna().values
        if len(vals) > 4:
            ci_event = np.percentile(vals, [2.5, 97.5])

    beta, p_sub, ci_sub = np.nan, np.nan, [np.nan, np.nan]
    if mix is not None:
        row = mix[mix["predictor"] == "delta_peak_unit"]
        if not row.empty:
            beta = float(row["coef"].iloc[0])
            p_sub = float(row["p"].iloc[0])
            ci_sub = [float(row["ci_low"].iloc[0]), float(row["ci_high"].iloc[0])]

    labels = [
        "Event-level",
        "Geo-unit level",
    ]
    y = np.array([1, 0])
    x = np.array([rho, beta])
    lo = np.array([ci_event[0], ci_sub[0]])
    hi = np.array([ci_event[1], ci_sub[1]])
    colors = [OKABE_ITO["blue"], OKABE_ITO["gray"] if (np.isnan(p_sub) or p_sub >= 0.05) else OKABE_ITO["blue"]]

    for i in range(2):
        if np.isfinite(lo[i]) and np.isfinite(hi[i]):
            ax.errorbar(
                x[i], y[i],
                xerr=[[x[i] - lo[i]], [hi[i] - x[i]]],
                fmt="o", ms=7, color=colors[i], capsize=3, elinewidth=1.3, zorder=3,
            )
        else:
            ax.scatter(x[i], y[i], s=55, color=colors[i], zorder=3)

    ax.axvline(0, color="black", lw=0.8, ls="--", alpha=0.5)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8.2)
    ax.set_xlabel("Effect size (estimate ± 95% CI)")
    ax.set_xlim(-0.82, 0.32)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", labelsize=8.6)
    ax.annotate(
        fr"$\rho={rho:.2f}$, $p={p_event:.3f}$",
        (x[0], y[0]),
        xytext=(10, -6),
        textcoords="offset points",
        fontsize=8.0,
        color=OKABE_ITO["blue"],
        va="center",
        ha="left",
    )
    if np.isfinite(p_sub):
        ax.annotate(
            fr"$\beta={beta:.2f}$, $p={p_sub:.3f}$",
            (x[1], y[1]),
            xytext=(-10, 8),
            textcoords="offset points",
            fontsize=8.0,
            color=colors[1],
            va="center",
            ha="right",
        )
    despine(ax)
    ax.spines["left"].set_visible(False)


def main():
    sel, jack, synth, cf, boot, prof, mix = load_data()

    with paper_style():
        fig = plt.figure(figsize=(7.35, 5.45))
        gs = gridspec.GridSpec(
            2, 2,
            figure=fig,
            hspace=0.56, wspace=0.58,
            left=0.12, right=0.98,
            top=0.94, bottom=0.12,
        )
        ax_a = fig.add_subplot(gs[0, 0])
        ax_b = fig.add_subplot(gs[0, 1])
        ax_c = fig.add_subplot(gs[1, 0])
        ax_d = fig.add_subplot(gs[1, 1])

        panel_a(ax_a, prof, sel)
        panel_b(ax_b, synth)
        panel_c(ax_c, cf, boot)
        panel_d(ax_d, sel, jack, mix)

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
