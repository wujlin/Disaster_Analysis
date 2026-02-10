#!/usr/bin/env python3
"""
D(t) 衰减分析：Robustness checks + 论文级可视化

Robustness 1: bounce tolerance 敏感性 (mono_tol_up ∈ {1.00, 1.02, 1.05, 1.10, 1.20})
Robustness 2: r_max 敏感性 (100, 150, 200, 300 km)
Robustness 3: near_thresh 敏感性 (0.01, 0.02, 0.05)

论文图:
  Fig1 (3-panel): 核心 story 的一页总结
    (a) D(t)/D_peak log-log decay curves, EVAC vs INFL 分色 + 参考 power-law 线
    (b) α 分布: EVAC vs INFL jitter-strip + 均值 ± sem
    (c) α 按灾难类型分布: 证明 event_type 比 disaster_type 更重要
  Fig2 (2-panel): Robustness summary
    (a) α vs mono_tol_up 敏感性
    (b) α vs r_max 敏感性
"""

from __future__ import annotations

import sys
from pathlib import Path

# ── path setup ──
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import numpy as np
import pandas as pd
from scipy import stats

from disaster import plot_style as ps
from disaster.dt_decay import (
    _compute_dt_timeseries,
    _discover_events,
    _load_metadata,
    _load_phi_rt_long,
    _pick_peak,
    _classify_event,
    _monotone_decay_segment,
    _fit_powerlaw_loglog,
    _short_name,
)

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D

# ── constants ──
OUTPUT_ROOT = REPO / "outputs"
OUT_DIR = OUTPUT_ROOT / "cross_disaster_comparison" / "Dt_decay"
TABS = OUT_DIR / "tables"
FIGS = OUT_DIR / "figures"
FIGS.mkdir(parents=True, exist_ok=True)

# Okabe-Ito semantic colors
C_EVAC = ps.OKABE_ITO["vermillion"]
C_INFL = ps.OKABE_ITO["blue"]
C_NEUT = ps.OKABE_ITO["gray"]
COLOR_MAP = {"EVAC": C_EVAC, "INFL": C_INFL, "NEUTRAL": C_NEUT, "LOW_SIGNAL": C_NEUT}

# Disaster type markers
DTYPE_MARKER = {
    "hurricane": "o",
    "typhoon": "s",
    "tropical_storm": "D",
    "flood": "^",
    "earthquake": "P",
    "wildfire": "X",
}


# ════════════════════════════════════════════════════════════════
# Helper: compute α for arbitrary parameters
# ════════════════════════════════════════════════════════════════
def _compute_all_alphas(
    *,
    r_max_km: float = 200.0,
    near_r_km: float = 50.0,
    min_tiles_overlap: int = 3,
    min_r_bins: int = 5,
    min_near_bins: int = 2,
    peak_min_hours: float | None = None,
    peak_max_hours: float | None = None,
    D_peak_min: float = 0.03,
    min_time_windows: int = 5,
    peak_frac: float = 0.5,
    near_thresh: float = 0.02,
    mono_tol_up: float = 1.05,
) -> pd.DataFrame:
    """Return a DataFrame with one row per event: short_name, event_type, disaster_type, alpha, r2, n_mono, D_peak."""
    refs = {r.slug: r for r in _discover_events(OUTPUT_ROOT)}
    rows = []
    for slug in sorted(refs):
        ref = refs[slug]
        name, disaster_type = _load_metadata(ref.output_root, slug)
        try:
            df = _load_phi_rt_long(ref.output_root, slug)
        except Exception:
            continue

        ts = _compute_dt_timeseries(
            df,
            r_max_km=r_max_km,
            near_r_km=near_r_km,
            min_tiles_overlap=min_tiles_overlap,
            min_r_bins=min_r_bins,
            min_near_bins=min_near_bins,
        )
        if ts.empty:
            continue

        t_peak, D_peak = _pick_peak(ts, peak_min_hours=peak_min_hours, peak_max_hours=peak_max_hours)
        event_type, near_mean = _classify_event(
            ts,
            D_peak=float(D_peak),
            D_peak_min=D_peak_min,
            min_time_windows=min_time_windows,
            peak_frac=peak_frac,
            near_thresh=near_thresh,
        )
        if event_type in {"EXCLUDED_SHORT"} or not np.isfinite(D_peak) or D_peak <= 0:
            continue

        post = ts[ts["hours_since_quake"] > t_peak].copy()
        post = post.sort_values("hours_since_quake").reset_index(drop=True)
        post["t_prime_h"] = post["hours_since_quake"] - t_peak
        post["D_norm"] = post["D"] / D_peak

        mono = _monotone_decay_segment(post[["t_prime_h", "D_norm"]].copy(), tol_up=mono_tol_up)
        alpha, logA, r2 = _fit_powerlaw_loglog(
            mono["t_prime_h"].values if not mono.empty else np.array([]),
            mono["D_norm"].values if not mono.empty else np.array([]),
        )
        rows.append({
            "slug": slug,
            "short_name": _short_name(slug),
            "disaster_type": disaster_type,
            "event_type": event_type,
            "D_peak": D_peak,
            "t_peak_hours": t_peak,
            "n_mono": len(mono),
            "alpha": alpha,
            "logA": logA,
            "r2": r2,
        })
    return pd.DataFrame(rows)


