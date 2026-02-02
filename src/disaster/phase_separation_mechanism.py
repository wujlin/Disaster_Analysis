from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.cross_disaster_phi_tau import auto_t0_and_center, load_catalog


@dataclass(frozen=True)
class Config:
    catalog: Path
    output_root: Path
    output_dir: Path
    distance_bin_km: float = 10.0
    epicenter_radius_km: float = 25.0
    phase_eps: float = 0.05
    epicenter_eps: float = 0.05


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _sign(v: float, *, eps: float) -> str:
    if not np.isfinite(float(v)):
        return "?"
    if float(v) >= 1.0 + float(eps):
        return "+"
    if float(v) <= 1.0 - float(eps):
        return "-"
    return "0"


def _collapse(seq: list[str]) -> list[str]:
    out: list[str] = []
    for s in seq:
        if not out or out[-1] != s:
            out.append(s)
    return out


def _three_phase_ok(phi: np.ndarray, *, eps: float) -> bool:
    raw = [_sign(float(v), eps=eps) for v in phi]
    compact = [s for s in raw if s in {"+", "-"}]
    return _collapse(compact) == ["+", "-", "+"]


def _load_phi_long(out_root: Path, slug: str) -> pd.DataFrame:
    p = out_root / slug / "phi_heatmap" / "tables" / "phi_rt_long.csv"
    if not p.exists():
        raise FileNotFoundError(f"未找到 heatmap 输出：{p}（请先运行 scripts/cross_disaster_phi_heatmap.py）")
    df = pd.read_csv(p, parse_dates=["window_start_pt"])
    need = {"hours_since_quake", "r_bin_km", "baseline_sum", "crisis_sum", "phi_aggregate"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise SystemExit(f"{p} 缺少列：{miss}")
    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df["r_bin_km"] = pd.to_numeric(df["r_bin_km"], errors="coerce")
    df["baseline_sum"] = pd.to_numeric(df["baseline_sum"], errors="coerce")
    df["crisis_sum"] = pd.to_numeric(df["crisis_sum"], errors="coerce")
    df["phi_aggregate"] = pd.to_numeric(df["phi_aggregate"], errors="coerce")
    return df.dropna(subset=["hours_since_quake", "r_bin_km"]).copy()


def _load_phi_matrix(out_root: Path, slug: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    p = out_root / slug / "phi_heatmap" / "tables" / "phi_rt_matrix.csv"
    if not p.exists():
        raise FileNotFoundError(f"未找到 heatmap 输出：{p}（请先运行 scripts/cross_disaster_phi_heatmap.py）")
    df = pd.read_csv(p)
    if "r_bin_km" not in df.columns:
        raise SystemExit(f"{p} 缺少列：r_bin_km")
    r = pd.to_numeric(df["r_bin_km"], errors="coerce").to_numpy(dtype=float)
    cols = [c for c in df.columns if c != "r_bin_km"]
    t: list[float] = []
    for c in cols:
        try:
            t.append(float(c))
        except Exception:
            t.append(float("nan"))
    times = np.array(t, dtype=float)
    z = df[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    return r, times, z


def run(cfg: Config) -> None:
    specs = load_catalog(cfg.catalog)
    _ensure_dir(cfg.output_dir)
    _ensure_dir(cfg.output_dir / "tables")

    rows: list[dict] = []
    for spec in specs:
        t0_pt, center_lat, center_lon, meta = auto_t0_and_center(spec)

        has_warning_period = 0 if str(spec.event_type).strip().lower() == "earthquake" else 1

        phi_long = _load_phi_long(cfg.output_root, spec.slug)
        phi_long = phi_long.dropna(subset=["baseline_sum", "crisis_sum"]).copy()

        # affected radius：以 heatmap long 中出现过的最大 r_bin 估计（上界为 max_distance_km）
        r_max = float(pd.to_numeric(phi_long["r_bin_km"], errors="coerce").max())
        affected_radius_km = float(r_max + float(cfg.distance_bin_km)) if np.isfinite(r_max) else float("nan")

        # epicenter φ：0-25km
        epi = phi_long[pd.to_numeric(phi_long["r_bin_km"], errors="coerce") < float(cfg.epicenter_radius_km)].copy()
        if epi.empty:
            epicenter_phi_max = float("nan")
        else:
            by_t = (
                epi.groupby("hours_since_quake", observed=True)
                .agg(baseline_sum=("baseline_sum", "sum"), crisis_sum=("crisis_sum", "sum"))
                .reset_index()
            )
            by_t["hours_since_quake"] = pd.to_numeric(by_t["hours_since_quake"], errors="coerce")
            by_t = by_t[by_t["hours_since_quake"] >= 0].copy()
            by_t = by_t[pd.to_numeric(by_t["baseline_sum"], errors="coerce") > 0].copy()
            by_t["phi"] = pd.to_numeric(by_t["crisis_sum"], errors="coerce") / pd.to_numeric(by_t["baseline_sum"], errors="coerce")
            epicenter_phi_max = float(pd.to_numeric(by_t["phi"], errors="coerce").max())

        epicenter_population_increase = int(bool(np.isfinite(epicenter_phi_max) and epicenter_phi_max > 1.0 + float(cfg.epicenter_eps)))

        # three-phase exists
        r_bins, times, z = _load_phi_matrix(cfg.output_root, spec.slug)
        ok_times: list[float] = []
        for j in range(z.shape[1]):
            t = float(times[j]) if np.isfinite(times[j]) else float("nan")
            if not np.isfinite(t) or t < 0:
                continue
            if _three_phase_ok(z[:, j], eps=float(cfg.phase_eps)):
                ok_times.append(float(t))
        ok_times = [t for t in ok_times if np.isfinite(t)]

        three_phase_exists = int(bool(ok_times))
        three_phase_first = float(np.min(ok_times)) if ok_times else float("nan")
        three_phase_last = float(np.max(ok_times)) if ok_times else float("nan")
        n_windows_total = int(np.sum(np.isfinite(times)))
        n_windows_three_phase = int(len(ok_times))

        rows.append(
            {
                "slug": spec.slug,
                "name": spec.name,
                "event_type": spec.event_type,
                "has_warning_period": int(has_warning_period),
                "t0_pt": str(pd.Timestamp(t0_pt)),
                "center_lat": float(center_lat),
                "center_lon": float(center_lon),
                "affected_radius_km": float(affected_radius_km),
                "epicenter_radius_km": float(cfg.epicenter_radius_km),
                "epicenter_phi_max": float(epicenter_phi_max),
                "epicenter_population_increase": int(epicenter_population_increase),
                "phase_eps": float(cfg.phase_eps),
                "three_phase_exists": int(three_phase_exists),
                "three_phase_first_hours": float(three_phase_first),
                "three_phase_last_hours": float(three_phase_last),
                "n_windows_total": int(n_windows_total),
                "n_windows_three_phase": int(n_windows_three_phase),
            }
        )

    out_df = pd.DataFrame(rows)
    out_csv = cfg.output_dir / "tables" / "phase_separation_mechanism.csv"
    out_df.to_csv(out_csv, index=False)

    # README
    supported = False
    if not out_df.empty:
        mask = out_df["three_phase_exists"].astype(int) == 1
        if bool(mask.any()):
            supported = bool((out_df.loc[mask, "has_warning_period"].astype(int) == 0).all())

    readme = f"""# Phase Separation Mechanism (Task 3)

本目录对应 `Opinion_PI.md` 的 **任务 3**：跨灾害对比表，用于检验假说：

> 三相分离只出现在（瞬时灾害 + 无预警期）的事件中

## 输入

- catalog: `{cfg.catalog}`
- heatmap 输出：`outputs/<slug>/phi_heatmap/`（需要先跑 `scripts/cross_disaster_phi_heatmap.py`）

## 口径

- 三相分离判定：对每个时间窗口的 $\\phi(r)$ 序列做符号化并 collapse，若为 `+-+` 记为 True
- eps: {float(cfg.phase_eps)}
- 震中人口增加判定：0–{float(cfg.epicenter_radius_km)}km 的 $\\max_{{t\\ge 0}} \\phi_{{agg}}(t) > 1 + {float(cfg.epicenter_eps)}$

## 输出

- `tables/phase_separation_mechanism.csv`

## 假说检验（当前表格的布尔结果）

- hypothesis_supported: {str(bool(supported))}
"""
    (cfg.output_dir / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_csv}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog.csv"), help="灾难配置表（CSV）")
    parser.add_argument("--output-root", type=Path, default=Path("outputs"), help="outputs 根目录（含 <slug>/phi_heatmap/）")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/cross_disaster_comparison/phase_separation_mechanism"),
        help="输出目录",
    )
    parser.add_argument("--distance-bin-km", type=float, default=10.0, help="距离 bin 宽度（用于 affected_radius 计算，默认 10）")
    parser.add_argument("--epicenter-radius-km", type=float, default=25.0, help="震中半径（km，默认 25）")
    parser.add_argument("--phase-eps", type=float, default=0.05, help="三相分离 eps（默认 0.05）")
    parser.add_argument("--epicenter-eps", type=float, default=0.05, help="震中人口增加 eps（默认 0.05）")
    args = parser.parse_args()

    cfg = Config(
        catalog=args.catalog,
        output_root=args.output_root,
        output_dir=args.output_dir,
        distance_bin_km=float(args.distance_bin_km),
        epicenter_radius_km=float(args.epicenter_radius_km),
        phase_eps=float(args.phase_eps),
        epicenter_eps=float(args.epicenter_eps),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()
