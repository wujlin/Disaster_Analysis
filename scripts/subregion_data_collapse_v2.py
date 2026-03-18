"""Route A v2: Refined Data Collapse + Alpha Clustering Analysis.

Key improvements over v1:
  - ICC (intraclass correlation) for alpha: how much variance is between vs within events
  - Per-event single-alpha fit: fit one alpha per event to all its subregions
  - Log-log collapse with event-median alpha
  - Functional form test: what fraction of units are well-fit by power law
  - Cross-event rescaling with event-level alpha
"""

from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats as sp_stats

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = (
    ROOT / "outputs/cross_disaster_comparison"
    / "geo_unit_scale_unified_h8_mtw4_mpp3_relaxed_20260225_141630"
    / "tables"
)
TS_CSV = RUN_DIR / "geo_unit_timeseries.csv"
FITS_CSV = RUN_DIR / "geo_unit_fits.csv"
OUT_DIR = ROOT / "outputs/cross_disaster_comparison/subregion_collapse"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MIN_NMONO = 4
MIN_R2 = 0.5
MIN_TAU_POINTS = 3


def load_data():
    ts = pd.read_csv(TS_CSV)
    fits = pd.read_csv(FITS_CSV)
    fits_clean = fits[(fits["n_mono"] >= MIN_NMONO) & (fits["r2_unit"] >= MIN_R2)].copy()
    merged = ts.merge(
        fits_clean[["slug", "geo_unit", "alpha_unit", "D_peak_unit", "t_peak_h",
                     "r2_unit", "n_mono"]],
        on=["slug", "geo_unit"], how="inner",
    )
    merged["tau"] = merged["hours_since_t0"] - merged["t_peak_h"]
    decay = merged[merged["tau"] > 0].copy()
    decay["D_norm"] = decay["D"] / decay["D_peak_unit"]
    counts = decay.groupby(["slug", "geo_unit"]).size()
    valid = counts[counts >= MIN_TAU_POINTS].index
    decay = decay.set_index(["slug", "geo_unit"]).loc[valid].reset_index()
    print(f"Units: {decay[['slug','geo_unit']].drop_duplicates().shape[0]}, "
          f"observations: {len(decay)}, events: {decay['slug'].nunique()}")
    return decay


def icc_one_way(df, group_col, value_col):
    """One-way random-effects ICC: fraction of variance between groups."""
    groups = df.groupby(group_col)[value_col]
    k = groups.ngroups
    ns = groups.count()
    n_total = ns.sum()
    grand_mean = df[value_col].mean()
    SS_between = sum(n * (g_mean - grand_mean) ** 2
                     for (_, g_mean), n in zip(groups.mean().items(), ns))
    SS_within = sum(((g[value_col] - g[value_col].mean()) ** 2).sum()
                    for _, g in df.groupby(group_col))
    MS_between = SS_between / (k - 1) if k > 1 else 0
    MS_within = SS_within / (n_total - k) if (n_total - k) > 0 else 1e-10
    n0 = (n_total - sum(ns ** 2) / n_total) / (k - 1) if k > 1 else 1
    icc = (MS_between - MS_within) / (MS_between + (n0 - 1) * MS_within)
    return max(0, min(1, icc))


def fit_event_alpha(decay):
    """Fit a single power-law exponent to ALL subregion data within each event."""
    results = []
    for slug, g in decay.groupby("slug"):
        mask = (g["tau"] > 0) & (g["D_norm"] > 0)
        d = g[mask]
        if len(d) < 10:
            continue
        log_tau = np.log10(d["tau"].values)
        log_dn = np.log10(d["D_norm"].values)
        slope, intercept, r, p, se = sp_stats.linregress(log_tau, log_dn)
        # individual alphas for this event
        unit_alphas = g.drop_duplicates(["geo_unit"])["alpha_unit"]
        results.append({
            "slug": slug,
            "event_type": g["event_type"].iloc[0],
            "alpha_event_pooled": -slope,
            "r2_event_pooled": r ** 2,
            "alpha_unit_median": unit_alphas.median(),
            "alpha_unit_mean": unit_alphas.mean(),
            "alpha_unit_std": unit_alphas.std(),
            "alpha_unit_cv": unit_alphas.std() / unit_alphas.mean() if unit_alphas.mean() > 0 else np.nan,
            "n_units": len(unit_alphas),
            "n_obs": len(d),
        })
    return pd.DataFrame(results)


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
            if alpha > 0:
                t_half = tau[0] * (dn[0] / 0.5) ** (1.0 / alpha)
            else:
                t_half = tau[-1] * 2
        records.append({"slug": slug, "geo_unit": gu, "t_half": max(t_half, 1.0)})
    return pd.DataFrame(records)