# ════════════════════════════════════════════════════════════════
# Robustness 1: bounce tolerance
# ════════════════════════════════════════════════════════════════
def robustness_bounce_tolerance():
    print("── Robustness 1: bounce tolerance ──")
    tols = [1.00, 1.02, 1.05, 1.10, 1.20]
    all_dfs = []
    for tol in tols:
        df = _compute_all_alphas(mono_tol_up=tol)
        df["mono_tol_up"] = tol
        all_dfs.append(df)
    combined = pd.concat(all_dfs, ignore_index=True)
    combined.to_csv(TABS / "robustness_bounce_tolerance.csv", index=False)
    print(f"  saved {len(combined)} rows")
    return combined


# ════════════════════════════════════════════════════════════════
# Robustness 2: r_max
# ════════════════════════════════════════════════════════════════
def robustness_r_max():
    print("── Robustness 2: r_max ──")
    r_maxes = [100.0, 150.0, 200.0, 300.0]
    all_dfs = []
    for r in r_maxes:
        df = _compute_all_alphas(r_max_km=r)
        df["r_max_km"] = r
        all_dfs.append(df)
    combined = pd.concat(all_dfs, ignore_index=True)
    combined.to_csv(TABS / "robustness_r_max.csv", index=False)
    print(f"  saved {len(combined)} rows")
    return combined


# ════════════════════════════════════════════════════════════════
# Robustness 3: near_thresh
# ════════════════════════════════════════════════════════════════
def robustness_near_thresh():
    print("── Robustness 3: near_thresh ──")
    thresholds = [0.01, 0.02, 0.05]
    all_dfs = []
    for th in thresholds:
        df = _compute_all_alphas(near_thresh=th)
        df["near_thresh"] = th
        all_dfs.append(df)
    combined = pd.concat(all_dfs, ignore_index=True)
    combined.to_csv(TABS / "robustness_near_thresh.csv", index=False)
    print(f"  saved {len(combined)} rows")
    return combined


# ════════════════════════════════════════════════════════════════
# Statistical test helper
# ════════════════════════════════════════════════════════════════
def _stat_test(evac_a, infl_a):
    """Return dict with Mann-Whitney p, Welch t p, Cohen's d, eta2."""
    if len(evac_a) < 2 or len(infl_a) < 2:
        return {}
    _, p_mw = stats.mannwhitneyu(evac_a, infl_a, alternative='greater')
    _, p_t = stats.ttest_ind(evac_a, infl_a, equal_var=False, alternative='greater')
    pooled = np.sqrt((np.std(evac_a, ddof=1)**2 + np.std(infl_a, ddof=1)**2) / 2)
    d = (np.mean(evac_a) - np.mean(infl_a)) / pooled if pooled > 0 else np.nan
    all_a = np.concatenate([evac_a, infl_a])
    ss_b = len(evac_a)*(np.mean(evac_a)-np.mean(all_a))**2 + len(infl_a)*(np.mean(infl_a)-np.mean(all_a))**2
    ss_t = np.sum((all_a - np.mean(all_a))**2)
    eta2 = ss_b / ss_t if ss_t > 0 else np.nan
    return {"p_mw": p_mw, "p_t": p_t, "d": d, "eta2": eta2}


