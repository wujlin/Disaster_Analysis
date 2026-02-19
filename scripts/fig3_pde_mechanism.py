"""
Figure 3: PDE Diffusion-Relaxation Mechanism  (2 × 3 layout)

Row 1: WHY shape predicts recovery
  (a) Modal energy spectrum — EVAC vs INFL bar chart
  (b) Spectral energy decay — E_n(t) mode-selective damping
  (c) α_pred vs δ_near scatter + bootstrap CI  [existing]

Row 2: VALIDATION and EVIDENCE
  (d) D_pred(t) vs D_emp(t) — trajectory comparison
  (e) Counterfactual dot plot                  [existing]
  (f) Parameter landscape — ρ vs (k, D_s) heatmap

All text in figure is minimised; details go to caption.
"""
import sys, os
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
from matplotlib.ticker import LogLocator, LogFormatter
from scipy.special import j0
from scipy.stats import spearmanr

from src.disaster.spatial_diffusion import predict_D_from_profile
from src.disaster.plot_style import (
    paper_style, OKABE_ITO, add_panel_label, save_figure, despine,
)

# ── paths ──────────────────────────────────────────────────────────────────
ROOT     = "outputs/cross_disaster_comparison"
SDR      = f"{ROOT}/spatial_diffusion_results/tables"
FLAGS_CSV     = f"{ROOT}/Dt_decay/tables/Dt_routeB_sample_flags.csv"
DT_CSV        = f"{ROOT}/Dt_decay/tables/Dt_all_events.csv"
COEFS_CSV     = f"{SDR}/bessel_coefficients.csv"
PRED_CSV      = f"{SDR}/pde_alpha_predictions.csv"
BOOTSTRAP_CSV = f"{SDR}/simulation_bootstrap.csv"
CF_CSV        = f"{SDR}/counterfactual_results.csv"
GRID_CSV      = f"{SDR}/pde_param_grid.csv"
OUT_DIR  = "Essay/figures"
OUT_PDF  = f"{OUT_DIR}/fig3_pde_mechanism.pdf"
OUT_PNG  = f"{OUT_DIR}/fig3_pde_mechanism.png"

# ── constants ──────────────────────────────────────────────────────────────
K_OPT  = 0.004175   # h⁻¹  (global optimum used in paper)
DS_OPT = 0.303920   # km²/h
R_MAX  = 200.0      # km
N_MODES = 10
R2_THRESHOLD = 0.75

DTYPE_COLOR = {
    "earthquake": OKABE_ITO["vermillion"],
    "hurricane":  OKABE_ITO["blue"],
    "typhoon":    OKABE_ITO["blue"],
    "flood":      OKABE_ITO["bluish_green"],
    "wildfire":   OKABE_ITO["orange"],
}
# Single-hue gradient for mode index (dark = low-order, light = high-order)
N_SHOW = 5  # modes to show in spectral decay panel
MODE_COLORS = plt.cm.Blues_r(np.linspace(0.15, 0.85, N_SHOW))


# ── helpers ────────────────────────────────────────────────────────────────

def _load_data():
    flags   = pd.read_csv(FLAGS_CSV)
    flags16 = flags[flags["route_b_selected"] == True].copy()
    dt_all  = pd.read_csv(DT_CSV)
    coefs   = pd.read_csv(COEFS_CSV)
    pred    = pd.read_csv(PRED_CSV)
    boot    = pd.read_csv(BOOTSTRAP_CSV)
    cf      = pd.read_csv(CF_CSV)
    grid    = pd.read_csv(GRID_CSV)
    return flags16, dt_all, coefs, pred, boot, cf, grid


def _mode_lambdas(roots):
    """Decay rate λ_n = k + D_s (μ_n/R)² for each mode."""
    return K_OPT + DS_OPT * (np.asarray(roots) / R_MAX) ** 2


def _event_coefs(coefs_df, short_name):
    row   = coefs_df[coefs_df["short_name"] == short_name].iloc[0]
    c_n   = np.array([row[f"c_{n}"] for n in range(N_MODES)])
    roots = np.array([row[f"root_{n}"] for n in range(N_MODES)])
    return c_n, roots


