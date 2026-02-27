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


@dataclass(frozen=True)
class JointModelConfig:
    input_csv: Path
    out_dir: Path


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _fit_joint_model(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    needed = {"slug", "alpha_unit", "D_peak_unit", "delta_peak_unit", "distance_km"}
    miss = sorted(needed - set(df.columns))
    if miss:
        raise ValueError(f"输入缺少列：{miss}")

    use = df[list(needed)].copy()
    for col in ["alpha_unit", "D_peak_unit", "delta_peak_unit", "distance_km"]:
        use[col] = pd.to_numeric(use[col], errors="coerce")
    use["slug"] = use["slug"].astype(str)
    use = use.dropna(subset=["slug", "alpha_unit", "D_peak_unit", "delta_peak_unit", "distance_km"]).reset_index(drop=True)
    if use.empty:
        raise ValueError("清洗后无可用样本")

    model = smf.mixedlm(
        "alpha_unit ~ D_peak_unit + delta_peak_unit + distance_km",
        data=use,
        groups=use["slug"],
        re_formula="1",
    )
    result = model.fit(reml=False, method="lbfgs", maxiter=500, disp=False)

    ci = result.conf_int()
    out_rows: list[dict] = []
    for name in ["D_peak_unit", "delta_peak_unit", "distance_km"]:
        out_rows.append(
            {
                "predictor": name,
                "coef": float(result.params.get(name, np.nan)),
                "se": float(result.bse.get(name, np.nan)),
                "z": float(result.tvalues.get(name, np.nan)),
                "p": float(result.pvalues.get(name, np.nan)),
                "ci_low": float(ci.loc[name, 0]) if name in ci.index else np.nan,
                "ci_high": float(ci.loc[name, 1]) if name in ci.index else np.nan,
            }
        )
    summary = {
        "n_obs": int(len(use)),
        "n_events": int(use["slug"].nunique()),
        "aic": float(result.aic) if np.isfinite(result.aic) else None,
        "bic": float(result.bic) if np.isfinite(result.bic) else None,
        "llf": float(result.llf) if np.isfinite(result.llf) else None,
    }
    return pd.DataFrame(out_rows), summary


def run(cfg: JointModelConfig) -> Path:
    _ensure_dir(cfg.out_dir)
    df = pd.read_csv(cfg.input_csv)
    coef_df, meta = _fit_joint_model(df)
    out_csv = cfg.out_dir / "mixed_effects_joint_3predictor.csv"
    coef_df.to_csv(out_csv, index=False)
    (cfg.out_dir / "metadata.json").write_text(
        json.dumps(
            {
                "input_csv": str(cfg.input_csv),
                "output_csv": str(out_csv),
                **meta,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return out_csv


def cli_main() -> None:
    p = argparse.ArgumentParser(description="Subregion 三预测变量 mixed-effects: alpha_unit ~ D_peak_unit + delta_peak_unit + distance_km")
    p.add_argument(
        "--input-csv",
        type=Path,
        default=Path(
            "outputs/cross_disaster_comparison/"
            "geo_unit_scale_unified_h8_mtw4_mpp3_relaxed_20260225_141630/"
            "tables/geo_unit_fits.csv"
        ),
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("outputs/cross_disaster_comparison/subregion_joint_model_unified_h8"),
    )
    args = p.parse_args()

    out = run(JointModelConfig(input_csv=args.input_csv, out_dir=args.out_dir))
    print(f"[ok] wrote: {out}")


if __name__ == "__main__":
    cli_main()

