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
from disaster.viz import default_distance_bin_color_map, save_png_and_pdf


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
    snapshot_offsets_hours: tuple[float, ...] = (-8.0, 16.0, 40.0, 88.0, 160.0, 328.0, 832.0)

    min_flow: float = 1.0  # n_crisis > 0
    clip_cos: bool = True


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


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


def _pick_nearest_by_hours(windows: list[dict], offsets_hours: tuple[float, ...]) -> list[dict]:
    if not windows:
        return []
    picked: list[dict] = []
    for off in offsets_hours:
        best = min(windows, key=lambda r: abs(float(r["hours_since_quake"]) - float(off)))
        picked.append(best)
    seen = set()
    uniq: list[dict] = []
    for r in picked:
        key = (str(r["path"]), float(r["hours_since_quake"]))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq


def _distance_band_indices(dist_km: np.ndarray, bins_km: np.ndarray) -> np.ndarray:
    # mimic pd.cut(..., right=False): [left, right)
    idx = np.searchsorted(bins_km, dist_km.astype(float), side="right") - 1
    return idx.astype(int)


def _safe_cos(v_lat: np.ndarray, v_lon: np.ndarray, r_lat: np.ndarray, r_lon: np.ndarray, *, clip: bool) -> np.ndarray:
    dot = v_lat * r_lat + v_lon * r_lon
    v_norm = np.sqrt(v_lat * v_lat + v_lon * v_lon)
    r_norm = np.sqrt(r_lat * r_lat + r_lon * r_lon)
    denom = v_norm * r_norm
    cos = np.full(dot.shape, np.nan, dtype=float)
    ok = np.isfinite(dot) & np.isfinite(denom) & (denom > 0)
    cos[ok] = dot[ok] / denom[ok]
    if clip:
        cos = np.clip(cos, -1.0, 1.0)
    return cos