def _D_emp_post_peak(dt_df, flags_df, short_name, t_max=192):
    """Return (t_prime, D_norm) arrays; normalised so D(t'=24) = 1.
    Duplicate t_prime values are averaged to handle multi-tile aggregations."""
    row_f   = flags_df[flags_df["short_name"] == short_name].iloc[0]
    t_peak  = float(row_f["t_peak_hours"])
    ev      = dt_df[dt_df["short_name"] == short_name].copy()
    ev["t_prime"] = ev["hours_since_quake"] - t_peak
    post    = (ev[(ev["t_prime"] >= 24) & (ev["t_prime"] <= t_max)]
               .groupby("t_prime", as_index=False)["D"].mean()
               .sort_values("t_prime"))
    if len(post) < 2:
        return None, None
    t_arr = post["t_prime"].values
    D_arr = post["D"].values
    norm  = float(np.interp(24.0, t_arr, D_arr))
    if norm < 1e-12:
        return None, None
    return t_arr, D_arr / norm


def _D_pred_normalised(c_n, roots, t_arr, norm_at=24.0):
    """Compute D_pred(t) from Bessel coefficients; normalise at t=norm_at."""
    t_full = np.concatenate([[norm_at], t_arr])
    D_full = predict_D_from_profile(c_n, roots, K_OPT, DS_OPT, t_full, R_max=R_MAX)
    norm   = D_full[0]
    if norm < 1e-12:
        return None
    return D_full[1:] / norm


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


# ── panel functions ────────────────────────────────────────────────────────

def panel_a(ax, coefs):
    """
    Modal energy spectrum E_n / E_total for n = 0 .. 9.
    EVAC representative: beryl_qr (δ_near=-0.218, fastest predicted)
    INFL representative: spain_flood (δ_near=+0.138)
    """
    events = {
        "beryl_qr":   ("EVAC",  OKABE_ITO["blue"]),
        "spain_flood": ("INFL",  OKABE_ITO["vermillion"]),
    }
    x      = np.arange(N_MODES)
    width  = 0.38

    for k_off, (sn, (label, col)) in enumerate(events.items()):
        c_n, _ = _event_coefs(coefs, sn)
        E_n    = c_n ** 2
        E_norm = E_n / E_n.sum()
        offset = (k_off - 0.5) * width
        ax.bar(x + offset, E_norm, width=width, color=col, alpha=0.85,
               label=label, edgecolor="white", linewidth=0.4)

    ax.set_xlabel("Bessel mode $n$")
    ax.set_ylabel(r"$E_n\,/\,E_{\mathrm{total}}$")
    ax.set_xticks(x)
    ax.set_xticklabels([str(n) for n in range(N_MODES)], fontsize=7)
    ax.legend(fontsize=7, frameon=False, loc="upper right",
              handlelength=1.0, handletextpad=0.4)
    despine(ax)


def panel_b(ax, coefs):
    """
    Mode decay rate λ_n = k + D_s (μ_n/R)² vs mode index n.
    The horizontal dashed line marks k (uniform relaxation); the upward
    trend with n is the diffusion contribution that makes high-frequency
    modes decay faster.  Bar colour encodes how much more energy EVAC
    events (beryl_qr) load into each mode relative to INFL (spain_flood),
    so readers see both the rate structure and the energy loading together.
    """
    # Use representative event roots (same for all events since global R)
    row_ref  = coefs[coefs["short_name"] == "beryl_qr"].iloc[0]
    roots    = np.array([row_ref[f"root_{n}"] for n in range(N_MODES)])
    lambdas  = _mode_lambdas(roots)

    # Mode energy fraction for EVAC and INFL representative events
    c_evac, _ = _event_coefs(coefs, "beryl_qr")
    c_infl, _ = _event_coefs(coefs, "spain_flood")
    E_evac_raw = c_evac ** 2; E_evac = E_evac_raw / E_evac_raw.sum()
    E_infl_raw = c_infl ** 2; E_infl = E_infl_raw / E_infl_raw.sum()

    x  = np.arange(N_MODES)
    # Gradient colour: dark = EVAC-heavy mode, light = INFL-heavy mode
    ratio = E_evac / (E_evac + E_infl + 1e-12)  # 1 = entirely EVAC, 0 = entirely INFL
    bar_colors = plt.cm.coolwarm(ratio)

    bars = ax.bar(x, lambdas * 1e3, color=bar_colors, edgecolor="white",
                  linewidth=0.4, zorder=3)

    # Mark k (uniform decay)
    ax.axhline(K_OPT * 1e3, color="black", lw=1.0, ls="--", alpha=0.7,
               label=r"$k$ (uniform)")
    ax.legend(fontsize=7, frameon=False, loc="upper left")

    ax.set_xlabel("Bessel mode $n$")
    ax.set_ylabel(r"$\lambda_n\;\times10^{-3}$ (h$^{-1}$)")
    ax.set_xticks(x)
    ax.set_xticklabels([str(n) for n in range(N_MODES)], fontsize=7)
    ax.text(0.97, 0.97,
            "warm = EVAC-loaded\ncool = INFL-loaded",
            transform=ax.transAxes, ha="right", va="top",
            fontsize=6.5, color="gray", linespacing=1.4)
    despine(ax)


