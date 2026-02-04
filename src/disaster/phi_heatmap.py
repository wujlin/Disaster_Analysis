from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.geo import haversine_km
from disaster.population_io import load_population_file, parse_window_start_pt
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    data_root: Path
    output_dir: Path
    center_lat: float
    center_lon: float
    t0_pt: pd.Timestamp
    center_track_csv: Path | None = None
    center_track_to_tz: str = "America/Los_Angeles"
    center_track_storm_name: str | None = None
    distance_mode: str = "radial"  # radial: 到中心点距离；path: 到轨迹折线最近距离
    hours_pt: tuple[int, ...] = (0, 8, 16)
    min_hours: float = -16.0
    max_hours: float = 832.0
    distance_bin_km: float = 10.0
    max_distance_km: float = 500.0
    phi_vmin: float = 0.6
    phi_vmax: float = 1.6
    contour_levels: tuple[float, ...] = (1.0, 0.9, 0.8)
    phase_eps: float = 0.05


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _sum_min_count_1(s: pd.Series) -> float:
    """
    避免 pandas 的默认行为：当某组全是 NaN 时 sum() 返回 0.0，导致 phi 伪信号（例如 phi=0）。
    """
    return float(s.sum(min_count=1))


def _list_population_windows(cfg: Config) -> list[dict]:
    pop_dir = cfg.data_root / "population"
    if not pop_dir.exists():
        raise FileNotFoundError(f"未找到目录：{pop_dir}")

    files = sorted(pop_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"目录为空：{pop_dir}")

    hours_keep = set(int(h) for h in cfg.hours_pt)
    rows: list[dict] = []
    for p in files:
        ts = parse_window_start_pt(p)
        if hours_keep and int(ts.hour) not in hours_keep:
            continue
        h = float((pd.Timestamp(ts) - pd.Timestamp(cfg.t0_pt)).total_seconds() / 3600.0)
        if h < float(cfg.min_hours) or h > float(cfg.max_hours):
            continue
        rows.append({"path": p, "window_start_pt": pd.Timestamp(ts), "hours_since_quake": float(h)})

    rows = sorted(rows, key=lambda r: float(r["hours_since_quake"]))
    if not rows:
        raise FileNotFoundError(
            f"未找到符合条件的 population 窗口：hours_pt={sorted(hours_keep)}，t范围=[{cfg.min_hours},{cfg.max_hours}]"
        )
    return rows


def _load_center_track(cfg: Config) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    if cfg.center_track_csv is None:
        return None
    p = Path(cfg.center_track_csv)
    if not p.exists():
        raise FileNotFoundError(f"未找到 center_track_csv：{p}")

    df = pd.read_csv(p)
    required = {"datetime_utc", "lat", "lon"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"track CSV 缺少列：{missing}（来自 {p}）")

    if "storm_name" in df.columns:
        names = (
            df["storm_name"]
            .dropna()
            .astype(str)
            .map(lambda s: s.strip())
            .replace("", np.nan)
            .dropna()
            .unique()
            .tolist()
        )
        want = str(cfg.center_track_storm_name).strip() if cfg.center_track_storm_name else ""
        if want:
            df = df[df["storm_name"].astype(str).str.strip().str.lower() == want.lower()].copy()
        elif len(names) > 1:
            raise SystemExit(f"track CSV 含多个 storm_name={sorted(names)}；请设置 center_track_storm_name 指定其一（来自 {p}）")

    t_utc = pd.to_datetime(df["datetime_utc"], utc=True, errors="coerce")
    t_local = t_utc.dt.tz_convert(str(cfg.center_track_to_tz)).dt.tz_localize(None)
    lat = pd.to_numeric(df["lat"], errors="coerce")
    lon = pd.to_numeric(df["lon"], errors="coerce")
    ok = t_local.notna() & lat.notna() & lon.notna()
    t_local = t_local[ok]
    lat = lat[ok]
    lon = lon[ok]
    if t_local.empty:
        raise SystemExit(f"track CSV 无有效时间/坐标：{p}")

    t_ns = t_local.astype("datetime64[ns]").astype("int64").to_numpy(dtype=np.int64)
    lat_v = lat.to_numpy(dtype=float)
    lon_v = lon.to_numpy(dtype=float)

    order = np.argsort(t_ns)
    t_ns = t_ns[order]
    lat_v = lat_v[order]
    lon_v = lon_v[order]

    # drop duplicate timestamps (keep last)
    if t_ns.size >= 2:
        keep = np.ones(t_ns.shape[0], dtype=bool)
        keep[:-1] = t_ns[:-1] != t_ns[1:]
        t_ns = t_ns[keep]
        lat_v = lat_v[keep]
        lon_v = lon_v[keep]

    return t_ns, lat_v, lon_v


