"""
Subregion 综合诊断脚本

解决三个核心问题：
  1. SNR confound: 高 D_peak 的 unit 拟合质量更好 → 伪正相关
  2. 样本不平衡: beryl_jamaica (n=1000) 主导 pooled 估计
  3. 斜率异质性: 随机截距模型假设同质斜率，但实际斜率方向翻转

输出: outputs/cross_disaster_comparison/subregion_diagnostic/
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.formula.api as smf

DEFAULT_FITS_CSV = Path(
    "outputs/cross_disaster_comparison/"
    "geo_unit_scale_unified_h8_mtw4_mpp3_relaxed_20260225_141630/"
    "tables/geo_unit_fits.csv"
)
DEFAULT_EVENT_CORR_CSV = Path(
    "outputs/cross_disaster_comparison/"
    "geo_unit_scale_unified_h8_mtw4_mpp3_relaxed_20260225_141630/"
    "tables/event_unit_correlations.csv"
)
DEFAULT_OUT_DIR = Path("outputs/cross_disaster_comparison/subregion_diagnostic")

FITS_CSV = DEFAULT_FITS_CSV
EVENT_CORR_CSV = DEFAULT_EVENT_CORR_CSV
OUT_DIR = DEFAULT_OUT_DIR


def load_data() -> pd.DataFrame:
    df = pd.read_csv(FITS_CSV)
    for c in ["alpha_unit", "D_peak_unit", "delta_peak_unit", "distance_km",
              "r2_unit", "n_mono", "n_tiles_median"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["slug"] = df["slug"].astype(str)
    df = df.dropna(subset=["alpha_unit", "D_peak_unit", "slug"]).reset_index(drop=True)
    return df


# ────────────────────────────────────────────
# Part 0: 数据概览
# ────────────────────────────────────────────
def part0_overview(df: pd.DataFrame) -> None:
    print("=" * 60)
    print("Part 0: 数据概览")
    print("=" * 60)
    print(f"总样本: {len(df)}, 事件数: {df.slug.nunique()}")
    print()

    event_stats = df.groupby("slug").agg(
        n=("alpha_unit", "size"),
        alpha_mean=("alpha_unit", "mean"),
        alpha_std=("alpha_unit", "std"),
        D_peak_mean=("D_peak_unit", "mean"),
        n_mono_median=("n_mono", "median"),
        r2_median=("r2_unit", "median"),
    ).sort_values("n", ascending=False)
    print("各事件统计:")
    print(event_stats.to_string())
    print()
    print(f"n_mono == 3 占比: {(df.n_mono == 3).mean():.3f}")
    print(f"n_mono >= 5 占比: {(df.n_mono >= 5).mean():.3f}")
    print(f"r2_unit < 0.3 占比: {(df.r2_unit < 0.3).mean():.3f}")
    print(f"r2_unit < 0.5 占比: {(df.r2_unit < 0.5).mean():.3f}")
    print()

    event_stats.to_csv(OUT_DIR / "part0_event_overview.csv")


# ────────────────────────────────────────────
# Part 1: SNR confound 诊断
# ────────────────────────────────────────────
def part1_snr_confound(df: pd.DataFrame) -> pd.DataFrame:
    print("=" * 60)
    print("Part 1: SNR confound 诊断")
    print("=" * 60)

    # 1a: D_peak_unit 与 n_mono / r2_unit 的相关
    rho_dpeak_nmono, p_dpeak_nmono = stats.spearmanr(
        df["D_peak_unit"], df["n_mono"])
    rho_dpeak_r2, p_dpeak_r2 = stats.spearmanr(
        df["D_peak_unit"], df["r2_unit"])
    rho_nmono_alpha, p_nmono_alpha = stats.spearmanr(
        df["n_mono"], df["alpha_unit"])
    rho_r2_alpha, p_r2_alpha = stats.spearmanr(
        df["r2_unit"], df["alpha_unit"])

    print("SNR 相关链: D_peak → (n_mono, r2) → alpha")
    print(f"  D_peak vs n_mono:  rho={rho_dpeak_nmono:.3f}, p={p_dpeak_nmono:.4f}")
    print(f"  D_peak vs r2:      rho={rho_dpeak_r2:.3f}, p={p_dpeak_r2:.4f}")
    print(f"  n_mono vs alpha:   rho={rho_nmono_alpha:.3f}, p={p_nmono_alpha:.4f}")
    print(f"  r2 vs alpha:       rho={rho_r2_alpha:.3f}, p={p_r2_alpha:.4f}")
    print()

    # 1b: 分层分析 — 控制 fit quality 后 D_peak 效应是否消失
    rows = []
    strata = [
        ("all", df),
        ("n_mono>=5", df[df["n_mono"] >= 5]),
        ("n_mono>=5 & r2>=0.5", df[(df["n_mono"] >= 5) & (df["r2_unit"] >= 0.5)]),
        ("n_mono>=4 & r2>=0.3", df[(df["n_mono"] >= 4) & (df["r2_unit"] >= 0.3)]),
        ("r2>=0.5", df[df["r2_unit"] >= 0.5]),
        ("r2>=0.7", df[df["r2_unit"] >= 0.7]),
    ]

    for label, sub in strata:
        if sub["slug"].nunique() < 3 or len(sub) < 20:
            continue
        # Mundlak within-between
        tmp = sub[["slug", "alpha_unit", "D_peak_unit"]].copy()
        tmp["D_within"] = tmp["D_peak_unit"] - tmp.groupby("slug")["D_peak_unit"].transform("mean")
        tmp["D_between"] = tmp.groupby("slug")["D_peak_unit"].transform("mean")

        try:
            model = smf.mixedlm("alpha_unit ~ D_within + D_between",
                                data=tmp, groups=tmp["slug"], re_formula="1")
            res = model.fit(reml=True, method="lbfgs", maxiter=600, disp=False)
            beta_w = float(res.params.get("D_within", np.nan))
            p_w = float(res.pvalues.get("D_within", np.nan))
            beta_b = float(res.params.get("D_between", np.nan))
            p_b = float(res.pvalues.get("D_between", np.nan))
        except Exception:
            beta_w = p_w = beta_b = p_b = np.nan

        # 随机斜率
        try:
            model_rs = smf.mixedlm("alpha_unit ~ D_peak_unit",
                                   data=sub, groups=sub["slug"],
                                   re_formula="~D_peak_unit")
            res_rs = model_rs.fit(reml=True, method="lbfgs", maxiter=600, disp=False)
            beta_rs = float(res_rs.params.get("D_peak_unit", np.nan))
            p_rs = float(res_rs.pvalues.get("D_peak_unit", np.nan))
        except Exception:
            beta_rs = p_rs = np.nan

        # demeaned Spearman
        dm = sub.copy()
        dm["a_dm"] = dm["alpha_unit"] - dm.groupby("slug")["alpha_unit"].transform("mean")
        dm["d_dm"] = dm["D_peak_unit"] - dm.groupby("slug")["D_peak_unit"].transform("mean")
        rho_dm, p_dm = stats.spearmanr(dm["a_dm"], dm["d_dm"])

        rows.append({
            "stratum": label,
            "n_obs": len(sub),
            "n_events": sub["slug"].nunique(),
            "mundlak_within_beta": beta_w,
            "mundlak_within_p": p_w,
            "mundlak_between_beta": beta_b,
            "mundlak_between_p": p_b,
            "random_slope_beta": beta_rs,
            "random_slope_p": p_rs,
            "demeaned_spearman_rho": float(rho_dm),
            "demeaned_spearman_p": float(p_dm),
        })

    result = pd.DataFrame(rows)
    result.to_csv(OUT_DIR / "part1_snr_stratified.csv", index=False)
    print("分层 Mundlak + Random Slope 结果:")
    print(result.to_string(index=False))
    print()
    return result


# ────────────────────────────────────────────
# Part 2: 加入 fit quality 控制变量的混合效应模型
# ────────────────────────────────────────────
def part2_controlled_model(df: pd.DataFrame) -> pd.DataFrame:
    print("=" * 60)
    print("Part 2: 控制 fit quality 的混合效应模型")
    print("=" * 60)

    models = {
        "M0: alpha ~ D_peak": "alpha_unit ~ D_peak_unit",
        "M1: alpha ~ D_peak + n_mono": "alpha_unit ~ D_peak_unit + n_mono",
        "M1b: alpha ~ D_peak + r2": "alpha_unit ~ D_peak_unit + r2_unit",
        "M2: alpha ~ D_peak + n_mono + r2": "alpha_unit ~ D_peak_unit + n_mono + r2_unit",
        "M3: alpha ~ D_peak + delta + dist": "alpha_unit ~ D_peak_unit + delta_peak_unit + distance_km",
        "M4: alpha ~ D_peak + delta + dist + n_mono + r2":
            "alpha_unit ~ D_peak_unit + delta_peak_unit + distance_km + n_mono + r2_unit",
    }

    rows = []
    for label, formula in models.items():
        try:
            model = smf.mixedlm(formula, data=df, groups=df["slug"], re_formula="1")
            res = model.fit(reml=True, method="lbfgs", maxiter=600, disp=False)
            beta_dp = float(res.params.get("D_peak_unit", np.nan))
            p_dp = float(res.pvalues.get("D_peak_unit", np.nan))
            aic = float(res.aic)
            bic = float(res.bic)
            rows.append({
                "model": label,
                "beta_D_peak": beta_dp,
                "p_D_peak": p_dp,
                "AIC": aic,
                "BIC": bic,
                "converged": True,
            })
        except Exception as e:
            rows.append({
                "model": label,
                "beta_D_peak": np.nan,
                "p_D_peak": np.nan,
                "AIC": np.nan,
                "BIC": np.nan,
                "converged": False,
            })

    result = pd.DataFrame(rows)
    result.to_csv(OUT_DIR / "part2_controlled_models.csv", index=False)
    print("模型比较:")
    print(result.to_string(index=False))
    print()
    return result


# ────────────────────────────────────────────
# Part 3: Two-Stage Meta-Analysis (每事件等权)
# ────────────────────────────────────────────
def part3_meta_analysis(df: pd.DataFrame) -> pd.DataFrame:
    print("=" * 60)
    print("Part 3: Two-Stage Meta-Analysis")
    print("=" * 60)

    slugs = sorted(df["slug"].unique())
    stage1_rows = []
    for slug in slugs:
        sub = df[df["slug"] == slug]
        n = len(sub)
        if n < 5:
            continue
        # D_peak_unit → alpha_unit
        slope, intercept, r_value, p_value, std_err = stats.linregress(
            sub["D_peak_unit"].values, sub["alpha_unit"].values)
        stage1_rows.append({
            "slug": slug, "n_units": n,
            "beta_D_peak": slope, "se_D_peak": std_err,
            "p_D_peak": p_value, "r_D_peak": r_value,
        })

    s1 = pd.DataFrame(stage1_rows)
    s1.to_csv(OUT_DIR / "part3_stage1_per_event.csv", index=False)

    betas = s1["beta_D_peak"].values
    ses = s1["se_D_peak"].values
    n_ev = len(betas)

    # 等权 t 检验
    t_stat, t_p = stats.ttest_1samp(betas, 0)
    uw_mean = np.mean(betas)
    uw_se = np.std(betas, ddof=1) / np.sqrt(n_ev)

    # 逆方差加权
    w = 1.0 / (ses ** 2 + 1e-12)
    iv_mean = np.sum(w * betas) / np.sum(w)
    iv_se = 1.0 / np.sqrt(np.sum(w))
    iv_z = iv_mean / iv_se
    iv_p = 2 * (1 - stats.norm.cdf(abs(iv_z)))

    # sign test
    n_pos = int((betas > 0).sum())
    n_neg = int((betas < 0).sum())
    sign_p = float(stats.binomtest(n_pos, n_pos + n_neg, 0.5).pvalue)

    # 排除 beryl_jamaica 的等权分析
    s1_no_bj = s1[~s1["slug"].str.contains("jamaica")]
    betas_nb = s1_no_bj["beta_D_peak"].values
    if len(betas_nb) >= 3:
        t_nb, p_nb = stats.ttest_1samp(betas_nb, 0)
        uw_mean_nb = np.mean(betas_nb)
    else:
        t_nb, p_nb, uw_mean_nb = np.nan, np.nan, np.nan

    # 排除全部 beryl
    s1_no_beryl = s1[~s1["slug"].str.contains("beryl")]
    betas_nba = s1_no_beryl["beta_D_peak"].values
    if len(betas_nba) >= 3:
        t_nba, p_nba = stats.ttest_1samp(betas_nba, 0)
        uw_mean_nba = np.mean(betas_nba)
    else:
        t_nba, p_nba, uw_mean_nba = np.nan, np.nan, np.nan

    summary = pd.DataFrame([{
        "n_events": n_ev,
        "uw_mean_beta": uw_mean,
        "uw_se": uw_se,
        "uw_ttest_t": t_stat,
        "uw_ttest_p": t_p,
        "iv_mean_beta": iv_mean,
        "iv_se": iv_se,
        "iv_p": iv_p,
        "n_positive": n_pos,
        "n_negative": n_neg,
        "sign_test_p": sign_p,
        "uw_mean_no_jamaica": uw_mean_nb,
        "uw_p_no_jamaica": p_nb,
        "uw_mean_no_beryl": uw_mean_nba,
        "uw_p_no_beryl": p_nba,
    }])
    summary.to_csv(OUT_DIR / "part3_meta_summary.csv", index=False)

    print("Stage 1 (per-event OLS):")
    print(s1[["slug", "n_units", "beta_D_peak", "se_D_peak", "p_D_peak"]].to_string(index=False))
    print()
    print("Stage 2 summary:")
    for _, r in summary.iterrows():
        print(f"  等权平均 beta = {r['uw_mean_beta']:.4f}, t-test p = {r['uw_ttest_p']:.4f}")
        print(f"  IV加权 beta   = {r['iv_mean_beta']:.4f}, z-test p = {r['iv_p']:.4f}")
        print(f"  方向: {r['n_positive']:.0f}正 vs {r['n_negative']:.0f}负, sign test p = {r['sign_test_p']:.4f}")
        print(f"  排除 jamaica: mean = {r['uw_mean_no_jamaica']:.4f}, p = {r['uw_p_no_jamaica']:.4f}")
        print(f"  排除 all beryl: mean = {r['uw_mean_no_beryl']:.4f}, p = {r['uw_p_no_beryl']:.4f}")
    print()
    return s1


# ────────────────────────────────────────────
# Part 4: LOO 影响力诊断
# ────────────────────────────────────────────
def part4_loo(df: pd.DataFrame) -> pd.DataFrame:
    print("=" * 60)
    print("Part 4: Leave-One-Event-Out 影响力诊断")
    print("=" * 60)

    slugs = sorted(df["slug"].unique())
    rows = []

    # full model baseline
    try:
        model_full = smf.mixedlm("alpha_unit ~ D_peak_unit",
                                 data=df, groups=df["slug"], re_formula="1")
        res_full = model_full.fit(reml=True, method="lbfgs", maxiter=600, disp=False)
        beta_full = float(res_full.params.get("D_peak_unit", np.nan))
        p_full = float(res_full.pvalues.get("D_peak_unit", np.nan))
    except Exception:
        beta_full = p_full = np.nan

    for excluded in slugs:
        sub = df[df["slug"] != excluded].copy()
        try:
            model = smf.mixedlm("alpha_unit ~ D_peak_unit",
                                data=sub, groups=sub["slug"], re_formula="1")
            res = model.fit(reml=True, method="lbfgs", maxiter=600, disp=False)
            beta = float(res.params.get("D_peak_unit", np.nan))
            p = float(res.pvalues.get("D_peak_unit", np.nan))
        except Exception:
            beta = p = np.nan

        rows.append({
            "excluded": excluded,
            "n_excluded": int((df["slug"] == excluded).sum()),
            "n_remaining": len(sub),
            "beta": beta,
            "p": p,
            "delta_beta": beta - beta_full if np.isfinite(beta) else np.nan,
        })

    # 全部 beryl 排除
    beryl_mask = df["slug"].str.contains("beryl")
    sub_nb = df[~beryl_mask].copy()
    try:
        model_nb = smf.mixedlm("alpha_unit ~ D_peak_unit",
                                data=sub_nb, groups=sub_nb["slug"], re_formula="1")
        res_nb = model_nb.fit(reml=True, method="lbfgs", maxiter=600, disp=False)
        rows.append({
            "excluded": "ALL_BERYL",
            "n_excluded": int(beryl_mask.sum()),
            "n_remaining": len(sub_nb),
            "beta": float(res_nb.params.get("D_peak_unit", np.nan)),
            "p": float(res_nb.pvalues.get("D_peak_unit", np.nan)),
            "delta_beta": np.nan,
        })
    except Exception:
        pass

    result = pd.DataFrame(rows)
    result.to_csv(OUT_DIR / "part4_loo.csv", index=False)
    print(f"Full model: beta={beta_full:.4f}, p={p_full:.4f}")
    print()
    print(result.to_string(index=False))
    print()
    return result


# ────────────────────────────────────────────
# Part 5: delta_peak_unit 语义诊断
# ────────────────────────────────────────────
def part5_delta_semantics(df: pd.DataFrame) -> None:
    print("=" * 60)
    print("Part 5: delta_peak_unit 与 distance_km 的关系")
    print("=" * 60)

    # delta_peak_unit 是否只是 distance 的代理？
    rows = []
    for slug in sorted(df["slug"].unique()):
        sub = df[df["slug"] == slug]
        if len(sub) < 5:
            continue
        rho_dd, p_dd = stats.spearmanr(sub["delta_peak_unit"], sub["distance_km"])
        rho_da, p_da = stats.spearmanr(sub["delta_peak_unit"], sub["alpha_unit"])
        rows.append({
            "slug": slug,
            "n": len(sub),
            "rho_delta_vs_dist": float(rho_dd),
            "p_delta_vs_dist": float(p_dd),
            "rho_delta_vs_alpha": float(rho_da),
            "p_delta_vs_alpha": float(p_da),
        })

    result = pd.DataFrame(rows)
    result.to_csv(OUT_DIR / "part5_delta_semantics.csv", index=False)
    print(result.to_string(index=False))

    # pooled
    rho_all, p_all = stats.spearmanr(df["delta_peak_unit"], df["distance_km"])
    print(f"\nPooled delta_peak vs distance: rho={rho_all:.3f}, p={p_all:.2e}")
    print()


# ────────────────────────────────────────────
# Part 6: 综合结论表
# ────────────────────────────────────────────
def part6_verdict(df: pd.DataFrame) -> None:
    print("=" * 60)
    print("Part 6: 综合结论")
    print("=" * 60)

    checks = []

    # 1. 原始随机截距模型
    try:
        m = smf.mixedlm("alpha_unit ~ D_peak_unit", data=df,
                         groups=df["slug"], re_formula="1")
        r = m.fit(reml=True, method="lbfgs", maxiter=600, disp=False)
        checks.append(("Random Intercept (D_peak)", f"beta={r.params['D_peak_unit']:.3f}", f"p={r.pvalues['D_peak_unit']:.4f}"))
    except Exception:
        pass

    # 2. 随机斜率
    try:
        m = smf.mixedlm("alpha_unit ~ D_peak_unit", data=df,
                         groups=df["slug"], re_formula="~D_peak_unit")
        r = m.fit(reml=True, method="lbfgs", maxiter=600, disp=False)
        checks.append(("Random Slope (D_peak)", f"beta={r.params['D_peak_unit']:.3f}", f"p={r.pvalues['D_peak_unit']:.4f}"))
    except Exception:
        pass

    # 3. Mundlak within
    tmp = df[["slug", "alpha_unit", "D_peak_unit"]].copy()
    tmp["D_within"] = tmp["D_peak_unit"] - tmp.groupby("slug")["D_peak_unit"].transform("mean")
    tmp["D_between"] = tmp.groupby("slug")["D_peak_unit"].transform("mean")
    try:
        m = smf.mixedlm("alpha_unit ~ D_within + D_between",
                         data=tmp, groups=tmp["slug"], re_formula="1")
        r = m.fit(reml=True, method="lbfgs", maxiter=600, disp=False)
        checks.append(("Mundlak Within (D_peak)", f"beta={r.params['D_within']:.3f}", f"p={r.pvalues['D_within']:.4f}"))
    except Exception:
        pass

    # 4. 控制 fit quality
    try:
        m = smf.mixedlm("alpha_unit ~ D_peak_unit + n_mono + r2_unit",
                         data=df, groups=df["slug"], re_formula="1")
        r = m.fit(reml=True, method="lbfgs", maxiter=600, disp=False)
        checks.append(("RI + n_mono + r2 控制", f"beta={r.params['D_peak_unit']:.3f}", f"p={r.pvalues['D_peak_unit']:.4f}"))
    except Exception:
        pass

    # 5. n_mono>=5 子集的随机截距
    sub5 = df[df["n_mono"] >= 5].copy()
    try:
        m = smf.mixedlm("alpha_unit ~ D_peak_unit", data=sub5,
                         groups=sub5["slug"], re_formula="1")
        r = m.fit(reml=True, method="lbfgs", maxiter=600, disp=False)
        checks.append((f"RI, n_mono>=5 (n={len(sub5)})", f"beta={r.params['D_peak_unit']:.3f}", f"p={r.pvalues['D_peak_unit']:.4f}"))
    except Exception:
        pass

    # 6. demeaned Spearman
    dm = df.copy()
    dm["a_dm"] = dm["alpha_unit"] - dm.groupby("slug")["alpha_unit"].transform("mean")
    dm["d_dm"] = dm["D_peak_unit"] - dm.groupby("slug")["D_peak_unit"].transform("mean")
    rho, p = stats.spearmanr(dm["a_dm"], dm["d_dm"])
    checks.append(("Demeaned Spearman", f"rho={rho:.3f}", f"p={p:.2e}"))

    # 7. 方向一致性
    dir_rows = []
    for slug in sorted(df["slug"].unique()):
        sub = df[df["slug"] == slug]
        if len(sub) < 5:
            continue
        r, p = stats.spearmanr(sub["D_peak_unit"], sub["alpha_unit"])
        dir_rows.append(r)
    n_pos = sum(1 for x in dir_rows if x > 0)
    n_neg = sum(1 for x in dir_rows if x < 0)
    sp = float(stats.binomtest(n_pos, n_pos + n_neg, 0.5).pvalue)
    checks.append(("Direction Consistency", f"{n_pos}+ vs {n_neg}-", f"sign p={sp:.4f}"))

    print()
    print("D_peak_unit → alpha_unit 效应的多重检验汇总:")
    print("-" * 70)
    for name, est, sig in checks:
        print(f"  {name:40s} {est:20s} {sig}")
    print("-" * 70)
    print()

    verdict_df = pd.DataFrame(checks, columns=["test", "estimate", "significance"])
    verdict_df.to_csv(OUT_DIR / "part6_verdict.csv", index=False)


def main():
    global FITS_CSV, EVENT_CORR_CSV, OUT_DIR
    parser = argparse.ArgumentParser(description="Subregion 综合诊断")
    parser.add_argument("--fits-csv", default=str(DEFAULT_FITS_CSV))
    parser.add_argument("--event-corr-csv", default=str(DEFAULT_EVENT_CORR_CSV))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    FITS_CSV = Path(args.fits_csv)
    EVENT_CORR_CSV = Path(args.event_corr_csv)
    OUT_DIR = Path(args.out_dir)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    df = load_data()
    part0_overview(df)
    part1_snr_confound(df)
    part2_controlled_model(df)
    part3_meta_analysis(df)
    part4_loo(df)
    part5_delta_semantics(df)
    part6_verdict(df)

    print("\n所有输出已写入:", OUT_DIR)


if __name__ == "__main__":
    main()