def panel_c(ax, flags16, pred, bootstrap):
    """α_pred vs δ_near scatter with bootstrap CI annotation."""
    merged = flags16[["slug", "disaster_type", "r2",
                       "near_delta_peak_windows_mean"]].merge(
        pred[["slug", "alpha_pred_E"]], on="slug", how="inner")

    x = merged["near_delta_peak_windows_mean"].values
    y = merged["alpha_pred_E"].values

    for _, row in merged.iterrows():
        xi    = row["near_delta_peak_windows_mean"]
        yi    = row["alpha_pred_E"]
        dtype = row["disaster_type"]
        ri2   = row["r2"]
        color = DTYPE_COLOR.get(dtype, "gray")
        fc    = color if ri2 >= R2_THRESHOLD else "none"
        ax.scatter(xi, yi, s=40, marker="o",
                   facecolors=fc, edgecolors=color,
                   linewidths=1.0,
                   alpha=0.95 if ri2 >= R2_THRESHOLD else 0.5, zorder=3)

    rho, pval = spearmanr(x, y)
    boot_vals  = bootstrap[bootstrap["mode"] == "E"][
        "rho_alpha_pred_vs_delta_near"].values
    ci_lo, ci_hi = np.percentile(boot_vals, [2.5, 97.5])
    ax.text(0.97, 0.97,
            fr"$\rho = {rho:.2f}$, $p = {pval:.3f}$"
            "\n"
            fr"95% CI $[{ci_lo:.2f},\,{ci_hi:.2f}]$",
            transform=ax.transAxes, ha="right", va="top", fontsize=7.5,
            linespacing=1.5)

    ax.set_xlabel(r"$\delta_{\mathrm{near}}$")
    ax.set_ylabel(r"$\alpha_{\mathrm{pred}}$")
    despine(ax)