# ════════════════════════════════════════════════════════════════
# Figure 1: Core Story (3-panel)
# ════════════════════════════════════════════════════════════════
def figure_core_story():
    """
    3-panel figure that tells the entire story:
    (a) D/D_peak decay (log-log) with reference slopes
    (b) α distribution: EVAC vs INFL
    (c) α by disaster type, colored by event_type
    """
    print("── Figure 1: Core story ──")

    # Load data
    dt_df = pd.read_csv(TABS / "Dt_all_events.csv")
    fits_df = pd.read_csv(TABS / "Dt_powerlaw_fits.csv")
    valid = fits_df[fits_df["n_mono"] >= 3].copy()

    # ── Build post-peak data ──
    d = dt_df.copy()
    d["hours_since_quake"] = pd.to_numeric(d["hours_since_quake"], errors="coerce")
    d["t_peak_hours"] = pd.to_numeric(d["t_peak_hours"], errors="coerce")
    d["D_norm"] = pd.to_numeric(d["D_norm"], errors="coerce")
    d = d[d["hours_since_quake"] > d["t_peak_hours"]].copy()
    d["t_prime_h"] = d["hours_since_quake"] - d["t_peak_hours"]
    d = d[(d["t_prime_h"] > 0) & (d["D_norm"] > 0)].copy()

    with ps.paper_style():
        fig = plt.figure(figsize=(7.2, 3.2), constrained_layout=True)
        gs = fig.add_gridspec(1, 3, width_ratios=[1.25, 0.75, 1.0])
        ax_a = fig.add_subplot(gs[0])
        ax_b = fig.add_subplot(gs[1])
        ax_c = fig.add_subplot(gs[2])

        # ════ Panel (a): Decay curves ════
        # Strategy: scatter (no lines → no zigzag) + binned median band

        evac_valid = valid[valid["event_type"] == "EVAC"]
        infl_valid = valid[valid["event_type"] == "INFL"]
        alpha_evac = evac_valid["alpha"].mean() if len(evac_valid) else 0.674
        alpha_infl = infl_valid["alpha"].mean() if len(infl_valid) else 0.147

        # 1) Individual data points as faint scatter
        for et, c, z, a, ms in [("INFL", C_INFL, 1, 0.18, 8),
                                  ("EVAC", C_EVAC, 2, 0.30, 10)]:
            sub = d[d["event_type"] == et]
            x = sub["t_prime_h"].values
            y = sub["D_norm"].values
            ok = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
            ax_a.scatter(x[ok], y[ok], color=c, s=ms, alpha=a,
                         linewidths=0, zorder=z, rasterized=True)

        # 2) Binned median ± IQR band (log-spaced bins)
        bin_edges = np.geomspace(8, 500, 12)
        for et, c, z in [("INFL", C_INFL, 3), ("EVAC", C_EVAC, 4)]:
            sub = d[d["event_type"] == et].copy()
            sub = sub[(sub["t_prime_h"] > 0) & (sub["D_norm"] > 0)]
            meds, q25s, q75s, bin_centers = [], [], [], []
            for j in range(len(bin_edges) - 1):
                lo, hi = bin_edges[j], bin_edges[j + 1]
                vals = sub[(sub["t_prime_h"] >= lo) & (sub["t_prime_h"] < hi)]["D_norm"].values
                vals = vals[np.isfinite(vals)]
                if len(vals) < 3:
                    continue
                meds.append(np.median(vals))
                q25s.append(np.percentile(vals, 25))
                q75s.append(np.percentile(vals, 75))
                bin_centers.append(np.sqrt(lo * hi))  # geometric center
            if meds:
                bc = np.array(bin_centers)
                ax_a.fill_between(bc, q25s, q75s, color=c, alpha=0.18, zorder=z, linewidth=0)
                ax_a.plot(bc, meds, color=c, lw=2.2, alpha=0.85, zorder=z + 1)

        # 3) Reference power-law dashed lines
        t_ref = np.geomspace(8, 400, 100)
        y_evac_ref = 0.7 * (t_ref / 16) ** (-alpha_evac)
        y_infl_ref = 0.7 * (t_ref / 16) ** (-alpha_infl)
        ax_a.plot(t_ref, y_evac_ref, color=C_EVAC, ls="--", lw=1.5, alpha=0.7,
                  label=f"$t'^{{-{alpha_evac:.2f}}}$", zorder=6)
        ax_a.plot(t_ref, y_infl_ref, color=C_INFL, ls="--", lw=1.5, alpha=0.7,
                  label=f"$t'^{{-{alpha_infl:.2f}}}$", zorder=6)

        ax_a.set_xscale("log")
        ax_a.set_yscale("log")
        ax_a.set_xlabel("$t'$ (hours after peak)")
        ax_a.set_ylabel("$D(t') \\,/\\, D_{\\mathrm{peak}}$")
        ax_a.set_xlim(6, 600)
        ax_a.set_ylim(0.03, 2.0)

        # Custom legend: colored line = median, band = IQR
        leg_elements = [
            Line2D([0], [0], color=C_EVAC, lw=2.0, label="EVAC median"),
            Line2D([0], [0], color=C_INFL, lw=2.0, label="INFL median"),
            Line2D([0], [0], color=C_EVAC, ls="--", lw=1.2, label=f"$t'^{{-{alpha_evac:.2f}}}$"),
            Line2D([0], [0], color=C_INFL, ls="--", lw=1.2, label=f"$t'^{{-{alpha_infl:.2f}}}$"),
        ]
        ax_a.legend(handles=leg_elements, fontsize=6.5, loc="lower left",
                    frameon=False, handlelength=1.6, labelspacing=0.3)
        ps.despine(ax_a)

        # ════ Panel (b): α distribution ════
        evac_a = evac_valid["alpha"].values
        infl_a = infl_valid["alpha"].values

        # Jitter strip plot
        rng = np.random.default_rng(42)
        jitter = 0.08

        # EVAC points
        x_evac = rng.normal(loc=0, scale=jitter, size=len(evac_a))
        ax_b.scatter(x_evac, evac_a, color=C_EVAC, s=35, alpha=0.85, zorder=3,
                     edgecolors="white", linewidths=0.5)
        # INFL points
        x_infl = rng.normal(loc=1, scale=jitter, size=len(infl_a))
        ax_b.scatter(x_infl, infl_a, color=C_INFL, s=35, alpha=0.85, zorder=3,
                     edgecolors="white", linewidths=0.5)

        # Mean ± SEM bars
        for i, (vals, color) in enumerate([(evac_a, C_EVAC), (infl_a, C_INFL)]):
            m = np.mean(vals)
            sem = np.std(vals, ddof=1) / np.sqrt(len(vals))
            ax_b.errorbar(i, m, yerr=sem, fmt="none", color="black", capsize=4, capthick=1.5, lw=1.5, zorder=5)
            ax_b.scatter([i], [m], marker="_", s=200, color="black", lw=2.0, zorder=5)

        # p-value annotation
        st = _stat_test(evac_a, infl_a)
        p_str = f"p = {st['p_mw']:.3f}" if st.get("p_mw") else ""
        d_str = f"d = {st['d']:.1f}" if st.get("d") else ""
        y_top = max(np.max(evac_a), np.max(infl_a)) * 1.08
        # bracket
        ax_b.plot([0, 0, 1, 1], [y_top, y_top*1.05, y_top*1.05, y_top],
                  color="black", lw=1.0, clip_on=False)
        ax_b.text(0.5, y_top*1.08, f"{p_str}\n{d_str}", ha="center", va="bottom",
                  fontsize=7, color="black")

        ax_b.set_xticks([0, 1])
        ax_b.set_xticklabels(["EVAC", "INFL"])
        ax_b.set_ylabel("$\\alpha$ (decay exponent)")
        ax_b.set_xlim(-0.5, 1.5)
        ax_b.axhline(0, color="#cccccc", lw=0.7, ls=":", zorder=0)
        ps.despine(ax_b)

        # ════ Panel (c): α by disaster type ════
        # Each event is one point: x = disaster_type, y = alpha, color = event_type
        plot_df = valid[valid["event_type"].isin(["EVAC", "INFL"])].copy()

        # Normalize disaster_type
        def _norm_dtype(s):
            s = str(s).lower().strip()
            if "hurricane" in s or "tropical" in s or "typhoon" in s:
                return "cyclone"
            if "flood" in s:
                return "flood"
            if "earthquake" in s:
                return "earthquake"
            if "wildfire" in s or "fire" in s:
                return "wildfire"
            return s

        plot_df["dtype_norm"] = plot_df["disaster_type"].apply(_norm_dtype)
        dtype_order = ["cyclone", "flood", "earthquake", "wildfire"]
        dtype_present = [d for d in dtype_order if d in plot_df["dtype_norm"].values]

        for i, dtype in enumerate(dtype_present):
            sub = plot_df[plot_df["dtype_norm"] == dtype]
            for _, row in sub.iterrows():
                c = COLOR_MAP[row["event_type"]]
                jit = rng.normal(0, 0.08)
                marker = "o" if row["event_type"] == "EVAC" else "s"
                ax_c.scatter(i + jit, row["alpha"], color=c, s=40, alpha=0.85,
                             edgecolors="white", linewidths=0.5, zorder=3,
                             marker=marker)

        ax_c.set_xticks(range(len(dtype_present)))
        ax_c.set_xticklabels([d.capitalize() for d in dtype_present], fontsize=9)
        ax_c.set_ylabel("$\\alpha$")
        ax_c.axhline(0, color="#cccccc", lw=0.7, ls=":", zorder=0)

        # Add horizontal bands for EVAC/INFL mean ± std
        ax_c.axhspan(np.mean(evac_a) - np.std(evac_a, ddof=1),
                     np.mean(evac_a) + np.std(evac_a, ddof=1),
                     color=C_EVAC, alpha=0.10, zorder=0, label="EVAC range")
        ax_c.axhspan(np.mean(infl_a) - np.std(infl_a, ddof=1),
                     np.mean(infl_a) + np.std(infl_a, ddof=1),
                     color=C_INFL, alpha=0.10, zorder=0, label="INFL range")

        # Custom legend for panel c
        legend_elements = [
            Line2D([0], [0], marker="o", color="w", markerfacecolor=C_EVAC,
                   markersize=6, label="EVAC"),
            Line2D([0], [0], marker="s", color="w", markerfacecolor=C_INFL,
                   markersize=6, label="INFL"),
        ]
        ax_c.legend(handles=legend_elements, fontsize=7, frameon=False, loc="upper right")

        ps.despine(ax_c)

        # Panel labels
        for ax, label in zip([ax_a, ax_b, ax_c], ["a", "b", "c"]):
            ps.add_panel_label(ax, label)

        # Save
        ps.save_figure(fig, FIGS / "Fig1_core_story.png", dpi=300)
        ps.save_figure(fig, FIGS / "Fig1_core_story.pdf")
        plt.close(fig)
        print("  saved Fig1_core_story")


