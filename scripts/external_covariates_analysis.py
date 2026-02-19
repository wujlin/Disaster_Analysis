#!/usr/bin/env python3
"""
External covariates analysis: HDI / INFORM vs D_peak → α
=========================================================
检验假说：D_peak → α 的相关性是否被社会韧性（HDI / INFORM）调节。
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import t as tdist

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "cross_disaster_comparison" / "external_covariates" / "tables"

# ═══════════════════════════════════════════════════════════════
# Load & merge
# ═══════════════════════════════════════════════════════════════

rb = pd.read_csv(ROOT / "outputs" / "cross_disaster_comparison" / "Dt_decay" / "tables" / "Dt_routeB_sample_flags.csv")
rb = rb[rb["route_b_selected"] == True].copy()
for c in ["D_peak", "alpha", "near_delta_peak_windows_mean"]:
    rb[c] = pd.to_numeric(rb[c], errors="coerce")
rb = rb.rename(columns={"near_delta_peak_windows_mean": "delta_near"})

ext = pd.read_csv(OUT / "country_level_indicators.csv")
for c in ["HDI", "GDP_per_capita_PPP", "INFORM_risk", "INFORM_lack_coping", "INFORM_vulnerability"]:
    ext[c] = pd.to_numeric(ext[c], errors="coerce")

# External CSV uses mixed naming; build a lookup by both full slug and short_name
ext = ext.rename(columns={"slug": "ext_slug"})
ext_cols = ["ext_slug", "country_iso3", "country_name", "HDI", "GDP_per_capita_PPP",
            "INFORM_risk", "INFORM_lack_coping", "INFORM_vulnerability"]

# Build lookup: ext_slug → row
ext_lookup = ext.set_index("ext_slug")[ext_cols[1:]].to_dict("index")

# For each Route B event, try matching: full slug → ext_slug, then short_name → ext_slug
matched = []
for _, row in rb.iterrows():
    s, sn = row["slug"], row["short_name"]
    hit = ext_lookup.get(s) or ext_lookup.get(sn)
    if hit is None:
        # Fuzzy: ext_slug startswith short_name (handles truncation)
        for es, vals in ext_lookup.items():
            if es.startswith(sn) or sn.startswith(es):
                hit = vals
                break
    d = dict(row)
    if hit:
        d.update(hit)
    matched.append(d)

df = pd.DataFrame(matched)
n_matched = df["country_iso3"].notna().sum()
missing = df[df["HDI"].isna()]["slug"].tolist()
if missing:
    print(f"  WARNING: unmatched events ({len(missing)}): {missing}")
else:
    print(f"  All {n_matched} events matched successfully.")

print(f"Merged: {len(df)} events, {df['country_iso3'].nunique()} countries")
print(f"HDI range: {df['HDI'].min():.3f} – {df['HDI'].max():.3f}")
print()

# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def spearman(x, y, label=""):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    r, p = stats.spearmanr(x[ok], y[ok])
    n = ok.sum()
    return {"pair": label, "rho": r, "p": p, "n": int(n)}


def partial_spearman(x, y, z, label=""):
    """Spearman partial correlation ρ(x, y | z), single control."""
    x, y, z = np.asarray(x, float), np.asarray(y, float), np.asarray(z, float)
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    x, y, z = x[ok], y[ok], z[ok]
    n = len(x)
    rxy = stats.spearmanr(x, y).statistic
    rxz = stats.spearmanr(x, z).statistic
    ryz = stats.spearmanr(y, z).statistic
    denom = np.sqrt(1 - rxz**2) * np.sqrt(1 - ryz**2)
    r_p = (rxy - rxz * ryz) / denom if denom > 1e-12 else np.nan
    t_val = r_p * np.sqrt((n - 3) / (1 - r_p**2)) if abs(r_p) < 1 else np.inf
    p_val = 2 * tdist.sf(abs(t_val), n - 3)
    return {"pair": label, "rho": r_p, "p": p_val, "n": int(n)}


def partial_spearman_2(x, y, z1, z2, label=""):
    """Spearman partial correlation ρ(x, y | z1, z2), two controls."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    z1, z2 = np.asarray(z1, float), np.asarray(z2, float)
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z1) & np.isfinite(z2)
    x, y, z1, z2 = x[ok], y[ok], z1[ok], z2[ok]
    n = len(x)
    # Rank-transform then use Pearson partial
    from scipy.stats import rankdata
    rx, ry, rz1, rz2 = rankdata(x), rankdata(y), rankdata(z1), rankdata(z2)
    # Regress out z1, z2 from x and y
    Z = np.column_stack([rz1, rz2, np.ones(n)])
    bx = np.linalg.lstsq(Z, rx, rcond=None)[0]
    by = np.linalg.lstsq(Z, ry, rcond=None)[0]
    ex = rx - Z @ bx
    ey = ry - Z @ by
    r_p = np.corrcoef(ex, ey)[0, 1]
    t_val = r_p * np.sqrt((n - 4 - 1) / (1 - r_p**2)) if abs(r_p) < 1 else np.inf
    p_val = 2 * tdist.sf(abs(t_val), n - 4 - 1) if (n - 4 - 1) > 0 else np.nan
    return {"pair": label, "rho": r_p, "p": p_val, "n": int(n)}


