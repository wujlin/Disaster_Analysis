"""Gao et al. (PNAS 2022) Exponential Decay Baseline Comparison.

Compares three temporal decay models on our D(t) data:
  M1  Power law:       D(t) = A * t'^(-alpha)
  M2  Exponential:     D(t) = A * exp(-lambda * t')    [Gao's k(t)]
  M3  Stretched exp:   D(t) = A * exp(-(t'/tau)^beta)

For each event, fits all three on the same monotone-decay segment and
reports AIC, BIC, R², and residual diagnostics.
"""
import argparse
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DT_CSV = ROOT / "outputs/cross_disaster_comparison/Dt_decay_unified_h8_mtw5_mpp4/tables/Dt_all_events.csv"
DEFAULT_FLAGS_CSV = ROOT / "outputs/cross_disaster_comparison/Dt_decay_unified_h8_mtw5_mpp4/tables/Dt_routeB_sample_flags.csv"
DEFAULT_OUT_DIR = ROOT / "outputs/cross_disaster_comparison/gao_baseline"

DT_CSV = DEFAULT_DT_CSV
FLAGS_CSV = DEFAULT_FLAGS_CSV
OUT_DIR = DEFAULT_OUT_DIR
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Model definitions ──────────────────────────────────────────────────

def power_law(t, A, alpha):
    return A * np.power(t, -alpha)

def exponential(t, A, lam):
    return A * np.exp(-lam * t)

def stretched_exp(t, A, tau, beta):
    return A * np.exp(-np.power(t / tau, beta))