def run():
    decay = load_data()
    t_half_df = compute_t_half(decay)
    decay = decay.merge(t_half_df, on=["slug", "geo_unit"], how="left")

    # ── 1. ICC for alpha ───────────────────────────────────────────────
    unit_df = decay.drop_duplicates(["slug", "geo_unit"])[["slug", "geo_unit", "alpha_unit", "event_type"]]
    icc = icc_one_way(unit_df, "slug", "alpha_unit")
    print(f"\n{'='*60}")
    print(f"ICC(alpha, event) = {icc:.4f}")
    print(f"  → {icc*100:.1f}% of alpha variance is BETWEEN events")
    print(f"  → {(1-icc)*100:.1f}% is WITHIN events (subregion heterogeneity)")

    # ── 2. Event-level pooled alpha ────────────────────────────────────
    event_alpha = fit_event_alpha(decay)
    print(f"\n{'='*60}")
    print("Event-level pooled alpha:")
    print(event_alpha[["slug", "alpha_event_pooled", "r2_event_pooled",
                        "alpha_unit_median", "alpha_unit_cv", "n_units"]].to_string(index=False))

    # ── 3. Functional form universality ────────────────────────────────
    # What fraction of units have R² >= 0.7 for their individual power-law fit?
    fits = pd.read_csv(FITS_CSV)
    fits_included = fits[(fits["n_mono"] >= MIN_NMONO)].copy()
    r2_bins = [0, 0.3, 0.5, 0.7, 0.9, 1.01]
    r2_labels = ["<0.3", "0.3-0.5", "0.5-0.7", "0.7-0.9", "≥0.9"]
    fits_included["r2_bin"] = pd.cut(fits_included["r2_unit"], bins=r2_bins, labels=r2_labels)
    r2_dist = fits_included["r2_bin"].value_counts().sort_index()
    pct_good = (fits_included["r2_unit"] >= 0.7).mean()
    print(f"\n{'='*60}")
    print(f"Power-law fit quality (n_mono >= {MIN_NMONO}):")
    print(f"  n = {len(fits_included)}")
    for lab in r2_labels:
        ct = r2_dist.get(lab, 0)
        print(f"  R² {lab}: {ct:4d} ({ct/len(fits_included)*100:.1f}%)")
    print(f"  Fraction R² ≥ 0.7: {pct_good:.1%}")

    # ── 4. Log-log collapse with event-median alpha ────────────────────
    # Strategy S4: rescale each unit by EVENT-LEVEL alpha
    # log(D_norm) vs alpha_event * log(tau)
    decay = decay.merge(
        event_alpha[["slug", "alpha_event_pooled"]],
        on="slug", how="left",
    )
    mask = (decay["tau"] > 0) & (decay["D_norm"] > 0)
    d_log = decay[mask].copy()
    d_log["log_tau"] = np.log10(d_log["tau"])
    d_log["log_Dn"] = np.log10(d_log["D_norm"])

    # S4a: x = alpha_event * log(tau), y = log(D_norm) → expect y = -x + C
    d_log["x_s4a"] = d_log["alpha_event_pooled"] * d_log["log_tau"]
    q_s4a = collapse_quality(d_log["x_s4a"].values, d_log["log_Dn"].values)

    # S4b: x = alpha_unit * log(tau), y = log(D_norm) → expect y = -x + C (per-unit alpha)
    d_log["x_s4b"] = d_log["alpha_unit"] * d_log["log_tau"]
    q_s4b = collapse_quality(d_log["x_s4b"].values, d_log["log_Dn"].values)

    # S2 for comparison
    decay["tau_scaled"] = decay["tau"] / decay["t_half"]
    q_s2 = collapse_quality(decay["tau_scaled"].values, decay["D_norm"].values)

    # ── 5. Within-event collapse quality (averaged) ────────────────────
    per_event_q = []
    for slug, g in decay.groupby("slug"):
        if g[["geo_unit"]].drop_duplicates().shape[0] < 5:
            continue
        # S2 within event
        g_s = g.copy()
        g_s["tau_s2"] = g_s["tau"] / g_s["t_half"]
        q2_in = collapse_quality(g_s["tau_s2"].values, g_s["D_norm"].values)

        # log-log within event
        ml = (g["tau"] > 0) & (g["D_norm"] > 0)
        gl = g[ml].copy()
        if len(gl) > 10:
            q_log = collapse_quality(np.log10(gl["tau"].values), np.log10(gl["D_norm"].values))
        else:
            q_log = np.nan

        per_event_q.append({
            "slug": slug,
            "n_units": g[["geo_unit"]].drop_duplicates().shape[0],
            "Q_S2_within": q2_in,
            "Q_loglog_within": q_log,
        })
    peq = pd.DataFrame(per_event_q)
    q_s2_within_mean = peq["Q_S2_within"].mean()
    q_log_within_mean = peq["Q_loglog_within"].mean()

    print(f"\n{'='*60}")
    print("COLLAPSE QUALITY SUMMARY")
    print(f"  S2 (D/Dp vs tau/t_half) global Q:    {q_s2:.4f}")
    print(f"  S4a (event alpha) global Q:          {q_s4a:.4f}")
    print(f"  S4b (unit alpha) global Q:           {q_s4b:.4f}")
    print(f"  S2 within-event mean Q:              {q_s2_within_mean:.4f}")
    print(f"  Log-log within-event mean Q:         {q_log_within_mean:.4f}")
    print()
    print("Within-event details:")
    print(peq.to_string(index=False))

    # ── 6. Residual analysis ───────────────────────────────────────────
    # After accounting for power-law form and event-level alpha,
    # how much residual variance is there?
    d_log["residual"] = d_log["log_Dn"] + d_log["alpha_event_pooled"] * d_log["log_tau"]
    residual_var_within = d_log.groupby("slug")["residual"].var().mean()
    residual_var_total = d_log["residual"].var()
    print(f"\n{'='*60}")
    print("Residual analysis (log(D_norm) + alpha_event * log(tau)):")
    print(f"  Total residual variance:       {residual_var_total:.4f}")
    print(f"  Mean within-event residual var: {residual_var_within:.4f}")
    print(f"  Ratio (within/total):           {residual_var_within/residual_var_total:.4f}")
    print(f"  → Event-level alpha explains {(1-residual_var_within/residual_var_total)*100:.1f}% "
          f"of inter-unit intercept variance")

    # ── 7. Save everything ─────────────────────────────────────────────
    summary = {
        "ICC_alpha": icc,
        "pct_units_r2_ge_07": pct_good,
        "Q_S2_global": q_s2,
        "Q_S4a_event_alpha": q_s4a,
        "Q_S4b_unit_alpha": q_s4b,
        "Q_S2_within_event_mean": q_s2_within_mean,
        "Q_loglog_within_event_mean": q_log_within_mean,
        "residual_var_ratio": residual_var_within / residual_var_total,
    }
    pd.DataFrame([summary]).to_csv(OUT_DIR / "collapse_v2_summary.csv", index=False)
    event_alpha.to_csv(OUT_DIR / "event_pooled_alpha.csv", index=False)
    peq.to_csv(OUT_DIR / "within_event_collapse_quality.csv", index=False)

    # ── 8. Plots ───────────────────────────────────────────────────────
    _plot_v2(decay, d_log, event_alpha, unit_df, icc, q_s2, q_s4a, peq)
    print(f"\nAll outputs saved to {OUT_DIR}")


