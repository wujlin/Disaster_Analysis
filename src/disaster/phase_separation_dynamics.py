from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    input_csv: Path
    output_dir: Path
    phi_col: str = "phi_aggregate"
    eps: float = 0.05
    distance_bin_km: float = 10.0


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


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


def _detect_three_phase(phi: np.ndarray, *, eps: float) -> tuple[bool, str]:
    raw = [_sign(float(v), eps=eps) for v in phi]
    compact = [s for s in raw if s in {"+", "-"}]
    collapsed = _collapse(compact)
    return collapsed == ["+", "-", "+"], "".join(collapsed)


def _interp_crossing(r0: float, y0: float, r1: float, y1: float, target: float = 1.0) -> float:
    if not (np.isfinite(r0) and np.isfinite(r1) and np.isfinite(y0) and np.isfinite(y1)):
        return float("nan")
    if float(y1) == float(y0):
        return float("nan")
    return float(r0 + (target - float(y0)) * (r1 - r0) / (float(y1) - float(y0)))


def _phase_boundaries(r_centers: np.ndarray, phi: np.ndarray) -> tuple[float, float]:
    """
    返回：(r_boundary_1, r_boundary_2)，均为 phi=1 的线性插值位置。
    若不存在三相边界则返回 NaN。
    """
    if r_centers.size != phi.size:
        return float("nan"), float("nan")

    # 只在有效值上找 crossing
    mask = np.isfinite(r_centers) & np.isfinite(phi)
    if int(np.sum(mask)) < 3:
        return float("nan"), float("nan")

    r = r_centers[mask].astype(float)
    y = phi[mask].astype(float)

    # 内边界：+ -> -
    b1 = float("nan")
    b2 = float("nan")
    for i in range(len(y) - 1):
        if y[i] > 1.0 and y[i + 1] < 1.0:
            b1 = _interp_crossing(float(r[i]), float(y[i]), float(r[i + 1]), float(y[i + 1]), 1.0)
            break

    if not np.isfinite(b1):
        return float("nan"), float("nan")

    # 外边界：- -> +
    for i in range(len(y) - 1):
        if r[i] <= b1:
            continue
        if y[i] < 1.0 and y[i + 1] > 1.0:
            b2 = _interp_crossing(float(r[i]), float(y[i]), float(r[i + 1]), float(y[i + 1]), 1.0)
            break

    return float(b1), float(b2)


def _find_contiguous_true_blocks(times: np.ndarray, ok: np.ndarray) -> list[dict]:
    """
    给定按时间排序的 (times, ok)，返回所有连续 True 段（按固定步长近似）。
    """
    if times.size == 0:
        return []
    if times.size != ok.size:
        return []

    dt = float(np.median(np.diff(times))) if times.size >= 2 else 8.0
    blocks: list[dict] = []

    start_idx: int | None = None
    for i in range(ok.size):
        if bool(ok[i]) and start_idx is None:
            start_idx = i
            continue
        if start_idx is None:
            continue
        # end block when ok turns false OR time gap is too large
        is_last = i == ok.size - 1
        gap = float(times[i] - times[i - 1]) if i >= 1 else dt
        if (not bool(ok[i])) or (gap > dt * 1.5) or is_last:
            end_idx = i if (bool(ok[i]) and is_last) else i - 1
            t0 = float(times[start_idx])
            t1 = float(times[end_idx])
            n = int(end_idx - start_idx + 1)
            blocks.append({"t_start_hours": t0, "t_end_hours": t1, "duration_hours": float(t1 - t0), "n_windows": n})
            start_idx = None

    return blocks


