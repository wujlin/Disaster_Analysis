"""Route A: Data Collapse Experiment for Subregion Recovery Trajectories.

Tests whether ~2500 subregion-level D(t) decay curves collapse onto a
universal master curve under appropriate rescaling, analogous to Gao et al.'s
finding of universal spatiotemporal decay in human mobility during crises.

Strategies tested:
  S0  raw D vs hours_since_peak           (baseline, no rescaling)
  S1  D/D_peak vs hours_since_peak        (amplitude-only rescaling)
  S2  D/D_peak vs tau/t_half              (two-parameter rescaling)
  S3  D/D_peak * tau^alpha vs constant    (alpha-guided collapse)

Collapse quality metric Q:
  Q = 1 - mean(sigma_bin^2) / sigma_global^2
  Q = 0 means no improvement over global variance;
  Q = 1 means perfect collapse.

Outputs saved to:
  outputs/cross_disaster_comparison/subregion_collapse/
"""

from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats as sp_stats

# ── paths ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = (
    ROOT
    / "outputs/cross_disaster_comparison"
    / "geo_unit_scale_unified_h8_mtw4_mpp3_relaxed_20260225_141630"
    / "tables"
)
TS_CSV = RUN_DIR / "geo_unit_timeseries.csv"
FITS_CSV = RUN_DIR / "geo_unit_fits.csv"
OUT_DIR = ROOT / "outputs/cross_disaster_comparison/subregion_collapse"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── quality thresholds ─────────────────────────────────────────────────
MIN_NMONO = 4        # minimum monotone decay points for reliable alpha
MIN_R2 = 0.5         # minimum fit quality
MIN_TAU_POINTS = 3   # minimum post-peak points for a unit to be included


def load_data():
    """Load timeseries + fits, merge, and filter to decay phase."""
    ts = pd.read_csv(TS_CSV)
    fits = pd.read_csv(FITS_CSV)

    fits_clean = fits[
        (fits["n_mono"] >= MIN_NMONO) & (fits["r2_unit"] >= MIN_R2)
    ].copy()
    print(f"Fits after quality filter: {len(fits_clean)} / {len(fits)}")
    print(f"  Events: {fits_clean['slug'].nunique()}")

    merged = ts.merge(
        fits_clean[["slug", "geo_unit", "alpha_unit", "D_peak_unit", "t_peak_h",
                     "r2_unit", "n_mono"]],
        on=["slug", "geo_unit"],
        how="inner",
    )
    # keep only decay phase (after peak)
    merged["tau"] = merged["hours_since_t0"] - merged["t_peak_h"]
    decay = merged[merged["tau"] > 0].copy()
    decay["D_norm"] = decay["D"] / decay["D_peak_unit"]

    # remove units with too few decay points
    counts = decay.groupby(["slug", "geo_unit"]).size()
    valid = counts[counts >= MIN_TAU_POINTS].index
    decay = decay.set_index(["slug", "geo_unit"]).loc[valid].reset_index()
    print(f"Units with >= {MIN_TAU_POINTS} decay points: {len(valid)}")
    print(f"Total decay observations: {len(decay)}")
    return decay


def compute_t_half(decay: pd.DataFrame) -> pd.DataFrame:
    """Estimate t_half (time for D to drop to D_peak/2) per unit via interpolation."""
    records = []
    for (slug, gu), g in decay.groupby(["slug", "geo_unit"]):
        g = g.sort_values("tau")
        dn = g["D_norm"].values
        tau = g["tau"].values
        # find first crossing below 0.5
        below = np.where(dn <= 0.5)[0]
        if len(below) > 0:
            idx = below[0]
            if idx > 0:
                t_half = np.interp(0.5, [dn[idx], dn[idx - 1]], [tau[idx], tau[idx - 1]])
            else:
                t_half = tau[idx]
        else:
            # extrapolate using fitted alpha
            alpha = g["alpha_unit"].iloc[0]
            if alpha > 0:
                t_half = tau[0] * (dn[0] / 0.5) ** (1.0 / alpha)
            else:
                t_half = tau[-1] * 2  # fallback
        records.append({"slug": slug, "geo_unit": gu, "t_half": max(t_half, 1.0)})
    return pd.DataFrame(records)


