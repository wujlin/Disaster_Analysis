#!/usr/bin/env python3
"""路径 1 实验：D_peak 维度的机制检验

核心问题：ρ(α, D_peak) = +0.600 的信号来自什么机制？
PDE 全局模型未能捕捉此关联 (ρ(α_pred, D_peak) = 0.394, p=0.131)。

三个实验：
  Exp-A: D_peak 与 Bessel 系数 {c_n} 的关系 — D_peak 编码了哪些模态信息？
  Exp-B: event-specific k_i = k_0 + β·D_peak,i — D_peak 是否调控恢复力强度？
  Exp-C: event-specific k_i = k_0 + β₁·D_peak,i + β₂·δ_near,i — 联合模型

思路：如果 Exp-B 显著改善 ρ(α_pred, D_peak)，说明 D_peak 的效应可通过
"大灾害恢复力更强"整合进 PDE 框架，模型从 2 参数扩展为 3 参数（k_0, β, Ds）。
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import j0, jn_zeros
from scipy.stats import spearmanr, pearsonr
from scipy.optimize import minimize

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
SD_TABLES = ROOT / "outputs" / "cross_disaster_comparison" / "spatial_diffusion_results" / "tables"
OUT_DIR = ROOT / "outputs" / "cross_disaster_comparison" / "spatial_diffusion_results" / "tables"

# ---------------------------------------------------------------------------
# 加载数据
# ---------------------------------------------------------------------------
def load_data():
    coeff_df = pd.read_csv(SD_TABLES / "bessel_coefficients.csv")
    pred_df = pd.read_csv(SD_TABLES / "pde_alpha_predictions.csv")
    return coeff_df, pred_df


def _spearman(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    n = int(np.sum(ok))
    if n < 3:
        return np.nan, np.nan, n
    if np.std(x[ok]) < 1e-12 or np.std(y[ok]) < 1e-12:
        return 0.0, 1.0, n
    rho, p = spearmanr(x[ok], y[ok])
    return float(rho), float(p), n


# ---------------------------------------------------------------------------
# Exp-A: D_peak 与 Bessel 系数的关系
# ---------------------------------------------------------------------------
def exp_a(coeff_df):
    print("=" * 70)
    print("Exp-A: D_peak 与 Bessel 系数 {c_n} 的关系")
    print("=" * 70)

    D_peak = coeff_df["D_peak"].values
    alpha_emp = coeff_df["alpha"].values
    delta_near = coeff_df["delta_near"].values

    # 提取 c_0 到 c_9
    c_cols = [f"c_{i}" for i in range(10)]
    E_cols = [f"E_{i}" for i in range(10)]

    print("\n--- ρ(c_n, D_peak) ---")
    for col in c_cols:
        c_n = coeff_df[col].values
        rho, p, n = _spearman(c_n, D_peak)
        sig = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""
        print(f"  {col:6s}: ρ={rho:+.3f}  p={p:.4f}  {sig}")

    print("\n--- ρ(E_n, D_peak) : 各模态能量占比 ---")
    for col in E_cols:
        e_n = coeff_df[col].values
        rho, p, n = _spearman(e_n, D_peak)
        sig = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""
        print(f"  {col:6s}: ρ={rho:+.3f}  p={p:.4f}  {sig}")

    # E_low_frac (低阶能量占比) vs D_peak
    E_low = coeff_df["E_low_frac"].values
    E_high = coeff_df["E_high_frac"].values
    rho_low, p_low, _ = _spearman(E_low, D_peak)
    rho_high, p_high, _ = _spearman(E_high, D_peak)
    print(f"\n  E_low_frac  vs D_peak: ρ={rho_low:+.3f}  p={p_low:.4f}")
    print(f"  E_high_frac vs D_peak: ρ={rho_high:+.3f}  p={p_high:.4f}")

    # E_total vs D_peak
    E_total = coeff_df["E_total"].values
    rho_et, p_et, _ = _spearman(E_total, D_peak)
    print(f"  E_total     vs D_peak: ρ={rho_et:+.3f}  p={p_et:.4f}")

    # 关键检验: E_low_frac vs alpha
    rho_la, p_la, _ = _spearman(E_low, alpha_emp)
    rho_ha, p_ha, _ = _spearman(E_high, alpha_emp)
    print(f"\n  E_low_frac  vs α_emp:  ρ={rho_la:+.3f}  p={p_la:.4f}")
    print(f"  E_high_frac vs α_emp:  ρ={rho_ha:+.3f}  p={p_ha:.4f}")


# ---------------------------------------------------------------------------
# Exp-B/C: event-specific k_i 模型
# ---------------------------------------------------------------------------
def _bessel_basis(r, root, R_max):
    if abs(float(root)) < 1e-12:
        return np.ones_like(r, dtype=float)
    return j0(float(root) * r / float(R_max))


def _build_t_eval():
    t_early = np.arange(0.0, 24.0, 1.0)
    t_late = np.arange(24.0, 248.1, 8.0)
    return np.unique(np.concatenate([t_early, t_late]))


def _predict_alpha_E(coeffs, roots, r_grid, basis_matrix, k, Ds, t_eval, t_start=1.0, t_end=120.0):
    """给定 k, Ds, 预测单个事件的 α_pred (E-mode)"""
    R_max = float(r_grid[-1])
    lambdas = k + Ds * (roots / R_max) ** 2
    decays = np.exp(-np.outer(t_eval, lambdas))
    delta_rt = decays @ (coeffs[:, None] * basis_matrix)
    w = np.maximum(r_grid, 1e-12)
    E_vals = np.average(delta_rt**2, weights=w, axis=1)

    # log-log fit on [t_start, t_end]
    ok = (t_eval >= t_start) & (t_eval <= t_end) & (E_vals > 0)
    if np.sum(ok) < 3:
        return np.nan
    lx = np.log(t_eval[ok])
    ly = np.log(E_vals[ok])
    slope, _ = np.polyfit(lx, ly, 1)
    return float(-slope)


def exp_bc(coeff_df):
    print("\n" + "=" * 70)
    print("Exp-B: event-specific k_i = k_0 + β·D_peak,i")
    print("Exp-C: event-specific k_i = k_0 + β₁·D_peak,i + β₂·δ_near,i")
    print("=" * 70)

    # 重建 ProfileModel 数据
    n_modes = 10
    R_max = 200.0
    n_grid = 200
    r_grid = np.linspace(0.0, R_max, n_grid)

    roots_nonzero = jn_zeros(0, n_modes - 1)
    roots = np.concatenate([[0.0], roots_nonzero])

    basis_matrix = np.vstack([_bessel_basis(r_grid, z, R_max) for z in roots])
    t_eval = _build_t_eval()

    # 提取系数矩阵
    events = []
    for _, row in coeff_df.iterrows():
        c_n = np.array([row[f"c_{i}"] for i in range(n_modes)])
        events.append({
            "slug": row["slug"],
            "alpha_emp": float(row["alpha"]),
            "D_peak": float(row["D_peak"]),
            "delta_near": float(row["delta_near"]),
            "coeffs": c_n,
        })

    alpha_emp = np.array([e["alpha_emp"] for e in events])
    D_peak = np.array([e["D_peak"] for e in events])
    delta_near = np.array([e["delta_near"] for e in events])
    n_events = len(events)

    # --- Baseline: 全局 k, Ds (v3 最优) ---
    k_global = 0.0041753189365604
    Ds_global = 0.3039195382313198

    alpha_pred_global = np.array([
        _predict_alpha_E(e["coeffs"], roots, r_grid, basis_matrix,
                         k_global, Ds_global, t_eval)
        for e in events
    ])

    rho_emp_g, p_emp_g, _ = _spearman(alpha_pred_global, alpha_emp)
    rho_dp_g, p_dp_g, _ = _spearman(alpha_pred_global, D_peak)
    rho_dn_g, p_dn_g, _ = _spearman(alpha_pred_global, delta_near)
    std_g = np.std(alpha_pred_global)

    print(f"\n--- Baseline (全局 k={k_global:.5f}, Ds={Ds_global:.4f}) ---")
    print(f"  ρ(α_pred, α_emp)     = {rho_emp_g:+.3f}  p={p_emp_g:.4f}")
    print(f"  ρ(α_pred, D_peak)    = {rho_dp_g:+.3f}  p={p_dp_g:.4f}")
    print(f"  ρ(α_pred, δ_near)    = {rho_dn_g:+.3f}  p={p_dn_g:.4f}")
    print(f"  α_pred std           = {std_g:.4f}  (α_emp std = {np.std(alpha_emp):.4f})")

    # --- Exp-B: k_i = k_0 + β·D_peak,i ---
    # 三参数优化: k_0, β, Ds
    def _objective_B(params):
        k0, beta, Ds = params[0], params[1], params[2]
        preds = []
        for e in events:
            k_i = k0 + beta * e["D_peak"]
            if k_i < 1e-6:
                return 1e6
            a = _predict_alpha_E(e["coeffs"], roots, r_grid, basis_matrix,
                                 k_i, Ds, t_eval)
            if not np.isfinite(a):
                return 1e6
            preds.append(a)
        preds = np.array(preds)
        # 目标: 最大化 Spearman(pred, emp) 等价于最小化负 Spearman
        # 但 Spearman 不可微 -> 用 MSE 作为连续代理
        return float(np.mean((preds - alpha_emp) ** 2))

    # 网格初始化 + 局部优化
    best_B = {"fun": 1e6}
    for k0_init in [0.001, 0.004, 0.01]:
        for beta_init in [0.1, 0.5, 1.0, 2.0]:
            for Ds_init in [0.1, 0.3, 1.0]:
                try:
                    res = minimize(_objective_B, [k0_init, beta_init, Ds_init],
                                   method="L-BFGS-B",
                                   bounds=[(1e-5, 0.1), (-5.0, 10.0), (0.01, 20.0)])
                    if res.fun < best_B["fun"]:
                        best_B = {"fun": res.fun, "x": res.x.copy()}
                except:
                    pass

    k0_B, beta_B, Ds_B = best_B["x"]
    alpha_pred_B = np.array([
        _predict_alpha_E(e["coeffs"], roots, r_grid, basis_matrix,
                         k0_B + beta_B * e["D_peak"], Ds_B, t_eval)
        for e in events
    ])

    rho_emp_B, p_emp_B, _ = _spearman(alpha_pred_B, alpha_emp)
    rho_dp_B, p_dp_B, _ = _spearman(alpha_pred_B, D_peak)
    rho_dn_B, p_dn_B, _ = _spearman(alpha_pred_B, delta_near)
    std_B = np.std(alpha_pred_B)
    mae_B = float(np.mean(np.abs(alpha_pred_B - alpha_emp)))

    print(f"\n--- Exp-B: k_i = k_0 + β·D_peak (3 params) ---")
    print(f"  k_0={k0_B:.5f}, β={beta_B:.4f}, Ds={Ds_B:.4f}")
    print(f"  k_i range: [{k0_B + beta_B * D_peak.min():.5f}, {k0_B + beta_B * D_peak.max():.5f}]")
    print(f"  ρ(α_pred, α_emp)     = {rho_emp_B:+.3f}  p={p_emp_B:.4f}")
    print(f"  ρ(α_pred, D_peak)    = {rho_dp_B:+.3f}  p={p_dp_B:.4f}")
    print(f"  ρ(α_pred, δ_near)    = {rho_dn_B:+.3f}  p={p_dn_B:.4f}")
    print(f"  α_pred std           = {std_B:.4f}  (α_emp std = {np.std(alpha_emp):.4f})")
    print(f"  MAE                  = {mae_B:.4f}")
    print(f"  MSE (obj)            = {best_B['fun']:.6f}")

    # 压缩比
    ratio_B = std_B / np.std(alpha_emp) if np.std(alpha_emp) > 1e-12 else np.nan
    ratio_g = std_g / np.std(alpha_emp) if np.std(alpha_emp) > 1e-12 else np.nan
    print(f"  压缩比: global={ratio_g:.3f} → Exp-B={ratio_B:.3f}")

    # --- Exp-C: k_i = k_0 + β₁·D_peak + β₂·δ_near ---
    def _objective_C(params):
        k0, b1, b2, Ds = params
        preds = []
        for e in events:
            k_i = k0 + b1 * e["D_peak"] + b2 * e["delta_near"]
            if k_i < 1e-6:
                return 1e6
            a = _predict_alpha_E(e["coeffs"], roots, r_grid, basis_matrix,
                                 k_i, Ds, t_eval)
            if not np.isfinite(a):
                return 1e6
            preds.append(a)
        preds = np.array(preds)
        return float(np.mean((preds - alpha_emp) ** 2))

    best_C = {"fun": 1e6}
    for k0_init in [0.001, 0.004, 0.01]:
        for b1_init in [0.5, 1.0, 2.0]:
            for b2_init in [-0.5, -0.1, 0.0, 0.5]:
                for Ds_init in [0.1, 0.3, 1.0]:
                    try:
                        res = minimize(_objective_C, [k0_init, b1_init, b2_init, Ds_init],
                                       method="L-BFGS-B",
                                       bounds=[(1e-5, 0.1), (-5.0, 10.0), (-5.0, 5.0), (0.01, 20.0)])
                        if res.fun < best_C["fun"]:
                            best_C = {"fun": res.fun, "x": res.x.copy()}
                    except:
                        pass

    k0_C, b1_C, b2_C, Ds_C = best_C["x"]
    alpha_pred_C = np.array([
        _predict_alpha_E(e["coeffs"], roots, r_grid, basis_matrix,
                         k0_C + b1_C * e["D_peak"] + b2_C * e["delta_near"], Ds_C, t_eval)
        for e in events
    ])

    rho_emp_C, p_emp_C, _ = _spearman(alpha_pred_C, alpha_emp)
    rho_dp_C, p_dp_C, _ = _spearman(alpha_pred_C, D_peak)
    rho_dn_C, p_dn_C, _ = _spearman(alpha_pred_C, delta_near)
    std_C = np.std(alpha_pred_C)
    mae_C = float(np.mean(np.abs(alpha_pred_C - alpha_emp)))
    ratio_C = std_C / np.std(alpha_emp) if np.std(alpha_emp) > 1e-12 else np.nan

    print(f"\n--- Exp-C: k_i = k_0 + β₁·D_peak + β₂·δ_near (4 params) ---")
    print(f"  k_0={k0_C:.5f}, β₁={b1_C:.4f}, β₂={b2_C:.4f}, Ds={Ds_C:.4f}")
    print(f"  ρ(α_pred, α_emp)     = {rho_emp_C:+.3f}  p={p_emp_C:.4f}")
    print(f"  ρ(α_pred, D_peak)    = {rho_dp_C:+.3f}  p={p_dp_C:.4f}")
    print(f"  ρ(α_pred, δ_near)    = {rho_dn_C:+.3f}  p={p_dn_C:.4f}")
    print(f"  α_pred std           = {std_C:.4f}  (α_emp std = {np.std(alpha_emp):.4f})")
    print(f"  MAE                  = {mae_C:.4f}")
    print(f"  MSE (obj)            = {best_C['fun']:.6f}")
    print(f"  压缩比: global={ratio_g:.3f} → Exp-C={ratio_C:.3f}")

    # --- 汇总比较 ---
    print("\n" + "=" * 70)
    print("汇总比较")
    print("=" * 70)
    print(f"{'模型':<30s} {'params':>6s} {'ρ(pred,emp)':>12s} {'ρ(pred,Dp)':>12s} {'ρ(pred,δn)':>12s} {'std_ratio':>10s} {'MAE':>8s}")
    print("-" * 90)

    mae_g = float(np.mean(np.abs(alpha_pred_global - alpha_emp)))
    print(f"{'Global k,Ds':<30s} {'2':>6s} {rho_emp_g:>+12.3f} {rho_dp_g:>+12.3f} {rho_dn_g:>+12.3f} {ratio_g:>10.3f} {mae_g:>8.4f}")
    print(f"{'k_i = k0 + β·Dp':<30s} {'3':>6s} {rho_emp_B:>+12.3f} {rho_dp_B:>+12.3f} {rho_dn_B:>+12.3f} {ratio_B:>10.3f} {mae_B:>8.4f}")
    print(f"{'k_i = k0 + β₁·Dp + β₂·δn':<30s} {'4':>6s} {rho_emp_C:>+12.3f} {rho_dp_C:>+12.3f} {rho_dn_C:>+12.3f} {ratio_C:>10.3f} {mae_C:>8.4f}")

    # --- Per-event 比较 ---
    print("\n--- Per-event α_pred ---")
    print(f"{'event':<25s} {'α_emp':>8s} {'global':>8s} {'Exp-B':>8s} {'Exp-C':>8s} {'D_peak':>8s} {'δ_near':>8s}")
    print("-" * 80)
    order = np.argsort(-alpha_emp)
    for i in order:
        e = events[i]
        print(f"{e['slug'][:24]:<25s} {e['alpha_emp']:>+8.3f} {alpha_pred_global[i]:>8.3f} {alpha_pred_B[i]:>8.3f} {alpha_pred_C[i]:>8.3f} {e['D_peak']:>8.3f} {e['delta_near']:>+8.3f}")

    # 保存结果
    results = []
    for i, e in enumerate(events):
        results.append({
            "slug": e["slug"],
            "alpha_emp": e["alpha_emp"],
            "alpha_pred_global": alpha_pred_global[i],
            "alpha_pred_expB": alpha_pred_B[i],
            "alpha_pred_expC": alpha_pred_C[i],
            "D_peak": e["D_peak"],
            "delta_near": e["delta_near"],
            "k_i_expB": k0_B + beta_B * e["D_peak"],
            "k_i_expC": k0_C + b1_C * e["D_peak"] + b2_C * e["delta_near"],
        })
    out_df = pd.DataFrame(results)
    out_path = OUT_DIR / "dpeak_mechanism_experiment.csv"
    out_df.to_csv(out_path, index=False)
    print(f"\n结果已保存: {out_path}")


if __name__ == "__main__":
    coeff_df, pred_df = load_data()
    exp_a(coeff_df)
    exp_bc(coeff_df)
