from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FitConfig:
    y_col: str = "z_score_mean"
    y_std_col: str | None = "z_score_std"
    y_n_col: str | None = "z_score_count"
    min_points: int = 10
    exclude_t0: bool = True
    min_sigma: float = 1e-6
    seed: int = 7


def _build_sigma(sub: pd.DataFrame, *, y_std_col: str, y_n_col: str, min_sigma: float) -> np.ndarray:
    std = pd.to_numeric(sub[y_std_col], errors="coerce").to_numpy(dtype=float)
    n = pd.to_numeric(sub[y_n_col], errors="coerce").to_numpy(dtype=float)
    se = std / np.sqrt(np.where(n > 0, n, np.nan))
    is_finite = np.isfinite(se)
    se = np.where(is_finite & (se >= min_sigma), se, np.where(is_finite, min_sigma, np.nan))
    return se


def _near_bound(v: float, lo: float, hi: float, *, rel_tol: float = 1e-3) -> bool:
    if np.isfinite(lo):
        if abs(v - lo) <= rel_tol * (abs(lo) + 1.0):
            return True
    if np.isfinite(hi):
        if abs(v - hi) <= rel_tol * (abs(hi) + 1.0):
            return True
    return False


def fit_relaxation_models(
    ts: pd.DataFrame,
    output_path: Path,
    *,
    cfg: FitConfig | None = None,
) -> None:
    """
    对每个 distance_bin 做多模型竞争并输出：
    - *_all_models.csv：每个 bin × 每个模型的拟合结果
    - *.csv：每个 bin 的 BIC 最优模型（best_by=bic）

    说明：
    - 若提供 y_std_col/y_n_col，则使用观测标准误（SE）作为 curve_fit 的 sigma，并以 chi2 计算 AIC/BIC。
      这更符合“不同时间点不确定性不同”的现实（异方差）。
    - 若缺少 scipy，会静默跳过（保持 pipeline 可跑）。
    """

    cfg = cfg or FitConfig()
    fit_df = fit_relaxation_models_table(ts, cfg=cfg)
    if fit_df.empty:
        return
    best = fit_df.loc[fit_df.groupby("distance_bin")["bic"].idxmin()].copy()
    best.insert(1, "best_by", "bic")

    fit_df.to_csv(output_path.with_name(output_path.stem + "_all_models.csv"), index=False)
    best.to_csv(output_path, index=False)


