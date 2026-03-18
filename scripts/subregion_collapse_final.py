"""Route A final: Master curve power-law fit + earthquake-excluded collapse.

Focused analysis to produce the publication-ready summary numbers.
"""
import argparse
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats as sp_stats
from scipy.optimize import curve_fit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR = (
    ROOT / "outputs/cross_disaster_comparison"
    / "geo_unit_scale_unified_h8_mtw4_mpp3_relaxed_20260225_141630"
    / "tables"
)
DEFAULT_OUT_DIR = ROOT / "outputs/cross_disaster_comparison/subregion_collapse"

RUN_DIR = DEFAULT_RUN_DIR
TS_CSV = RUN_DIR / "geo_unit_timeseries.csv"
FITS_CSV = RUN_DIR / "geo_unit_fits.csv"
OUT_DIR = DEFAULT_OUT_DIR
OUT_DIR.mkdir(parents=True, exist_ok=True)

MIN_NMONO = 4
MIN_R2 = 0.5
MIN_TAU_POINTS = 3


def load_data(exclude_earthquake=False):
    ts = pd.read_csv(TS_CSV)
    fits = pd.read_csv(FITS_CSV)
    fits_clean = fits[(fits["n_mono"] >= MIN_NMONO) & (fits["r2_unit"] >= MIN_R2)].copy()
    merged = ts.merge(
        fits_clean[["slug", "geo_unit", "alpha_unit", "D_peak_unit", "t_peak_h",
                     "r2_unit", "n_mono"]],
        on=["slug", "geo_unit"], how="inner",
    )
    if exclude_earthquake:
        merged = merged[merged["event_type"] != "earthquake"]
    merged["tau"] = merged["hours_since_t0"] - merged["t_peak_h"]
    decay = merged[merged["tau"] > 0].copy()
    decay["D_norm"] = decay["D"] / decay["D_peak_unit"]
    counts = decay.groupby(["slug", "geo_unit"]).size()
    valid = counts[counts >= MIN_TAU_POINTS].index
    decay = decay.set_index(["slug", "geo_unit"]).loc[valid].reset_index()
    return decay


def compute_t_half(decay):
    records = []
    for (slug, gu), g in decay.groupby(["slug", "geo_unit"]):
        g = g.sort_values("tau")
        dn = g["D_norm"].values
        tau = g["tau"].values
        below = np.where(dn <= 0.5)[0]
        if len(below) > 0:
            idx = below[0]
            if idx > 0:
                t_half = np.interp(0.5, [dn[idx], dn[idx - 1]], [tau[idx], tau[idx - 1]])
            else:
                t_half = tau[idx]
        else:
            alpha = g["alpha_unit"].iloc[0]
            t_half = tau[0] * (dn[0] / 0.5) ** (1.0 / alpha) if alpha > 0 else tau[-1] * 2
        records.append({"slug": slug, "geo_unit": gu, "t_half": max(t_half, 1.0)})
    return pd.DataFrame(records)


def collapse_quality(x_vals, y_vals, n_bins=30):
    sigma_global = np.var(y_vals)
    if sigma_global < 1e-15:
        return 1.0
    bins = np.linspace(np.nanpercentile(x_vals, 2), np.nanpercentile(x_vals, 98), n_bins + 1)
    bin_idx = np.digitize(x_vals, bins)
    variances = []
    for b in range(1, n_bins + 1):
        mask = bin_idx == b
        if mask.sum() > 3:
            variances.append(np.var(y_vals[mask]))
    if not variances:
        return 0.0
    return float(1.0 - np.mean(variances) / sigma_global)


def power_law_model(x, beta, C):
    """D_norm = C * (tau/t_half)^(-beta)"""
    return C * np.power(x, -beta)