def collapse_quality(x_vals, y_vals, n_bins=30):
    """Compute collapse quality Q for a set of (x, y) points.

    Q = 1 - <var_bin> / var_global.
    Higher Q = better collapse.
    """
    sigma_global = np.var(y_vals)
    if sigma_global < 1e-15:
        return 1.0
    bins = np.linspace(np.nanpercentile(x_vals, 1), np.nanpercentile(x_vals, 99), n_bins + 1)
    bin_idx = np.digitize(x_vals, bins)
    variances = []
    for b in range(1, n_bins + 1):
        mask = bin_idx == b
        if mask.sum() > 2:
            variances.append(np.var(y_vals[mask]))
    if not variances:
        return 0.0
    return float(1.0 - np.mean(variances) / sigma_global)


def fit_universal_exponent(decay: pd.DataFrame):
    """Fit a single power-law exponent to all collapsed decay curves.
    log(D_norm) = -alpha_univ * log(tau) + c
    """
    mask = (decay["tau"] > 0) & (decay["D_norm"] > 0)
    d = decay[mask]
    log_tau = np.log10(d["tau"].values)
    log_dn = np.log10(d["D_norm"].values)
    slope, intercept, r, p, se = sp_stats.linregress(log_tau, log_dn)
    return {
        "alpha_universal": -slope,
        "intercept": intercept,
        "r2": r ** 2,
        "p_value": p,
        "se": se,
        "n_points": len(d),
    }