def fit_relaxation_models_table(ts: pd.DataFrame, *, cfg: FitConfig | None = None) -> pd.DataFrame:
    """
    与 fit_relaxation_models 同逻辑，但返回 DataFrame（方便做 bootstrap / 时间截断等稳健性分析）。
    """

    cfg = cfg or FitConfig()
    try:
        from scipy.optimize import curve_fit  # type: ignore
    except Exception:
        return pd.DataFrame()

    def exp_model(t, tau, a, c):
        return a * np.exp(-t / tau) + c

    def power_law(t, alpha, a, c):
        return a * np.power(t + 1.0, -alpha) + c

    def stretched_exp(t, tau, beta, a, c):
        return a * np.exp(-np.power(t / tau, beta)) + c

    def log_relax(t, tau, a, c):
        # 经验型“对数松弛”候选：在有限时间窗内可拟合慢恢复/缓慢漂移
        # 注意：t→∞ 时不收敛到常数（会随 log 继续漂移），因此更适合作为竞争模型/诊断工具。
        return a * np.log1p(t / tau) + c

    rows: list[dict] = []
    for dist_bin, sub in ts.groupby("distance_bin", sort=False, observed=True):
        t = pd.to_numeric(sub["hours_since_quake"], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(sub[cfg.y_col], errors="coerce").to_numpy(dtype=float)

        sigma = None
        use_sigma = cfg.y_std_col is not None and cfg.y_n_col is not None
        if use_sigma:
            sigma = _build_sigma(sub, y_std_col=cfg.y_std_col, y_n_col=cfg.y_n_col, min_sigma=cfg.min_sigma)

        mask = np.isfinite(t) & np.isfinite(y)
        if sigma is not None:
            mask &= np.isfinite(sigma)
        if cfg.exclude_t0:
            mask &= t > 0
        else:
            mask &= t >= 0

        t, y = t[mask], y[mask]
        if sigma is not None:
            sigma = sigma[mask]

        if len(t) < int(cfg.min_points):
            continue

        t_max = float(np.nanmax(t))
        tau_hi = max(2000.0, 3.0 * t_max)

        y0 = float(y[0])
        y_end = float(np.median(y[-max(3, len(y) // 5) :]))
        a_guess = y0 - y_end
        c_guess = y_end
        tau_guess = float(np.clip(72.0, 1.0, max(10.0, t_max)))

        log_a_guess = a_guess
        log_den = float(np.log1p(float(t[-1]) / max(tau_guess, 1e-6)))
        if np.isfinite(log_den) and log_den != 0.0:
            log_a_guess = (y_end - y0) / log_den
        log_c_guess = y0

        models: dict[str, tuple[object, int, dict]] = {
            "exponential": (
                exp_model,
                3,
                dict(p0=[tau_guess, a_guess, c_guess], bounds=([0.1, -np.inf, -np.inf], [tau_hi, np.inf, np.inf])),
            ),
            "power_law": (
                power_law,
                3,
                dict(p0=[0.5, a_guess, c_guess], bounds=([0.01, -np.inf, -np.inf], [3.0, np.inf, np.inf])),
            ),
            "stretched_exp": (
                stretched_exp,
                4,
                dict(p0=[tau_guess, 0.6, a_guess, c_guess], bounds=([0.1, 0.1, -np.inf, -np.inf], [tau_hi, 2.0, np.inf, np.inf])),
            ),
            "log": (
                log_relax,
                3,
                dict(p0=[tau_guess, log_a_guess, log_c_guess], bounds=([0.1, -np.inf, -np.inf], [tau_hi, np.inf, np.inf])),
            ),
        }

        for name, (fn, k, kw) in models.items():
            try:
                fit_kw = dict(maxfev=12000, **kw)
                if sigma is not None:
                    fit_kw.update({"sigma": sigma, "absolute_sigma": True})
                popt, _ = curve_fit(fn, t, y, **fit_kw)
                yhat = fn(t, *popt)
                resid = y - yhat

                if sigma is not None:
                    chi2 = float(np.sum((resid / sigma) ** 2))
                    aic = chi2 + 2 * k
                    bic = chi2 + k * np.log(len(t))
                    sse = float(np.sum(resid**2))
                else:
                    sse = float(np.sum(resid**2))
                    n = len(t)
                    aic = n * np.log(sse / n) + 2 * k
                    bic = n * np.log(sse / n) + k * np.log(n)
                    chi2 = float("nan")

                lo_bounds, hi_bounds = kw.get("bounds", (None, None))
                at_bounds = False
                if lo_bounds is not None and hi_bounds is not None:
                    for v, lo, hi in zip(popt, lo_bounds, hi_bounds, strict=False):
                        at_bounds |= _near_bound(float(v), float(lo), float(hi))

                row = {
                    "distance_bin": str(dist_bin),
                    "model": name,
                    "n_points": int(len(t)),
                    "sse": float(sse),
                    "chi2": float(chi2),
                    "aic": float(aic),
                    "bic": float(bic),
                    "at_bounds": bool(at_bounds),
                }
                if name in {"exponential", "log"}:
                    row.update({"tau": float(popt[0]), "A": float(popt[1]), "C": float(popt[2])})
                elif name == "power_law":
                    row.update({"alpha": float(popt[0]), "A": float(popt[1]), "C": float(popt[2])})
                else:
                    row.update({"tau": float(popt[0]), "beta": float(popt[1]), "A": float(popt[2]), "C": float(popt[3])})
                rows.append(row)
            except Exception:
                continue

    return pd.DataFrame(rows)


def try_fit_relaxation_models(ts: pd.DataFrame, output_path: Path, *, exclude_t0: bool = True) -> None:
    """
    兼容旧入口：默认拟合 z_score_mean（并写入 best_bic.csv）。
    """

    fit_relaxation_models(ts, output_path, cfg=FitConfig(exclude_t0=exclude_t0))