def run():
    # ── Two analyses: all events vs excl. earthquake ───────────────────
    for label, excl_eq in [("all_events", False), ("excl_earthquake", True)]:
        print(f"\n{'='*60}")
        print(f"Analysis: {label}")
        print(f"{'='*60}")

        decay = load_data(exclude_earthquake=excl_eq)
        t_half_df = compute_t_half(decay)
        decay = decay.merge(t_half_df, on=["slug", "geo_unit"], how="left")
        decay["tau_scaled"] = decay["tau"] / decay["t_half"]

        n_units = decay[["slug", "geo_unit"]].drop_duplicates().shape[0]
        n_events = decay["slug"].nunique()
        print(f"  Units: {n_units}, Events: {n_events}, Obs: {len(decay)}")

        # Collapse Q
        q_s2 = collapse_quality(decay["tau_scaled"].values, decay["D_norm"].values)
        print(f"  Q(S2 global) = {q_s2:.4f}")

        # Per-event mean
        per_event_q = []
        for slug, g in decay.groupby("slug"):
            if g[["geo_unit"]].drop_duplicates().shape[0] < 5:
                continue
            g_s = g.copy()
            g_s["tau_s2"] = g_s["tau"] / g_s["t_half"]
            q2 = collapse_quality(g_s["tau_s2"].values, g_s["D_norm"].values)
            per_event_q.append(q2)
        print(f"  Q(S2 within-event mean) = {np.mean(per_event_q):.4f}")

        # ── Master curve binning ──────────────────────────────────────
        tau_s = decay["tau_scaled"].values
        dn = decay["D_norm"].values
        # log-space bins for better coverage at long times
        bins_log = np.logspace(np.log10(0.05), np.log10(15), 40)
        bin_centers, medians, q25, q75 = [], [], [], []
        for i in range(len(bins_log) - 1):
            mask = (tau_s >= bins_log[i]) & (tau_s < bins_log[i + 1])
            vals = dn[mask]
            if len(vals) >= 10:
                bin_centers.append(np.sqrt(bins_log[i] * bins_log[i + 1]))
                medians.append(np.median(vals))
                q25.append(np.percentile(vals, 25))
                q75.append(np.percentile(vals, 75))

        bc = np.array(bin_centers)
        md = np.array(medians)

        # fit power law to master curve median
        try:
            popt, pcov = curve_fit(power_law_model, bc, md,
                                   p0=[0.5, 0.5], bounds=([0, 0], [5, 5]))
            beta_master, C_master = popt
            y_pred = power_law_model(bc, *popt)
            ss_res = np.sum((md - y_pred) ** 2)
            ss_tot = np.sum((md - np.mean(md)) ** 2)
            r2_master = 1 - ss_res / ss_tot
            print(f"  Master curve power law: β = {beta_master:.4f}, C = {C_master:.4f}, R² = {r2_master:.4f}")
        except Exception as e:
            beta_master, C_master, r2_master = np.nan, np.nan, np.nan
            print(f"  Master curve fit failed: {e}")

        # ── alpha distribution summary ─────────────────────────────────
        alphas = decay.drop_duplicates(["slug", "geo_unit"])["alpha_unit"]
        print(f"  Alpha: median={alphas.median():.3f}, IQR=[{alphas.quantile(0.25):.3f}, {alphas.quantile(0.75):.3f}]")

        # ── R² distribution ────────────────────────────────────────────
        fits = pd.read_csv(FITS_CSV)
        if excl_eq:
            fits = fits.merge(
                pd.read_csv(TS_CSV)[["slug", "event_type"]].drop_duplicates(),
                on="slug", how="left",
            )
            fits = fits[fits["event_type"] != "earthquake"]
        fits_f = fits[fits["n_mono"] >= MIN_NMONO]
        pct_good = (fits_f["r2_unit"] >= 0.7).mean()
        pct_decent = (fits_f["r2_unit"] >= 0.5).mean()
        print(f"  Power-law R² ≥ 0.7: {pct_good:.1%}")
        print(f"  Power-law R² ≥ 0.5: {pct_decent:.1%}")

        # ── Publication figure (excl_earthquake only) ──────────────────
        if excl_eq:
            _plot_final(decay, bc, md, np.array(q25), np.array(q75),
                        beta_master, C_master, r2_master, n_units, n_events,
                        q_s2, per_event_q)

    # ── Save final summary ─────────────────────────────────────────────
    summary = pd.DataFrame([{
        "scope": "excl_earthquake",
        "n_units": n_units,
        "n_events": n_events,
        "Q_S2_global": q_s2,
        "Q_S2_within_mean": np.mean(per_event_q),
        "beta_master": beta_master,
        "C_master": C_master,
        "r2_master": r2_master,
        "alpha_median": alphas.median(),
        "alpha_IQR_low": alphas.quantile(0.25),
        "alpha_IQR_high": alphas.quantile(0.75),
        "pct_r2_ge_07": pct_good,
        "pct_r2_ge_05": pct_decent,
    }])
    summary.to_csv(OUT_DIR / "collapse_final_summary.csv", index=False)
    print(f"\nFinal summary saved.")


