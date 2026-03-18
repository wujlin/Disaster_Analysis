from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`。") from e

try:
    import statsmodels.formula.api as smf
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：statsmodels。请先运行 `pip install -r requirements.txt`。") from e

try:
    from scipy import stats as sp_stats
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：scipy。请先运行 `pip install -r requirements.txt`。") from e


@dataclass(frozen=True)
class JointModelConfig:
    input_csv: Path
    out_dir: Path
    min_n_mono: int = 3


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _fit_mixed_ri(df: pd.DataFrame, formula: str, label: str) -> dict:
    """随机截距混合效应模型 (REML)。"""
    try:
        model = smf.mixedlm(formula, data=df, groups=df["slug"], re_formula="1")
        result = model.fit(reml=True, method="lbfgs", maxiter=600, disp=False)
        ci = result.conf_int()
        predictors = [p.strip() for p in formula.split("~")[1].split("+")]
        rows = []
        for name in predictors:
            name = name.strip()
            rows.append({
                "model": label,
                "predictor": name,
                "coef": float(result.params.get(name, np.nan)),
                "se": float(result.bse.get(name, np.nan)),
                "z": float(result.tvalues.get(name, np.nan)),
                "p": float(result.pvalues.get(name, np.nan)),
                "ci_low": float(ci.loc[name, 0]) if name in ci.index else np.nan,
                "ci_high": float(ci.loc[name, 1]) if name in ci.index else np.nan,
            })
        return {"rows": rows, "n_obs": len(df), "n_events": df["slug"].nunique(),
                "converged": True}
    except Exception as e:
        return {"rows": [], "n_obs": len(df), "n_events": df["slug"].nunique(),
                "converged": False, "error": str(e)}


def _two_stage_meta(df: pd.DataFrame, x_col: str, y_col: str = "alpha_unit") -> dict:
    """每事件独立 OLS，然后等权 + IV 加权汇总。"""
    slugs = sorted(df["slug"].unique())
    betas, ses, ns = [], [], []
    for slug in slugs:
        sub = df[df["slug"] == slug]
        if len(sub) < 5:
            continue
        slope, _, _, p, se = sp_stats.linregress(sub[x_col].values, sub[y_col].values)
        betas.append(slope)
        ses.append(se)
        ns.append(len(sub))

    betas = np.array(betas)
    ses = np.array(ses)
    n_ev = len(betas)
    if n_ev < 3:
        return {"n_events": n_ev, "uw_mean": np.nan, "uw_p": np.nan}

    t_stat, t_p = sp_stats.ttest_1samp(betas, 0)
    n_pos = int((betas > 0).sum())
    n_neg = int((betas < 0).sum())
    sign_p = float(sp_stats.binomtest(n_pos, n_pos + n_neg, 0.5).pvalue) if (n_pos + n_neg) > 0 else np.nan

    w = 1.0 / (ses ** 2 + 1e-12)
    iv_mean = np.sum(w * betas) / np.sum(w)
    iv_se = 1.0 / np.sqrt(np.sum(w))
    iv_z = iv_mean / iv_se
    iv_p = 2 * (1 - sp_stats.norm.cdf(abs(iv_z)))

    return {
        "predictor": x_col, "n_events": n_ev,
        "uw_mean": float(np.mean(betas)), "uw_se": float(np.std(betas, ddof=1) / np.sqrt(n_ev)),
        "uw_t": float(t_stat), "uw_p": float(t_p),
        "iv_mean": float(iv_mean), "iv_se": float(iv_se), "iv_p": float(iv_p),
        "n_positive": n_pos, "n_negative": n_neg, "sign_test_p": sign_p,
    }


def run(cfg: JointModelConfig) -> Path:
    _ensure_dir(cfg.out_dir)
    df_raw = pd.read_csv(cfg.input_csv)

    needed = {"slug", "alpha_unit", "D_peak_unit", "delta_peak_unit", "distance_km"}
    for col in ["alpha_unit", "D_peak_unit", "delta_peak_unit", "distance_km",
                "n_mono", "r2_unit"]:
        if col in df_raw.columns:
            df_raw[col] = pd.to_numeric(df_raw[col], errors="coerce")
    df_raw["slug"] = df_raw["slug"].astype(str)
    df = df_raw.dropna(subset=list(needed)).reset_index(drop=True)
    if df.empty:
        raise ValueError("清洗后无可用样本")

    # ─── M0: 原始三预测变量随机截距 (REML) ───
    m0 = _fit_mixed_ri(df, "alpha_unit ~ D_peak_unit + delta_peak_unit + distance_km",
                        "M0_all_RI")

    # ─── M1: 加入 fit quality 控制变量 ───
    m1_rows = []
    if "n_mono" in df.columns and "r2_unit" in df.columns:
        m1 = _fit_mixed_ri(df,
            "alpha_unit ~ D_peak_unit + delta_peak_unit + distance_km + n_mono + r2_unit",
            "M1_quality_controlled")
        m1_rows = m1.get("rows", [])

    # ─── M2: 高质量子集 (n_mono >= 5) ───
    m2_rows = []
    if "n_mono" in df.columns:
        df_hq = df[df["n_mono"] >= 5].copy()
        if df_hq["slug"].nunique() >= 3 and len(df_hq) >= 20:
            m2 = _fit_mixed_ri(df_hq,
                "alpha_unit ~ D_peak_unit + delta_peak_unit + distance_km",
                f"M2_n_mono_ge5 (n={len(df_hq)})")
            m2_rows = m2.get("rows", [])

    all_coef_rows = m0.get("rows", []) + m1_rows + m2_rows
    coef_df = pd.DataFrame(all_coef_rows)

    # ─── Two-Stage Meta-Analysis ───
    meta_rows = []
    for x_col in ["D_peak_unit", "delta_peak_unit", "distance_km"]:
        meta_rows.append(_two_stage_meta(df, x_col))
    meta_df = pd.DataFrame(meta_rows)

    # ─── 输出 ───
    out_csv = cfg.out_dir / "mixed_effects_joint_3predictor.csv"
    coef_df.to_csv(out_csv, index=False)
    meta_df.to_csv(cfg.out_dir / "two_stage_meta_analysis.csv", index=False)

    meta_info = {
        "input_csv": str(cfg.input_csv),
        "output_csv": str(out_csv),
        "n_obs_all": int(len(df)),
        "n_events_all": int(df["slug"].nunique()),
        "n_obs_hq": int(len(df_hq)) if "n_mono" in df.columns and len(df_hq) else 0,
        "models": ["M0_all_RI", "M1_quality_controlled", "M2_n_mono_ge5"],
    }
    (cfg.out_dir / "metadata.json").write_text(
        json.dumps(meta_info, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_csv


def cli_main() -> None:
    p = argparse.ArgumentParser(
        description="Subregion mixed-effects (含 fit quality 控制 + meta-analysis)")
    p.add_argument("--input-csv", type=Path, default=Path(
        "outputs/cross_disaster_comparison/"
        "geo_unit_scale_unified_h8_mtw4_mpp3_relaxed_20260225_141630/"
        "tables/geo_unit_fits.csv"))
    p.add_argument("--out-dir", type=Path, default=Path(
        "outputs/cross_disaster_comparison/subregion_joint_model_unified_h8"))
    p.add_argument("--min-n-mono", type=int, default=3)
    args = p.parse_args()
    out = run(JointModelConfig(
        input_csv=args.input_csv, out_dir=args.out_dir, min_n_mono=args.min_n_mono))
    print(f"[ok] wrote: {out}")


if __name__ == "__main__":
    cli_main()