def panel_d(ax, flags16, dt_all, coefs):
    """
    D_pred(t') vs D_emp(t') for 3 representative events on log–log axes.
    Both normalised to D(t'=24 h) = 1.

    Events span the α_pred range and are selected for monotonic D_emp:
      fast:   beryl_qr (α_pred=0.291, EVAC hurricane)
      medium: the_earthquake_across_ (α_pred=0.222, INFL earthquake, mono)
      slow:   flooding_in_central_an (α_pred=0.218, INFL flood)
    """
    # (short_name, disaster_type, short_label)
    # Select events spanning α_pred range with relatively clean trajectories
    event_specs = [
        ("beryl_qr",              "hurricane", "beryl_qr (EVAC)"),
        ("spain_flood",            "flood",     "spain flood (INFL)"),
        ("flooding_in_central_an", "flood",     "flooding_eu (INFL)"),
    ]

    for sn, dtype, label in event_specs:
        col = DTYPE_COLOR.get(dtype, "gray")
        c_n, roots = _event_coefs(coefs, sn)

        t_emp, D_emp = _D_emp_post_peak(dt_all, flags16, sn)
        if t_emp is None:
            continue

        D_pred_norm = _D_pred_normalised(c_n, roots, t_emp)
        if D_pred_norm is None:
            continue

        # Filter non-positive for log scale
        mask = (t_emp > 0) & (D_emp > 0) & (D_pred_norm > 0)
        t_   = t_emp[mask]
        De_  = D_emp[mask]
        Dp_  = D_pred_norm[mask]

        ax.plot(t_, De_, color=col, lw=1.8, alpha=0.92, zorder=3)
        ax.plot(t_, Dp_, color=col, lw=1.2, ls="--", alpha=0.65, zorder=2)

    ax.set_xscale("log")
    ax.set_yscale("log")
    # Clean tick marks for t' in [24, 192] hours
    ax.set_xlim(20, 210)
    ax.xaxis.set_major_locator(LogLocator(base=10, numticks=4))
    ax.xaxis.set_major_formatter(LogFormatter(base=10, labelOnlyBase=True))
    ax.set_xticks([24, 48, 96, 192])
    ax.set_xticklabels(["24", "48", "96", "192"], fontsize=7)
    ax.set_xlabel(r"$t'$ (h since peak)")
    ax.set_ylabel(r"$D(t')\,/\,D(24\,\mathrm{h})$")

    # Compact legend: line style only
    emp_h  = Line2D([0],[0], color="k", lw=1.8, label="Empirical")
    pred_h = Line2D([0],[0], color="k", lw=1.2, ls="--", label="PDE pred.")
    ax.legend(handles=[emp_h, pred_h], fontsize=7, frameon=False,
              loc="lower left", handlelength=1.4)
    despine(ax)


def panel_e(ax, cf, bootstrap):
    """Counterfactual dot plot (unchanged from previous version)."""
    scenarios = [
        ("pde_predicted",                          "Baseline PDE",           OKABE_ITO["blue"]),
        ("counterfactual_no_diffusion_Ds0",        r"No diffusion ($D_s=0$)", "#888888"),
        ("counterfactual_uniform_profile_only_c0", r"$c_0$-only",            "#888888"),
        ("counterfactual_shuffle_profiles",         "Shuffled profiles",      "#888888"),
    ]
    y_pos = np.arange(len(scenarios))[::-1]

    boot_vals   = bootstrap[bootstrap["mode"] == "E"][
        "rho_alpha_pred_vs_delta_near"].values
    baseline_ci = np.percentile(boot_vals, [2.5, 97.5])

    for i, (sc_key, label, color) in enumerate(scenarios):
        row = cf[cf["scenario"] == sc_key]
        if row.empty:
            continue
        rho_val = float(row["rho"].iloc[0])
        yi = y_pos[i]

        is_det = sc_key in ("counterfactual_no_diffusion_Ds0",
                             "counterfactual_uniform_profile_only_c0")
        if is_det:
            ax.scatter(rho_val, yi, color=color, s=50, marker="D",
                       edgecolors="white", linewidths=0.4, zorder=4,
                       clip_on=False)
        elif sc_key == "pde_predicted":
            ax.errorbar(rho_val, yi,
                        xerr=[[rho_val - baseline_ci[0]],
                              [baseline_ci[1] - rho_val]],
                        fmt="o", color=color, ms=6,
                        capsize=3, capthick=1.0, elinewidth=1.2, zorder=4)
        elif sc_key == "counterfactual_shuffle_profiles":
            note = row["note"].iloc[0] if "note" in row.columns else ""
            if "95%CI=[" in str(note):
                ci_str = note.split("95%CI=[")[1].split("]")[0]
                ci_lo, ci_hi = map(float, ci_str.split(","))
                ax.errorbar(rho_val, yi,
                            xerr=[[rho_val - ci_lo], [ci_hi - rho_val]],
                            fmt="o", color=color, ms=6,
                            capsize=3, capthick=1.0, elinewidth=1.2, zorder=4)
            else:
                ax.scatter(rho_val, yi, color=color, s=50, marker="o",
                           edgecolors="white", linewidths=0.4, zorder=4)

    ax.axvline(0, color="black", lw=0.8, ls="--", alpha=0.6)
    ax.set_yticks(y_pos)
    ax.set_yticklabels([s[1] for s in scenarios], fontsize=7.5)
    ax.set_xlabel(r"Spearman $\rho\,(\alpha_{\mathrm{pred}},\;\delta_{\mathrm{near}})$")
    ax.set_xlim(-0.90, 0.65)
    ax.tick_params(axis="y", length=0)
    despine(ax)
    ax.spines["left"].set_visible(False)


