from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.geo import distance_bin_labels, haversine_km
from disaster.movement_io import load_movement_file
from disaster.population_io import parse_window_start_pt, resolve_subdir


@dataclass(frozen=True)
class Config:
    data_root: Path
    output_dir: Path
    center_lat: float
    center_lon: float
    t0_pt: pd.Timestamp

    slug: str | None = None
    only_hour_pt: int = 8
    min_hours: float = -16.0
    max_hours: float = 832.0

    distance_bins_km: tuple[float, ...] = (0.0, 25.0, 50.0, 100.0, 200.0, float("inf"))
    target_band: str = "50-100km"
    internal_bands: tuple[str, ...] = ("0-25km", "25-50km")
    external_bands: tuple[str, ...] = ("100-200km", "200km+")
    min_flow: float = 1.0

    population_by_band_csv: Path | None = None


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _parse_movement_window_start(path: Path) -> pd.Timestamp:
    try:
        return pd.Timestamp(parse_window_start_pt(path))
    except Exception:
        head = pd.read_csv(path, usecols=lambda c: c == "date_time", na_values=["\\N", ""], nrows=1)
        if "date_time" not in head.columns or head.empty:
            raise ValueError(f"无法解析窗口时间（文件名与 date_time 均失败）：{path.name}")
        return pd.Timestamp(pd.to_datetime(head["date_time"].iloc[0], errors="coerce"))


def _list_movement_windows(cfg: Config) -> list[dict]:
    mov_dir = resolve_subdir(cfg.data_root, "movement")

    files = sorted(mov_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"目录为空：{mov_dir}")

    rows: list[dict] = []
    for path in files:
        ts = _parse_movement_window_start(path)
        if int(ts.hour) != int(cfg.only_hour_pt):
            continue
        hs = float((pd.Timestamp(ts) - pd.Timestamp(cfg.t0_pt)).total_seconds() / 3600.0)
        if hs < float(cfg.min_hours) or hs > float(cfg.max_hours):
            continue
        rows.append({"path": path, "window_start_pt": pd.Timestamp(ts), "hours_since_quake": hs})

    rows = sorted(rows, key=lambda r: float(r["hours_since_quake"]))
    if not rows:
        raise FileNotFoundError(f"未找到符合条件的 movement 窗口：hour={cfg.only_hour_pt}, t∈[{cfg.min_hours},{cfg.max_hours}]")
    return rows


