from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e


@dataclass(frozen=True)
class Config:
    input_csv: Path
    output_dir: Path
    bootstrap_samples: int = 2000
    permutation_samples: int = 5000
    seed: int = 7
    compare_ranges_km: tuple[tuple[float, float], ...] = ((25.0, 50.0), (50.0, 100.0), (100.0, 200.0))


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _bootstrap_ci_diff_median(rng: np.random.Generator, x: np.ndarray, y: np.ndarray, *, b: int) -> tuple[float, float]:
    xs = x[np.isfinite(x)]
    ys = y[np.isfinite(y)]
    if xs.size < 20 or ys.size < 20:
        return float("nan"), float("nan")
    n0, n1 = xs.size, ys.size
    diffs = np.empty(int(b), dtype=float)
    for i in range(int(b)):
        bx = xs[rng.integers(0, n0, size=n0)]
        by = ys[rng.integers(0, n1, size=n1)]
        diffs[i] = float(np.nanmedian(bx) - np.nanmedian(by))
    return float(np.nanpercentile(diffs, 2.5)), float(np.nanpercentile(diffs, 97.5))


def _permutation_p_value(rng: np.random.Generator, x: np.ndarray, y: np.ndarray, *, n_perm: int, alternative: str) -> float:
    xs = x[np.isfinite(x)]
    ys = y[np.isfinite(y)]
    if xs.size < 20 or ys.size < 20:
        return float("nan")
    n0, n1 = xs.size, ys.size
    pooled = np.concatenate([xs, ys])
    obs = float(np.nanmedian(xs) - np.nanmedian(ys))

    cnt = 0
    for _ in range(int(n_perm)):
        perm = rng.permutation(pooled)
        a = perm[:n0]
        b = perm[n0:]
        stat = float(np.nanmedian(a) - np.nanmedian(b))
        if alternative == "greater":
            cnt += int(stat >= obs)
        elif alternative == "less":
            cnt += int(stat <= obs)
        else:
            cnt += int(abs(stat) >= abs(obs))
    return float((cnt + 1) / (int(n_perm) + 1))


def _bh_fdr(pvals: list[float]) -> list[float]:
    arr = np.array([p if np.isfinite(p) else np.nan for p in pvals], dtype=float)
    n = int(np.sum(np.isfinite(arr)))
    if n == 0:
        return [float("nan")] * len(pvals)
    order = np.argsort(arr, kind="stable")
    ranked = np.empty_like(arr)
    prev = 1.0
    for i, idx in enumerate(order, start=1):
        p = arr[idx]
        if not np.isfinite(p):
            ranked[idx] = np.nan
            continue
        q = p * n / i
        q = min(q, prev)
        prev = q
        ranked[idx] = q
    return ranked.tolist()