def _sign(x: float) -> int:
    if not np.isfinite(float(x)):
        return 0
    if float(x) > 0:
        return 1
    if float(x) < 0:
        return -1
    return 0


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

    windows = _list_movement_windows(cfg)
    if max_files is not None:
        windows = windows[: int(max_files)]

    bins_km = np.array(cfg.distance_bins_km, dtype=float)
    if bins_km.ndim != 1 or bins_km.size < 2:
        raise ValueError("distance_bins_km 至少需要 2 个边界值")
    if not np.isinf(bins_km[-1]):
        bins_km = np.concatenate([bins_km, [float("inf")]])
    labels = distance_bin_labels(bins_km)
    n_bands = int(len(labels))

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
            for b in labels:
                rows.append(
                    {
                        "window_start_pt": window_start,
                        "hours_since_quake": hs,
                        "only_hour_pt": int(cfg.only_hour_pt),
                        "distance_band": str(b),
                        "n_od": 0,
                        "F_r": float("nan"),
                        "F_total": 0.0,
                        "P": float("nan"),
                        "A": float("nan"),
                    }
                )
            continue

        slat = slat[keep]
        slon = slon[keep]
        elat = elat[keep]
        elon = elon[keep]
        nc = nc[keep]

        v_lat = elat - slat
        v_lon = elon - slon
        r_lat = slat - float(cfg.center_lat)
        r_lon = slon - float(cfg.center_lon)

        cos_alpha = _safe_cos(v_lat, v_lon, r_lat, r_lon, clip=bool(cfg.clip_cos))
        dist_km = haversine_km(slat, slon, float(cfg.center_lat), float(cfg.center_lon))

        ok = np.isfinite(cos_alpha) & np.isfinite(dist_km) & (dist_km >= 0)
        if not np.any(ok):
            for b in labels:
                rows.append(
                    {
                        "window_start_pt": window_start,
                        "hours_since_quake": hs,
                        "only_hour_pt": int(cfg.only_hour_pt),
                        "distance_band": str(b),
                        "n_od": 0,
                        "F_r": float("nan"),
                        "F_total": 0.0,
                        "P": float("nan"),
                        "A": float("nan"),
                    }
                )
            continue

        cos_alpha = cos_alpha[ok]
        dist_km = dist_km[ok]
        nc = nc[ok]

        idx = _distance_band_indices(dist_km, bins_km)
        in_range = (idx >= 0) & (idx < n_bands)
        if not np.any(in_range):
            for b in labels:
                rows.append(
                    {
                        "window_start_pt": window_start,
                        "hours_since_quake": hs,
                        "only_hour_pt": int(cfg.only_hour_pt),
                        "distance_band": str(b),
                        "n_od": 0,
                        "F_r": float("nan"),
                        "F_total": 0.0,
                        "P": float("nan"),
                        "A": float("nan"),
                    }
                )
            continue

        idx = idx[in_range]
        nc = nc[in_range]
        cos_alpha = cos_alpha[in_range]

        f_total = np.bincount(idx, weights=nc, minlength=n_bands).astype(float)
        f_rad = np.bincount(idx, weights=nc * cos_alpha, minlength=n_bands).astype(float)
        n_od = np.bincount(idx, minlength=n_bands).astype(int)

        for k, band in enumerate(labels):
            ft = float(f_total[k])
            fr = float(f_rad[k])
            if np.isfinite(ft) and ft > 0:
                p = fr / ft
                a = abs(fr) / ft
            else:
                p = float("nan")
                a = float("nan")
            rows.append(
                {
                    "window_start_pt": window_start,
                    "hours_since_quake": hs,
                    "only_hour_pt": int(cfg.only_hour_pt),
                    "distance_band": str(band),
                    "n_od": int(n_od[k]),
                    "F_r": fr,
                    "F_total": ft,
                    "P": float(p) if np.isfinite(p) else float("nan"),
                    "A": float(a) if np.isfinite(a) else float("nan"),
                }
            )

        if i % 30 == 0:
            print(f"[directional_polarization] processed {i}/{len(windows)} windows...")

    df_long = pd.DataFrame(rows)
    df_long["distance_band"] = pd.Categorical(df_long["distance_band"], categories=[str(x) for x in labels], ordered=True)
    df_long = df_long.sort_values(["hours_since_quake", "distance_band"], kind="stable")
    out_long = out.tables / "flow_directional_by_band_time.csv"
    df_long.to_csv(out_long, index=False)

    # wide time series for P(t)
    wide = df_long.pivot_table(index=["window_start_pt", "hours_since_quake"], columns="distance_band", values="P", aggfunc="first").reset_index()
    wide = wide.sort_values(["hours_since_quake"], kind="stable")
    out_wide = out.tables / "polarization_time_series.csv"
    wide.to_csv(out_wide, index=False)

    # summary: peak and sign flip (per band)
    summary_rows: list[dict] = []
    for band, sub in df_long.groupby("distance_band", sort=False, observed=True):
        sub = sub.sort_values("hours_since_quake", kind="stable")
        hs_arr = pd.to_numeric(sub["hours_since_quake"], errors="coerce").to_numpy(dtype=float)
        p_arr = pd.to_numeric(sub["P"], errors="coerce").to_numpy(dtype=float)
        okp = np.isfinite(hs_arr) & np.isfinite(p_arr)
        hs_arr = hs_arr[okp]
        p_arr = p_arr[okp]

        row: dict = {"distance_band": str(band), "n_windows": int(p_arr.size)}
        if p_arr.size == 0:
            row.update(
                {
                    "P_max": float("nan"),
                    "t_at_P_max": float("nan"),
                    "P_min": float("nan"),
                    "t_at_P_min": float("nan"),
                    "t_flip_start": float("nan"),
                    "t_flip_end": float("nan"),
                    "P_flip_start": float("nan"),
                    "P_flip_end": float("nan"),
                }
            )
            summary_rows.append(row)
            continue

        imax = int(np.nanargmax(p_arr))
        imin = int(np.nanargmin(p_arr))
        row["P_max"] = float(p_arr[imax])
        row["t_at_P_max"] = float(hs_arr[imax])
        row["P_min"] = float(p_arr[imin])
        row["t_at_P_min"] = float(hs_arr[imin])

        # first sign flip across consecutive windows (ignore exact zeros)
        sgn = np.array([_sign(float(x)) for x in p_arr], dtype=int)
        nz = sgn != 0
        flip_found = False
        if np.any(nz):
            idxs = np.where(nz)[0]
            for a, b in zip(idxs[:-1], idxs[1:], strict=False):
                if int(sgn[a]) != int(sgn[b]):
                    row["t_flip_start"] = float(hs_arr[a])
                    row["t_flip_end"] = float(hs_arr[b])
                    row["P_flip_start"] = float(p_arr[a])
                    row["P_flip_end"] = float(p_arr[b])
                    flip_found = True
                    break
        if not flip_found:
            row["t_flip_start"] = float("nan")
            row["t_flip_end"] = float("nan")
            row["P_flip_start"] = float("nan")
            row["P_flip_end"] = float("nan")

        summary_rows.append(row)

    summary_df = pd.DataFrame(summary_rows)
    summary_df["distance_band"] = pd.Categorical(summary_df["distance_band"], categories=[str(x) for x in labels], ordered=True)
    summary_df = summary_df.sort_values(["distance_band"], kind="stable")
    out_summary = out.tables / "polarization_summary.csv"
    summary_df.to_csv(out_summary, index=False)

    # figures
    label = cfg.slug or "event"
    times = sorted(df_long["hours_since_quake"].dropna().unique().astype(float).tolist())
    pivot = df_long.pivot_table(index="distance_band", columns="hours_since_quake", values="P", aggfunc="first")
    pivot = pivot.reindex(index=[str(x) for x in labels])
    pivot = pivot.reindex(columns=times)

    with ps.paper_style():
        import matplotlib.pyplot as plt
        from matplotlib.colors import TwoSlopeNorm

        z = pivot.to_numpy(dtype=float)
        xs = np.array(times, dtype=float)
        ys = np.arange(n_bands, dtype=float)

        fig, ax = plt.subplots(figsize=(ps.FIGSIZE_FULL[0], ps.FIGSIZE_FULL[1] * 0.9))
        if xs.size >= 2:
            x_step = float(np.median(np.diff(xs)))
        else:
            x_step = 24.0

        norm = TwoSlopeNorm(vmin=-1.0, vcenter=0.0, vmax=1.0)
        im = ax.imshow(
            z,
            origin="lower",
            aspect="auto",
            cmap="RdBu_r",
            norm=norm,
            extent=[float(xs.min() - x_step / 2.0), float(xs.max() + x_step / 2.0), -0.5, float(n_bands) - 0.5],
        )
        ax.axvline(0.0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.set_xlabel("Hours since event (PT windows)")
        ax.set_ylabel("Distance band (by origin tile)")
        ax.set_title(rf"Directional polarization $P(r,t)$ heatmap ({label})")

        ax.set_yticks(ys)
        ax.set_yticklabels([str(x) for x in labels])
        if xs.size:
            step_idx = max(1, int(xs.size / 10))
            xt_idx = np.arange(0, xs.size, step_idx)
            ax.set_xticks(xs[xt_idx])
            ax.set_xticklabels([f"{int(round(xs[j]))}" for j in xt_idx])

        cb = fig.colorbar(im, ax=ax, shrink=0.92)
        cb.set_label(r"$P=F_r/F_{total}$ (outward>0, inward<0)")
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / f"polarization_heatmap_{label}.png")
        plt.close(fig)

    # P(t) time series
    color_map = default_distance_bin_color_map(ps, [str(x) for x in labels])
    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        for band in labels:
            sub = df_long[df_long["distance_band"] == str(band)].sort_values("hours_since_quake", kind="stable")
            x = pd.to_numeric(sub["hours_since_quake"], errors="coerce").to_numpy(dtype=float)
            y = pd.to_numeric(sub["P"], errors="coerce").to_numpy(dtype=float)
            ax.plot(x, y, marker="o", label=str(band), color=color_map.get(str(band), ps.OKABE_ITO["gray"]), alpha=0.9)

        ax.axvline(0.0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.axhline(0.0, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.6)
        ax.set_xlabel("Hours since event (PT windows)")
        ax.set_ylabel(r"Polarization $P=F_r/F_{total}$")
        ax.set_title(f"Directional polarization time series ({label})")
        ax.set_ylim(-1.02, 1.02)
        ps.despine(ax)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3, frameon=False)
        fig.subplots_adjust(bottom=0.28)
        save_png_and_pdf(ps, fig, out.figures / "polarization_time_series.png")
        plt.close(fig)

    # snapshots: P(r) at selected times
    picked = _pick_nearest_by_hours(windows, cfg.snapshot_offsets_hours)
    for meta in picked:
        hs = float(meta["hours_since_quake"])
        sub = df_long[df_long["hours_since_quake"] == hs].copy()
        sub = sub.sort_values("distance_band", kind="stable")
        y = pd.to_numeric(sub["P"], errors="coerce").to_numpy(dtype=float)
        x = np.arange(n_bands, dtype=float)
        with ps.paper_style():
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
            ax.plot(x, y, marker="o", color=ps.OKABE_ITO["blue"], alpha=0.9)
            ax.axhline(0.0, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.6)
            ax.set_xticks(x)
            ax.set_xticklabels([str(b) for b in labels], rotation=0)
            ax.set_xlabel("Distance band (km)")
            ax.set_ylabel(r"Polarization $P$")
            ax.set_title(f"P(r) at t={hs:g}h ({label})")
            ax.set_ylim(-1.02, 1.02)
            ps.despine(ax)
            fig.tight_layout()
            save_png_and_pdf(ps, fig, out.figures / f"polarization_vs_distance_t{int(round(hs))}h.png")
            plt.close(fig)

    t_min = pd.to_datetime(df_long["window_start_pt"]).min() if not df_long.empty else None
    t_max = pd.to_datetime(df_long["window_start_pt"]).max() if not df_long.empty else None
    readme = f"""# Movement 方向极化分析

本目录实现 PI 提案的 **Movement 方向极化** 指标：

- 对每条 OD（i→j），定义
  - 流动向量：v = (lat_j-lat_i, lon_j-lon_i)
  - 径向向量：r = (lat_i-lat_c, lon_i-lon_c)
  - cos_alpha = (v·r)/(|v||r|)
- 按 (distance_band, time_window) 聚合：
  - F_r = Σ n_crisis · cos_alpha
  - F_total = Σ n_crisis
  - P = F_r / F_total ∈ [-1,1]（>0 外流；<0 内流）
  - A = |F_r| / F_total ∈ [0,1]

## 配置

- slug: {cfg.slug}
- center: ({float(cfg.center_lat):.4f}, {float(cfg.center_lon):.4f})
- t0_pt: {pd.Timestamp(cfg.t0_pt)}
- only_hour_pt: {int(cfg.only_hour_pt)}
- time range (hours_since_quake): [{float(cfg.min_hours)}, {float(cfg.max_hours)}]
- distance_bins_km: {list(float(x) for x in bins_km)}

## 输出

- `tables/flow_directional_by_band_time.csv`：长表（band×time 的 F_r/F_total/P/A）
- `tables/polarization_time_series.csv`：宽表（每行一个窗口，列为各距离带的 P）
- `tables/polarization_summary.csv`：每距离带的峰值与首次方向反转（相邻窗口符号翻转）
- `figures/polarization_heatmap_{label}.*`：P(r,t) 热图
- `figures/polarization_time_series.*`：P(t) 时间序列（多距离带）
- `figures/polarization_vs_distance_t*h.*`：选定时间点的 P(r)

## 覆盖时间（PT）

- {t_min} → {t_max}
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_long}")
    print(f"Done. Wrote: {out_wide}")
    print(f"Done. Wrote: {out_summary}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True, help="数据根目录（包含 movement/）")
    parser.add_argument("--output-dir", type=Path, required=True, help="输出目录（例如 outputs/<slug>/directional_polarization）")
    parser.add_argument("--center-lat", type=float, required=True, help="中心点纬度（震中/灾害中心）")
    parser.add_argument("--center-lon", type=float, required=True, help="中心点经度（震中/灾害中心）")
    parser.add_argument("--t0-pt", type=str, required=True, help="t=0 的 PT 时间戳（例如 2023-02-05 16:00）")
    parser.add_argument("--slug", type=str, default=None, help="用于文件命名的标签（默认 None）")

    parser.add_argument("--only-hour-pt", type=int, default=8, help="仅使用该小时（PT）的窗口（默认 08:00）")
    parser.add_argument("--min-hours", type=float, default=-16.0, help="最小 hours_since_quake（默认 -16）")
    parser.add_argument("--max-hours", type=float, default=832.0, help="最大 hours_since_quake（默认 832）")
    parser.add_argument("--distance-bins-km", type=float, nargs="*", default=[0, 25, 50, 100, 200], help="距离带边界（km，不含 inf）")
    parser.add_argument("--snapshot-offsets-hours", type=float, nargs="*", default=[-8, 16, 40, 88, 160, 328, 832], help="输出 P(r) 的时间点（小时）")
    parser.add_argument("--min-flow", type=float, default=1.0, help="保留的最小 n_crisis（默认 1）")
    parser.add_argument("--no-clip-cos", action="store_true", help="不对 cos_alpha 裁剪到 [-1,1]")
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
        snapshot_offsets_hours=tuple(float(x) for x in args.snapshot_offsets_hours),
        min_flow=float(args.min_flow),
        clip_cos=not bool(args.no_clip_cos),
    )
    run(cfg, max_files=int(args.max_files) if args.max_files is not None else None)


if __name__ == "__main__":
    cli_main()
