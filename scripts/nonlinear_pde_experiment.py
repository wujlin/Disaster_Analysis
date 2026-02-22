#!/usr/bin/env python3
"""
Non-linear PDE experiment: state-dependent recovery rate
=========================================================

Physical model
--------------
  dD/dt' = -(k₀ + γ·D) · D

where D(t') is the mean absolute displacement.  D_peak enters as a KNOWN
covariate → only 2 global parameters (k₀, γ).

Normalised solution (Bernoulli ODE, D_norm = D/D_peak, D_norm(0)=1):

  D_norm(t') = k₀ / [(k₀ + γ·D_peak)·exp(k₀·t') − γ·D_peak]

With a residual floor D_inf (known from data):

  δ = D − D_inf   ⟹   same ODE for δ
  D_norm(t') = D_inf_norm + (1−D_inf_norm)·k₀
               / [(k₀ + γ·D_peak·(1−D_inf_norm))·exp(k₀·t')
                  − γ·D_peak·(1−D_inf_norm)]

Experiments
-----------
  N1  Log-log curvature: concave ⇔ state-dependent recovery
  N2  Global ODE fit  (2 params) vs per-event power law (2×16 params)
  N3  Predict α ranking from ODE → ρ(α_pred, α_emp)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import optimize, stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "outputs" / "cross_disaster_comparison" / "nonlinear_pde"
OUT_TABLES = OUT / "tables"
OUT_FIGS = OUT / "figures"
OUT_TABLES.mkdir(parents=True, exist_ok=True)
OUT_FIGS.mkdir(parents=True, exist_ok=True)

DT_DIR = ROOT / "outputs" / "cross_disaster_comparison" / "Dt_decay" / "tables"

# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _load_route_b() -> pd.DataFrame:
    """Route B event metadata (16 events)."""
    flags = pd.read_csv(DT_DIR / "Dt_routeB_sample_flags.csv")
    rb = flags[flags["route_b_selected"] == True].copy()  # noqa: E712
    for c in ["D_peak", "t_peak_hours", "alpha", "D_inf",
              "t_decay_start", "t_decay_end", "near_delta_peak_windows_mean"]:
        if c in rb.columns:
            rb[c] = pd.to_numeric(rb[c], errors="coerce")
    return rb


def _load_dt_all() -> pd.DataFrame:
    """Full D(t) timeseries from Dt_all_events.csv."""
    df = pd.read_csv(DT_DIR / "Dt_all_events.csv")
    for c in ["hours_since_quake", "D", "D_norm", "D_peak", "t_peak_hours"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["t_prime_h"] = df["hours_since_quake"] - df["t_peak_hours"]
    return df


def _prepare_event_data(
    dt_all: pd.DataFrame,
    rb: pd.DataFrame,
    *,
    use_monotone: bool = False,
) -> list[dict]:
    """
    Prepare per-event arrays for fitting.

    If use_monotone=True, restrict to the monotone decay segment
    [t_decay_start, t_decay_end] from the existing power-law fits.
    """
    rb_slugs = set(rb["slug"])
    events = []
    for slug in sorted(rb_slugs):
        grp = dt_all[dt_all["slug"] == slug].copy()
        post = grp[(grp["t_prime_h"] > 0) & (grp["D_norm"] > 0)].copy()
        post = post.sort_values("t_prime_h")

        if use_monotone:
            row = rb[rb["slug"] == slug].iloc[0]
            ts, te = float(row["t_decay_start"]), float(row["t_decay_end"])
            if np.isfinite(ts) and np.isfinite(te):
                post = post[(post["t_prime_h"] >= ts) & (post["t_prime_h"] <= te)]

        if post.shape[0] < 2:
            continue

        meta = rb[rb["slug"] == slug].iloc[0]
        D_peak = float(meta["D_peak"])
        D_inf_norm = float(meta["D_inf"]) if pd.notna(meta["D_inf"]) else 0.0
        alpha_emp = float(meta["alpha"]) if pd.notna(meta["alpha"]) else np.nan

        events.append({
            "slug": slug,
            "t_prime": post["t_prime_h"].values.astype(float),
            "D_norm":  post["D_norm"].values.astype(float),
            "D_peak":  D_peak,
            "D_inf_norm": D_inf_norm,
            "alpha_emp": alpha_emp,
            "n_pts":   int(post.shape[0]),
        })
    return events


# ═══════════════════════════════════════════════════════════════
# ODE analytical solution
# ═══════════════════════════════════════════════════════════════

def ode_pred(t_prime: np.ndarray, k0: float, gamma: float,
             D_peak: float, D_inf_norm: float = 0.0) -> np.ndarray:
    """
    Predicted D_norm(t') from the Bernoulli ODE with D_inf floor.

    D_norm = D_inf_norm + δ₀_norm · k₀ / [denom]
    where  δ₀_norm = 1 − D_inf_norm
           δ₀_phys = D_peak · δ₀_norm
           denom   = (k₀ + γ·δ₀_phys) · exp(k₀·t') − γ·δ₀_phys
    """
    t_prime = np.asarray(t_prime, dtype=float)
    delta0_norm = max(1.0 - D_inf_norm, 1e-6)
    delta0_phys = D_peak * delta0_norm
    gd = gamma * delta0_phys
    denom = (k0 + gd) * np.exp(k0 * t_prime) - gd
    denom = np.maximum(denom, 1e-15)
    delta_norm = delta0_norm * k0 / denom
    return D_inf_norm + delta_norm


# ═══════════════════════════════════════════════════════════════
# Exp-N1 : log-log curvature
# ═══════════════════════════════════════════════════════════════

def exp_n1(events: list[dict]) -> pd.DataFrame:
    """
    Fit log(D_norm) = a·(log t')² + b·(log t') + c   per event.
    a < 0  →  concave  →  faster-than-power-law early decay.
    """
    rows = []
    for ev in events:
        t, y = ev["t_prime"], ev["D_norm"]
        ok = (t > 0) & (y > 0)
        t, y = t[ok], y[ok]
        if t.size < 4:
            rows.append({"slug": ev["slug"], "D_peak": ev["D_peak"],
                         "a": np.nan, "b": np.nan, "n_pts": t.size})
            continue
        lx, ly = np.log(t), np.log(y)
        a, b, c = np.polyfit(lx, ly, 2)
        rows.append({"slug": ev["slug"], "D_peak": ev["D_peak"],
                      "a": float(a), "b": float(b), "n_pts": int(t.size)})
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════
# Exp-N2 : global ODE fit
# ═══════════════════════════════════════════════════════════════

def _ssr_ode(params: tuple[float, float], events: list[dict],
             use_dinf: bool = True) -> float:
    k0, gamma = params
    if k0 <= 0:
        return 1e20
    total = 0.0
    for ev in events:
        dinf = ev["D_inf_norm"] if use_dinf else 0.0
        pred = ode_pred(ev["t_prime"], k0, gamma, ev["D_peak"], dinf)
        total += float(np.sum((ev["D_norm"] - pred) ** 2))
    return total


def _fit_ode_global(events: list[dict], *, use_dinf: bool = True,
                    ) -> tuple[float, float, float]:
    """Return (k0, gamma, ssr)."""
    res = optimize.differential_evolution(
        _ssr_ode,
        bounds=[(1e-6, 0.1), (0.0, 10.0)],
        args=(events, use_dinf),
        seed=42, maxiter=2000, tol=1e-12, polish=True,
    )
    return float(res.x[0]), float(res.x[1]), float(res.fun)


def _fit_powerlaw_per_event(events: list[dict]) -> list[dict]:
    """Per-event power law on same data points → for BIC comparison."""
    rows = []
    for ev in events:
        t, y = ev["t_prime"], ev["D_norm"]
        ok = (t > 0) & (y > 0)
        t, y = t[ok], y[ok]
        if t.size < 2:
            rows.append({"slug": ev["slug"], "ssr_pl": np.nan, "alpha_pl": np.nan,
                          "r2_pl": np.nan, "n_pts": int(t.size)})
            continue
        lx, ly = np.log(t), np.log(y)
        slope, intercept = np.polyfit(lx, ly, 1)
        pred = np.exp(slope * lx + intercept)
        ssr = float(np.sum((y - pred) ** 2))
        sst = float(np.sum((y - np.mean(y)) ** 2))
        r2 = 1.0 - ssr / sst if sst > 0 else np.nan
        rows.append({"slug": ev["slug"], "ssr_pl": ssr, "alpha_pl": float(-slope),
                      "r2_pl": r2, "n_pts": int(t.size)})
    return rows


def exp_n2(events: list[dict]) -> tuple[dict, pd.DataFrame]:
    """Global ODE fit + BIC comparison."""
    # ── ODE fit ──
    k0, gamma, ssr_ode = _fit_ode_global(events, use_dinf=True)
    n_total = sum(ev["n_pts"] for ev in events)

    # Per-event ODE residuals
    event_rows = []
    for ev in events:
        pred = ode_pred(ev["t_prime"], k0, gamma, ev["D_peak"], ev["D_inf_norm"])
        ssr_ev = float(np.sum((ev["D_norm"] - pred) ** 2))
        sst_ev = float(np.sum((ev["D_norm"] - np.mean(ev["D_norm"])) ** 2))
        r2_ev = 1.0 - ssr_ev / sst_ev if sst_ev > 0 else np.nan
        event_rows.append({"slug": ev["slug"], "D_peak": ev["D_peak"],
                           "D_inf_norm": ev["D_inf_norm"],
                           "n_pts": ev["n_pts"],
                           "ssr_ode": ssr_ev, "r2_ode": r2_ev})

    # ── Per-event power law ──
    pl_rows = _fit_powerlaw_per_event(events)
    ssr_pl = sum(r["ssr_pl"] for r in pl_rows if np.isfinite(r["ssr_pl"]))
    n_events = len(events)
    k_pl = 2 * n_events

    # Merge per-event tables
    pl_map = {r["slug"]: r for r in pl_rows}
    for er in event_rows:
        pl = pl_map.get(er["slug"], {})
        er["ssr_pl"] = pl.get("ssr_pl", np.nan)
        er["r2_pl"] = pl.get("r2_pl", np.nan)
        er["alpha_pl"] = pl.get("alpha_pl", np.nan)

    # ── BIC ──
    bic_ode = n_total * np.log(ssr_ode / n_total) + 2 * np.log(n_total)
    bic_pl = n_total * np.log(ssr_pl / n_total) + k_pl * np.log(n_total)

    # ── Null model: γ = 0 (pure exponential) ──
    def _ssr_null(k0_val):
        return _ssr_ode((k0_val, 0.0), events, True)
    res_null = optimize.minimize_scalar(_ssr_null, bounds=(1e-6, 0.1), method="bounded")
    k0_null_val = float(res_null.x)
    ssr_null_val = float(res_null.fun)
    bic_null = n_total * np.log(ssr_null_val / n_total) + 1 * np.log(n_total)

    r2_ode = 1.0 - ssr_ode / sum(
        np.sum((ev["D_norm"] - np.mean(ev["D_norm"])) ** 2) for ev in events
    )

    summary = {
        "k0": k0, "gamma": gamma,
        "k0_null": k0_null_val,
        "n_events": n_events, "n_total_pts": n_total,
        "ssr_ode": ssr_ode, "ssr_pl": ssr_pl, "ssr_null": ssr_null_val,
        "r2_ode_total": r2_ode,
        "bic_ode": bic_ode, "bic_pl": bic_pl, "bic_null": bic_null,
        "delta_bic_ode_vs_pl": bic_ode - bic_pl,
        "delta_bic_ode_vs_null": bic_ode - bic_null,
        "k_ode": 2, "k_null": 1, "k_pl": k_pl,
    }
    return summary, pd.DataFrame(event_rows)


# ═══════════════════════════════════════════════════════════════
# Exp-N3 : predict α from ODE
# ═══════════════════════════════════════════════════════════════

def exp_n3(events: list[dict], k0: float, gamma: float) -> pd.DataFrame:
    """
    For each event, generate ODE prediction on the event's t' grid,
    then fit a power law to the prediction → α_pred.
    Compare with α_emp.
    """
    rows = []
    for ev in events:
        t = ev["t_prime"]
        pred = ode_pred(t, k0, gamma, ev["D_peak"], ev["D_inf_norm"])

        # Fit power law to ODE prediction (on the decaying part only: subtract D_inf)
        delta_pred = pred - ev["D_inf_norm"]
        ok = (t > 0) & (delta_pred > 1e-10)
        if ok.sum() >= 2:
            slope, _ = np.polyfit(np.log(t[ok]), np.log(delta_pred[ok]), 1)
            alpha_pred = float(-slope)
        else:
            alpha_pred = np.nan

        # Effective initial decay rate from ODE
        delta0_phys = ev["D_peak"] * max(1.0 - ev["D_inf_norm"], 1e-6)
        k_eff_peak = k0 + gamma * delta0_phys

        rows.append({
            "slug": ev["slug"],
            "D_peak": ev["D_peak"],
            "D_inf_norm": ev["D_inf_norm"],
            "alpha_emp": ev["alpha_emp"],
            "alpha_pred": alpha_pred,
            "k_eff_peak": k_eff_peak,
        })
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════
# LOO cross-validation for γ > 0
# ═══════════════════════════════════════════════════════════════

def exp_n3_loo(events: list[dict]) -> pd.DataFrame:
    """Leave-one-out: fit on 15 events, predict α for held-out event."""
    rows = []
    for i, held in enumerate(events):
        train = [ev for j, ev in enumerate(events) if j != i]
        k0_loo, gamma_loo, _ = _fit_ode_global(train, use_dinf=True)

        # Predict on held-out
        t = held["t_prime"]
        pred = ode_pred(t, k0_loo, gamma_loo, held["D_peak"], held["D_inf_norm"])
        delta_pred = pred - held["D_inf_norm"]
        ok = (t > 0) & (delta_pred > 1e-10)
        if ok.sum() >= 2:
            slope, _ = np.polyfit(np.log(t[ok]), np.log(delta_pred[ok]), 1)
            alpha_pred = float(-slope)
        else:
            alpha_pred = np.nan

        # Prediction error on data
        ssr_loo = float(np.sum((held["D_norm"] - pred) ** 2))

        rows.append({
            "slug": held["slug"],
            "D_peak": held["D_peak"],
            "alpha_emp": held["alpha_emp"],
            "alpha_pred_loo": alpha_pred,
            "k0_loo": k0_loo,
            "gamma_loo": gamma_loo,
            "ssr_loo": ssr_loo,
        })
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════
# Figures
# ═══════════════════════════════════════════════════════════════

def _plot_representative_fits(events: list[dict], k0: float, gamma: float):
    """Plot ODE vs power-law vs data for 3 representative events."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[WARN] matplotlib not available, skipping figures")
        return

    # Pick 3 events: highest D_peak, median, lowest
    sorted_ev = sorted(events, key=lambda e: e["D_peak"])
    picks = [sorted_ev[-1], sorted_ev[len(sorted_ev)//2], sorted_ev[0]]

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharey=False)
    for ax, ev in zip(axes, picks):
        t, y = ev["t_prime"], ev["D_norm"]
        ok = (t > 0) & (y > 0)
        t_ok, y_ok = t[ok], y[ok]

        # Data
        ax.scatter(t_ok, y_ok, s=30, c="k", zorder=5, label="data")

        # ODE
        t_fine = np.linspace(t_ok.min(), t_ok.max(), 200)
        y_ode = ode_pred(t_fine, k0, gamma, ev["D_peak"], ev["D_inf_norm"])
        ax.plot(t_fine, y_ode, "C0-", lw=2, label=f"ODE (γ={gamma:.3f})")

        # Power law (per-event)
        if t_ok.size >= 2:
            sl, ic = np.polyfit(np.log(t_ok), np.log(y_ok), 1)
            y_pl = np.exp(sl * np.log(t_fine) + ic)
            ax.plot(t_fine, y_pl, "C3--", lw=1.5,
                    label=f"power α={-sl:.2f}")

        # D_inf line
        ax.axhline(ev["D_inf_norm"], ls=":", c="grey", lw=0.8, label="D_inf")

        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("t' (h)")
        ax.set_ylabel("D_norm")
        ax.set_title(f"{ev['slug'][:20]}\nD_peak={ev['D_peak']:.3f}")
        ax.legend(fontsize=7, loc="lower left")

    fig.tight_layout()
    fig.savefig(OUT_FIGS / "representative_ode_fits.png", dpi=200)
    plt.close(fig)
    print(f"  Saved figure: {OUT_FIGS / 'representative_ode_fits.png'}")


def _plot_alpha_scatter(alpha_df: pd.DataFrame):
    """α_pred vs α_emp scatter."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    valid = alpha_df.dropna(subset=["alpha_emp", "alpha_pred"])
    if valid.empty:
        return

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(valid["alpha_pred"], valid["alpha_emp"], s=50, c=valid["D_peak"],
               cmap="viridis", edgecolors="k", zorder=5)
    mn = min(valid["alpha_pred"].min(), valid["alpha_emp"].min()) - 0.05
    mx = max(valid["alpha_pred"].max(), valid["alpha_emp"].max()) + 0.05
    ax.plot([mn, mx], [mn, mx], "k--", lw=0.8, alpha=0.5)
    ax.set_xlabel("α_pred (from ODE)")
    ax.set_ylabel("α_emp (power law)")
    ax.set_title("Exp-N3: α prediction from state-dependent ODE")
    rho = stats.spearmanr(valid["alpha_pred"], valid["alpha_emp"])
    ax.text(0.05, 0.95, f"ρ = {rho.statistic:.3f}\np = {rho.pvalue:.4f}",
            transform=ax.transAxes, va="top", fontsize=10,
            bbox=dict(facecolor="white", alpha=0.8))
    cb = fig.colorbar(ax.collections[0], ax=ax, label="D_peak")
    fig.tight_layout()
    fig.savefig(OUT_FIGS / "alpha_pred_vs_emp.png", dpi=200)
    plt.close(fig)
    print(f"  Saved figure: {OUT_FIGS / 'alpha_pred_vs_emp.png'}")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("Non-linear PDE: State-Dependent Recovery Experiment")
    print("  dD/dt' = -(k₀ + γ·D)·D")
    print("=" * 65)

    rb = _load_route_b()
    dt = _load_dt_all()
    print(f"\nRoute B events: {len(rb)}")

    # ── Prepare two datasets ──
    events_full = _prepare_event_data(dt, rb, use_monotone=False)
    events_mono = _prepare_event_data(dt, rb, use_monotone=True)
    n_full = sum(e["n_pts"] for e in events_full)
    n_mono = sum(e["n_pts"] for e in events_mono)
    print(f"Full post-peak: {len(events_full)} events, {n_full} pts")
    print(f"Monotone segment: {len(events_mono)} events, {n_mono} pts")

    # ══════════════════════════════════════════════════════════
    # Exp-N1: Log-log curvature
    # ══════════════════════════════════════════════════════════
    print("\n" + "─" * 65)
    print("Exp-N1: Log-log curvature (full post-peak)")
    print("─" * 65)

    curv = exp_n1(events_full)
    curv_ok = curv.dropna(subset=["a"])
    if len(curv_ok) >= 5:
        rho, p = stats.spearmanr(curv_ok["a"], curv_ok["D_peak"])
        frac_neg = (curv_ok["a"] < 0).sum()
        print(f"  Events with quadratic fit: {len(curv_ok)}")
        print(f"  Mean curvature a = {curv_ok['a'].mean():.4f}")
        print(f"  Fraction a < 0 (concave): {frac_neg}/{len(curv_ok)}")
        print(f"  ρ(a, D_peak) = {rho:.3f}, p = {p:.4f}")
        print(f"  Prediction: ρ < 0 (larger D_peak → more concave)")
    curv.to_csv(OUT_TABLES / "exp_n1_loglog_curvature.csv", index=False)

    # ══════════════════════════════════════════════════════════
    # Exp-N2: Global ODE fit (full post-peak)
    # ══════════════════════════════════════════════════════════
    print("\n" + "─" * 65)
    print("Exp-N2: Global ODE fit (full post-peak, with D_inf)")
    print("─" * 65)

    summ_full, ev_full = exp_n2(events_full)
    k0, gamma = summ_full["k0"], summ_full["gamma"]

    print(f"\n  Fitted: k₀ = {k0:.6f} h⁻¹,  γ = {gamma:.4f}")
    print(f"  Null (γ=0): k₀_null = {summ_full['k0_null']:.6f} h⁻¹")
    print(f"\n  ── Goodness of fit ──")
    print(f"  R²_ODE (total)   = {summ_full['r2_ode_total']:.4f}")
    print(f"  SSR_ODE           = {summ_full['ssr_ode']:.6f}")
    print(f"  SSR_PL (per-evt)  = {summ_full['ssr_pl']:.6f}")
    print(f"  SSR_null (γ=0)    = {summ_full['ssr_null']:.6f}")
    print(f"\n  ── BIC comparison (lower is better) ──")
    print(f"  BIC_ODE  = {summ_full['bic_ode']:.2f}  (k={summ_full['k_ode']})")
    print(f"  BIC_null = {summ_full['bic_null']:.2f}  (k={summ_full['k_null']})")
    print(f"  BIC_PL   = {summ_full['bic_pl']:.2f}  (k={summ_full['k_pl']})")
    print(f"  ΔBIC(ODE − PL)   = {summ_full['delta_bic_ode_vs_pl']:.2f}")
    print(f"  ΔBIC(ODE − null)  = {summ_full['delta_bic_ode_vs_null']:.2f}")

    if gamma > 0:
        print(f"\n  γ > 0 ⟹ recovery rate INCREASES with displacement")
        print(f"  Effective k_eff at peak (D_peak=0.40) = {k0 + gamma*0.40:.5f} h⁻¹")
        print(f"  Effective k_eff at peak (D_peak=0.06) = {k0 + gamma*0.06:.5f} h⁻¹")
        print(f"  Ratio: {(k0 + gamma*0.40)/(k0 + gamma*0.06):.2f}x")

    pd.DataFrame([summ_full]).to_csv(OUT_TABLES / "exp_n2_global_fit.csv", index=False)
    ev_full.to_csv(OUT_TABLES / "exp_n2_per_event.csv", index=False)

    # ── Repeat on monotone segment ──
    print("\n" + "─" * 65)
    print("Exp-N2b: Global ODE fit (monotone segment)")
    print("─" * 65)

    summ_mono, ev_mono = exp_n2(events_mono)
    k0m, gm = summ_mono["k0"], summ_mono["gamma"]
    print(f"  Fitted: k₀ = {k0m:.6f} h⁻¹,  γ = {gm:.4f}")
    print(f"  BIC_ODE  = {summ_mono['bic_ode']:.2f}  (k=2)")
    print(f"  BIC_PL   = {summ_mono['bic_pl']:.2f}  (k={summ_mono['k_pl']})")
    print(f"  ΔBIC     = {summ_mono['delta_bic_ode_vs_pl']:.2f}")

    pd.DataFrame([summ_mono]).to_csv(OUT_TABLES / "exp_n2_global_fit_mono.csv", index=False)
    ev_mono.to_csv(OUT_TABLES / "exp_n2_per_event_mono.csv", index=False)

    # ══════════════════════════════════════════════════════════
    # Exp-N3: Predict α from ODE
    # ══════════════════════════════════════════════════════════
    print("\n" + "─" * 65)
    print("Exp-N3: Predict α ranking from ODE (full post-peak)")
    print("─" * 65)

    alpha_df = exp_n3(events_full, k0, gamma)
    valid = alpha_df.dropna(subset=["alpha_emp", "alpha_pred"])
    if len(valid) >= 5:
        rho_pred, p_pred = stats.spearmanr(valid["alpha_pred"], valid["alpha_emp"])
        rho_keff, p_keff = stats.spearmanr(valid["k_eff_peak"], valid["alpha_emp"])
        print(f"  Events: {len(valid)}")
        print(f"  ρ(α_pred, α_emp)   = {rho_pred:.3f}, p = {p_pred:.4f}")
        print(f"  ρ(k_eff_peak, α_emp) = {rho_keff:.3f}, p = {p_keff:.4f}")
    alpha_df.to_csv(OUT_TABLES / "exp_n3_alpha_prediction.csv", index=False)

    # ── LOO ──
    print("\n  LOO cross-validation (may take a moment)...")
    loo_df = exp_n3_loo(events_full)
    loo_valid = loo_df.dropna(subset=["alpha_emp", "alpha_pred_loo"])
    if len(loo_valid) >= 5:
        rho_loo, p_loo = stats.spearmanr(loo_valid["alpha_pred_loo"],
                                          loo_valid["alpha_emp"])
        print(f"  ρ(α_pred_LOO, α_emp) = {rho_loo:.3f}, p = {p_loo:.4f}")
        gamma_range = loo_valid["gamma_loo"]
        print(f"  γ_LOO range: [{gamma_range.min():.4f}, {gamma_range.max():.4f}]")
        frac_pos = (gamma_range > 0).sum()
        print(f"  γ_LOO > 0 in {frac_pos}/{len(gamma_range)} folds")
    loo_df.to_csv(OUT_TABLES / "exp_n3_loo.csv", index=False)

    # ══════════════════════════════════════════════════════════
    # Figures
    # ══════════════════════════════════════════════════════════
    print("\n" + "─" * 65)
    print("Generating figures...")
    print("─" * 65)
    _plot_representative_fits(events_full, k0, gamma)
    _plot_alpha_scatter(alpha_df)

    # ══════════════════════════════════════════════════════════
    # Summary table
    # ══════════════════════════════════════════════════════════
    print("\n" + "─" * 65)
    print("Per-event summary (sorted by D_peak)")
    print("─" * 65)
    merged = alpha_df.merge(
        ev_full[["slug", "r2_ode", "r2_pl", "n_pts"]], on="slug", how="left"
    )
    merged = merged.sort_values("D_peak", ascending=False)
    cols = ["slug", "D_peak", "D_inf_norm", "alpha_emp", "alpha_pred",
            "k_eff_peak", "r2_ode", "r2_pl", "n_pts"]
    cols = [c for c in cols if c in merged.columns]
    print(merged[cols].to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}" if pd.notna(x) else "NaN",
    ))

    print("\n" + "=" * 65)
    print("Done. All outputs → " + str(OUT))
    print("=" * 65)


if __name__ == "__main__":
    main()
