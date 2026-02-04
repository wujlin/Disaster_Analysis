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

from disaster.physical_model_phi_rt import Config as PhysicalConfig
from disaster.physical_model_phi_rt import run as run_physical
from disaster.population_io import load_population_file, parse_window_start_pt
from disaster.population_redistribution import Config as RedistributionConfig
from disaster.population_redistribution import run as run_redistribution


@dataclass(frozen=True)
class DisasterSpec:
    slug: str
    name: str
    data_root: Path
    event_type: str
    t0_pt: pd.Timestamp | None
    center_lat: float | None
    center_lon: float | None
    center_track_csv: Path | None = None
    center_track_to_tz: str = "America/Los_Angeles"
    center_track_storm_name: str | None = None
    only_hour_pt: int = 8
    outflow_phi_threshold: float = 0.9
    inflow_phi_threshold: float = 1.1


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    redistribution: Path
    physical_model: Path


def _output_dirs(output_root: Path, slug: str) -> OutputDirs:
    root = output_root / slug
    return OutputDirs(
        root=root,
        redistribution=root / "population_redistribution",
        physical_model=root / "physical_model",
    )


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _safe_float(x: object) -> float | None:
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() == "nan":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _safe_int(x: object, default: int) -> int:
    try:
        if x is None:
            return int(default)
        s = str(x).strip()
        if s == "" or s.lower() == "nan":
            return int(default)
        return int(float(s))
    except Exception:
        return int(default)


def _safe_timestamp(x: object) -> pd.Timestamp | None:
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() == "nan":
        return None
    ts = pd.to_datetime(s, errors="coerce")
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts)


def load_catalog(path: Path) -> list[DisasterSpec]:
    if not path.exists():
        raise FileNotFoundError(f"未找到 catalog：{path}")
    df = pd.read_csv(path)
    required = {"slug", "name", "data_root", "event_type"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"catalog 缺少列：{missing}（来自 {path}）")

    specs: list[DisasterSpec] = []
    for row in df.to_dict(orient="records"):
        track_csv = str(row.get("center_track_csv", "")).strip() or str(row.get("track_csv", "")).strip()
        track_to_tz = str(row.get("center_track_to_tz", "")).strip() or "America/Los_Angeles"
        track_storm = str(row.get("center_track_storm_name", "")).strip() or str(row.get("track_storm_name", "")).strip()
        specs.append(
            DisasterSpec(
                slug=str(row["slug"]).strip(),
                name=str(row["name"]).strip(),
                data_root=Path(str(row["data_root"]).strip()),
                event_type=str(row.get("event_type", "")).strip() or "unknown",
                t0_pt=_safe_timestamp(row.get("t0_pt")),
                center_lat=_safe_float(row.get("center_lat")),
                center_lon=_safe_float(row.get("center_lon")),
                center_track_csv=Path(track_csv) if track_csv else None,
                center_track_to_tz=str(track_to_tz),
                center_track_storm_name=str(track_storm) if track_storm else None,
                only_hour_pt=_safe_int(row.get("only_hour_pt"), 8),
                outflow_phi_threshold=float(_safe_float(row.get("outflow_phi_threshold")) or 0.9),
                inflow_phi_threshold=float(_safe_float(row.get("inflow_phi_threshold")) or 1.1),
            )
        )

    bad = [s.slug for s in specs if not s.slug]
    if bad:
        raise SystemExit(f"catalog 中存在空 slug：{bad}")
    return specs


def _list_population_windows(data_root: Path, *, only_hour_pt: int) -> list[dict]:
    pop_dir = data_root / "population"
    if not pop_dir.exists():
        raise FileNotFoundError(f"未找到目录：{pop_dir}")
    files = sorted(pop_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"目录为空：{pop_dir}")
    rows: list[dict] = []
    for path in files:
        ts = parse_window_start_pt(path)
        if int(ts.hour) != int(only_hour_pt):
            continue
        rows.append({"path": path, "window_start_pt": pd.Timestamp(ts)})
    rows = sorted(rows, key=lambda r: pd.Timestamp(r["window_start_pt"]))
    if not rows:
        raise FileNotFoundError(f"未找到 hour={only_hour_pt} 的 population 文件：{pop_dir}")
    return rows


