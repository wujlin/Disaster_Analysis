#!/usr/bin/env python3
"""
P0：0–150km、前 200 小时的“疏散-回流”分析

输出：
- tables/evacuation_return_summary_<metric>_0-150km_200h.csv
- figures/evacuation_return_<metric>_0-150km_200h.pdf/png
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


def _bootstrap_src() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class MetricSpec:
    y_col: str
    label: str


def _metric_spec(metric: str) -> MetricSpec:
    metric = str(metric).strip().lower()
    if metric in {"z", "z_score", "zscore"}:
        return MetricSpec(y_col="z_score_mean", label="z_score_mean")
    if metric in {"phi"}:
        return MetricSpec(y_col="phi_mean", label="phi_mean")
    raise SystemExit(f"未知 metric：{metric}（可选：z_score/phi）")


def _lin_interp_crossing(x0: float, y0: float, x1: float, y1: float, y_target: float) -> float | None:
    if not (x1 > x0):
        return None
    if (y0 - y_target) == 0:
        return x0
    if (y1 - y_target) == 0:
        return x1
    if (y0 - y_target) * (y1 - y_target) > 0:
        return None
    denom = (y1 - y0)
    if denom == 0:
        return None
    w = (y_target - y0) / denom
    return x0 + w * (x1 - x0)


def main() -> None:
    _bootstrap_src()

    try:
        import numpy as np
        import pandas as pd
    except ModuleNotFoundError as e:
        raise SystemExit("缺少依赖：numpy/pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

    try:
        from disaster import plot_style as ps
    except ModuleNotFoundError as e:
        raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

    import matplotlib.pyplot as plt
    from disaster.bins import parse_km_bin

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ts-csv",
        type=Path,
        default=Path("outputs/population_relaxation/tables/population_relaxation_by_distance.csv"),
        help="按距离分箱聚合后的时间序列 CSV（由 scripts/population_relaxation.py 生成）",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("outputs/population_relaxation"),
        help="输出根目录（会写入 figures/ 与 tables/）",
    )
    parser.add_argument("--metric", type=str, default="z_score", help="指标：z_score / phi")
    parser.add_argument("--max-distance-km", type=float, default=150.0, help="只分析 hi<=该值的距离 bin（默认 150km）")
    parser.add_argument("--min-hours", type=float, default=0.0, help="最小 hours_since_quake（默认 0）")
    parser.add_argument("--max-hours", type=float, default=200.0, help="最大 hours_since_quake（默认 200）")
    args = parser.parse_args()

    if not args.ts_csv.exists():
        raise SystemExit(f"未找到时间序列：{args.ts_csv}。请先运行 `python scripts/population_relaxation.py` 生成 tables。")

    out_fig = args.output_root / "figures"
    out_tbl = args.output_root / "tables"
    _ensure_dir(out_fig)
    _ensure_dir(out_tbl)

    spec = _metric_spec(args.metric)

    ts = pd.read_csv(args.ts_csv, parse_dates=["window_start_pt"])
    ts["hours_since_quake"] = pd.to_numeric(ts["hours_since_quake"], errors="coerce")
    ts[spec.y_col] = pd.to_numeric(ts[spec.y_col], errors="coerce")
    ts = ts[ts["hours_since_quake"].notna()].copy()
    ts = ts[(ts["hours_since_quake"] >= float(args.min_hours)) & (ts["hours_since_quake"] <= float(args.max_hours))].copy()

    # 选择 0–150km（按 bin 的 hi<=max_distance）
    ts["km_bin"] = ts["distance_bin"].astype(str).apply(parse_km_bin)
    ts["lo_km"] = ts["km_bin"].apply(lambda b: float(b.lo))
    ts["hi_km"] = ts["km_bin"].apply(lambda b: float(b.hi))
    ts = ts[ts["hi_km"] <= float(args.max_distance_km)].copy()

    if ts.empty:
        raise SystemExit("筛选后数据为空：请检查 ts-csv、距离分箱或时间范围。")

    bins_sorted = (
        ts[["distance_bin", "lo_km", "hi_km"]]
        .drop_duplicates()
        .sort_values(["lo_km", "hi_km"], kind="stable")["distance_bin"]
        .astype(str)
        .tolist()
    )

    rows: list[dict] = []
    for b in bins_sorted:
        sub = ts[ts["distance_bin"].astype(str) == b].sort_values("hours_since_quake", kind="stable").copy()
        x = sub["hours_since_quake"].to_numpy(dtype=float)
        y = sub[spec.y_col].to_numpy(dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        x, y = x[mask], y[mask]
        if len(x) < 3:
            continue

        i_min = int(np.argmin(y))
        t_min = float(x[i_min])
        y_min = float(y[i_min])

        t_cross0 = None
        for tt, yy in zip(x[i_min:], y[i_min:], strict=False):
            if yy >= 0:
                t_cross0 = float(tt)
                break

        neg_mask = y < 0
        t_last_neg = float(x[neg_mask][-1]) if np.any(neg_mask) else None
        duration_neg = float(t_last_neg - float(args.min_hours)) if t_last_neg is not None else 0.0

        # half-recovery：从 y_min 回升到 y_min/2（仍为负）的时间（线性插值）
        t_half = None
        if y_min < 0:
            target = y_min / 2.0
            for j in range(i_min, len(x) - 1):
                t_hit = _lin_interp_crossing(float(x[j]), float(y[j]), float(x[j + 1]), float(y[j + 1]), target)
                if t_hit is not None and t_hit >= t_min:
                    t_half = float(t_hit)
                    break

        # 负面积：∫ max(-y,0) dt
        y_neg = np.clip(-y, 0.0, None)
        trapz = getattr(np, "trapezoid", np.trapz)
        area_neg = float(trapz(y_neg, x))

        rows.append(
            {
                "distance_bin": b,
                "metric": spec.label,
                "n_points": int(len(x)),
                "t_min": t_min,
                "y_min": y_min,
                "t_cross0": t_cross0,
                "t_last_neg": t_last_neg,
                "duration_neg": duration_neg,
                "t_half_recover": t_half,
                "area_neg": area_neg,
                "t_window_min": float(args.min_hours),
                "t_window_max": float(args.max_hours),
            }
        )

    summary = pd.DataFrame(rows)
    out_csv = out_tbl / f"evacuation_return_summary_{spec.label}_0-150km_200h.csv"
    summary.to_csv(out_csv, index=False)

    # figure：每个 bin 一个子图
    with ps.paper_style():
        n = len(bins_sorted)
        fig, axes = plt.subplots(nrows=n, ncols=1, figsize=(ps.FIGSIZE_FULL[0], 2.0 * n), sharex=True, sharey=True)
        if n == 1:
            axes = [axes]

        for ax, b in zip(axes, bins_sorted, strict=False):
            sub = ts[ts["distance_bin"].astype(str) == b].sort_values("hours_since_quake", kind="stable").copy()
            x = sub["hours_since_quake"].to_numpy(dtype=float)
            y = sub[spec.y_col].to_numpy(dtype=float)
            ax.plot(x, y, marker="o", color=ps.OKABE_ITO["blue"])
            ax.axhline(0, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.6)
            ax.set_title(str(b))
            ps.despine(ax)

            row = summary[summary["distance_bin"].astype(str) == b]
            if not row.empty:
                t_min = float(row["t_min"].iloc[0])
                y_min = float(row["y_min"].iloc[0])
                ax.scatter([t_min], [y_min], s=60, color=ps.OKABE_ITO["vermillion"], zorder=5)
                t_cross0 = row["t_cross0"].iloc[0]
                if pd.notna(t_cross0):
                    ax.axvline(float(t_cross0), color=ps.OKABE_ITO["vermillion"], linestyle=":", linewidth=1.2, alpha=0.75)

        axes[-1].set_xlabel("Hours since earthquake (PT windows)")
        fig.suptitle(f"Evacuation → return (0–150km, first 200h): {spec.label}", y=0.99)
        fig.tight_layout(rect=(0, 0, 1, 0.97))

        out_pdf = out_fig / f"evacuation_return_{spec.label}_0-150km_200h.pdf"
        ps.save_figure(fig, out_pdf)
        ps.save_figure(fig, out_pdf.with_suffix(".png"), dpi=200)
        plt.close(fig)

    print(f"Done. Wrote: {out_csv}")
    print(f"Done. Wrote: {out_pdf}")


if __name__ == "__main__":
    main()
