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
    from scipy.stats import binomtest
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：scipy。请先运行 `pip install -r requirements.txt`。") from e

try:
    import statsmodels.formula.api as smf
    from statsmodels.regression.mixed_linear_model import MixedLMParams
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：statsmodels。请先运行 `pip install -r requirements.txt`。") from e


@dataclass(frozen=True)
class CorrectionConfig:
    fits_csv: Path
    event_corr_csv: Path
    out_dir: Path


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _load_fit_df(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    needed = {"slug", "alpha_unit", "D_peak_unit", "delta_peak_unit", "distance_km"}
    miss = sorted(needed - set(df.columns))
    if miss:
        raise ValueError(f"输入缺少列：{miss}")
    use = df.copy()
    use["slug"] = use["slug"].astype(str)
    for col in ["alpha_unit", "D_peak_unit", "delta_peak_unit", "distance_km"]:
        use[col] = pd.to_numeric(use[col], errors="coerce")
    use = use.dropna(subset=["slug", "alpha_unit", "D_peak_unit", "delta_peak_unit", "distance_km"]).reset_index(drop=True)
    if use.empty:
        raise ValueError("清洗后无可用 subregion 样本")
    return use


def _fit_with_attempts(model, methods: tuple[str, ...]) -> tuple[object | None, str, bool, str]:
    last_err = ""
    for m in methods:
        try:
            res = model.fit(reml=True, method=m, maxiter=600, disp=False)
            if bool(getattr(res, "converged", False)):
                return res, m, True, ""
            last_err = f"method={m}, converged=False"
        except Exception as e:
            last_err = f"method={m}, err={type(e).__name__}: {e}"
    return None, "", False, last_err


def _fit_random_slope(df: pd.DataFrame, predictor: str) -> pd.DataFrame:
    model = smf.mixedlm(
        f"alpha_unit ~ {predictor}",
        data=df,
        groups=df["slug"],
        re_formula=f"~{predictor}",
    )
    res, method, ok, msg = _fit_with_attempts(model, ("lbfgs", "nm", "powell"))
    fit_strategy = method

    if not ok:
        try:
            free = MixedLMParams.from_components(
                fe_params=np.ones(model.k_fe),
                cov_re=np.eye(model.k_re),
            )
            res = model.fit(reml=True, method="lbfgs", maxiter=600, disp=False, free=free)
            ok = bool(getattr(res, "converged", False))
            fit_strategy = "lbfgs_diag_free"
            if not ok and not msg:
                msg = "lbfgs_diag_free converged=False"
        except Exception as e:
            msg = f"{msg} | lbfgs_diag_free err={type(e).__name__}: {e}"

    if (res is None) or (not ok):
        return pd.DataFrame(
            [
                {
                    "predictor": predictor,
                    "fixed_beta": np.nan,
                    "fixed_se": np.nan,
                    "fixed_p": np.nan,
                    "random_intercept_var": np.nan,
                    "random_slope_var": np.nan,
                    "random_corr": np.nan,
                    "converged": False,
                    "fit_strategy": fit_strategy,
                    "message": msg,
                }
            ]
        )

    cov_re = np.asarray(res.cov_re, dtype=float)
    if cov_re.ndim == 2 and cov_re.shape == (2, 2):
        vi = float(cov_re[0, 0])
        vs = float(cov_re[1, 1])
        c = float(cov_re[0, 1])
        corr = c / np.sqrt(max(vi, 1e-12) * max(vs, 1e-12))
    else:
        vi = float(cov_re[0, 0]) if cov_re.size else np.nan
        vs = np.nan
        corr = np.nan

    return pd.DataFrame(
        [
            {
                "predictor": predictor,
                "fixed_beta": float(res.params.get(predictor, np.nan)),
                "fixed_se": float(res.bse.get(predictor, np.nan)),
                "fixed_p": float(res.pvalues.get(predictor, np.nan)),
                "random_intercept_var": vi,
                "random_slope_var": vs,
                "random_corr": float(corr) if np.isfinite(corr) else np.nan,
                "converged": bool(getattr(res, "converged", False)),
                "fit_strategy": fit_strategy,
                "message": "",
            }
        ]
    )


def _fit_mundlak(df: pd.DataFrame, predictor: str) -> pd.DataFrame:
    tmp = df[["slug", "alpha_unit", predictor]].copy()
    tmp[f"{predictor}_event_mean"] = tmp.groupby("slug")[predictor].transform("mean")
    tmp[f"{predictor}_within"] = tmp[predictor] - tmp[f"{predictor}_event_mean"]
    formula = f"alpha_unit ~ {predictor}_within + {predictor}_event_mean"
    model = smf.mixedlm(formula, data=tmp, groups=tmp["slug"], re_formula="1")
    res, method, ok, msg = _fit_with_attempts(model, ("lbfgs", "nm", "powell"))
    if (res is None) or (not ok):
        return pd.DataFrame(
            [
                {
                    "predictor": predictor,
                    "component": "within",
                    "coef": np.nan,
                    "se": np.nan,
                    "z": np.nan,
                    "p": np.nan,
                    "ci_low": np.nan,
                    "ci_high": np.nan,
                    "converged": False,
                    "fit_strategy": method,
                    "message": msg,
                },
                {
                    "predictor": predictor,
                    "component": "between",
                    "coef": np.nan,
                    "se": np.nan,
                    "z": np.nan,
                    "p": np.nan,
                    "ci_low": np.nan,
                    "ci_high": np.nan,
                    "converged": False,
                    "fit_strategy": method,
                    "message": msg,
                },
            ]
        )

    ci = res.conf_int()
    rows = []
    for comp, name in [("within", f"{predictor}_within"), ("between", f"{predictor}_event_mean")]:
        rows.append(
            {
                "predictor": predictor,
                "component": comp,
                "coef": float(res.params.get(name, np.nan)),
                "se": float(res.bse.get(name, np.nan)),
                "z": float(res.tvalues.get(name, np.nan)),
                "p": float(res.pvalues.get(name, np.nan)),
                "ci_low": float(ci.loc[name, 0]) if name in ci.index else np.nan,
                "ci_high": float(ci.loc[name, 1]) if name in ci.index else np.nan,
                "converged": bool(getattr(res, "converged", False)),
                "fit_strategy": method,
                "message": "",
            }
        )
    return pd.DataFrame(rows)


def _direction_consistency(path: Path) -> pd.DataFrame:
    corr = pd.read_csv(path)
    rows: list[dict] = []
    spec = [
        ("D_peak_unit", "rho_alpha_vs_D_peak_unit", "p_alpha_vs_D_peak_unit"),
        ("delta_peak_unit", "rho_alpha_vs_delta_peak_unit", "p_alpha_vs_delta_peak_unit"),
    ]
    for predictor, rho_col, p_col in spec:
        if (rho_col not in corr.columns) or (p_col not in corr.columns):
            rows.append(
                {
                    "predictor": predictor,
                    "n_events": 0,
                    "n_positive": 0,
                    "n_negative": 0,
                    "n_sig_positive": 0,
                    "n_sig_negative": 0,
                    "sign_test_p": np.nan,
                }
            )
            continue

        tmp = corr[[rho_col, p_col]].copy()
        tmp[rho_col] = pd.to_numeric(tmp[rho_col], errors="coerce")
        tmp[p_col] = pd.to_numeric(tmp[p_col], errors="coerce")
        tmp = tmp.dropna(subset=[rho_col]).reset_index(drop=True)
        rho = tmp[rho_col].to_numpy(dtype=float)
        pvals = tmp[p_col].to_numpy(dtype=float)

        n_pos = int((rho > 0).sum())
        n_neg = int((rho < 0).sum())
        n_sig_pos = int(((rho > 0) & (pvals < 0.05)).sum())
        n_sig_neg = int(((rho < 0) & (pvals < 0.05)).sum())
        n_nonzero = n_pos + n_neg
        sign_p = float(binomtest(k=n_pos, n=n_nonzero, p=0.5).pvalue) if n_nonzero > 0 else np.nan

        rows.append(
            {
                "predictor": predictor,
                "n_events": int(len(tmp)),
                "n_positive": n_pos,
                "n_negative": n_neg,
                "n_sig_positive": n_sig_pos,
                "n_sig_negative": n_sig_neg,
                "sign_test_p": sign_p,
            }
        )
    return pd.DataFrame(rows)


def run(cfg: CorrectionConfig) -> dict[str, Path]:
    _ensure_dir(cfg.out_dir)
    df = _load_fit_df(cfg.fits_csv)

    rs_d = _fit_random_slope(df, "D_peak_unit")
    rs_delta = _fit_random_slope(df, "delta_peak_unit")
    mundlak = pd.concat(
        [
            _fit_mundlak(df, "D_peak_unit"),
            _fit_mundlak(df, "delta_peak_unit"),
        ],
        ignore_index=True,
    )
    direction = _direction_consistency(cfg.event_corr_csv)

    p_rs_d = cfg.out_dir / "random_slope_D_peak.csv"
    p_rs_delta = cfg.out_dir / "random_slope_delta_peak.csv"
    p_mundlak = cfg.out_dir / "mundlak_decomposition.csv"
    p_direction = cfg.out_dir / "within_event_direction_consistency.csv"

    rs_d.to_csv(p_rs_d, index=False)
    rs_delta.to_csv(p_rs_delta, index=False)
    mundlak.to_csv(p_mundlak, index=False)
    direction.to_csv(p_direction, index=False)

    (cfg.out_dir / "metadata.json").write_text(
        json.dumps(
            {
                "fits_csv": str(cfg.fits_csv),
                "event_corr_csv": str(cfg.event_corr_csv),
                "n_obs": int(len(df)),
                "n_events": int(df["slug"].nunique()),
                "outputs": {
                    "random_slope_D_peak": str(p_rs_d),
                    "random_slope_delta_peak": str(p_rs_delta),
                    "mundlak_decomposition": str(p_mundlak),
                    "within_event_direction_consistency": str(p_direction),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "random_slope_D_peak": p_rs_d,
        "random_slope_delta_peak": p_rs_delta,
        "mundlak_decomposition": p_mundlak,
        "within_event_direction_consistency": p_direction,
    }


def cli_main() -> None:
    p = argparse.ArgumentParser(description="Subregion 模型修正：随机斜率 + Mundlak 分解 + 方向一致性")
    p.add_argument(
        "--fits-csv",
        type=Path,
        default=Path(
            "outputs/cross_disaster_comparison/"
            "geo_unit_scale_unified_h8_mtw4_mpp3_relaxed_20260225_141630/"
            "tables/geo_unit_fits.csv"
        ),
    )
    p.add_argument(
        "--event-corr-csv",
        type=Path,
        default=Path(
            "outputs/cross_disaster_comparison/"
            "geo_unit_scale_unified_h8_mtw4_mpp3_relaxed_20260225_141630/"
            "tables/event_unit_correlations.csv"
        ),
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("outputs/cross_disaster_comparison/subregion_model_correction_unified_h8"),
    )
    args = p.parse_args()
    out = run(
        CorrectionConfig(
            fits_csv=args.fits_csv,
            event_corr_csv=args.event_corr_csv,
            out_dir=args.out_dir,
        )
    )
    for k, v in out.items():
        print(f"[ok] {k}: {v}")


if __name__ == "__main__":
    cli_main()