def _weighted_centroid(lat: np.ndarray, lon: np.ndarray, w: np.ndarray) -> tuple[float, float] | None:
    mask = np.isfinite(lat) & np.isfinite(lon) & np.isfinite(w) & (w > 0)
    if not np.any(mask):
        return None
    ww = w[mask].astype(float)
    ww_sum = float(np.sum(ww))
    if ww_sum <= 0:
        return None
    return float(np.sum(lat[mask] * ww) / ww_sum), float(np.sum(lon[mask] * ww) / ww_sum)


def auto_t0_and_center(spec: DisasterSpec) -> tuple[pd.Timestamp, float, float, dict]:
    """
    返回：(t0_pt, center_lat, center_lon, metadata_dict)
    """

    windows = _list_population_windows(spec.data_root, only_hour_pt=int(spec.only_hour_pt))
    first = windows[0]
    first_ts = pd.Timestamp(first["window_start_pt"])

    pop_dir = spec.data_root / "population"

    # t0：若未提供，则默认取“首个 08:00 窗口所在日期的 16:00 窗口”
    t0_method = "provided"
    if spec.t0_pt is None:
        t0_candidate = pd.Timestamp(f"{first_ts:%Y-%m-%d} 16:00")
        matches = list(pop_dir.glob(f"*_{t0_candidate:%Y-%m-%d}_{t0_candidate:%H%M}.csv"))
        if len(matches) == 1:
            t0_pt = pd.Timestamp(t0_candidate)
            t0_method = "auto_first_day_1600"
            t0_file = matches[0]
        else:
            t0_pt = pd.Timestamp(first_ts)
            t0_method = "auto_first_population_window"
            t0_file = Path(first["path"])
    else:
        t0_pt = pd.Timestamp(spec.t0_pt)
        matches = list(pop_dir.glob(f"*_{t0_pt:%Y-%m-%d}_{t0_pt:%H%M}.csv"))
        t0_file = matches[0] if len(matches) == 1 else Path(first["path"])

    # center：若未提供，则优先用 t0 窗口（更可能落在“扰动开始/峰值”附近）
    center_source_ts = pd.Timestamp(t0_pt)
    center_source_file = t0_file
    df = load_population_file(Path(center_source_file))
    lat = pd.to_numeric(df["lat"], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(df["lon"], errors="coerce").to_numpy(dtype=float)
    diff = pd.to_numeric(df.get("n_difference", np.nan), errors="coerce").to_numpy(dtype=float)
    crisis = pd.to_numeric(df.get("n_crisis", np.nan), errors="coerce").to_numpy(dtype=float)

    center_method = "provided"
    if spec.center_lat is None or spec.center_lon is None:
        # 优先按 |n_difference| 加权，定位“变化最大”的区域
        out = _weighted_centroid(lat, lon, np.abs(diff))
        if out is None:
            out = _weighted_centroid(lat, lon, crisis)
            center_method = "auto_centroid_n_crisis"
        else:
            center_method = "auto_centroid_abs_n_difference"
        if out is None:
            raise SystemExit(f"无法自动估计中心点：{spec.slug}（首窗无有效坐标/权重）")
        center_lat, center_lon = out
    else:
        center_lat, center_lon = float(spec.center_lat), float(spec.center_lon)

    meta = {
        "slug": spec.slug,
        "name": spec.name,
        "event_type": spec.event_type,
        "data_root": str(spec.data_root),
        "only_hour_pt": int(spec.only_hour_pt),
        "t0_pt": str(t0_pt),
        "t0_method": t0_method,
        "center_lat": float(center_lat),
        "center_lon": float(center_lon),
        "center_method": center_method,
        "center_source_window_pt": str(center_source_ts),
        "center_source_file": str(Path(center_source_file).name),
        "first_population_window_pt": str(first_ts),
        "first_population_window_file": str(Path(first["path"]).name),
    }
    return t0_pt, float(center_lat), float(center_lon), meta


def _sign_pattern(phi: np.ndarray, *, eps: float) -> list[str]:
    """
    将 phi 相对 1 的状态离散成 '+', '-', '0'。
    """
    out: list[str] = []
    for v in phi:
        if not np.isfinite(v):
            out.append("?")
        elif v >= 1.0 + float(eps):
            out.append("+")
        elif v <= 1.0 - float(eps):
            out.append("-")
        else:
            out.append("0")
    return out


def _collapse(seq: list[str]) -> list[str]:
    out: list[str] = []
    for s in seq:
        if not out or out[-1] != s:
            out.append(s)
    return out


def detect_three_phase(phi_row: np.ndarray, *, eps: float = 0.05) -> tuple[bool, str, str]:
    """
    三相分离（+ - +）的简单判定：
    - 按距离带顺序得到符号串
    - 丢弃 '0' 与 '?' 后做 run-length collapse
    - 若 collapse 后恰好为 '+-+'，返回 True
    """
    raw = _sign_pattern(phi_row, eps=eps)
    compact = [s for s in raw if s in {"+", "-"}]
    collapsed = _collapse(compact)
    ok = collapsed == ["+", "-", "+"]
    return ok, "".join(raw), "".join(collapsed)


def run_one(
    spec: DisasterSpec,
    *,
    output_root: Path,
    fit_min_hours: float,
    fit_max_hours: float | None,
    plot_times_hours: tuple[float, ...],
    phase_eps: float,
    phase_times_hours: tuple[float, ...],
) -> tuple[pd.DataFrame, dict]:
    out = _output_dirs(output_root, spec.slug)
    _ensure_dir(out.root)

    t0_pt, center_lat, center_lon, meta = auto_t0_and_center(spec)
    (out.root / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 1: population redistribution
    red_cfg = RedistributionConfig(
        data_root=spec.data_root,
        output_dir=out.redistribution,
        epicenter_lat=float(center_lat),
        epicenter_lon=float(center_lon),
        t0_pt=pd.Timestamp(t0_pt),
        only_hour_pt=int(spec.only_hour_pt),
        outflow_phi_threshold=float(spec.outflow_phi_threshold),
        inflow_phi_threshold=float(spec.inflow_phi_threshold),
    )
    run_redistribution(red_cfg)

    # Step 2: physical model
    input_csv = out.redistribution / "tables" / "redistribution_by_distance_band.csv"
    phy_cfg = PhysicalConfig(
        input_csv=input_csv,
        output_dir=out.physical_model,
        fit_min_hours=float(fit_min_hours),
        fit_max_hours=float(fit_max_hours) if fit_max_hours is not None else None,
        plot_times_hours=tuple(float(x) for x in plot_times_hours),
    )
    run_physical(phy_cfg)

    # Step 3: collect tau + phase separation summary
    fit_csv = out.physical_model / "tables" / "relaxation_fit_by_band.csv"
    fit_df = pd.read_csv(fit_csv)
    fit_df.insert(0, "slug", spec.slug)
    fit_df.insert(1, "name", spec.name)
    fit_df.insert(2, "event_type", spec.event_type)

    phi_matrix_csv = out.physical_model / "tables" / "phi_rt_matrix.csv"
    phi_df = pd.read_csv(phi_matrix_csv)
    phi_df["hours_since_quake"] = pd.to_numeric(phi_df["hours_since_quake"], errors="coerce")
    phi_df = phi_df.dropna(subset=["hours_since_quake"]).copy()
    hours = phi_df["hours_since_quake"].to_numpy(dtype=float)

    band_cols = [c for c in phi_df.columns if c != "hours_since_quake"]
    phase_rows: list[dict] = []
    for t in phase_times_hours:
        if hours.size == 0:
            continue
        idx = int(np.argmin(np.abs(hours - float(t))))
        t_near = float(hours[idx])
        row = phi_df.loc[phi_df.index[idx], band_cols].to_numpy(dtype=float)
        ok, raw, collapsed = detect_three_phase(row, eps=float(phase_eps))
        phase_rows.append(
            {
                "t_req_hours": float(t),
                "t_used_hours": t_near,
                "three_phase_ok": int(ok),
                "pattern_raw": raw,
                "pattern_collapsed": collapsed,
            }
        )

    phase = {
        "slug": spec.slug,
        "name": spec.name,
        "event_type": spec.event_type,
        "phase_eps": float(phase_eps),
        "phase_times_hours": list(float(x) for x in phase_times_hours),
        "rows": phase_rows,
    }
    return fit_df, phase


def write_phase_summary_md(phases: list[dict], out_path: Path) -> None:
    lines: list[str] = []
    lines.append("# Phase Separation Summary (three-phase: + - +)\n")
    lines.append("判定口径：对每个灾难，在若干时间点取最近的窗口，比较距离带的 $\\phi_{agg}$ 相对 1 的符号（>1+eps 为 +，<1-eps 为 -）。\n")

    for ph in phases:
        lines.append(f"## {ph['slug']}  ({ph['event_type']})\n")
        lines.append(f"- name: {ph['name']}\n")
        lines.append(f"- eps: {ph['phase_eps']}\n")
        if not ph["rows"]:
            lines.append("- 无可用窗口（跳过）\n")
            continue
        ok_any = any(int(r["three_phase_ok"]) == 1 for r in ph["rows"])
        lines.append(f"- three-phase exists: {str(ok_any)}\n")
        lines.append("\n| t_req(h) | t_used(h) | three_phase | raw | collapsed |\n|---:|---:|---:|---|---|\n")
        for r in ph["rows"]:
            lines.append(
                f"| {int(round(float(r['t_req_hours'])))} | {int(round(float(r['t_used_hours'])))} | {int(r['three_phase_ok'])} | `{r['pattern_raw']}` | `{r['pattern_collapsed']}` |\n"
            )
        lines.append("\n")

    out_path.write_text("".join(lines), encoding="utf-8")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog.csv"), help="灾难配置表（CSV）")
    parser.add_argument("--output-root", type=Path, default=Path("outputs"), help="输出根目录")
    parser.add_argument("--summary-dir", type=Path, default=Path("outputs/cross_disaster_comparison"), help="跨灾难汇总输出目录")
    parser.add_argument("--fit-min-hours", type=float, default=0.0, help="指数恢复拟合 t>=min")
    parser.add_argument("--fit-max-hours", type=float, default=None, help="指数恢复拟合 t<=max（可选）")
    parser.add_argument("--plot-times-hours", type=float, nargs="*", default=[16, 40, 88, 160, 832], help="每个灾难输出 φ(r) 曲线的时间点（取 nearest）")
    parser.add_argument("--phase-eps", type=float, default=0.05, help="三相分离判定阈值 eps（phi 与 1 的差）")
    parser.add_argument("--phase-times-hours", type=float, nargs="*", default=[16, 40, 88, 160, 832], help="三相分离判定用的时间点（取 nearest）")
    args = parser.parse_args()

    specs = load_catalog(args.catalog)
    _ensure_dir(Path(args.summary_dir))

    all_fit: list[pd.DataFrame] = []
    phases: list[dict] = []
    for spec in specs:
        print(f"[cross_disaster] running: {spec.slug} ({spec.name})")
        fit_df, phase = run_one(
            spec,
            output_root=Path(args.output_root),
            fit_min_hours=float(args.fit_min_hours),
            fit_max_hours=float(args.fit_max_hours) if args.fit_max_hours is not None else None,
            plot_times_hours=tuple(float(x) for x in args.plot_times_hours),
            phase_eps=float(args.phase_eps),
            phase_times_hours=tuple(float(x) for x in args.phase_times_hours),
        )
        all_fit.append(fit_df)
        phases.append(phase)

    tau_out = Path(args.summary_dir) / "tau_comparison.csv"
    if all_fit:
        out_df = pd.concat(all_fit, ignore_index=True)
        out_df.to_csv(tau_out, index=False)
        print(f"Done. Wrote: {tau_out}")

    md_out = Path(args.summary_dir) / "phase_separation_summary.md"
    write_phase_summary_md(phases, md_out)
    print(f"Done. Wrote: {md_out}")


if __name__ == "__main__":
    cli_main()