def _center_at(track: tuple[np.ndarray, np.ndarray, np.ndarray], ts: pd.Timestamp) -> tuple[float, float]:
    t_ns_arr, lat_arr, lon_arr = track
    x = np.int64(pd.Timestamp(ts).value)
    lat = float(np.interp(x, t_ns_arr, lat_arr, left=float(lat_arr[0]), right=float(lat_arr[-1])))
    lon = float(np.interp(x, t_ns_arr, lon_arr, left=float(lon_arr[0]), right=float(lon_arr[-1])))
    return lat, lon


def _equirect_xy_km(
    lat_deg: np.ndarray, lon_deg: np.ndarray, *, lat0_deg: float, lon0_deg: float
) -> tuple[np.ndarray, np.ndarray]:
    """
    简单等距圆柱投影（equirectangular approximation）。
    目的：在不引入 shapely/pyproj 依赖的前提下，计算点到折线的近似距离（km）。
    """
    r_earth_km = 6371.0088
    lat = np.deg2rad(lat_deg.astype(float))
    lon = np.deg2rad(lon_deg.astype(float))
    lat0 = float(np.deg2rad(float(lat0_deg)))
    lon0 = float(np.deg2rad(float(lon0_deg)))
    x = (lon - lon0) * np.cos(lat0) * r_earth_km
    y = (lat - lat0) * r_earth_km
    return x, y


def _min_dist_to_polyline_km(
    lat_deg: np.ndarray,
    lon_deg: np.ndarray,
    *,
    seg_ax: np.ndarray,
    seg_ay: np.ndarray,
    seg_bx: np.ndarray,
    seg_by: np.ndarray,
    lat0_deg: float,
    lon0_deg: float,
) -> np.ndarray:
    ok = np.isfinite(lat_deg) & np.isfinite(lon_deg)
    d = np.full(lat_deg.shape, np.nan, dtype=float)
    if not np.any(ok):
        return d

    x, y = _equirect_xy_km(lat_deg[ok], lon_deg[ok], lat0_deg=float(lat0_deg), lon0_deg=float(lon0_deg))
    min_d2 = np.full(x.shape, np.inf, dtype=float)
    for ax, ay, bx, by in zip(seg_ax.tolist(), seg_ay.tolist(), seg_bx.tolist(), seg_by.tolist(), strict=False):
        abx = float(bx) - float(ax)
        aby = float(by) - float(ay)
        denom = abx * abx + aby * aby
        if denom <= 0:
            continue
        t = ((x - float(ax)) * abx + (y - float(ay)) * aby) / denom
        t = np.clip(t, 0.0, 1.0)
        cx = float(ax) + t * abx
        cy = float(ay) + t * aby
        d2 = (x - cx) ** 2 + (y - cy) ** 2
        min_d2 = np.minimum(min_d2, d2)

    d_ok = np.sqrt(min_d2)
    d[ok] = d_ok
    return d


def _distance_bins(cfg: Config) -> np.ndarray:
    step = float(cfg.distance_bin_km)
    if step <= 0:
        raise ValueError("distance_bin_km 必须 > 0")
    max_r = float(cfg.max_distance_km)
    if max_r <= 0:
        raise ValueError("max_distance_km 必须 > 0")
    return np.arange(0.0, max_r, step, dtype=float)


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