# ═══════════════════════════════════════════════════════════════
# 1. Bivariate correlations: externals vs D_peak, α
# ═══════════════════════════════════════════════════════════════

print("=" * 65)
print("1. Bivariate Spearman correlations")
print("=" * 65)

ext_vars = ["HDI", "GDP_per_capita_PPP", "INFORM_risk", "INFORM_lack_coping", "INFORM_vulnerability"]
targets = ["D_peak", "alpha"]

biv_rows = []
for ev in ext_vars:
    for tgt in targets:
        r = spearman(df[ev], df[tgt], f"{ev} vs {tgt}")
        biv_rows.append(r)
        print(f"  ρ({ev:22s}, {tgt:6s}) = {r['rho']:+.3f}, p = {r['p']:.4f}")
    print()

# Also: δ_near vs externals
for ev in ext_vars:
    r = spearman(df[ev], df["delta_near"], f"{ev} vs delta_near")
    biv_rows.append(r)
print("  δ_near vs externals:")
for ev in ext_vars:
    r = [x for x in biv_rows if x["pair"] == f"{ev} vs delta_near"][0]
    print(f"  ρ({ev:22s}, δ_near) = {r['rho']:+.3f}, p = {r['p']:.4f}")

pd.DataFrame(biv_rows).to_csv(OUT / "bivariate_spearman.csv", index=False)

# ═══════════════════════════════════════════════════════════════
# 2. Partial correlations: D_peak → α controlling externals
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 65)
print("2. Partial Spearman: ρ(D_peak, α | control)")
print("=" * 65)

# Baseline (no control)
base = spearman(df["D_peak"], df["alpha"], "D_peak vs alpha (raw)")
print(f"\n  Baseline:  ρ(D_peak, α) = {base['rho']:+.3f}, p = {base['p']:.4f}")

part_rows = [base]
for ctrl in ext_vars:
    r = partial_spearman(df["D_peak"].values, df["alpha"].values, df[ctrl].values,
                         f"D_peak vs alpha | {ctrl}")
    part_rows.append(r)
    sig = "***" if r["p"] < 0.01 else "**" if r["p"] < 0.05 else "*" if r["p"] < 0.1 else "ns"
    print(f"  ρ(D_peak, α | {ctrl:22s}) = {r['rho']:+.3f}, p = {r['p']:.4f} {sig}")

# Double controls
print("\n  Double controls:")
double_pairs = [
    ("HDI", "delta_near"),
    ("INFORM_lack_coping", "delta_near"),
    ("GDP_per_capita_PPP", "delta_near"),
]
for c1, c2 in double_pairs:
    r = partial_spearman_2(df["D_peak"].values, df["alpha"].values,
                           df[c1].values, df[c2].values,
                           f"D_peak vs alpha | {c1}+{c2}")
    part_rows.append(r)
    sig = "***" if r["p"] < 0.01 else "**" if r["p"] < 0.05 else "*" if r["p"] < 0.1 else "ns"
    print(f"  ρ(D_peak, α | {c1}+{c2}) = {r['rho']:+.3f}, p = {r['p']:.4f} {sig}")

pd.DataFrame(part_rows).to_csv(OUT / "partial_spearman_dpeak_alpha.csv", index=False)