def panel_f(ax, grid):
    """
    Parameter landscape: Spearman ρ(α_pred, α_emp) over the (k, D_s) grid.
    Colour = ρ (red = strong positive correlation).  White star = optimum.
    """
    # Pivot to 2D matrix for imshow
    k_vals  = sorted(grid["k"].unique())
    Ds_vals = sorted(grid["Ds"].unique())
    rho_mat = np.full((len(k_vals), len(Ds_vals)), np.nan)

    for _, row in grid.iterrows():
        ki  = k_vals.index(row["k"])
        Dsi = Ds_vals.index(row["Ds"])
        rho_mat[ki, Dsi] = row["spearman_rho_alpha_emp_E"]

    # Plot on log-log grid using pcolormesh
    log_k  = np.log10(k_vals)
    log_Ds = np.log10(Ds_vals)
    # Create edge arrays for pcolormesh
    dk  = (log_k[1]  - log_k[0])  / 2 if len(log_k)  > 1 else 0.1
    dDs = (log_Ds[1] - log_Ds[0]) / 2 if len(log_Ds) > 1 else 0.1
    k_edges  = np.append(log_k  - dk,  log_k[-1]  + dk)
    Ds_edges = np.append(log_Ds - dDs, log_Ds[-1] + dDs)

    Ds_grid, k_grid = np.meshgrid(Ds_edges, k_edges)
    vabs = np.nanmax(np.abs(rho_mat))
    pcm = ax.pcolormesh(Ds_grid, k_grid, rho_mat,
                        cmap="RdBu_r", vmin=-vabs, vmax=vabs,
                        rasterized=True)
    plt.colorbar(pcm, ax=ax, label=r"$\rho$", fraction=0.046, pad=0.04,
                 aspect=20)

    # Mark optimum
    ax.scatter(np.log10(DS_OPT), np.log10(K_OPT), marker="*", s=90,
               color="gold", edgecolors="black", linewidths=0.6, zorder=5)

    ax.set_xlabel(r"$\log_{10}(D_s)$")
    ax.set_ylabel(r"$\log_{10}(k)$")
    despine(ax)


# ── main ───────────────────────────────────────────────────────────────────

def main():
    flags16, dt_all, coefs, pred, boot, cf, grid = _load_data()

    with paper_style():
        fig = plt.figure(figsize=(7.2, 4.8))
        gs  = gridspec.GridSpec(
            2, 3,
            figure=fig,
            wspace=0.52, hspace=0.58,
            left=0.08, right=0.96,
            top=0.91, bottom=0.18,
        )
        ax_a = fig.add_subplot(gs[0, 0])
        ax_b = fig.add_subplot(gs[0, 1])
        ax_c = fig.add_subplot(gs[0, 2])
        ax_d = fig.add_subplot(gs[1, 0])
        ax_e = fig.add_subplot(gs[1, 1])
        ax_f = fig.add_subplot(gs[1, 2])

        panel_a(ax_a, coefs)
        panel_b(ax_b, coefs)
        panel_c(ax_c, flags16, pred, boot)
        panel_d(ax_d, flags16, dt_all, coefs)
        panel_e(ax_e, cf, boot)
        panel_f(ax_f, grid)

        for ax, lbl in zip([ax_a, ax_b, ax_c, ax_d, ax_e, ax_f],
                           "abcdef"):
            add_panel_label(ax, lbl, dy=8)

        fig.legend(handles=_shared_legend_handles(),
                   loc="lower center", bbox_to_anchor=(0.5, 0.01),
                   ncol=4, fontsize=7.5, frameon=False,
                   handlelength=1, handletextpad=0.3, columnspacing=1.2)

        os.makedirs(OUT_DIR, exist_ok=True)
        save_figure(fig, OUT_PDF)
        save_figure(fig, OUT_PNG, dpi=150)
        plt.close(fig)

    print(f"Saved: {OUT_PDF}, {OUT_PNG}")


if __name__ == "__main__":
    main()