# ════════════════════════════════════════════════════════════════
# Figure 2: Robustness summary (2-panel)
# ════════════════════════════════════════════════════════════════
def figure_robustness(rob_tol, rob_rmax):
    """
    2-panel: α stability under parameter variations.
    (a) bounce tolerance sensitivity
    (b) r_max sensitivity
    """
    print("── Figure 2: Robustness ──")

    with ps.paper_style():
        fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(6.5, 3.0), constrained_layout=True)

        # ════ Panel (a): bounce tolerance ════
        valid_tol = rob_tol[rob_tol["n_mono"] >= 3].copy()

        for et, color in [("EVAC", C_EVAC), ("INFL", C_INFL)]:
            sub = valid_tol[valid_tol["event_type"] == et]
            # Group by tol, compute mean ± sem
            grouped = sub.groupby("mono_tol_up")["alpha"].agg(["mean", "std", "count"]).reset_index()
            grouped["sem"] = grouped["std"] / np.sqrt(grouped["count"])
            x = grouped["mono_tol_up"].values
            y = grouped["mean"].values
            yerr = grouped["sem"].values
            ax_a.errorbar(x, y, yerr=yerr, color=color, marker="o", ms=5, lw=1.5,
                          capsize=3, label=et, alpha=0.9)

        ax_a.set_xlabel("Bounce tolerance")
        ax_a.set_ylabel("$\\bar{\\alpha}$ (mean ± SEM)")
        ax_a.legend(fontsize=8, frameon=False)
        ps.despine(ax_a)

        # p-value at each tol
        for tol in sorted(valid_tol["mono_tol_up"].unique()):
            ev = valid_tol[(valid_tol["mono_tol_up"] == tol) & (valid_tol["event_type"] == "EVAC")]["alpha"].values
            inf = valid_tol[(valid_tol["mono_tol_up"] == tol) & (valid_tol["event_type"] == "INFL")]["alpha"].values
            if len(ev) >= 2 and len(inf) >= 2:
                _, p = stats.mannwhitneyu(ev, inf, alternative="greater")
                y_pos = max(np.mean(ev), np.mean(inf)) + 0.15
                sig = "**" if p < 0.01 else "*" if p < 0.05 else "ns"
                ax_a.text(tol, y_pos, sig, ha="center", fontsize=7, color="#333333")

        # ════ Panel (b): r_max ════
        valid_rmax = rob_rmax[rob_rmax["n_mono"] >= 3].copy()

        for et, color in [("EVAC", C_EVAC), ("INFL", C_INFL)]:
            sub = valid_rmax[valid_rmax["event_type"] == et]
            grouped = sub.groupby("r_max_km")["alpha"].agg(["mean", "std", "count"]).reset_index()
            grouped["sem"] = grouped["std"] / np.sqrt(grouped["count"])
            x = grouped["r_max_km"].values
            y = grouped["mean"].values
            yerr = grouped["sem"].values
            ax_b.errorbar(x, y, yerr=yerr, color=color, marker="o", ms=5, lw=1.5,
                          capsize=3, label=et, alpha=0.9)

        ax_b.set_xlabel("$r_{\\max}$ (km)")
        ax_b.set_ylabel("$\\bar{\\alpha}$ (mean ± SEM)")
        ax_b.legend(fontsize=8, frameon=False)
        ps.despine(ax_b)

        # p-value at each r_max
        for rmax in sorted(valid_rmax["r_max_km"].unique()):
            ev = valid_rmax[(valid_rmax["r_max_km"] == rmax) & (valid_rmax["event_type"] == "EVAC")]["alpha"].values
            inf = valid_rmax[(valid_rmax["r_max_km"] == rmax) & (valid_rmax["event_type"] == "INFL")]["alpha"].values
            if len(ev) >= 2 and len(inf) >= 2:
                _, p = stats.mannwhitneyu(ev, inf, alternative="greater")
                y_pos = max(np.mean(ev), np.mean(inf)) + 0.15
                sig = "**" if p < 0.01 else "*" if p < 0.05 else "ns"
                ax_b.text(rmax, y_pos, sig, ha="center", fontsize=7, color="#333333")

        for ax, label in zip([ax_a, ax_b], ["a", "b"]):
            ps.add_panel_label(ax, label)

        ps.save_figure(fig, FIGS / "Fig2_robustness.png", dpi=300)
        ps.save_figure(fig, FIGS / "Fig2_robustness.pdf")
        plt.close(fig)
        print("  saved Fig2_robustness")