# ═══════════════════════════════════════════════════════════════
# 3. Partial correlations: δ_near → α controlling externals
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 65)
print("3. Partial Spearman: ρ(δ_near, α | control)")
print("=" * 65)

base_dn = spearman(df["delta_near"], df["alpha"], "delta_near vs alpha (raw)")
print(f"\n  Baseline:  ρ(δ_near, α) = {base_dn['rho']:+.3f}, p = {base_dn['p']:.4f}")

dn_rows = [base_dn]
for ctrl in ext_vars:
    r = partial_spearman(df["delta_near"].values, df["alpha"].values, df[ctrl].values,
                         f"delta_near vs alpha | {ctrl}")
    dn_rows.append(r)
    sig = "***" if r["p"] < 0.01 else "**" if r["p"] < 0.05 else "*" if r["p"] < 0.1 else "ns"
    print(f"  ρ(δ_near, α | {ctrl:22s}) = {r['rho']:+.3f}, p = {r['p']:.4f} {sig}")

pd.DataFrame(dn_rows).to_csv(OUT / "partial_spearman_delta_near_alpha.csv", index=False)

# ═══════════════════════════════════════════════════════════════
# 4. Key diagnostic: does HDI mediate or confound?
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 65)
print("4. Mediation diagnostic")
print("=" * 65)

# If HDI → D_peak AND HDI → α, then HDI could be confounder
# If D_peak → α persists after controlling HDI, then HDI is NOT the explanation
r_hdi_dp = spearman(df["HDI"], df["D_peak"], "HDI vs D_peak")
r_hdi_a = spearman(df["HDI"], df["alpha"], "HDI vs alpha")
r_dp_a_ctrl = [x for x in part_rows if x["pair"] == "D_peak vs alpha | HDI"][0]

print(f"\n  Path a: ρ(HDI, D_peak) = {r_hdi_dp['rho']:+.3f}, p = {r_hdi_dp['p']:.4f}")
print(f"  Path b: ρ(HDI, α)     = {r_hdi_a['rho']:+.3f}, p = {r_hdi_a['p']:.4f}")
print(f"  Direct:  ρ(D_peak, α | HDI) = {r_dp_a_ctrl['rho']:+.3f}, p = {r_dp_a_ctrl['p']:.4f}")

if abs(r_hdi_dp["rho"]) < 0.3 and r_hdi_dp["p"] > 0.1:
    print("\n  → HDI does NOT predict D_peak → cannot be confounder")
elif r_dp_a_ctrl["p"] < 0.05:
    print("\n  → D_peak → α survives HDI control → HDI is partial mediator at best")
else:
    print("\n  → D_peak → α vanishes after HDI control → HDI may be the driver")

# Same for INFORM_lack_coping
r_ic_dp = spearman(df["INFORM_lack_coping"], df["D_peak"], "INFORM_lack_coping vs D_peak")
r_ic_a = spearman(df["INFORM_lack_coping"], df["alpha"], "INFORM_lack_coping vs alpha")
r_dp_a_ctrl_ic = [x for x in part_rows if x["pair"] == "D_peak vs alpha | INFORM_lack_coping"][0]

print(f"\n  Path a: ρ(INFORM_lack_coping, D_peak) = {r_ic_dp['rho']:+.3f}, p = {r_ic_dp['p']:.4f}")
print(f"  Path b: ρ(INFORM_lack_coping, α)     = {r_ic_a['rho']:+.3f}, p = {r_ic_a['p']:.4f}")
print(f"  Direct:  ρ(D_peak, α | INFORM_lack_coping) = {r_dp_a_ctrl_ic['rho']:+.3f}, p = {r_dp_a_ctrl_ic['p']:.4f}")

# ═══════════════════════════════════════════════════════════════
# 5. Full summary table
# ═══════════════════════════════════════════════════════════════

print("\n" + "=" * 65)
print("5. Per-event data (sorted by D_peak)")
print("=" * 65)

cols = ["slug", "country_iso3", "D_peak", "alpha", "delta_near",
        "HDI", "INFORM_lack_coping"]
print(df.sort_values("D_peak", ascending=False)[cols].to_string(
    index=False,
    float_format=lambda x: f"{x:.3f}" if pd.notna(x) else "NaN",
))

print("\nDone. All outputs → " + str(OUT))
