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
    distance_bins_km: tuple[float, ...] = (0.0, 25.0, 50.0, 100.0, 200.0, float("inf"))
    min_flow: float = 1.0

    population_by_band_csv: Path | None = None  # outputs/<slug>/population_redistribution/tables/redistribution_by_distance_band.csv


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


def _distance_band_indices(dist_km: np.ndarray, bins_km: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(bins_km, dist_km.astype(float), side="right") - 1
    return idx.astype(int)


def _load_phi_by_band(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    needed = {"window_start_pt", "hours_since_quake", "distance_band"}
    if not needed <= set(df.columns):
        raise ValueError(f"population_by_band_csv 缺少列：{sorted(needed - set(df.columns))}")
    keep_cols = [
        "window_start_pt",
        "hours_since_quake",
        "distance_band",
        "phi_aggregate",
        "baseline_mean_overlap",
        "crisis_mean_overlap",
    ]
    cols = [c for c in keep_cols if c in df.columns]
    out = df[cols].copy()
    out["hours_since_quake"] = pd.to_numeric(out["hours_since_quake"], errors="coerce")
    out["phi_aggregate"] = pd.to_numeric(out.get("phi_aggregate", np.nan), errors="coerce")
    out["baseline_mean_overlap"] = pd.to_numeric(out.get("baseline_mean_overlap", np.nan), errors="coerce")
    out["crisis_mean_overlap"] = pd.to_numeric(out.get("crisis_mean_overlap", np.nan), errors="coerce")
    out["phi_mean_overlap_ratio"] = out["crisis_mean_overlap"] / out["baseline_mean_overlap"]
    out["phi_mean_overlap_minus_1"] = out["phi_mean_overlap_ratio"] - 1.0
    return out


def run(cfg: Config, *, max_files: int | None = None) -> None:
    out_root = Path(cfg.output_dir)
    out_tables = out_root / "tables"
    _ensure_dir(out_root)
    _ensure_dir(out_tables)

    bins_km = np.array(cfg.distance_bins_km, dtype=float)
    if bins_km.ndim != 1 or bins_km.size < 2:
        raise ValueError("distance_bins_km 至少需要 2 个边界值")
    if not np.isinf(bins_km[-1]):
        bins_km = np.concatenate([bins_km, [float("inf")]])
    labels = distance_bin_labels(bins_km)
    n_bands = int(len(labels))

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
            for band in labels:
                rows.append(
                    {
                        "window_start_pt": window_start,
                        "hours_since_quake": hs,
                        "only_hour_pt": int(cfg.only_hour_pt),
                        "distance_band": str(band),
                        "n_od": 0,
                        "start_sum": 0.0,
                        "end_sum": 0.0,
                        "same_sum": 0.0,
                        "N_out": 0.0,
                        "N_in": 0.0,
                        "Net": 0.0,
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
        if not np.any(ok):
            for band in labels:
                rows.append(
                    {
                        "window_start_pt": window_start,
                        "hours_since_quake": hs,
                        "only_hour_pt": int(cfg.only_hour_pt),
                        "distance_band": str(band),
                        "n_od": 0,
                        "start_sum": 0.0,
                        "end_sum": 0.0,
                        "same_sum": 0.0,
                        "N_out": 0.0,
                        "N_in": 0.0,
                        "Net": 0.0,
                    }
                )
            continue

        nc = nc[ok]
        sidx = sidx[ok].astype(int)
        eidx = eidx[ok].astype(int)

        start_sum = np.bincount(sidx, weights=nc, minlength=n_bands).astype(float)
        end_sum = np.bincount(eidx, weights=nc, minlength=n_bands).astype(float)
        same_mask = sidx == eidx
        same_sum = np.bincount(sidx[same_mask], weights=nc[same_mask], minlength=n_bands).astype(float) if np.any(same_mask) else np.zeros(n_bands, dtype=float)
        start_count = np.bincount(sidx, minlength=n_bands).astype(int)

        for k, band in enumerate(labels):
            ssum = float(start_sum[k])
            esum = float(end_sum[k])
            same = float(same_sum[k])
            n_out = float(ssum - same)
            n_in = float(esum - same)
            rows.append(
                {
                    "window_start_pt": window_start,
                    "hours_since_quake": hs,
                    "only_hour_pt": int(cfg.only_hour_pt),
                    "distance_band": str(band),
                    "n_od": int(start_count[k]),
                    "start_sum": ssum,
                    "end_sum": esum,
                    "same_sum": same,
                    "N_out": n_out,
                    "N_in": n_in,
                    "Net": float(esum - ssum),
                }
            )

        if i % 30 == 0:
            print(f"[cross_band_net_flow] processed {i}/{len(windows)} windows...")

    out_df = pd.DataFrame(rows)
    out_df["distance_band"] = pd.Categorical(out_df["distance_band"], categories=[str(x) for x in labels], ordered=True)
    out_df = out_df.sort_values(["hours_since_quake", "distance_band"], kind="stable").reset_index(drop=True)

    # Merge φ
    phi_df: pd.DataFrame | None = None
    if cfg.population_by_band_csv is not None and Path(cfg.population_by_band_csv).exists():
        phi_df = _load_phi_by_band(Path(cfg.population_by_band_csv))
        out_df = out_df.merge(
            phi_df,
            on=["window_start_pt", "hours_since_quake", "distance_band"],
            how="left",
            validate="many_to_one",
        )

    out_csv = out_tables / "cross_band_net_flow.csv"
    out_df.to_csv(out_csv, index=False)

    if phi_df is not None:
        corr_rows: list[dict] = []
        for band, sub in out_df.groupby("distance_band", sort=False, observed=True):
            net = pd.to_numeric(sub["Net"], errors="coerce")
            phi_m = pd.to_numeric(sub.get("phi_mean_overlap_minus_1", np.nan), errors="coerce")
            phi_a = pd.to_numeric(sub.get("phi_aggregate", np.nan), errors="coerce")
            ok_m = net.notna() & phi_m.notna()
            ok_a = net.notna() & phi_a.notna()
            corr_rows.append(
                {
                    "distance_band": str(band),
                    "n_points_phi_mean": int(ok_m.sum()),
                    "corr_net_phi_mean_overlap_minus_1": float(net[ok_m].corr(phi_m[ok_m])) if int(ok_m.sum()) >= 3 else float("nan"),
                    "n_points_phi_aggregate": int(ok_a.sum()),
                    "corr_net_phi_aggregate": float(net[ok_a].corr(phi_a[ok_a])) if int(ok_a.sum()) >= 3 else float("nan"),
                }
            )
        corr_df = pd.DataFrame(corr_rows)
        corr_df["distance_band"] = pd.Categorical(corr_df["distance_band"], categories=[str(x) for x in labels], ordered=True)
        corr_df = corr_df.sort_values(["distance_band"], kind="stable").reset_index(drop=True)
        out_corr = out_tables / "net_flow_phi_corr_by_band.csv"
        corr_df.to_csv(out_corr, index=False)
        print(f"Done. Wrote: {out_corr}")

    readme = f"""# Movement 跨带净流量（cross-band net flow）

本目录实现 PI 更新任务框的 **跨带净流量** 指标（按距离带与时间窗口聚合）：

对每条 OD：
- 计算起点距离带 start_band（按起点到中心距离分箱）
- 计算终点距离带 end_band（按终点到中心距离分箱）

对每个距离带 band、时间窗口 t：
- N_out(band,t) = Σ n_crisis where start_band==band and end_band!=band
- N_in(band,t)  = Σ n_crisis where end_band==band and start_band!=band
- Net(band,t)   = N_in - N_out (= end_sum - start_sum)

## 配置

- slug: {cfg.slug}
- center: ({float(cfg.center_lat):.4f}, {float(cfg.center_lon):.4f})
- t0_pt: {pd.Timestamp(cfg.t0_pt)}
- only_hour_pt: {int(cfg.only_hour_pt)}
- time range (hours_since_quake): [{float(cfg.min_hours)}, {float(cfg.max_hours)}]
- distance_bins_km: {list(float(x) for x in bins_km)}

## 输出

- `tables/cross_band_net_flow.csv`：每个 (band, time) 的 N_in/N_out/Net（可选合并 φ 字段）
- `tables/net_flow_phi_corr_by_band.csv`：若提供 population_by_band_csv，则输出 corr(Net, φ-1)（按 band）
"""
    (out_root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_csv}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True, help="数据根目录（包含 movement/）")
    parser.add_argument("--output-dir", type=Path, required=True, help="输出目录（例如 outputs/<slug>/cross_band_net_flow）")
    parser.add_argument("--center-lat", type=float, required=True, help="中心点纬度（震中/灾害中心）")
    parser.add_argument("--center-lon", type=float, required=True, help="中心点经度（震中/灾害中心）")
    parser.add_argument("--t0-pt", type=str, required=True, help="t=0 的 PT 时间戳（例如 2023-02-05 16:00）")
    parser.add_argument("--slug", type=str, default=None, help="用于 README 的标签（默认 None）")

    parser.add_argument("--only-hour-pt", type=int, default=8, help="仅使用该小时（PT）的窗口（默认 08:00）")
    parser.add_argument("--min-hours", type=float, default=-16.0, help="最小 hours_since_quake（默认 -16）")
    parser.add_argument("--max-hours", type=float, default=832.0, help="最大 hours_since_quake（默认 832）")
    parser.add_argument("--distance-bins-km", type=float, nargs="*", default=[0, 25, 50, 100, 200], help="距离带边界（km，不含 inf）")
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
        min_flow=float(args.min_flow),
        population_by_band_csv=(Path(args.population_by_band_csv) if args.population_by_band_csv else None),
    )
    run(cfg, max_files=int(args.max_files) if args.max_files is not None else None)


if __name__ == "__main__":
    cli_main()