# ════════════════════════════════════════════════════════════════
# Figure 3: Robustness — near_thresh sensitivity
# ════════════════════════════════════════════════════════════════
def figure_robustness_thresh(rob_thresh):
    """Single panel: how many events per type & α change with near_thresh."""
    print("── Figure 3: near_thresh sensitivity ──")

    valid = rob_thresh[rob_thresh["n_mono"] >= 3].copy()

    with ps.paper_style():
        fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(6.0, 2.8), constrained_layout=True)

        thresholds = sorted(valid["near_thresh"].unique())

        # (a) event count by type vs threshold
        for et, color in [("EVAC", C_EVAC), ("INFL", C_INFL), ("NEUTRAL", C_NEUT)]:
            counts = []
            for th in thresholds:
                n = len(valid[(valid["near_thresh"] == th) & (valid["event_type"] == et)])
                counts.append(n)
            ax_a.plot(thresholds, counts, marker="o", color=color, lw=1.5, ms=5, label=et)

        ax_a.set_xlabel("near_thresh")
        ax_a.set_ylabel("# events with valid fit")
        ax_a.legend(fontsize=7, frameon=False)
        ps.despine(ax_a)

        # (b) α mean ± sem vs threshold
        for et, color in [("EVAC", C_EVAC), ("INFL", C_INFL)]:
            means, sems = [], []
            for th in thresholds:
                vals = valid[(valid["near_thresh"] == th) & (valid["event_type"] == et)]["alpha"].values
                means.append(np.mean(vals) if len(vals) else np.nan)
                sems.append(np.std(vals, ddof=1)/np.sqrt(len(vals)) if len(vals) >= 2 else 0)
            ax_b.errorbar(thresholds, means, yerr=sems, color=color, marker="o", ms=5,
                          lw=1.5, capsize=3, label=et, alpha=0.9)

        ax_b.set_xlabel("near_thresh")
        ax_b.set_ylabel("$\\bar{\\alpha}$ (mean ± SEM)")
        ax_b.legend(fontsize=7, frameon=False)
        ps.despine(ax_b)

        for ax, label in zip([ax_a, ax_b], ["a", "b"]):
            ps.add_panel_label(ax, label)

        ps.save_figure(fig, FIGS / "Fig3_robustness_thresh.png", dpi=300)
        ps.save_figure(fig, FIGS / "Fig3_robustness_thresh.pdf")
        plt.close(fig)
        print("  saved Fig3_robustness_thresh")


