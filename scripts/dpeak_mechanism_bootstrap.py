#!/usr/bin/env python3
"""路径 1 实验 — Bootstrap 稳健性检验

检验内容：
  1. Exp-B 参数 (k₀, β, Ds) 的 bootstrap 置信区间
  2. ρ(α_pred, α_emp) 和 ρ(α_pred, D_peak) 的 bootstrap CI
  3. β > 0 的稳健性（多少比例 bootstrap 样本中 β > 0？）
  4. Permutation test: Exp-B 相对 Global 模型的改善是否显著
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import j0, jn_zeros
from scipy.stats import spearmanr
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent
SD_TABLES = ROOT / "outputs" / "cross_disaster_comparison" / "spatial_diffusion_results" / "tables"

np.random.seed(42)

# ---------------------------------------------------------------------------
# PDE 预测核心
# ---------------------------------------------------------------------------
N_MODES = 10
R_MAX = 200.0
N_GRID = 200

r_grid = np.linspace(0.0, R_MAX, N_GRID)
roots = np.concatenate([[0.0], jn_zeros(0, N_MODES - 1)])
basis_matrix = np.vstack([
    j0(root * r_grid / R_MAX) if abs(root) > 1e-12 else np.ones_like(r_grid)
    for root in roots
])

t_early = np.arange(0.0, 24.0, 1.0)
t_late = np.arange(24.0, 248.1, 8.0)
t_eval = np.unique(np.concatenate([t_early, t_late]))


def _predict_alpha(coeffs, k, Ds):
    """单事件 α_pred。"""
    if k < 1e-7:
        return np.nan
    lambdas = k + Ds * (roots / R_MAX) ** 2
    decays = np.exp(-np.outer(t_eval, lambdas))
    delta_rt = decays @ (coeffs[:, None] * basis_matrix)
    w = np.maximum(r_grid, 1e-12)
    E_vals = np.average(delta_rt ** 2, weights=w, axis=1)
    ok = (t_eval >= 1.0) & (t_eval <= 120.0) & (E_vals > 0)
    if np.sum(ok) < 3:
        return np.nan
    slope, _ = np.polyfit(np.log(t_eval[ok]), np.log(E_vals[ok]), 1)
    return float(-slope)


def _spearman(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    n = int(np.sum(ok))
    if n < 5 or np.std(x[ok]) < 1e-12 or np.std(y[ok]) < 1e-12:
        return 0.0, 1.0
    rho, p = spearmanr(x[ok], y[ok])
    return float(rho), float(p)


# ---------------------------------------------------------------------------
# 加载数据
# ---------------------------------------------------------------------------
coeff_df = pd.read_csv(SD_TABLES / "bessel_coefficients.csv")
n_events = len(coeff_df)

all_coeffs = np.array([[coeff_df.iloc[i][f"c_{m}"] for m in range(N_MODES)] for i in range(n_events)])
alpha_emp = coeff_df["alpha"].values.astype(float)
D_peak = coeff_df["D_peak"].values.astype(float)
delta_near = coeff_df["delta_near"].values.astype(float)

# ---------------------------------------------------------------------------
# 拟合函数
# ---------------------------------------------------------------------------
# 全样本最优解作为 warm-start
_WARM_GLOBAL = [0.00418, 0.304]
_WARM_EXPB = [0.00230, 0.0209, 2.304]


def fit_global(idx):
    """全局模型: k, Ds 两个参数。"""
    ae = alpha_emp[idx]
    co = all_coeffs[idx]

    def obj(params):
        k, Ds = params
        if k < 1e-7 or Ds < 1e-3:
            return 1e6
        preds = np.array([_predict_alpha(c, k, Ds) for c in co])
        if not np.all(np.isfinite(preds)):
            return 1e6
        return float(np.mean((preds - ae) ** 2))

    best = {"fun": 1e6}
    for x0 in [_WARM_GLOBAL, [0.004, 1.0], [0.008, 0.1]]:
        try:
            res = minimize(obj, x0, method="L-BFGS-B",
                           bounds=[(1e-5, 0.1), (0.01, 20.0)])
            if res.fun < best["fun"]:
                best = {"fun": res.fun, "x": res.x.copy()}
        except Exception:
            pass

    k, Ds = best["x"]
    preds = np.array([_predict_alpha(c, k, Ds) for c in co])
    return k, Ds, preds


def fit_expB(idx):
    """Exp-B 模型: k_i = k₀ + β·D_peak,i, Ds。3 参数。"""
    ae = alpha_emp[idx]
    co = all_coeffs[idx]
    dp = D_peak[idx]

    def obj(params):
        k0, beta, Ds = params
        if Ds < 1e-3:
            return 1e6
        preds = []
        for j in range(len(ae)):
            ki = k0 + beta * dp[j]
            if ki < 1e-7:
                return 1e6
            a = _predict_alpha(co[j], ki, Ds)
            if not np.isfinite(a):
                return 1e6
            preds.append(a)
        return float(np.mean((np.array(preds) - ae) ** 2))

    best = {"fun": 1e6}
    for x0 in [_WARM_EXPB, [0.001, 0.5, 1.0], [0.004, 1.0, 0.3], [0.01, 0.1, 2.0]]:
        try:
            res = minimize(obj, x0, method="L-BFGS-B",
                           bounds=[(1e-5, 0.1), (-5.0, 10.0), (0.01, 20.0)])
            if res.fun < best["fun"]:
                best = {"fun": res.fun, "x": res.x.copy()}
        except Exception:
            pass

    k0, beta, Ds = best["x"]
    preds = np.array([_predict_alpha(co[j], k0 + beta * dp[j], Ds) for j in range(len(ae))])
    return k0, beta, Ds, preds


# ---------------------------------------------------------------------------
# 1) 全样本结果 (point estimate)
# ---------------------------------------------------------------------------
print("=" * 70)
print("Step 0: 全样本 point estimate")
print("=" * 70)

full_idx = np.arange(n_events)
k_g, Ds_g, pred_g = fit_global(full_idx)
k0_B, beta_B, Ds_B, pred_B = fit_expB(full_idx)

rho_g_emp, _ = _spearman(pred_g, alpha_emp)
rho_g_dp, _ = _spearman(pred_g, D_peak)
rho_B_emp, _ = _spearman(pred_B, alpha_emp)
rho_B_dp, _ = _spearman(pred_B, D_peak)
rho_B_dn, _ = _spearman(pred_B, delta_near)

mse_g = float(np.mean((pred_g - alpha_emp) ** 2))
mse_B = float(np.mean((pred_B - alpha_emp) ** 2))

print(f"  Global:  k={k_g:.5f}, Ds={Ds_g:.4f}  ρ(emp)={rho_g_emp:+.3f}  ρ(Dp)={rho_g_dp:+.3f}  MSE={mse_g:.5f}")
print(f"  Exp-B:   k₀={k0_B:.5f}, β={beta_B:.4f}, Ds={Ds_B:.4f}  ρ(emp)={rho_B_emp:+.3f}  ρ(Dp)={rho_B_dp:+.3f}  MSE={mse_B:.5f}")
print(f"  ΔMSE = {mse_g - mse_B:.5f}  (Global − Exp-B; >0 means Exp-B better)")

# ---------------------------------------------------------------------------
# 2) Bootstrap: Case resampling
# ---------------------------------------------------------------------------
N_BOOT = 200
print(f"\n{'=' * 70}")
print(f"Step 1: Bootstrap ({N_BOOT} iterations)")
print("=" * 70)
sys.stdout.flush()

boot_results = {
    "beta": [], "k0": [], "Ds_B": [],
    "rho_B_emp": [], "rho_B_dp": [], "rho_B_dn": [],
    "rho_G_emp": [], "rho_G_dp": [],
    "delta_rho_emp": [],    # ρ_B(emp) - ρ_G(emp)
    "delta_mse": [],        # MSE_G - MSE_B
}

for b in range(N_BOOT):
    if (b + 1) % 20 == 0:
        print(f"  bootstrap {b + 1}/{N_BOOT}...", flush=True)
    idx = np.random.choice(n_events, size=n_events, replace=True)

    try:
        k_g_b, Ds_g_b, pred_g_b = fit_global(idx)
        k0_b, beta_b, Ds_b, pred_B_b = fit_expB(idx)
    except Exception:
        continue

    ae_b = alpha_emp[idx]
    dp_b = D_peak[idx]
    dn_b = delta_near[idx]

    rho_ge, _ = _spearman(pred_g_b, ae_b)
    rho_gd, _ = _spearman(pred_g_b, dp_b)
    rho_be, _ = _spearman(pred_B_b, ae_b)
    rho_bd, _ = _spearman(pred_B_b, dp_b)
    rho_bn, _ = _spearman(pred_B_b, dn_b)

    mse_g_b = float(np.mean((pred_g_b - ae_b) ** 2))
    mse_B_b = float(np.mean((pred_B_b - ae_b) ** 2))

    boot_results["beta"].append(beta_b)
    boot_results["k0"].append(k0_b)
    boot_results["Ds_B"].append(Ds_b)
    boot_results["rho_B_emp"].append(rho_be)
    boot_results["rho_B_dp"].append(rho_bd)
    boot_results["rho_B_dn"].append(rho_bn)
    boot_results["rho_G_emp"].append(rho_ge)
    boot_results["rho_G_dp"].append(rho_gd)
    boot_results["delta_rho_emp"].append(rho_be - rho_ge)
    boot_results["delta_mse"].append(mse_g_b - mse_B_b)

for k in boot_results:
    boot_results[k] = np.array(boot_results[k])

n_valid = len(boot_results["beta"])

def ci(arr, lo=2.5, hi=97.5):
    return np.percentile(arr, lo), np.percentile(arr, hi)

print(f"\n  有效 bootstrap 样本: {n_valid}/{N_BOOT}")

print(f"\n--- 参数 bootstrap CI (95%) ---")
lo, hi = ci(boot_results["beta"])
frac_pos = np.mean(boot_results["beta"] > 0) * 100
print(f"  β:    median={np.median(boot_results['beta']):.4f}  CI=[{lo:.4f}, {hi:.4f}]  P(β>0)={frac_pos:.1f}%")
lo, hi = ci(boot_results["k0"])
print(f"  k₀:   median={np.median(boot_results['k0']):.5f}  CI=[{lo:.5f}, {hi:.5f}]")
lo, hi = ci(boot_results["Ds_B"])
print(f"  Ds:   median={np.median(boot_results['Ds_B']):.4f}  CI=[{lo:.4f}, {hi:.4f}]")

print(f"\n--- Spearman ρ bootstrap CI (95%) ---")
for name, key in [("ρ(α_pred_B, α_emp)", "rho_B_emp"),
                   ("ρ(α_pred_B, D_peak)", "rho_B_dp"),
                   ("ρ(α_pred_B, δ_near)", "rho_B_dn"),
                   ("ρ(α_pred_G, α_emp)", "rho_G_emp")]:
    arr = boot_results[key]
    lo, hi = ci(arr)
    print(f"  {name:<25s}: median={np.median(arr):+.3f}  CI=[{lo:+.3f}, {hi:+.3f}]")

print(f"\n--- Exp-B vs Global 改善 ---")
lo, hi = ci(boot_results["delta_rho_emp"])
frac = np.mean(boot_results["delta_rho_emp"] > 0) * 100
print(f"  Δρ(emp) = ρ_B - ρ_G:  median={np.median(boot_results['delta_rho_emp']):+.3f}  CI=[{lo:+.3f}, {hi:+.3f}]  P(>0)={frac:.1f}%")

lo, hi = ci(boot_results["delta_mse"])
frac_mse = np.mean(boot_results["delta_mse"] > 0) * 100
print(f"  ΔMSE = MSE_G - MSE_B: median={np.median(boot_results['delta_mse']):+.5f}  CI=[{lo:+.5f}, {hi:+.5f}]  P(>0)={frac_mse:.1f}%")

# ---------------------------------------------------------------------------
# 3) Permutation test: 打乱 D_peak 后 Exp-B 是否仍有效
# ---------------------------------------------------------------------------
N_PERM = 200
print(f"\n{'=' * 70}")
print(f"Step 2: Permutation test ({N_PERM} iterations)")
print("=" * 70)
sys.stdout.flush()

# 观测量: 全样本 Exp-B 的 ρ(α_pred, α_emp)
rho_obs = rho_B_emp
delta_mse_obs = mse_g - mse_B

perm_rho = []
perm_delta_mse = []

D_peak_orig = D_peak.copy()

for p in range(N_PERM):
    if (p + 1) % 20 == 0:
        print(f"  permutation {p + 1}/{N_PERM}...", flush=True)

    # 打乱 D_peak 的分配（破坏 D_peak ↔ event 的对应）
    perm_idx = np.random.permutation(n_events)
    D_peak_perm = D_peak_orig[perm_idx]

    # 用打乱后的 D_peak 重新拟合 Exp-B
    def obj_perm(params):
        k0, beta, Ds = params
        preds = []
        for j in range(n_events):
            ki = k0 + beta * D_peak_perm[j]
            if ki < 1e-7:
                return 1e6
            a = _predict_alpha(all_coeffs[j], ki, Ds)
            if not np.isfinite(a):
                return 1e6
            preds.append(a)
        return float(np.mean((np.array(preds) - alpha_emp) ** 2))

    best_p = {"fun": 1e6}
    for x0 in [_WARM_EXPB, [0.004, 1.0, 0.3]]:
        try:
            res = minimize(obj_perm, x0, method="L-BFGS-B",
                           bounds=[(1e-5, 0.1), (-5.0, 10.0), (0.01, 20.0)])
            if res.fun < best_p["fun"]:
                best_p = {"fun": res.fun, "x": res.x.copy()}
        except Exception:
            pass

    k0_p, beta_p, Ds_p = best_p["x"]
    pred_p = np.array([_predict_alpha(all_coeffs[j], k0_p + beta_p * D_peak_perm[j], Ds_p)
                        for j in range(n_events)])

    rho_p, _ = _spearman(pred_p, alpha_emp)
    mse_p = float(np.mean((pred_p - alpha_emp) ** 2))

    perm_rho.append(rho_p)
    perm_delta_mse.append(mse_g - mse_p)

perm_rho = np.array(perm_rho)
perm_delta_mse = np.array(perm_delta_mse)

p_value_rho = np.mean(perm_rho >= rho_obs)
p_value_mse = np.mean(perm_delta_mse >= delta_mse_obs)

print(f"\n  观测 ρ(α_pred_B, α_emp) = {rho_obs:+.3f}")
print(f"  Permutation ρ: mean={np.mean(perm_rho):+.3f}, std={np.std(perm_rho):.3f}")
print(f"  p-value (one-sided, ρ >= obs): {p_value_rho:.4f}")
print(f"\n  观测 ΔMSE (Global−ExpB) = {delta_mse_obs:+.5f}")
print(f"  Permutation ΔMSE: mean={np.mean(perm_delta_mse):+.5f}, std={np.std(perm_delta_mse):.5f}")
print(f"  p-value (one-sided, ΔMSE >= obs): {p_value_mse:.4f}")

# ---------------------------------------------------------------------------
# 4) Leave-one-out cross-validation
# ---------------------------------------------------------------------------
print(f"\n{'=' * 70}")
print("Step 3: Leave-One-Out Cross-Validation")
print("=" * 70)

loo_pred_g = np.full(n_events, np.nan)
loo_pred_B = np.full(n_events, np.nan)

for i in range(n_events):
    train = np.concatenate([np.arange(0, i), np.arange(i + 1, n_events)])

    # Global LOO
    k_t, Ds_t, _ = fit_global(train)
    loo_pred_g[i] = _predict_alpha(all_coeffs[i], k_t, Ds_t)

    # Exp-B LOO
    k0_t, beta_t, Ds_t_B, _ = fit_expB(train)
    loo_pred_B[i] = _predict_alpha(all_coeffs[i], k0_t + beta_t * D_peak[i], Ds_t_B)

    print(f"  LOO {i + 1:2d}/{n_events}: α_emp={alpha_emp[i]:+.3f}  global={loo_pred_g[i]:.3f}  ExpB={loo_pred_B[i]:.3f}  ({coeff_df.iloc[i]['short_name']})")

mae_loo_g = float(np.mean(np.abs(loo_pred_g - alpha_emp)))
mae_loo_B = float(np.mean(np.abs(loo_pred_B - alpha_emp)))
mse_loo_g = float(np.mean((loo_pred_g - alpha_emp) ** 2))
mse_loo_B = float(np.mean((loo_pred_B - alpha_emp) ** 2))
rho_loo_g, _ = _spearman(loo_pred_g, alpha_emp)
rho_loo_B, _ = _spearman(loo_pred_B, alpha_emp)

print(f"\n  LOO 结果:")
print(f"  {'模型':<15s} {'MAE':>8s} {'MSE':>8s} {'ρ(pred,emp)':>12s}")
print(f"  {'Global':<15s} {mae_loo_g:>8.4f} {mse_loo_g:>8.5f} {rho_loo_g:>+12.3f}")
print(f"  {'Exp-B':<15s} {mae_loo_B:>8.4f} {mse_loo_B:>8.5f} {rho_loo_B:>+12.3f}")

# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
print(f"\n{'=' * 70}")
print("汇总: Exp-B 稳健性")
print("=" * 70)
lo_beta, hi_beta = ci(boot_results["beta"])
lo_rho, hi_rho = ci(boot_results["rho_B_emp"])
lo_rho_dp, hi_rho_dp = ci(boot_results["rho_B_dp"])
print(f"  β = {beta_B:.4f}  CI=[{lo_beta:.4f}, {hi_beta:.4f}]  P(β>0)={frac_pos:.1f}%")
print(f"  ρ(α_pred, α_emp) = {rho_B_emp:+.3f}  CI=[{lo_rho:+.3f}, {hi_rho:+.3f}]")
print(f"  ρ(α_pred, D_peak) = {rho_B_dp:+.3f}  CI=[{lo_rho_dp:+.3f}, {hi_rho_dp:+.3f}]")
print(f"  Permutation p-value (ρ): {p_value_rho:.4f}")
print(f"  Permutation p-value (ΔMSE): {p_value_mse:.4f}")
print(f"  LOO ρ(pred,emp): Global={rho_loo_g:+.3f}  Exp-B={rho_loo_B:+.3f}")
print(f"  LOO MAE:         Global={mae_loo_g:.4f}  Exp-B={mae_loo_B:.4f}")