def _plot_final(decay, bc, md, q25, q75,
                beta_master, C_master, r2_master,
                n_units, n_events, q_global, per_event_q):
    """Three-panel publication figure."""
    cmap = plt.cm.tab20
    slugs = sorted(decay["slug"].unique())
    color_map = {s: cmap(i / max(len(slugs), 1)) for i, s in enumerate(slugs)}

    fig, axes = plt.subplots(1, 3, figsize=(17, 5.5))

    # ── Panel A: D_norm vs tau/t_half with master curve ────────────────
    ax = axes[0]
    for slug in slugs:
        g = decay[decay["slug"] == slug]
        for _, gg in g.groupby("geo_unit"):
            gg = gg.sort_values("tau_scaled")
            ax.plot(gg["tau_scaled"], gg["D_norm"], alpha=0.04, lw=0.3,
                    color=color_map[slug])
    ax.plot(bc, md, "k-", lw=2.5, zorder=5, label="Median")
    ax.fill_between(bc, q25, q75, alpha=0.3, color="gray", zorder=4, label="IQR")
    # power-law fit
    x_fit = np.linspace(bc.min(), bc.max(), 200)
    ax.plot(x_fit, power_law_model(x_fit, beta_master, C_master),
            "r--", lw=2, zorder=6,
            label=f"Power law: β={beta_master:.2f}, R²={r2_master:.2f}")
    ax.set_xlabel("τ / t_half", fontsize=12)
    ax.set_ylabel("D / D_peak", fontsize=12)
    ax.set_title(f"(a) Data collapse: {n_units} subregions, {n_events} events\n"
                 f"Q = {q_global:.3f}", fontsize=11)
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 1.5)
    ax.legend(fontsize=8, loc="upper right")

    # ── Panel B: Log-log master curve ──────────────────────────────────
    ax = axes[1]
    for slug in slugs:
        g = decay[decay["slug"] == slug]
        mask = (g["tau_scaled"] > 0) & (g["D_norm"] > 0)
        g = g[mask]
        for _, gg in g.groupby("geo_unit"):
            gg = gg.sort_values("tau_scaled")
            ax.plot(np.log10(gg["tau_scaled"]), np.log10(gg["D_norm"]),
                    alpha=0.04, lw=0.3, color=color_map[slug])
    ax.plot(np.log10(bc), np.log10(md), "k-", lw=2.5, zorder=5)
    ax.plot(np.log10(bc), np.log10(q25), "k:", lw=1, zorder=4, alpha=0.5)
    ax.plot(np.log10(bc), np.log10(q75), "k:", lw=1, zorder=4, alpha=0.5)
    # fit line
    ax.plot(np.log10(x_fit), np.log10(power_law_model(x_fit, beta_master, C_master)),
            "r--", lw=2, zorder=6,
            label=f"Slope = −{beta_master:.2f}")
    ax.set_xlabel("log₁₀(τ / t_half)", fontsize=12)
    ax.set_ylabel("log₁₀(D / D_peak)", fontsize=12)
    ax.set_title("(b) Log-log: power law verification", fontsize=11)
    ax.legend(fontsize=9)
    ax.set_xlim(-1.5, 1.2)
    ax.set_ylim(-2.0, 0.5)

    # ── Panel C: per-event alpha boxplot ───────────────────────────────
    ax = axes[2]
    unit_df = decay.drop_duplicates(["slug", "geo_unit"])
    event_order = (unit_df.groupby("slug")["alpha_unit"].median()
                   .sort_values().index.tolist())
    data_for_bp = [unit_df[unit_df["slug"] == s]["alpha_unit"].values for s in event_order]
    bp = ax.boxplot(data_for_bp, vert=True, patch_artist=True, widths=0.6,
                    showfliers=False)
    for patch, slug in zip(bp["boxes"], event_order):
        patch.set_facecolor(color_map[slug])
        patch.set_alpha(0.6)
    ax.set_xticklabels([s[:15] for s in event_order], rotation=90, fontsize=6)
    ax.axhline(unit_df["alpha_unit"].median(), color="red", ls="--", lw=1.5,
               label=f"Global median α = {unit_df['alpha_unit'].median():.2f}")
    ax.set_ylabel("α (power-law exponent)", fontsize=12)
    ax.set_title("(c) α distribution: universal form, diverse rates", fontsize=11)
    ax.legend(fontsize=8)
    ax.set_ylim(-0.5, 4.0)

    # event legend
    handles = [plt.Line2D([0], [0], color=color_map[s], lw=3, label=s[:35])
               for s in event_order]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=6,
               frameon=False, bbox_to_anchor=(0.5, -0.08))

    fig.tight_layout(rect=[0, 0.05, 1, 1])
    fig.savefig(OUT_DIR / "data_collapse_final.png", dpi=250, bbox_inches="tight")
    plt.close(fig)
    print("Final figure saved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Subregion data collapse (final)")
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR), help="geo_unit tables 目录")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    RUN_DIR = Path(args.run_dir)
    TS_CSV = RUN_DIR / "geo_unit_timeseries.csv"
    FITS_CSV = RUN_DIR / "geo_unit_fits.csv"
    OUT_DIR = Path(args.out_dir)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    warnings.filterwarnings("ignore")
    run()