def fit_model(t, D, model_func, p0, bounds, n_params):
    """Fit a model and return AIC, BIC, R², parameters."""
    try:
        popt, pcov = curve_fit(model_func, t, D, p0=p0, bounds=bounds,
                               maxfev=5000)
        D_pred = model_func(t, *popt)
        residuals = D - D_pred
        n = len(D)
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((D - np.mean(D)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        # log-likelihood (assuming Gaussian errors)
        sigma2 = ss_res / n
        if sigma2 > 0:
            log_lik = -n / 2 * (np.log(2 * np.pi * sigma2) + 1)
        else:
            log_lik = 0

        k = n_params
        aic = 2 * k - 2 * log_lik
        bic = k * np.log(n) - 2 * log_lik

        return {
            "params": popt,
            "r2": r2,
            "aic": aic,
            "bic": bic,
            "ss_res": ss_res,
            "n": n,
            "converged": True,
            "D_pred": D_pred,
        }
    except Exception as e:
        return {
            "params": None,
            "r2": np.nan,
            "aic": np.nan,
            "bic": np.nan,
            "ss_res": np.nan,
            "n": len(D),
            "converged": False,
            "D_pred": None,
        }


def extract_decay_segment(dt_all, flags, slug):
    """Extract the monotone decay segment used for alpha fitting."""
    row = flags[flags["slug"] == slug].iloc[0]
    t_peak_hours = float(row["t_peak_hours"])
    n_mono = int(row["n_mono"])

    ts = dt_all[dt_all["slug"] == slug].copy()
    ts["hours_since_quake"] = pd.to_numeric(ts["hours_since_quake"], errors="coerce")
    ts["D"] = pd.to_numeric(ts["D"], errors="coerce")
    ts = ts.dropna(subset=["hours_since_quake", "D"])
    ts = ts.sort_values("hours_since_quake")

    # post-peak, t' > 0
    ts["t_prime"] = ts["hours_since_quake"] - t_peak_hours
    post = ts[ts["t_prime"] > 0].copy()

    if post.empty or n_mono < 3:
        return None, None

    # reconstruct monotone segment: skip t'<24h, then keep while D doesn't rise >5%
    post = post[post["t_prime"] >= 24].copy()
    D_vals = post["D"].values
    t_vals = post["t_prime"].values

    keep = [0]
    for i in range(1, len(D_vals)):
        if D_vals[i] <= 1.05 * D_vals[keep[-1]]:
            keep.append(i)
        else:
            break

    if len(keep) < 3:
        return None, None

    t_seg = t_vals[keep]
    D_seg = D_vals[keep]
    return t_seg, D_seg


def run():
    dt_all = pd.read_csv(DT_CSV)
    flags = pd.read_csv(FLAGS_CSV)
    selected = flags[flags["route_b_selected"] == True].copy()

    results = []

    for _, row in selected.iterrows():
        slug = row["slug"]
        t_seg, D_seg = extract_decay_segment(dt_all, flags, slug)
        if t_seg is None:
            continue

        D_peak = float(row["D_peak"])
        D_norm = D_seg / D_peak

        # M1: Power law
        m1 = fit_model(t_seg, D_norm, power_law,
                       p0=[1.0, 0.5], bounds=([0, -1], [100, 10]), n_params=2)

        # M2: Exponential (Gao)
        m2 = fit_model(t_seg, D_norm, exponential,
                       p0=[1.0, 0.01], bounds=([0, 1e-6], [100, 1]), n_params=2)

        # M3: Stretched exponential
        m3 = fit_model(t_seg, D_norm, stretched_exp,
                       p0=[1.0, 100, 0.5], bounds=([0, 1, 0.01], [100, 5000, 5]), n_params=3)

        rec = {
            "slug": slug,
            "event_type": row.get("event_type", ""),
            "n_points": len(t_seg),
            "alpha_original": float(row["alpha"]),
            # M1
            "M1_power_law_r2": m1["r2"],
            "M1_power_law_aic": m1["aic"],
            "M1_power_law_bic": m1["bic"],
            "M1_alpha": m1["params"][1] if m1["converged"] else np.nan,
            "M1_A": m1["params"][0] if m1["converged"] else np.nan,
            # M2
            "M2_exponential_r2": m2["r2"],
            "M2_exponential_aic": m2["aic"],
            "M2_exponential_bic": m2["bic"],
            "M2_lambda": m2["params"][1] if m2["converged"] else np.nan,
            "M2_A": m2["params"][0] if m2["converged"] else np.nan,
            # M3
            "M3_stretched_exp_r2": m3["r2"],
            "M3_stretched_exp_aic": m3["aic"],
            "M3_stretched_exp_bic": m3["bic"],
            "M3_tau": m3["params"][1] if m3["converged"] else np.nan,
            "M3_beta": m3["params"][2] if m3["converged"] else np.nan,
            "M3_A": m3["params"][0] if m3["converged"] else np.nan,
        }
        results.append(rec)

    df = pd.DataFrame(results)
    df.to_csv(OUT_DIR / "model_comparison.csv", index=False)

    # ── Summary statistics ─────────────────────────────────────────────
    print("=" * 70)
    print("MODEL COMPARISON: Power Law vs Exponential (Gao) vs Stretched Exp")
    print("=" * 70)

    for model, r2_col, aic_col, bic_col in [
        ("M1 Power Law", "M1_power_law_r2", "M1_power_law_aic", "M1_power_law_bic"),
        ("M2 Exponential (Gao)", "M2_exponential_r2", "M2_exponential_aic", "M2_exponential_bic"),
        ("M3 Stretched Exp", "M3_stretched_exp_r2", "M3_stretched_exp_aic", "M3_stretched_exp_bic"),
    ]:
        r2 = df[r2_col].dropna()
        aic = df[aic_col].dropna()
        bic = df[bic_col].dropna()
        print(f"\n{model}:")
        print(f"  R² mean={r2.mean():.4f}, median={r2.median():.4f}, "
              f"range=[{r2.min():.4f}, {r2.max():.4f}]")
        print(f"  AIC mean={aic.mean():.1f}, BIC mean={bic.mean():.1f}")

    # BIC preference (lower is better)
    print("\n" + "=" * 70)
    print("BIC MODEL PREFERENCE (per event)")
    print("=" * 70)
    bic_cols = ["M1_power_law_bic", "M2_exponential_bic", "M3_stretched_exp_bic"]
    model_names = ["Power Law", "Exponential", "Stretched Exp"]
    df["bic_best"] = df[bic_cols].idxmin(axis=1).map(dict(zip(bic_cols, model_names)))
    print(df[["slug", "n_points", "M1_power_law_r2", "M2_exponential_r2",
              "M3_stretched_exp_r2", "bic_best"]].to_string(index=False))

    print("\nBIC winner counts:")
    print(df["bic_best"].value_counts().to_string())

    # ── Delta BIC (M1 vs M2) ──────────────────────────────────────────
    df["delta_bic_M1_M2"] = df["M1_power_law_bic"] - df["M2_exponential_bic"]
    print("\nDelta BIC (Power Law - Exponential):")
    print(f"  Negative = Power Law better, Positive = Exponential better")
    print(f"  Mean = {df['delta_bic_M1_M2'].mean():.2f}")
    print(f"  Events where Power Law wins: {(df['delta_bic_M1_M2'] < 0).sum()}/{len(df)}")
    print(f"  Events where Exponential wins: {(df['delta_bic_M1_M2'] > 0).sum()}/{len(df)}")
    for _, r in df.iterrows():
        winner = "PL" if r["delta_bic_M1_M2"] < 0 else "EXP"
        print(f"    {r['slug'][:45]:45s}  ΔBIC={r['delta_bic_M1_M2']:+.2f}  ({winner})")

    # ── Plot ───────────────────────────────────────────────────────────
    _plot_comparison(dt_all, flags, selected, df)

    print(f"\nAll outputs saved to {OUT_DIR}")


def _plot_comparison(dt_all, flags, selected, df):
    """Per-event 3-model comparison + summary panel."""
    n = len(df)
    ncols = 4
    nrows = (n + ncols - 1) // ncols + 1  # extra row for summary
    fig, axes = plt.subplots(nrows, ncols, figsize=(16, 4 * nrows))
    axes = axes.flatten()

    for idx, (_, row) in enumerate(df.iterrows()):
        ax = axes[idx]
        slug = row["slug"]
        t_seg, D_seg = extract_decay_segment(dt_all, flags, slug)
        if t_seg is None:
            continue

        D_peak = float(selected[selected["slug"] == slug].iloc[0]["D_peak"])
        D_norm = D_seg / D_peak
        t_fine = np.linspace(t_seg.min(), t_seg.max(), 200)

        ax.plot(t_seg, D_norm, "ko", ms=4, label="Data")

        if not np.isnan(row["M1_alpha"]):
            ax.plot(t_fine, power_law(t_fine, row["M1_A"], row["M1_alpha"]),
                    "b-", lw=1.5, label=f"PL α={row['M1_alpha']:.2f}")
        if not np.isnan(row["M2_lambda"]):
            ax.plot(t_fine, exponential(t_fine, row["M2_A"], row["M2_lambda"]),
                    "r--", lw=1.5, label=f"Exp λ={row['M2_lambda']:.4f}")
        if not np.isnan(row["M3_beta"]):
            ax.plot(t_fine, stretched_exp(t_fine, row["M3_A"], row["M3_tau"], row["M3_beta"]),
                    "g:", lw=1.5, label=f"SE β={row['M3_beta']:.2f}")

        winner = row["bic_best"]
        ax.set_title(f"{slug[:25]}\nBIC→{winner}", fontsize=8)
        ax.legend(fontsize=5)
        ax.set_xlabel("t' (hours)", fontsize=7)
        ax.set_ylabel("D / D_peak", fontsize=7)

    # Summary panel: BIC comparison bar
    ax_sum = axes[n]
    slugs_short = [s[:20] for s in df["slug"]]
    x = np.arange(len(df))
    w = 0.25
    ax_sum.barh(x - w, df["M1_power_law_bic"], w, label="Power Law", color="steelblue")
    ax_sum.barh(x, df["M2_exponential_bic"], w, label="Exponential (Gao)", color="indianred")
    ax_sum.barh(x + w, df["M3_stretched_exp_bic"], w, label="Stretched Exp", color="seagreen")
    ax_sum.set_yticks(x)
    ax_sum.set_yticklabels(slugs_short, fontsize=6)
    ax_sum.set_xlabel("BIC (lower = better)")
    ax_sum.set_title("BIC comparison")
    ax_sum.legend(fontsize=7)
    ax_sum.invert_yaxis()

    for idx in range(n + 1, len(axes)):
        axes[idx].set_visible(False)

    fig.tight_layout()
    fig.savefig(OUT_DIR / "gao_baseline_comparison.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gao baseline 三模型比较")
    parser.add_argument("--dt-csv", default=str(DEFAULT_DT_CSV))
    parser.add_argument("--flags-csv", default=str(DEFAULT_FLAGS_CSV))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    DT_CSV = Path(args.dt_csv)
    FLAGS_CSV = Path(args.flags_csv)
    OUT_DIR = Path(args.out_dir)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    warnings.filterwarnings("ignore")
    run()