# ════════════════════════════════════════════════════════════════
# Robustness summary table
# ════════════════════════════════════════════════════════════════
def robustness_summary_table(rob_tol, rob_rmax, rob_thresh):
    """Produce a tidy summary: for each condition, EVAC ᾱ, INFL ᾱ, p, d."""
    print("── Robustness summary table ──")
    rows = []

    def _add(name, param_name, param_val, df):
        v = df[df["n_mono"] >= 3].copy()
        ea = v[v["event_type"] == "EVAC"]["alpha"].values
        ia = v[v["event_type"] == "INFL"]["alpha"].values
        st = _stat_test(ea, ia)
        rows.append({
            "test": name,
            "param": param_name,
            "value": param_val,
            "n_evac": len(ea),
            "n_infl": len(ia),
            "alpha_evac_mean": np.mean(ea) if len(ea) else np.nan,
            "alpha_evac_std": np.std(ea, ddof=1) if len(ea) >= 2 else np.nan,
            "alpha_infl_mean": np.mean(ia) if len(ia) else np.nan,
            "alpha_infl_std": np.std(ia, ddof=1) if len(ia) >= 2 else np.nan,
            "p_mannwhitney": st.get("p_mw", np.nan),
            "p_welch": st.get("p_t", np.nan),
            "cohens_d": st.get("d", np.nan),
            "eta2": st.get("eta2", np.nan),
        })

    for tol in sorted(rob_tol["mono_tol_up"].unique()):
        _add("bounce_tol", "mono_tol_up", tol, rob_tol[rob_tol["mono_tol_up"] == tol])
    for r in sorted(rob_rmax["r_max_km"].unique()):
        _add("r_max", "r_max_km", r, rob_rmax[rob_rmax["r_max_km"] == r])
    for th in sorted(rob_thresh["near_thresh"].unique()):
        _add("near_thresh", "near_thresh", th, rob_thresh[rob_thresh["near_thresh"] == th])

    out = pd.DataFrame(rows)
    out.to_csv(TABS / "robustness_summary.csv", index=False)
    print(out.to_string(index=False))
    return out


# ════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("D(t) Robustness Checks & Publication Figures")
    print("=" * 60)

    # Run robustness checks
    rob_tol = robustness_bounce_tolerance()
    rob_rmax = robustness_r_max()
    rob_thresh = robustness_near_thresh()

    # Summary table
    robustness_summary_table(rob_tol, rob_rmax, rob_thresh)

    # Figures
    figure_core_story()
    figure_robustness(rob_tol, rob_rmax)
    figure_robustness_thresh(rob_thresh)

    print("\n✅ All done!")