def _distance_band_indices(dist_km: np.ndarray, bins_km: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(bins_km, dist_km.astype(float), side="right") - 1
    return idx.astype(int)


def _load_phi_by_band(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    needed = {"window_start_pt", "hours_since_quake", "distance_band", "phi_aggregate"}
    if not needed <= set(df.columns):
        raise ValueError(f"population_by_band_csv 缺少列：{sorted(needed - set(df.columns))}")
    cols = [c for c in ["window_start_pt", "hours_since_quake", "distance_band", "phi_aggregate", "baseline_mean_overlap", "crisis_mean_overlap"] if c in df.columns]
    out = df[cols].copy()
    out["window_start_pt"] = pd.to_datetime(out["window_start_pt"], errors="coerce")
    out["hours_since_quake"] = pd.to_numeric(out["hours_since_quake"], errors="coerce")
    out["phi_aggregate"] = pd.to_numeric(out.get("phi_aggregate", np.nan), errors="coerce")
    out["baseline_mean_overlap"] = pd.to_numeric(out.get("baseline_mean_overlap", np.nan), errors="coerce")
    out["crisis_mean_overlap"] = pd.to_numeric(out.get("crisis_mean_overlap", np.nan), errors="coerce")
    out["phi_mean_overlap_ratio"] = out["crisis_mean_overlap"] / out["baseline_mean_overlap"]
    out["phi_mean_overlap_minus_1"] = out["phi_mean_overlap_ratio"] - 1.0
    return out


def run(cfg: Config, *, max_files: int | None = None) -> None:
    out_root = Path(cfg.output_dir)
    out_tab = out_root / "tables"
    _ensure_dir(out_root)
    _ensure_dir(out_tab)

    bins_km = np.array(cfg.distance_bins_km, dtype=float)
    if bins_km.ndim != 1 or bins_km.size < 2:
        raise ValueError("distance_bins_km 至少需要 2 个边界值")
    if not np.isinf(bins_km[-1]):
        bins_km = np.concatenate([bins_km, [float("inf")]])
    labels = distance_bin_labels(bins_km)
    n_bands = int(len(labels))

    if str(cfg.target_band) not in set(labels):
        raise ValueError(f"target_band 不在距离带中：{cfg.target_band}；可选：{labels}")
    target_idx = int(labels.index(str(cfg.target_band)))

    internal = [b for b in cfg.internal_bands if b in set(labels)]
    external = [b for b in cfg.external_bands if b in set(labels)]
    internal_idx = set(int(labels.index(b)) for b in internal)
    external_idx = set(int(labels.index(b)) for b in external)

    windows = _list_movement_windows(cfg)
    if max_files is not None:
        windows = windows[: int(max_files)]

    rows: list[dict] = []
    for i, meta in enumerate(windows, start=1):
        path = Path(meta["path"])
        window_start = pd.Timestamp(meta["window_start_pt"])
        hs = float(meta["hours_since_quake"])

        df = load_movement_file(path)
        nc = pd.to_numeric(df.get("n_crisis", np.nan), errors="coerce").to_numpy(dtype=float)
        slat = pd.to_numeric(df.get("start_lat", np.nan), errors="coerce").to_numpy(dtype=float)
        slon = pd.to_numeric(df.get("start_lon", np.nan), errors="coerce").to_numpy(dtype=float)
        elat = pd.to_numeric(df.get("end_lat", np.nan), errors="coerce").to_numpy(dtype=float)
        elon = pd.to_numeric(df.get("end_lon", np.nan), errors="coerce").to_numpy(dtype=float)

        keep = np.isfinite(nc) & (nc > float(cfg.min_flow)) & np.isfinite(slat) & np.isfinite(slon) & np.isfinite(elat) & np.isfinite(elon)
        if not np.any(keep):
            rows.append(
                {
                    "window_start_pt": window_start,
                    "hours_since_quake": hs,
                    "target_band": str(cfg.target_band),
                    "F_start_total": 0.0,
                    "F_end_total": 0.0,
                    "Net_total": 0.0,
                    "Net_internal": 0.0,
                    "Net_external": 0.0,
                    "F_within": 0.0,
                    "F_in_from_internal": 0.0,
                    "F_out_to_internal": 0.0,
                    "F_in_from_external": 0.0,
                    "F_out_to_external": 0.0,
                }
            )
            continue

        nc = nc[keep]
        slat = slat[keep]
        slon = slon[keep]
        elat = elat[keep]
        elon = elon[keep]

        sdist = haversine_km(slat, slon, float(cfg.center_lat), float(cfg.center_lon))
        edist = haversine_km(elat, elon, float(cfg.center_lat), float(cfg.center_lon))
        sidx = _distance_band_indices(sdist, bins_km)
        eidx = _distance_band_indices(edist, bins_km)

        ok = np.isfinite(sdist) & np.isfinite(edist) & (sidx >= 0) & (sidx < n_bands) & (eidx >= 0) & (eidx < n_bands)
        nc = nc[ok]
        sidx = sidx[ok].astype(int)
        eidx = eidx[ok].astype(int)

        if nc.size == 0:
            rows.append(
                {
                    "window_start_pt": window_start,
                    "hours_since_quake": hs,
                    "target_band": str(cfg.target_band),
                    "F_start_total": 0.0,
                    "F_end_total": 0.0,
                    "Net_total": 0.0,
                    "Net_internal": 0.0,
                    "Net_external": 0.0,
                    "F_within": 0.0,
                    "F_in_from_internal": 0.0,
                    "F_out_to_internal": 0.0,
                    "F_in_from_external": 0.0,
                    "F_out_to_external": 0.0,
                }
            )
            continue

        start_is_target = sidx == target_idx
        end_is_target = eidx == target_idx

        f_start_total = float(np.nansum(nc[start_is_target]))
        f_end_total = float(np.nansum(nc[end_is_target]))
        net_total = float(f_end_total - f_start_total)

        within = start_is_target & end_is_target
        f_within = float(np.nansum(nc[within]))

        start_internal = np.isin(sidx, list(internal_idx)) if internal_idx else np.zeros_like(sidx, dtype=bool)
        end_internal = np.isin(eidx, list(internal_idx)) if internal_idx else np.zeros_like(eidx, dtype=bool)
        start_external = np.isin(sidx, list(external_idx)) if external_idx else np.zeros_like(sidx, dtype=bool)
        end_external = np.isin(eidx, list(external_idx)) if external_idx else np.zeros_like(eidx, dtype=bool)

        f_in_from_internal = float(np.nansum(nc[end_is_target & start_internal]))
        f_out_to_internal = float(np.nansum(nc[start_is_target & end_internal]))
        net_internal = float(f_in_from_internal - f_out_to_internal)

        f_in_from_external = float(np.nansum(nc[end_is_target & start_external]))
        f_out_to_external = float(np.nansum(nc[start_is_target & end_external]))
        net_external = float(f_in_from_external - f_out_to_external)

        rows.append(
            {
                "window_start_pt": window_start,
                "hours_since_quake": hs,
                "target_band": str(cfg.target_band),
                "F_start_total": f_start_total,
                "F_end_total": f_end_total,
                "Net_total": net_total,
                "Net_internal": net_internal,
                "Net_external": net_external,
                "F_within": f_within,
                "F_in_from_internal": f_in_from_internal,
                "F_out_to_internal": f_out_to_internal,
                "F_in_from_external": f_in_from_external,
                "F_out_to_external": f_out_to_external,
            }
        )

        if i % 30 == 0:
            print(f"[net_flow_decomposition] processed {i}/{len(windows)} windows...")

    df_out = pd.DataFrame(rows).sort_values("hours_since_quake", kind="stable").reset_index(drop=True)

    # Merge φ for the same target band
    phi_df: pd.DataFrame | None = None
    if cfg.population_by_band_csv is not None and Path(cfg.population_by_band_csv).exists():
        phi_df = _load_phi_by_band(Path(cfg.population_by_band_csv))
        phi_sub = phi_df[phi_df["distance_band"].astype(str) == str(cfg.target_band)].copy()
        df_out = df_out.merge(phi_sub, on=["window_start_pt", "hours_since_quake"], how="left", validate="one_to_one")

    out_csv = out_tab / "net_flow_decomposed.csv"
    df_out.to_csv(out_csv, index=False)

    # Correlation table
    corr_rows: list[dict] = []
    if phi_df is not None:
        net_int = pd.to_numeric(df_out["Net_internal"], errors="coerce")
        net_ext = pd.to_numeric(df_out["Net_external"], errors="coerce")
        phi_m = pd.to_numeric(df_out.get("phi_mean_overlap_minus_1", np.nan), errors="coerce")
        phi_a = pd.to_numeric(df_out.get("phi_aggregate", np.nan), errors="coerce")

        ok_int_m = net_int.notna() & phi_m.notna()
        ok_ext_m = net_ext.notna() & phi_m.notna()
        ok_int_a = net_int.notna() & phi_a.notna()
        ok_ext_a = net_ext.notna() & phi_a.notna()

        corr_rows.append(
            {
                "target_band": str(cfg.target_band),
                "n_points_phi_mean": int(ok_int_m.sum()),
                "corr_net_internal_phi_mean_overlap_minus_1": float(net_int[ok_int_m].corr(phi_m[ok_int_m])) if int(ok_int_m.sum()) >= 3 else float("nan"),
                "corr_net_external_phi_mean_overlap_minus_1": float(net_ext[ok_ext_m].corr(phi_m[ok_ext_m])) if int(ok_ext_m.sum()) >= 3 else float("nan"),
                "n_points_phi_aggregate": int(ok_int_a.sum()),
                "corr_net_internal_phi_aggregate": float(net_int[ok_int_a].corr(phi_a[ok_int_a])) if int(ok_int_a.sum()) >= 3 else float("nan"),
                "corr_net_external_phi_aggregate": float(net_ext[ok_ext_a].corr(phi_a[ok_ext_a])) if int(ok_ext_a.sum()) >= 3 else float("nan"),
            }
        )

    corr_df = pd.DataFrame(corr_rows) if corr_rows else pd.DataFrame(columns=["target_band"])
    out_corr = out_tab / "net_flow_decomposed_corr.csv"
    corr_df.to_csv(out_corr, index=False)

    readme = f"""# Net 流分解（用于验证 H3）

目标：对指定距离带（默认 50-100km）的 Net_total 进行分解：

- Net_internal：与 0-50km 的带间净流（默认 internal_bands={list(cfg.internal_bands)}）
- Net_external：与 100km+ 的带间净流（默认 external_bands={list(cfg.external_bands)}）
- F_within：带内流量（start=end=target_band）

定义（每个时间窗口 t）：

- F_start_total = Σ n_crisis where start_band==target
- F_end_total   = Σ n_crisis where end_band==target
- Net_total     = F_end_total - F_start_total
- Net_internal  = (Σ end=target,start∈internal) - (Σ start=target,end∈internal)
- Net_external  = (Σ end=target,start∈external) - (Σ start=target,end∈external)
- F_within      = Σ start=target,end=target

## 配置

- slug: {cfg.slug}
- center: ({float(cfg.center_lat):.4f}, {float(cfg.center_lon):.4f})
- t0_pt: {pd.Timestamp(cfg.t0_pt)}
- only_hour_pt: {int(cfg.only_hour_pt)}
- time range (hours_since_quake): [{float(cfg.min_hours)}, {float(cfg.max_hours)}]
- target_band: {cfg.target_band}
- internal_bands: {list(cfg.internal_bands)}
- external_bands: {list(cfg.external_bands)}

## 输出

- `tables/net_flow_decomposed.csv`：每窗口的分解结果（可选包含 φ 字段）
- `tables/net_flow_decomposed_corr.csv`：corr(Net_internal, φ) 与 corr(Net_external, φ)
"""
    # 避免覆盖已有目录（例如 cross_band_net_flow/README.md）
    (out_root / "README_net_flow_decomposition.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_csv}")
    print(f"Done. Wrote: {out_corr}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True, help="数据根目录（包含 movement/）")
    parser.add_argument("--output-dir", type=Path, required=True, help="输出目录（建议 outputs/<slug>/cross_band_net_flow）")
    parser.add_argument("--center-lat", type=float, required=True, help="中心点纬度（震中/灾害中心）")
    parser.add_argument("--center-lon", type=float, required=True, help="中心点经度（震中/灾害中心）")
    parser.add_argument("--t0-pt", type=str, required=True, help="t=0 的 PT 时间戳（例如 2023-02-05 16:00）")
    parser.add_argument("--slug", type=str, default=None, help="用于 README 的标签（默认 None）")

    parser.add_argument("--only-hour-pt", type=int, default=8, help="仅使用该小时（PT）的窗口（默认 08:00）")
    parser.add_argument("--min-hours", type=float, default=-16.0, help="最小 hours_since_quake（默认 -16）")
    parser.add_argument("--max-hours", type=float, default=832.0, help="最大 hours_since_quake（默认 832）")
    parser.add_argument("--distance-bins-km", type=float, nargs="*", default=[0, 25, 50, 100, 200], help="距离带边界（km，不含 inf）")
    parser.add_argument("--target-band", type=str, default="50-100km", help="目标距离带（默认 50-100km）")
    parser.add_argument("--internal-bands", type=str, nargs="*", default=["0-25km", "25-50km"], help="内部带集合（默认 0-25km 25-50km）")
    parser.add_argument("--external-bands", type=str, nargs="*", default=["100-200km", "200km+"], help="外部带集合（默认 100-200km 200km+）")
    parser.add_argument("--min-flow", type=float, default=1.0, help="保留的最小 n_crisis（默认 1）")
    parser.add_argument("--population-by-band-csv", type=Path, default=None, help="可选：population_redistribution 的 redistribution_by_distance_band.csv")
    parser.add_argument("--max-files", type=int, default=None, help="最多处理多少个窗口文件（冒烟测试用）")
    args = parser.parse_args()

    bins = [float(x) for x in args.distance_bins_km]
    if not bins or bins[0] != 0.0:
        bins = [0.0] + bins
    bins = sorted(set(bins))
    bins.append(float("inf"))

    cfg = Config(
        data_root=args.data_root,
        output_dir=args.output_dir,
        center_lat=float(args.center_lat),
        center_lon=float(args.center_lon),
        t0_pt=pd.Timestamp(str(args.t0_pt)),
        slug=(str(args.slug).strip() if args.slug else None),
        only_hour_pt=int(args.only_hour_pt),
        min_hours=float(args.min_hours),
        max_hours=float(args.max_hours),
        distance_bins_km=tuple(float(x) for x in bins),
        target_band=str(args.target_band),
        internal_bands=tuple(str(x) for x in args.internal_bands),
        external_bands=tuple(str(x) for x in args.external_bands),
        min_flow=float(args.min_flow),
        population_by_band_csv=(Path(args.population_by_band_csv) if args.population_by_band_csv else None),
    )
    run(cfg, max_files=int(args.max_files) if args.max_files is not None else None)


if __name__ == "__main__":
    cli_main()