def run_experiment():
    decay = load_data()
    t_half_df = compute_t_half(decay)
    decay = decay.merge(t_half_df, on=["slug", "geo_unit"], how="left")

    # ── S0: raw ────────────────────────────────────────────────────────
    q_s0 = collapse_quality(decay["tau"].values, decay["D"].values)

    # ── S1: amplitude rescaling only ───────────────────────────────────
    q_s1 = collapse_quality(decay["tau"].values, decay["D_norm"].values)

    # ── S2: two-parameter rescaling ────────────────────────────────────
    decay["tau_scaled"] = decay["tau"] / decay["t_half"]
    q_s2 = collapse_quality(decay["tau_scaled"].values, decay["D_norm"].values)

    # ── S3: alpha-guided collapse ──────────────────────────────────────
    mask_s3 = (decay["tau"] > 0) & (decay["D_norm"] > 0)
    d_s3 = decay[mask_s3].copy()
    d_s3["y_s3"] = np.log10(d_s3["D_norm"]) + d_s3["alpha_unit"] * np.log10(d_s3["tau"])
    q_s3 = collapse_quality(
        np.log10(d_s3["tau"].values),
        d_s3["y_s3"].values,
    )

    # ── universal exponent ─────────────────────────────────────────────
    univ = fit_universal_exponent(decay)

    # ── per-event alpha distribution ───────────────────────────────────
    alpha_stats = (
        decay.groupby("slug")["alpha_unit"]
        .agg(["mean", "std", "median", "count"])
        .reset_index()
    )
    alpha_stats = alpha_stats.drop_duplicates(subset="slug")

    # overall alpha distribution
    all_alpha = decay.drop_duplicates(subset=["slug", "geo_unit"])["alpha_unit"]

    # ── master curve: binned median + IQR in S2 space ──────────────────
    tau_s = decay["tau_scaled"].values
    dn = decay["D_norm"].values
    bins = np.linspace(np.nanpercentile(tau_s, 1), np.nanpercentile(tau_s, 95), 50)
    bin_centers = 0.5 * (bins[:-1] + bins[1:])
    medians, q25, q75, counts = [], [], [], []
    for i in range(len(bins) - 1):
        mask = (tau_s >= bins[i]) & (tau_s < bins[i + 1])
        vals = dn[mask]
        if len(vals) >= 5:
            medians.append(np.median(vals))
            q25.append(np.percentile(vals, 25))
            q75.append(np.percentile(vals, 75))
            counts.append(len(vals))
        else:
            medians.append(np.nan)
            q25.append(np.nan)
            q75.append(np.nan)
            counts.append(len(vals))

    master = pd.DataFrame({
        "tau_over_thalf": bin_centers,
        "D_norm_median": medians,
        "D_norm_q25": q25,
        "D_norm_q75": q75,
        "n_points": counts,
    })
    master.to_csv(OUT_DIR / "master_curve_S2.csv", index=False)

    # ── per-event collapse quality ─────────────────────────────────────
    event_q = []
    for slug, g in decay.groupby("slug"):
        if len(g) < 20:
            continue
        g_s = g.copy()
        q1 = collapse_quality(g_s["tau"].values, g_s["D_norm"].values)
        g_s["tau_s2"] = g_s["tau"] / g_s["t_half"]
        q2 = collapse_quality(g_s["tau_s2"].values, g_s["D_norm"].values)
        event_q.append({
            "slug": slug,
            "event_type": g["event_type"].iloc[0],
            "n_units": g[["geo_unit"]].drop_duplicates().shape[0],
            "Q_S1": q1,
            "Q_S2": q2,
            "alpha_median": g.drop_duplicates(["geo_unit"])["alpha_unit"].median(),
            "alpha_IQR": sp_stats.iqr(g.drop_duplicates(["geo_unit"])["alpha_unit"]),
        })
    event_q_df = pd.DataFrame(event_q)
    event_q_df.to_csv(OUT_DIR / "collapse_quality_by_event.csv", index=False)

    # ── by disaster type ───────────────────────────────────────────────
    type_q = []
    for etype, g in decay.groupby("event_type"):
        if len(g) < 20:
            continue
        q1 = collapse_quality(g["tau"].values, g["D_norm"].values)
        g_s = g.copy()
        g_s["tau_s2"] = g_s["tau"] / g_s["t_half"]
        q2 = collapse_quality(g_s["tau_s2"].values, g_s["D_norm"].values)
        type_q.append({
            "event_type": etype,
            "n_units": g[["slug", "geo_unit"]].drop_duplicates().shape[0],
            "Q_S1": q1,
            "Q_S2": q2,
        })
    type_q_df = pd.DataFrame(type_q)
    type_q_df.to_csv(OUT_DIR / "collapse_quality_by_type.csv", index=False)

    # ── summary table ──────────────────────────────────────────────────
    summary = pd.DataFrame([
        {"strategy": "S0_raw", "Q": q_s0, "description": "D vs tau (no rescaling)"},
        {"strategy": "S1_amp", "Q": q_s1, "description": "D/D_peak vs tau"},
        {"strategy": "S2_two_param", "Q": q_s2, "description": "D/D_peak vs tau/t_half"},
        {"strategy": "S3_alpha_guided", "Q": q_s3, "description": "log(D/D_peak)+alpha*log(tau) vs log(tau)"},
    ])
    summary.to_csv(OUT_DIR / "collapse_quality_summary.csv", index=False)

    # ── print results ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("DATA COLLAPSE QUALITY (Q)")
    print("=" * 60)
    for _, row in summary.iterrows():
        print(f"  {row['strategy']:20s}  Q = {row['Q']:.4f}  ({row['description']})")
    print()

    print(f"Universal exponent: alpha = {univ['alpha_universal']:.4f} "
          f"(R² = {univ['r2']:.4f}, n = {univ['n_points']})")
    print()

    print("Alpha distribution across units:")
    print(f"  mean = {all_alpha.mean():.4f}, std = {all_alpha.std():.4f}, "
          f"median = {all_alpha.median():.4f}")
    print(f"  IQR = [{all_alpha.quantile(0.25):.4f}, {all_alpha.quantile(0.75):.4f}]")
    print(f"  range = [{all_alpha.min():.4f}, {all_alpha.max():.4f}]")
    print()

    print("Per-event collapse quality:")
    print(event_q_df[["slug", "event_type", "n_units", "Q_S1", "Q_S2",
                       "alpha_median"]].to_string(index=False))
    print()

    print("Per-type collapse quality:")
    print(type_q_df.to_string(index=False))

    # ── figures ────────────────────────────────────────────────────────
    _plot_collapse(decay, master, event_q_df, univ)

    # save universal exponent
    pd.DataFrame([univ]).to_csv(OUT_DIR / "universal_exponent.csv", index=False)
    alpha_stats.to_csv(OUT_DIR / "alpha_distribution_by_event.csv", index=False)

    print(f"\nAll outputs saved to {OUT_DIR}")


