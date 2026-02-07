from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e


@dataclass(frozen=True)
class Config:
    phi_rt_long_csv: Path
    out_dir: Path
    day_hours: float = 24.0
    require_complete_day: bool = False


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _sum_min_count_1(s: pd.Series) -> float:
    return float(s.sum(min_count=1))


def _aggregate_daily(df: pd.DataFrame, *, day_hours: float, require_complete_day: bool) -> pd.DataFrame:
    need = {"hours_since_quake", "r_bin_km", "baseline_sum", "crisis_sum", "baseline_sum_overlap", "crisis_sum_overlap", "phi_aggregate", "phi_overlap"}
    missing = sorted(need - set(df.columns))
    if missing:
        raise SystemExit(f"phi_rt_long 缺少列：{missing}")

    out = df.copy()
    out["hours_since_quake"] = pd.to_numeric(out["hours_since_quake"], errors="coerce")
    out["r_bin_km"] = pd.to_numeric(out["r_bin_km"], errors="coerce")
    for c in ["baseline_sum", "crisis_sum", "baseline_sum_overlap", "crisis_sum_overlap", "phi_aggregate", "phi_overlap"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["hours_since_quake", "r_bin_km"]).copy()
    if out.empty:
        return pd.DataFrame()

    day = np.floor(out["hours_since_quake"].to_numpy(dtype=float) / float(day_hours)).astype(int)
    out["day_idx"] = day
    out["day_start_hours"] = out["day_idx"].astype(float) * float(day_hours)

    g = (
        out.groupby(["day_idx", "day_start_hours", "r_bin_km"], observed=True)
        .agg(
            n_windows=("hours_since_quake", "count"),
            baseline_sum_day=("baseline_sum", _sum_min_count_1),
            crisis_sum_day=("crisis_sum", _sum_min_count_1),
            baseline_sum_overlap_day=("baseline_sum_overlap", _sum_min_count_1),
            crisis_sum_overlap_day=("crisis_sum_overlap", _sum_min_count_1),
            phi_aggregate_mor=("phi_aggregate", "mean"),
            phi_overlap_mor=("phi_overlap", "mean"),
        )
        .reset_index()
    )
    g["phi_aggregate_ros"] = g["crisis_sum_day"] / g["baseline_sum_day"]
    g["phi_overlap_ros"] = g["crisis_sum_overlap_day"] / g["baseline_sum_overlap_day"]

    if require_complete_day:
        # 以该文件中每一天出现的窗口数量的众数作为“完整天”的窗口数
        n_mode = int(out.groupby("day_idx", observed=True)["hours_since_quake"].count().mode().iloc[0])
        g = g[g["n_windows"] >= n_mode].copy()

    # 差异（用于诊断 mean-of-ratios vs ratio-of-sums）
    g["delta_phi_aggregate"] = g["phi_aggregate_ros"] - g["phi_aggregate_mor"]
    g["delta_phi_overlap"] = g["phi_overlap_ros"] - g["phi_overlap_mor"]

    return g.sort_values(["day_start_hours", "r_bin_km"], kind="stable")


def run(cfg: Config) -> None:
    out = Path(cfg.out_dir)
    tabs = out / "tables"
    _ensure_dir(tabs)

    df = pd.read_csv(cfg.phi_rt_long_csv)
    daily = _aggregate_daily(df, day_hours=float(cfg.day_hours), require_complete_day=bool(cfg.require_complete_day))
    daily.to_csv(tabs / "phi_rt_daily_compare.csv", index=False)

    # 总结：差异的量级
    summary = {
        "phi_rt_long_csv": str(Path(cfg.phi_rt_long_csv)),
        "day_hours": float(cfg.day_hours),
        "require_complete_day": int(bool(cfg.require_complete_day)),
        "n_rows_daily": int(daily.shape[0]),
        "delta_phi_aggregate_abs_p95": float(np.nanpercentile(np.abs(pd.to_numeric(daily["delta_phi_aggregate"], errors="coerce")), 95))
        if not daily.empty
        else float("nan"),
        "delta_phi_overlap_abs_p95": float(np.nanpercentile(np.abs(pd.to_numeric(daily["delta_phi_overlap"], errors="coerce")), 95))
        if not daily.empty
        else float("nan"),
        "delta_phi_aggregate_abs_max": float(np.nanmax(np.abs(pd.to_numeric(daily["delta_phi_aggregate"], errors="coerce")))) if not daily.empty else float("nan"),
        "delta_phi_overlap_abs_max": float(np.nanmax(np.abs(pd.to_numeric(daily["delta_phi_overlap"], errors="coerce")))) if not daily.empty else float("nan"),
    }
    (out / "metadata.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Done. Wrote: {tabs / 'phi_rt_daily_compare.csv'}")


def cli_main() -> None:
    p = argparse.ArgumentParser(description="验证 8h 窗口 phi_rt_long 的 24h 聚合方式（RoS vs MoR）")
    p.add_argument("--phi-rt-long-csv", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, default=Path("outputs/_tmp_phi_time_aggregation_verify"))
    p.add_argument("--day-hours", type=float, default=24.0)
    p.add_argument("--require-complete-day", action="store_true")
    args = p.parse_args()

    run(
        Config(
            phi_rt_long_csv=Path(args.phi_rt_long_csv),
            out_dir=Path(args.out_dir),
            day_hours=float(args.day_hours),
            require_complete_day=bool(args.require_complete_day),
        )
    )


if __name__ == "__main__":
    cli_main()