def run(cfg: Config) -> None:
    if not cfg.input_csv.exists():
        raise FileNotFoundError(f"未找到输入：{cfg.input_csv}")

    out = _output_dirs(cfg.output_dir)
    _ensure_dir(out.root)
    _ensure_dir(out.tables)

    df = pd.read_csv(cfg.input_csv)
    required = {"distance_km", "tau_hours"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"输入缺少列：{missing}（来自 {cfg.input_csv}）")

    df["distance_km"] = pd.to_numeric(df["distance_km"], errors="coerce")
    df["tau_hours"] = pd.to_numeric(df["tau_hours"], errors="coerce")
    df = df[df["distance_km"].notna() & df["tau_hours"].notna()].copy()

    rng = np.random.default_rng(int(cfg.seed))

    # A) τ 分布比较：默认做 (25-50) vs (50-100), (50-100) vs (100-200), ...
    ranges = list(cfg.compare_ranges_km)
    comparisons: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for i in range(len(ranges) - 1):
        comparisons.append((ranges[i], ranges[i + 1]))

    rows: list[dict] = []
    pvals: list[float] = []
    for (a0, a1), (b0, b1) in comparisons:
        A = df[(df["distance_km"] >= float(a0)) & (df["distance_km"] < float(a1))]["tau_hours"].to_numpy(dtype=float)
        B = df[(df["distance_km"] >= float(b0)) & (df["distance_km"] < float(b1))]["tau_hours"].to_numpy(dtype=float)
        if A.size < 50 or B.size < 50:
            continue

        stat = float(np.nanmedian(A) - np.nanmedian(B))
        ci_lo, ci_hi = _bootstrap_ci_diff_median(rng, A, B, b=int(cfg.bootstrap_samples))
        # 备择：后一段更快 => median(B) < median(A) => stat > 0
        p = _permutation_p_value(rng, A, B, n_perm=int(cfg.permutation_samples), alternative="greater")
        pvals.append(p)
        rows.append(
            {
                "range_a_km": f"{a0:g}-{a1:g}",
                "range_b_km": f"{b0:g}-{b1:g}",
                "n_a": int(np.sum(np.isfinite(A))),
                "n_b": int(np.sum(np.isfinite(B))),
                "median_a": float(np.nanmedian(A)),
                "median_b": float(np.nanmedian(B)),
                "diff_median_a_minus_b": stat,
                "diff_median_ci025": float(ci_lo),
                "diff_median_ci975": float(ci_hi),
                "p_perm_one_sided": float(p),
            }
        )

    if rows:
        res = pd.DataFrame(rows)
        # 多重校正
        res["p_bonferroni"] = np.minimum(1.0, res["p_perm_one_sided"] * len(res))
        res["p_fdr_bh"] = _bh_fdr(res["p_perm_one_sided"].tolist())
        out_tau = out.tables / "tau_range_comparisons.csv"
        res.to_csv(out_tau, index=False)
    else:
        out_tau = None

    # B) “可见性 vs 强度”恢复（paired）
    if {"t_first_overlap_hours", "t_intensity_geq_thr_hours"} <= set(df.columns):
        df["t_first_overlap_hours"] = pd.to_numeric(df["t_first_overlap_hours"], errors="coerce")
        df["t_intensity_geq_thr_hours"] = pd.to_numeric(df["t_intensity_geq_thr_hours"], errors="coerce")
        df["d_intensity_minus_visibility"] = df["t_intensity_geq_thr_hours"] - df["t_first_overlap_hours"]

        rows2: list[dict] = []
        for lo, hi in ranges:
            sub = df[(df["distance_km"] >= float(lo)) & (df["distance_km"] < float(hi))].copy()
            d = pd.to_numeric(sub["d_intensity_minus_visibility"], errors="coerce").to_numpy(dtype=float)
            d = d[np.isfinite(d)]
            if d.size < 100:
                continue

            # effect size
            med = float(np.nanmedian(d))
            mean = float(np.nanmean(d))
            prop_pos = float(np.mean(d > 0))

            # bootstrap CI (median)
            diffs = np.empty(int(cfg.bootstrap_samples), dtype=float)
            for i in range(int(cfg.bootstrap_samples)):
                bd = d[rng.integers(0, d.size, size=d.size)]
                diffs[i] = float(np.nanmedian(bd))
            ci_lo = float(np.nanpercentile(diffs, 2.5))
            ci_hi = float(np.nanpercentile(diffs, 97.5))

            # paired permutation: sign flip
            cnt = 0
            obs = med
            for _ in range(int(cfg.permutation_samples)):
                signs = rng.choice([-1.0, 1.0], size=d.size, replace=True)
                stat = float(np.nanmedian(d * signs))
                cnt += int(stat >= obs)
            p = float((cnt + 1) / (int(cfg.permutation_samples) + 1))

            rows2.append(
                {
                    "range_km": f"{lo:g}-{hi:g}",
                    "n_tiles": int(d.size),
                    "median_d_hours": med,
                    "mean_d_hours": mean,
                    "prop_d_gt_0": prop_pos,
                    "median_d_ci025": ci_lo,
                    "median_d_ci975": ci_hi,
                    "p_perm_one_sided": p,
                }
            )

        out_vis = out.tables / "visibility_vs_intensity_tests.csv"
        pd.DataFrame(rows2).to_csv(out_vis, index=False)
    else:
        out_vis = None

    readme = f"""# Non-parametric Tests (tile-level)

对应 PI 的“统计显著性/稳健性”要求：

1) τ 排序显著性：相邻距离范围的 median(τ) 差异 + bootstrap CI + permutation test
2) 假说 B vs A/C（代理）：tile 可见性恢复是否显著快于强度恢复（paired sign-flip permutation）

## 输入

- `{cfg.input_csv}`

## 输出

- `tables/tau_range_comparisons.csv`（若可计算）
- `tables/visibility_vs_intensity_tests.csv`（若输入包含 tile-level 恢复时间列）
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    if out_tau is not None:
        print(f"Done. Wrote: {out_tau}")
    if out_vis is not None:
        print(f"Done. Wrote: {out_vis}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=Path("outputs/tau_continuous_fit/tables/tile_level_tau.csv"),
        help="tile-level τ 表（含 distance_km/tau_hours）",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/nonparametric_tau_tests"), help="输出目录")
    parser.add_argument("--bootstrap-samples", type=int, default=2000, help="bootstrap 次数")
    parser.add_argument("--permutation-samples", type=int, default=5000, help="permutation 次数")
    parser.add_argument("--seed", type=int, default=7, help="随机种子")
    args = parser.parse_args()

    cfg = Config(
        input_csv=args.input_csv,
        output_dir=args.output_dir,
        bootstrap_samples=int(args.bootstrap_samples),
        permutation_samples=int(args.permutation_samples),
        seed=int(args.seed),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()