def run(cfg: Config) -> None:
    if not cfg.input_csv.exists():
        raise FileNotFoundError(f"未找到输入：{cfg.input_csv}")

    out = _output_dirs(cfg.output_dir)
    _ensure_dir(out.root)
    _ensure_dir(out.figures)
    _ensure_dir(out.tables)

    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    df = pd.read_csv(cfg.input_csv, parse_dates=["window_start_pt"])
    required = {"window_start_pt", "hours_since_quake", "r_bin_km", cfg.phi_col}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"输入缺少列：{missing}（来自 {cfg.input_csv}）")

    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df["r_bin_km"] = pd.to_numeric(df["r_bin_km"], errors="coerce")
    df[cfg.phi_col] = pd.to_numeric(df[cfg.phi_col], errors="coerce")
    df = df.dropna(subset=["hours_since_quake", "r_bin_km"]).copy()

    time_map = (
        df[["hours_since_quake", "window_start_pt"]]
        .dropna(subset=["hours_since_quake", "window_start_pt"])
        .drop_duplicates(subset=["hours_since_quake"])
        .sort_values("hours_since_quake", kind="stable")
    )
    hours_to_ts = dict(zip(time_map["hours_since_quake"].to_numpy(dtype=float), time_map["window_start_pt"].tolist(), strict=False))

    pivot = df.pivot(index="r_bin_km", columns="hours_since_quake", values=cfg.phi_col).sort_index().sort_index(axis=1)
    r_bins = pivot.index.to_numpy(dtype=float)
    times = pivot.columns.to_numpy(dtype=float)

    # r centers（用于边界插值）
    step = float(cfg.distance_bin_km)
    r_centers = r_bins + step / 2.0

    rows: list[dict] = []
    ok_flags: list[bool] = []
    for t in times:
        phi = pivot[t].to_numpy(dtype=float)
        ok, collapsed = _detect_three_phase(phi, eps=float(cfg.eps))
        if float(t) < 0:
            ok = False
        b1, b2 = (float("nan"), float("nan"))
        if ok:
            b1, b2 = _phase_boundaries(r_centers, phi)

        ok_flags.append(bool(ok))
        rows.append(
            {
                "hours_since_quake": float(t),
                "window_start_pt": hours_to_ts.get(float(t), pd.NaT),
                "three_phase_ok": int(bool(ok)),
                "pattern_collapsed": collapsed,
                "r_boundary_1_km": float(b1),
                "r_boundary_2_km": float(b2),
            }
        )

    out_rows = pd.DataFrame(rows).sort_values("hours_since_quake", kind="stable")
    out_csv = out.tables / "phase_boundaries_by_time.csv"
    out_rows.to_csv(out_csv, index=False)

    blocks = _find_contiguous_true_blocks(times=np.array(times, dtype=float), ok=np.array(ok_flags, dtype=bool))
    blocks_df = pd.DataFrame(blocks)
    out_blocks = out.tables / "three_phase_windows.csv"
    blocks_df.to_csv(out_blocks, index=False)

    # plot
    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        sub = out_rows[out_rows["three_phase_ok"] == 1].copy()
        if not sub.empty:
            x = sub["hours_since_quake"].to_numpy(dtype=float)
            y1 = pd.to_numeric(sub["r_boundary_1_km"], errors="coerce").to_numpy(dtype=float)
            y2 = pd.to_numeric(sub["r_boundary_2_km"], errors="coerce").to_numpy(dtype=float)
            ax.plot(x, y1, marker="o", color=ps.OKABE_ITO["blue"], label=r"$r_{b1}(t)$ (+→-)")
            ax.plot(x, y2, marker="o", color=ps.OKABE_ITO["vermillion"], label=r"$r_{b2}(t)$ (-→+)")

        for b in blocks:
            ax.axvspan(float(b["t_start_hours"]), float(b["t_end_hours"]), color=ps.OKABE_ITO["gray"], alpha=0.12, linewidth=0)

        ax.axvline(0.0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.set_xlabel("Hours since event")
        ax.set_ylabel("Phase boundary r (km)")
        ax.set_title("Three-phase separation boundaries over time")
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(frameon=False)
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "phase_boundaries_over_time.png")
        plt.close(fig)

    readme = f"""# Phase Separation Dynamics (Task 2)

本目录对应 `Opinion_PI.md` 的 **任务 2**：追踪三相分离（+−+）的时间演化，提取相边界：

- $r_{{b1}}(t)$：+→- 的边界（phi 从 >1 跨到 <1）
- $r_{{b2}}(t)$：-→+ 的边界（phi 从 <1 跨到 >1）

## 输入

- `{cfg.input_csv}`
- 使用列：`{cfg.phi_col}`，eps={float(cfg.eps)}

## 输出

- `tables/phase_boundaries_by_time.csv`
- `tables/three_phase_windows.csv`（三相分离存在的连续时间段）
- `figures/phase_boundaries_over_time.*`
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_csv}")
    print(f"Done. Wrote: {out_blocks}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-csv", type=Path, required=True, help="输入（来自 phi_heatmap 的 tables/phi_rt_long.csv）")
    parser.add_argument("--output-dir", type=Path, required=True, help="输出目录")
    parser.add_argument("--phi-col", type=str, default="phi_aggregate", help="使用哪个 φ 列（默认 phi_aggregate）")
    parser.add_argument("--eps", type=float, default=0.05, help="三相分离判定 eps（默认 0.05）")
    parser.add_argument("--distance-bin-km", type=float, default=10.0, help="距离 bin 宽度（用于边界插值，默认 10）")
    args = parser.parse_args()

    cfg = Config(
        input_csv=args.input_csv,
        output_dir=args.output_dir,
        phi_col=str(args.phi_col),
        eps=float(args.eps),
        distance_bin_km=float(args.distance_bin_km),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()