def _plot_collapse(decay, master, event_q_df, univ):
    """Generate publication-quality collapse plots."""
    cmap = plt.cm.tab20
    slugs = sorted(decay["slug"].unique())
    color_map = {s: cmap(i / max(len(slugs), 1)) for i, s in enumerate(slugs)}

    fig, axes = plt.subplots(2, 2, figsize=(14, 11))

    # ── Panel A: Raw D vs tau (S0) ─────────────────────────────────────
    ax = axes[0, 0]
    for slug, g in decay.groupby("slug"):
        for gu, gg in g.groupby("geo_unit"):
            gg = gg.sort_values("tau")
            ax.plot(gg["tau"], gg["D"], alpha=0.05, lw=0.3, color=color_map[slug])
    ax.set_xlabel("τ = hours since peak")
    ax.set_ylabel("D(t)")
    ax.set_title("(a) Raw: no rescaling")
    ax.set_xlim(0, 800)

    # ── Panel B: D_norm vs tau (S1) ────────────────────────────────────
    ax = axes[0, 1]
    for slug, g in decay.groupby("slug"):
        for gu, gg in g.groupby("geo_unit"):
            gg = gg.sort_values("tau")
            ax.plot(gg["tau"], gg["D_norm"], alpha=0.05, lw=0.3, color=color_map[slug])
    ax.set_xlabel("τ = hours since peak")
    ax.set_ylabel("D / D_peak")
    ax.set_title("(b) Amplitude-normalized")
    ax.set_xlim(0, 800)
    ax.set_ylim(0, 2.5)

    # ── Panel C: D_norm vs tau/t_half (S2) — master curve ──────────────
    ax = axes[1, 0]
    for slug, g in decay.groupby("slug"):
        for gu, gg in g.groupby("geo_unit"):
            gg = gg.sort_values("tau_scaled")
            ax.plot(gg["tau_scaled"], gg["D_norm"], alpha=0.05, lw=0.3,
                    color=color_map[slug])
    valid_m = master.dropna(subset=["D_norm_median"])
    ax.plot(valid_m["tau_over_thalf"], valid_m["D_norm_median"],
            "k-", lw=2.5, label="Median (master curve)")
    ax.fill_between(valid_m["tau_over_thalf"], valid_m["D_norm_q25"],
                     valid_m["D_norm_q75"], alpha=0.3, color="gray", label="IQR")
    ax.set_xlabel("τ / t_half")
    ax.set_ylabel("D / D_peak")
    ax.set_title("(c) Two-parameter collapse")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 2.0)
    ax.legend(fontsize=8)

    # ── Panel D: log-log with universal fit (S3) ───────────────────────
    ax = axes[1, 1]
    mask = (decay["tau"] > 0) & (decay["D_norm"] > 0)
    d = decay[mask]
    for slug, g in d.groupby("slug"):
        for gu, gg in g.groupby("geo_unit"):
            gg = gg.sort_values("tau")
            ax.plot(np.log10(gg["tau"]), np.log10(gg["D_norm"]),
                    alpha=0.05, lw=0.3, color=color_map[slug])
    # universal fit line
    x_fit = np.linspace(0.5, 3.0, 100)
    y_fit = univ["intercept"] - univ["alpha_universal"] * x_fit
    ax.plot(x_fit, y_fit, "r-", lw=2.5,
            label=f"Universal α = {univ['alpha_universal']:.3f} (R² = {univ['r2']:.3f})")
    ax.set_xlabel("log₁₀(τ)")
    ax.set_ylabel("log₁₀(D / D_peak)")
    ax.set_title("(d) Log-log with universal power law")
    ax.set_xlim(0.5, 3.0)
    ax.set_ylim(-2.5, 1.0)
    ax.legend(fontsize=8)

    # ── legend for events ──────────────────────────────────────────────
    handles = [plt.Line2D([0], [0], color=color_map[s], lw=2, label=s[:30])
               for s in slugs]

    fig.tight_layout(rect=[0, 0.08, 1, 1])
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=6,
               frameon=False)
    fig.savefig(OUT_DIR / "data_collapse_4panel.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    # ── Supplementary: per-event master curves ─────────────────────────
    n_events = len(event_q_df)
    ncols = 4
    nrows = (n_events + ncols - 1) // ncols
    fig2, axes2 = plt.subplots(nrows, ncols, figsize=(16, 4 * nrows))
    axes2 = axes2.flatten() if n_events > 1 else [axes2]

    for idx, (_, row) in enumerate(event_q_df.iterrows()):
        ax = axes2[idx]
        g = decay[decay["slug"] == row["slug"]].copy()
        g["tau_s"] = g["tau"] / g["t_half"]
        for gu, gg in g.groupby("geo_unit"):
            gg = gg.sort_values("tau_s")
            ax.plot(gg["tau_s"], gg["D_norm"], alpha=0.15, lw=0.5, color="steelblue")
        ax.set_title(f"{row['slug'][:25]}\nQ={row['Q_S2']:.3f}, n={row['n_units']}",
                     fontsize=8)
        ax.set_xlim(0, 8)
        ax.set_ylim(0, 2.0)
        if idx % ncols == 0:
            ax.set_ylabel("D / D_peak")
        if idx >= (nrows - 1) * ncols:
            ax.set_xlabel("τ / t_half")

    for idx in range(n_events, len(axes2)):
        axes2[idx].set_visible(False)

    fig2.suptitle("Per-event collapse (S2: D/D_peak vs τ/t_half)", fontsize=12)
    fig2.tight_layout()
    fig2.savefig(OUT_DIR / "per_event_collapse.png", dpi=200, bbox_inches="tight")
    plt.close(fig2)

    # ── Alpha histogram ────────────────────────────────────────────────
    fig3, ax3 = plt.subplots(figsize=(8, 5))
    alphas = decay.drop_duplicates(["slug", "geo_unit"])
    for slug in slugs:
        sub = alphas[alphas["slug"] == slug]
        ax3.hist(sub["alpha_unit"], bins=20, alpha=0.4, color=color_map[slug],
                 label=slug[:25], density=True)
    ax3.axvline(alphas["alpha_unit"].median(), color="red", ls="--", lw=2,
                label=f"Median = {alphas['alpha_unit'].median():.3f}")
    ax3.set_xlabel("α (power-law exponent)")
    ax3.set_ylabel("Density")
    ax3.set_title("Distribution of unit-level α across all events")
    ax3.legend(fontsize=6, ncol=2)
    fig3.tight_layout()
    fig3.savefig(OUT_DIR / "alpha_distribution.png", dpi=200, bbox_inches="tight")
    plt.close(fig3)


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    run_experiment()