def _three_phase_ok(phi: np.ndarray, *, eps: float) -> tuple[bool, str]:
    raw = [_sign(float(v), eps=eps) for v in phi]
    compact = [s for s in raw if s in {"+", "-"}]
    collapsed = _collapse(compact)
    return collapsed == ["+", "-", "+"], "".join(collapsed)


def _contiguous_true_blocks(times: np.ndarray, ok: np.ndarray) -> list[dict]:
    if times.size == 0 or ok.size == 0 or times.size != ok.size:
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


def run(cfg: Config, *, max_files: int | None = None) -> None:
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

    windows = _list_population_windows(cfg)
    if max_files is not None:
        windows = windows[: int(max_files)]

    track = _load_center_track(cfg)
    distance_mode = str(cfg.distance_mode).strip().lower() or "radial"
    if distance_mode not in {"radial", "path"}:
        raise SystemExit(f"不支持的 distance_mode：{cfg.distance_mode}（仅支持 radial/path）")

    path_ctx: dict | None = None
    if distance_mode == "path":
        if track is None:
            raise SystemExit("distance_mode=path 需要 center_track_csv（用于定义灾害路径折线）")
        _t, lat_arr, lon_arr = track
        if lat_arr.size < 2:
            raise SystemExit("distance_mode=path 需要至少 2 个轨迹点")
        lat0 = float(np.nanmean(lat_arr))
        lon0 = float(np.nanmean(lon_arr))
        x_tr, y_tr = _equirect_xy_km(lat_arr, lon_arr, lat0_deg=lat0, lon0_deg=lon0)
        path_ctx = {
            "lat0": float(lat0),
            "lon0": float(lon0),
            "seg_ax": x_tr[:-1].astype(float),
            "seg_ay": y_tr[:-1].astype(float),
            "seg_bx": x_tr[1:].astype(float),
            "seg_by": y_tr[1:].astype(float),
        }

    r_bins = _distance_bins(cfg)
    step = float(cfg.distance_bin_km)
    r_max = float(cfg.max_distance_km)

    rows: list[pd.DataFrame] = []
    center_rows: list[dict] = []
    for i, meta in enumerate(windows, start=1):
        p = Path(meta["path"])
        df = load_population_file(p)

        n_baseline = pd.to_numeric(df["n_baseline"], errors="coerce").to_numpy(dtype=float)
        n_crisis = pd.to_numeric(df["n_crisis"], errors="coerce").to_numpy(dtype=float)
        lat = pd.to_numeric(df["lat"], errors="coerce").to_numpy(dtype=float)
        lon = pd.to_numeric(df["lon"], errors="coerce").to_numpy(dtype=float)

        window_ts = pd.Timestamp(meta["window_start_pt"])
        if track is None:
            center_lat, center_lon = float(cfg.center_lat), float(cfg.center_lon)
        else:
            center_lat, center_lon = _center_at(track, window_ts)
        center_rows.append(
            {
                "window_start_pt": window_ts,
                "hours_since_quake": float(meta["hours_since_quake"]),
                "center_lat": float(center_lat),
                "center_lon": float(center_lon),
                "center_mode": "track" if track is not None else "static",
                "distance_mode": str(distance_mode),
                "center_track_csv": str(cfg.center_track_csv) if cfg.center_track_csv is not None else "",
                "center_track_to_tz": str(cfg.center_track_to_tz),
                "center_track_storm_name": str(cfg.center_track_storm_name) if cfg.center_track_storm_name else "",
            }
        )

        if distance_mode == "radial":
            dist = haversine_km(lat, lon, float(center_lat), float(center_lon))
        else:
            assert path_ctx is not None
            dist = _min_dist_to_polyline_km(
                lat,
                lon,
                seg_ax=path_ctx["seg_ax"],
                seg_ay=path_ctx["seg_ay"],
                seg_bx=path_ctx["seg_bx"],
                seg_by=path_ctx["seg_by"],
                lat0_deg=float(path_ctx["lat0"]),
                lon0_deg=float(path_ctx["lon0"]),
            )
        r_bin = np.floor(dist / step) * step
        keep = np.isfinite(r_bin) & (r_bin >= 0) & (r_bin < r_max)

        tmp = pd.DataFrame(
            {
                "r_bin_km": r_bin[keep].astype(float),
                "n_baseline": n_baseline[keep],
                "n_crisis": n_crisis[keep],
            }
        )
        both = tmp["n_baseline"].notna() & tmp["n_crisis"].notna()
        tmp["baseline_overlap"] = tmp["n_baseline"].where(both)
        tmp["crisis_overlap"] = tmp["n_crisis"].where(both)

        agg = (
            tmp.groupby("r_bin_km", observed=True)
            .agg(
                n_tiles=("n_baseline", "count"),
                n_tiles_crisis=("n_crisis", "count"),
                n_tiles_overlap=("baseline_overlap", "count"),
                baseline_sum=("n_baseline", _sum_min_count_1),
                crisis_sum=("n_crisis", _sum_min_count_1),
                baseline_sum_overlap=("baseline_overlap", _sum_min_count_1),
                crisis_sum_overlap=("crisis_overlap", _sum_min_count_1),
            )
            .reset_index()
        )
        agg["phi_aggregate"] = agg["crisis_sum"] / agg["baseline_sum"]
        agg["phi_overlap"] = agg["crisis_sum_overlap"] / agg["baseline_sum_overlap"]
        agg.loc[agg["n_tiles"] <= 0, "phi_aggregate"] = np.nan
        agg.loc[agg["n_tiles_overlap"] <= 0, "phi_overlap"] = np.nan
        agg["tile_overlap_ratio"] = np.where(agg["n_tiles"] > 0, agg["n_tiles_overlap"] / agg["n_tiles"], np.nan)
        agg.insert(0, "window_start_pt", pd.Timestamp(meta["window_start_pt"]))
        agg.insert(1, "hours_since_quake", float(meta["hours_since_quake"]))

        rows.append(agg)

        if i % 20 == 0:
            print(f"[phi_heatmap] processed {i}/{len(windows)} windows...")

    long_df = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    out_long = out.tables / "phi_rt_long.csv"
    long_df.to_csv(out_long, index=False)

    pd.DataFrame(center_rows).to_csv(out.tables / "center_by_window.csv", index=False)

    # pivot：r_bin_km x hours_since_quake
    pivot = long_df.pivot(index="r_bin_km", columns="hours_since_quake", values="phi_aggregate").sort_index().sort_index(axis=1)
    pivot = pivot.reindex(index=r_bins)
    t_grid = np.arange(float(cfg.min_hours), float(cfg.max_hours) + 1e-9, 8.0, dtype=float)
    pivot = pivot.reindex(columns=t_grid)
    out_matrix = out.tables / "phi_rt_matrix.csv"
    pivot.reset_index().to_csv(out_matrix, index=False)

    # three-phase detection by time
    times = pivot.columns.to_numpy(dtype=float)
    ok_rows: list[dict] = []
    ok_flags: list[bool] = []
    patterns: list[str] = []
    for t in times:
        phi = pivot[t].to_numpy(dtype=float)
        ok, collapsed = _three_phase_ok(phi, eps=float(cfg.phase_eps))
        if float(t) < 0:
            ok = False
        ok_flags.append(bool(ok))
        patterns.append(collapsed)
        ok_rows.append({"hours_since_quake": float(t), "three_phase_ok": int(bool(ok)), "pattern_collapsed": str(collapsed)})

    ok_df = pd.DataFrame(ok_rows)
    out_ok = out.tables / "three_phase_by_time.csv"
    ok_df.to_csv(out_ok, index=False)

    blocks = _contiguous_true_blocks(times=times, ok=np.array(ok_flags, dtype=bool))
    blocks_df = pd.DataFrame(blocks)
    out_blocks = out.tables / "three_phase_windows.csv"
    blocks_df.to_csv(out_blocks, index=False)

    # heatmap
    with ps.paper_style():
        import matplotlib.pyplot as plt
        from matplotlib.colors import TwoSlopeNorm

        z = pivot.to_numpy(dtype=float)
        xs = pivot.columns.to_numpy(dtype=float)
        ys = pivot.index.to_numpy(dtype=float)

        fig, ax = plt.subplots(figsize=(ps.FIGSIZE_FULL[0], ps.FIGSIZE_FULL[1] * 1.05))

        if xs.size >= 2:
            x_step = float(np.median(np.diff(xs)))
        else:
            x_step = 8.0
        if ys.size >= 2:
            y_step = float(np.median(np.diff(ys)))
        else:
            y_step = float(cfg.distance_bin_km)

        x_centers = xs
        y_centers = ys + y_step / 2.0

        norm = TwoSlopeNorm(vmin=float(cfg.phi_vmin), vcenter=1.0, vmax=float(cfg.phi_vmax))
        im = ax.imshow(
            z,
            origin="lower",
            aspect="auto",
            cmap="RdBu_r",
            norm=norm,
            extent=[float(xs.min() - x_step / 2.0), float(xs.max() + x_step / 2.0), float(ys.min()), float(ys.max() + y_step)],
        )

        # 三相分离窗口阴影
        for b in blocks:
            ax.axvspan(float(b["t_start_hours"]) - x_step / 2.0, float(b["t_end_hours"]) + x_step / 2.0, color=ps.OKABE_ITO["gray"], alpha=0.12, linewidth=0)

        # 等值线（phi=1/0.9/0.8）
        try:
            xx, yy = np.meshgrid(x_centers, y_centers)
            cs = ax.contour(
                xx,
                yy,
                z,
                levels=[float(x) for x in cfg.contour_levels],
                colors=[ps.OKABE_ITO["black"]] * len(cfg.contour_levels),
                linewidths=1.0,
                linestyles=["--", ":", ":"][: len(cfg.contour_levels)],
                alpha=0.85,
            )
            ax.clabel(cs, inline=True, fontsize=8, fmt=lambda v: f"{v:.1f}")
        except Exception:
            pass

        ax.axvline(0.0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.set_xlabel("Hours since event (PT windows, 8h step)")
        ax.set_ylabel("Distance to center r (km)")
        ax.set_title(r"$\phi_{agg}(r,t)$ heatmap (red>1, white=1, blue<1)")

        cb = fig.colorbar(im, ax=ax, shrink=0.92)
        cb.set_label(r"$\phi_{agg}=\sum n_{crisis}/\sum n_{baseline}$")

        # y ticks 稀疏化（每 50km）
        if ys.size:
            yt = np.arange(0, float(cfg.max_distance_km) + 1e-9, 50.0)
            ax.set_yticks(yt)
            ax.set_yticklabels([f"{int(v)}" for v in yt])
        # x ticks 稀疏化
        if xs.size:
            step_idx = max(1, int(xs.size / 10))
            xt_idx = np.arange(0, xs.size, step_idx)
            ax.set_xticks(xs[xt_idx])
            ax.set_xticklabels([f"{int(round(xs[j]))}" for j in xt_idx])

        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "phi_rt_heatmap.png")
        plt.close(fig)

    t_min = pd.to_datetime(long_df["window_start_pt"]).min() if not long_df.empty else None
    t_max = pd.to_datetime(long_df["window_start_pt"]).max() if not long_df.empty else None
    readme = f"""# Phi Heatmap (Task 4)

本目录对应 `Opinion_PI.md` 的 **任务 4**：计算并可视化连续版本的 $\\phi(r,t)$：

- 距离：0–{int(cfg.max_distance_km)} km，每 {int(cfg.distance_bin_km)} km 一个 bin
- 时间：每 8 小时一个窗口（PT），t 范围 [{float(cfg.min_hours)}, {float(cfg.max_hours)}] 小时
- 指标：$\\phi_{{agg}}(r,t)=\\sum n_{{crisis}}/\\sum n_{{baseline}}$

## 配置

 - center: ({float(cfg.center_lat):.4f}, {float(cfg.center_lon):.4f})
 - center_track_csv: {cfg.center_track_csv}
 - center_track_to_tz: {cfg.center_track_to_tz}
 - center_track_storm_name: {cfg.center_track_storm_name}
 - distance_mode: {distance_mode}
 - t0_pt: {pd.Timestamp(cfg.t0_pt)}
 - hours_pt: {list(int(h) for h in cfg.hours_pt)}

## 输出

- `tables/phi_rt_long.csv`：长表（每个窗口 × 每个 r_bin 的汇总）
- `tables/phi_rt_matrix.csv`：宽表（rows=r_bin_km, cols=hours_since_quake）
- `tables/center_by_window.csv`：每个时间窗口使用的中心点（static 或 track 插值）
- `tables/three_phase_by_time.csv`：三相分离判定（按时间）
- `tables/three_phase_windows.csv`：三相分离连续时间段
- `figures/phi_rt_heatmap.*`：热力图（含 φ=1/0.9/0.8 等值线）

## 覆盖时间（PT）

- {t_min} → {t_max}
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_long}")
    print(f"Done. Wrote: {out_matrix}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True, help="数据根目录（包含 population/）")
    parser.add_argument("--output-dir", type=Path, required=True, help="输出目录")
    parser.add_argument("--center-lat", type=float, required=True, help="中心点纬度（震中/灾害中心）")
    parser.add_argument("--center-lon", type=float, required=True, help="中心点经度（震中/灾害中心）")
    parser.add_argument("--center-track-csv", type=Path, default=None, help="可选：时变中心轨迹 CSV（含 datetime_utc,lat,lon 列）")
    parser.add_argument("--center-track-to-tz", type=str, default="America/Los_Angeles", help="轨迹时间从 UTC 转到该时区再对齐（默认 America/Los_Angeles）")
    parser.add_argument("--center-track-storm-name", type=str, default=None, help="可选：当轨迹 CSV 含多个 storm_name 时用于过滤")
    parser.add_argument(
        "--distance-mode",
        type=str,
        default="radial",
        choices=["radial", "path"],
        help="距离定义：radial=到中心点（static/track）；path=到轨迹折线最近距离（需要 center_track_csv）",
    )
    parser.add_argument("--t0-pt", type=str, required=True, help="t=0 的 PT 时间戳（例如 2023-02-05 16:00）")
    parser.add_argument("--hours-pt", type=int, nargs="*", default=[0, 8, 16], help="保留哪些 PT 小时窗口（默认 0 8 16）")
    parser.add_argument("--min-hours", type=float, default=-16.0, help="最小 hours_since_quake（默认 -16）")
    parser.add_argument("--max-hours", type=float, default=832.0, help="最大 hours_since_quake（默认 832）")
    parser.add_argument("--distance-bin-km", type=float, default=10.0, help="距离 bin 宽度（km，默认 10）")
    parser.add_argument("--max-distance-km", type=float, default=500.0, help="最大距离（km，默认 500）")
    parser.add_argument("--phi-vmin", type=float, default=0.6, help="热力图 vmin（默认 0.6）")
    parser.add_argument("--phi-vmax", type=float, default=1.6, help="热力图 vmax（默认 1.6）")
    parser.add_argument("--max-files", type=int, default=None, help="最多处理多少个窗口文件（冒烟测试用）")
    args = parser.parse_args()

    cfg = Config(
        data_root=args.data_root,
        output_dir=args.output_dir,
        center_lat=float(args.center_lat),
        center_lon=float(args.center_lon),
        center_track_csv=Path(args.center_track_csv) if args.center_track_csv is not None else None,
        center_track_to_tz=str(args.center_track_to_tz),
        center_track_storm_name=str(args.center_track_storm_name) if args.center_track_storm_name else None,
        distance_mode=str(args.distance_mode),
        t0_pt=pd.Timestamp(str(args.t0_pt)),
        hours_pt=tuple(int(x) for x in args.hours_pt),
        min_hours=float(args.min_hours),
        max_hours=float(args.max_hours),
        distance_bin_km=float(args.distance_bin_km),
        max_distance_km=float(args.max_distance_km),
        phi_vmin=float(args.phi_vmin),
        phi_vmax=float(args.phi_vmax),
    )
    run(cfg, max_files=int(args.max_files) if args.max_files is not None else None)


if __name__ == "__main__":
    cli_main()
