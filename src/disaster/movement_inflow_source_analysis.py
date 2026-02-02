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
from disaster.population_io import parse_window_start_pt


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

    target_hours: float = 40.0
    distance_bins_km: tuple[float, ...] = (0.0, 25.0, 50.0, 100.0, 200.0, float("inf"))
    end_band: str = "25-50km"
    min_flow: float = 1.0


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
    mov_dir = cfg.data_root / "movement"
    if not mov_dir.exists():
        raise FileNotFoundError(f"未找到目录：{mov_dir}")

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


def _pick_nearest_window(windows: list[dict], target_hours: float) -> dict:
    return min(windows, key=lambda r: abs(float(r["hours_since_quake"]) - float(target_hours)))


def _distance_band_indices(dist_km: np.ndarray, bins_km: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(bins_km, dist_km.astype(float), side="right") - 1
    return idx.astype(int)


def run(cfg: Config) -> None:
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
    if str(cfg.end_band) not in set(labels):
        raise ValueError(f"end_band 不在可用距离带中：{cfg.end_band}；可选：{labels}")
    n_bands = int(len(labels))
    end_band_idx = int(labels.index(str(cfg.end_band)))

    windows = _list_movement_windows(cfg)
    picked = _pick_nearest_window(windows, float(cfg.target_hours))
    path = Path(picked["path"])
    window_start = pd.Timestamp(picked["window_start_pt"])
    hs = float(picked["hours_since_quake"])

    df = load_movement_file(path)
    nc = pd.to_numeric(df.get("n_crisis", np.nan), errors="coerce").to_numpy(dtype=float)
    slat = pd.to_numeric(df.get("start_lat", np.nan), errors="coerce").to_numpy(dtype=float)
    slon = pd.to_numeric(df.get("start_lon", np.nan), errors="coerce").to_numpy(dtype=float)
    elat = pd.to_numeric(df.get("end_lat", np.nan), errors="coerce").to_numpy(dtype=float)
    elon = pd.to_numeric(df.get("end_lon", np.nan), errors="coerce").to_numpy(dtype=float)

    keep = np.isfinite(nc) & (nc > float(cfg.min_flow)) & np.isfinite(slat) & np.isfinite(slon) & np.isfinite(elat) & np.isfinite(elon)
    if not np.any(keep):
        raise SystemExit("该窗口无有效 OD（n_crisis 与坐标过滤后为空）")

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

    sel = eidx == end_band_idx
    if not np.any(sel):
        raise SystemExit("筛选后无样本（检查 end_band / target_hours）")

    nc_sel = nc[sel]
    sidx_sel = sidx[sel]

    total = float(np.nansum(nc_sel))
    n_od = int(nc_sel.size)

    by_start = np.bincount(sidx_sel, weights=nc_sel, minlength=n_bands).astype(float)
    rows: list[dict] = []
    for k, band in enumerate(labels):
        w = float(by_start[k])
        rows.append({"start_band": str(band), "flow_sum": w, "flow_fraction": (w / total) if total > 0 else float("nan")})
    out_df = pd.DataFrame(rows)
    out_df["start_band"] = pd.Categorical(out_df["start_band"], categories=[str(x) for x in labels], ordered=True)
    out_df = out_df.sort_values(["start_band"], kind="stable").reset_index(drop=True)

    out_csv = out_tab / "inflow_source_by_band.csv"
    out_df.to_csv(out_csv, index=False)

    summary = pd.DataFrame(
        [
            {
                "slug": cfg.slug,
                "picked_window_start_pt": str(window_start),
                "picked_hours_since_quake": float(hs),
                "movement_file": str(path.name),
                "end_band": str(cfg.end_band),
                "n_od": int(n_od),
                "total_flow_sum": float(total),
                "share_from_0_25km": float(out_df.loc[out_df["start_band"] == "0-25km", "flow_fraction"].iloc[0]) if "0-25km" in set(out_df["start_band"].astype(str)) else float("nan"),
                "share_from_25_50km": float(out_df.loc[out_df["start_band"] == "25-50km", "flow_fraction"].iloc[0]) if "25-50km" in set(out_df["start_band"].astype(str)) else float("nan"),
                "share_from_50_100km": float(out_df.loc[out_df["start_band"] == "50-100km", "flow_fraction"].iloc[0]) if "50-100km" in set(out_df["start_band"].astype(str)) else float("nan"),
                "share_from_100_200km": float(out_df.loc[out_df["start_band"] == "100-200km", "flow_fraction"].iloc[0]) if "100-200km" in set(out_df["start_band"].astype(str)) else float("nan"),
                "share_from_200kmplus": float(out_df.loc[out_df["start_band"] == "200km+", "flow_fraction"].iloc[0]) if "200km+" in set(out_df["start_band"].astype(str)) else float("nan"),
            }
        ]
    )
    out_sum = out_tab / "inflow_source_summary.csv"
    summary.to_csv(out_sum, index=False)

    readme = f"""# Movement 流入来源分析（按 start_band 分解）

本目录用于验证：目的地落在某个距离带（默认 25-50km）时，其流入主要来自哪些起点距离带。

## 本次运行配置

- slug: {cfg.slug}
- center: ({float(cfg.center_lat):.4f}, {float(cfg.center_lon):.4f})
- t0_pt: {pd.Timestamp(cfg.t0_pt)}
- only_hour_pt: {int(cfg.only_hour_pt)}
- target_hours: {float(cfg.target_hours):g}（实际选取最近窗口 hs={hs:g}）
- end_band: {cfg.end_band}
- distance_bins_km: {list(float(x) for x in bins_km)}

## 输出

- `tables/inflow_source_by_band.csv`：按 start_band 的流量占比（权重 n_crisis）
- `tables/inflow_source_summary.csv`：本次窗口的关键 share 指标
"""
    (out_root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_csv}")
    print(f"Done. Wrote: {out_sum}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True, help="数据根目录（包含 movement/）")
    parser.add_argument("--output-dir", type=Path, required=True, help="输出目录（例如 outputs/<slug>/movement_inflow_source_analysis）")
    parser.add_argument("--center-lat", type=float, required=True, help="中心点纬度（震中/灾害中心）")
    parser.add_argument("--center-lon", type=float, required=True, help="中心点经度（震中/灾害中心）")
    parser.add_argument("--t0-pt", type=str, required=True, help="t=0 的 PT 时间戳（例如 2023-02-05 16:00）")
    parser.add_argument("--slug", type=str, default=None, help="用于 README 的标签（默认 None）")

    parser.add_argument("--only-hour-pt", type=int, default=8, help="仅使用该小时（PT）的窗口（默认 08:00）")
    parser.add_argument("--min-hours", type=float, default=-16.0, help="最小 hours_since_quake（默认 -16）")
    parser.add_argument("--max-hours", type=float, default=832.0, help="最大 hours_since_quake（默认 832）")
    parser.add_argument("--target-hours", type=float, default=40.0, help="目标时刻（小时，默认 40h）")
    parser.add_argument("--distance-bins-km", type=float, nargs="*", default=[0, 25, 50, 100, 200], help="距离带边界（km，不含 inf）")
    parser.add_argument("--end-band", type=str, default="25-50km", help="目的地距离带（默认 25-50km）")
    parser.add_argument("--min-flow", type=float, default=1.0, help="保留的最小 n_crisis（默认 1）")
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
        target_hours=float(args.target_hours),
        distance_bins_km=tuple(float(x) for x in bins),
        end_band=str(args.end_band),
        min_flow=float(args.min_flow),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()

