from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def try_fit_relaxation_models(ts: pd.DataFrame, output_path: Path, *, exclude_t0: bool = True) -> None:
    try:
        from scipy.optimize import curve_fit  # type: ignore
    except Exception:
        return

    def exp_model(t, tau, a, c):
        return a * np.exp(-t / tau) + c

    def power_law(t, alpha, a, c):
        return a * np.power(t + 1.0, -alpha) + c

    def stretched_exp(t, tau, beta, a, c):
        return a * np.exp(-np.power(t / tau, beta)) + c

    models = {
        "exponential": (exp_model, 3, dict(p0=[72.0, -1.0, 0.0], bounds=([0.1, -np.inf, -np.inf], [2000, np.inf, np.inf]))),
        "power_law": (power_law, 3, dict(p0=[0.5, -1.0, 0.0], bounds=([0.01, -np.inf, -np.inf], [3.0, np.inf, np.inf]))),
        "stretched_exp": (
            stretched_exp,
            4,
            dict(
                p0=[72.0, 0.6, -1.0, 0.0],
                bounds=([0.1, 0.1, -np.inf, -np.inf], [2000, 2.0, np.inf, np.inf]),
            ),
        ),
    }

    rows: list[dict] = []
    for dist_bin, sub in ts.groupby("distance_bin", sort=False, observed=True):
        t = sub["hours_since_quake"].to_numpy(dtype=float)
        y = sub["z_score_mean"].to_numpy(dtype=float)
        mask = np.isfinite(t) & np.isfinite(y)
        if exclude_t0:
            mask &= t > 0
        else:
            mask &= t >= 0

        t, y = t[mask], y[mask]
        if len(t) < 10:
            continue

        for name, (fn, k, kw) in models.items():
            try:
                popt, _ = curve_fit(fn, t, y, maxfev=8000, **kw)
                resid = y - fn(t, *popt)
                sse = float(np.sum(resid**2))
                n = len(t)
                aic = n * np.log(sse / n) + 2 * k
                bic = n * np.log(sse / n) + k * np.log(n)
                row = {
                    "distance_bin": str(dist_bin),
                    "model": name,
                    "n_points": n,
                    "sse": sse,
                    "aic": aic,
                    "bic": bic,
                }
                if name == "exponential":
                    row.update({"tau": popt[0], "A": popt[1], "C": popt[2]})
                elif name == "power_law":
                    row.update({"alpha": popt[0], "A": popt[1], "C": popt[2]})
                else:
                    row.update({"tau": popt[0], "beta": popt[1], "A": popt[2], "C": popt[3]})
                rows.append(row)
            except Exception:
                continue

    if not rows:
        return

    fit_df = pd.DataFrame(rows)
    best = fit_df.loc[fit_df.groupby("distance_bin")["bic"].idxmin()].copy()
    best.insert(1, "best_by", "bic")

    fit_df.to_csv(output_path.with_name(output_path.stem + "_all_models.csv"), index=False)
    best.to_csv(output_path, index=False)