def _plot_v2(decay, d_log, event_alpha, unit_df, icc, q_s2, q_s4a, peq):
    cmap = plt.cm.tab20
    slugs = sorted(decay["slug"].unique())
    color_map = {s: cmap(i / max(len(slugs), 1)) for i, s in enumerate(slugs)}

    fig, axes = plt.subplots(2, 2, figsize=(14, 11))

    # Panel A: alpha distributions per event (violin-like)
    ax = axes[0, 0]
    positions = range(len(slugs))
    for i, slug in enumerate(slugs):
        sub = unit_df[unit_df["slug"] == slug]["alpha_unit"]
        if len(sub) < 3:
            continue
        parts = ax.violinplot(sub.values, [i], widths=0.7, showextrema=False)
        for pc in parts["bodies"]:
            pc.set_facecolor(color_map[slug])
            pc.set_alpha(0.6)
        ax.scatter([i] * len(sub), sub.values, s=3, alpha=0.3, color=color_map[slug])
    ax.set_xticks(list(positions))
    ax.set_xticklabels([s[:15] for s in slugs], rotation=90, fontsize=6)
    ax.set_ylabel("α (power-law exponent)")
    ax.set_title(f"(a) α distribution by event | ICC = {icc:.3f}")
    ax.axhline(unit_df["alpha_unit"].median(), color="red", ls="--", lw=1,
               label=f"Global median = {unit_df['alpha_unit'].median():.2f}")
    ax.legend(fontsize=7)

    # Panel B: Log-log overlay colored by event
    ax = axes[0, 1]
    for slug in slugs:
        g = d_log[d_log["slug"] == slug]
        for _, gg in g.groupby("geo_unit"):
            gg = gg.sort_values("log_tau")
            ax.plot(gg["log_tau"], gg["log_Dn"], alpha=0.06, lw=0.4,
                    color=color_map[slug])
    # per-event regression lines
    for slug in slugs:
        row = event_alpha[event_alpha["slug"] == slug]
        if row.empty:
            continue
        a = row["alpha_event_pooled"].iloc[0]
        g = d_log[d_log["slug"] == slug]
        x_rng = np.linspace(g["log_tau"].min(), g["log_tau"].max(), 50)
        y_pred = -a * x_rng + np.median(g["log_Dn"] + a * g["log_tau"])
        ax.plot(x_rng, y_pred, color=color_map[slug], lw=1.5, alpha=0.8)
    ax.set_xlabel("log₁₀(τ)")
    ax.set_ylabel("log₁₀(D / D_peak)")
    ax.set_title("(b) Log-log with per-event power law")
    ax.set_xlim(1.0, 3.0)
    ax.set_ylim(-2.5, 1.0)

    # Panel C: S4a collapse — log(D_norm) vs alpha_event * log(tau)
    ax = axes[1, 0]
    for slug in slugs:
        g = d_log[d_log["slug"] == slug]
        for _, gg in g.groupby("geo_unit"):
            ax.plot(gg["x_s4a"], gg["log_Dn"], alpha=0.06, lw=0.4,
                    color=color_map[slug])
    # universal line y = -x + C
    x_range = np.linspace(d_log["x_s4a"].quantile(0.02), d_log["x_s4a"].quantile(0.98), 100)
    c_median = np.median(d_log["log_Dn"] + d_log["x_s4a"])
    ax.plot(x_range, -x_range + c_median, "r-", lw=2.5,
            label=f"y = -x + {c_median:.2f}")
    ax.set_xlabel("α_event × log₁₀(τ)")
    ax.set_ylabel("log₁₀(D / D_peak)")
    ax.set_title(f"(c) Event-alpha rescaled collapse | Q = {q_s4a:.3f}")
    ax.legend(fontsize=8)

    # Panel D: within-event Q bar chart
    ax = axes[1, 1]
    peq_sorted = peq.sort_values("Q_S2_within", ascending=True)
    colors = [color_map.get(s, "gray") for s in peq_sorted["slug"]]
    bars = ax.barh(range(len(peq_sorted)), peq_sorted["Q_S2_within"], color=colors)
    ax.set_yticks(range(len(peq_sorted)))
    ax.set_yticklabels([s[:30] for s in peq_sorted["slug"]], fontsize=6)
    ax.axvline(peq_sorted["Q_S2_within"].mean(), color="red", ls="--", lw=1.5,
               label=f"Mean Q = {peq_sorted['Q_S2_within'].mean():.3f}")
    # annotate n_units
    for idx, (_, row) in enumerate(peq_sorted.iterrows()):
        ax.text(max(row["Q_S2_within"], 0) + 0.02, idx, f"n={row['n_units']:.0f}",
                fontsize=6, va="center")
    ax.set_xlabel("Collapse quality Q (S2)")
    ax.set_title("(d) Within-event collapse quality")
    ax.legend(fontsize=8)
    ax.set_xlim(-0.6, 1.0)

    fig.tight_layout()
    fig.savefig(OUT_DIR / "data_collapse_v2_4panel.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    # ── Supplementary: per-event log-log panels ────────────────────────
    n_events = len(slugs)
    ncols = 4
    nrows = (n_events + ncols - 1) // ncols
    fig2, axes2 = plt.subplots(nrows, ncols, figsize=(16, 4 * nrows))
    axes2 = axes2.flatten()

    for idx, slug in enumerate(slugs):
        ax = axes2[idx]
        g = d_log[d_log["slug"] == slug]
        if g.empty:
            ax.set_visible(False)
            continue
        for _, gg in g.groupby("geo_unit"):
            gg = gg.sort_values("log_tau")
            ax.plot(gg["log_tau"], gg["log_Dn"], alpha=0.2, lw=0.5, color="steelblue")
        row = event_alpha[event_alpha["slug"] == slug]
        if not row.empty:
            a = row["alpha_event_pooled"].iloc[0]
            r2 = row["r2_event_pooled"].iloc[0]
            cv = row["alpha_unit_cv"].iloc[0]
            x_rng = np.linspace(g["log_tau"].min(), g["log_tau"].max(), 50)
            y_pred = -a * x_rng + np.median(g["log_Dn"] + a * g["log_tau"])
            ax.plot(x_rng, y_pred, "r-", lw=2)
            ax.set_title(f"{slug[:22]}\nα={a:.2f}, R²={r2:.2f}, CV={cv:.2f}",
                         fontsize=7)
        ax.set_xlim(1.0, 3.0)
        ax.set_ylim(-2.5, 1.0)
        if idx % ncols == 0:
            ax.set_ylabel("log₁₀(D/D_peak)")
        if idx >= (nrows - 1) * ncols:
            ax.set_xlabel("log₁₀(τ)")

    for idx in range(n_events, len(axes2)):
        axes2[idx].set_visible(False)

    fig2.suptitle("Per-event log-log decay with pooled power law", fontsize=12)
    fig2.tight_layout()
    fig2.savefig(OUT_DIR / "per_event_loglog.png", dpi=200, bbox_inches="tight")
    plt.close(fig2)


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    run()
