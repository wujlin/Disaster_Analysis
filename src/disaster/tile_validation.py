from __future__ import annotations

import argparse
import re
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


WINDOW_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<hhmm>\d{4})$")


@dataclass(frozen=True)
class Config:
    data_root: Path
    output_dir: Path
    epicenter_lat: float = 37.174
    epicenter_lon: float = 37.032
    max_distance_km: float = 25.0
    pre_window: str = "2023-02-05_0800"
    post_window: str = "2023-02-06_0800"
    pre_crisis_max: float = 1.0
    post_crisis_min: float = 10.0
    evolution_all_windows: bool = True
    evolution_windows: tuple[str, ...] = ()
    evolution_max_files: int | None = None
    radius_divisor: float = 5.0
    max_marker_radius: float = 40.0


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _parse_window_id(s: str) -> tuple[str, str, pd.Timestamp]:
    s = str(s).strip()
    m = WINDOW_RE.match(s)
    if not m:
        raise ValueError(f"window 格式应为 YYYY-MM-DD_HHMM，例如 2023-02-06_0800。收到：{s}")
    date_str = m.group("date")
    hhmm = m.group("hhmm")
    hh, mm = int(hhmm[:2]), int(hhmm[2:])
    ts = pd.Timestamp(f"{date_str} {hh:02d}:{mm:02d}")
    return date_str, hhmm, ts


def _find_unique_file(pop_dir: Path, window_id: str) -> Path:
    date_str, hhmm, _ = _parse_window_id(window_id)
    matches = list(pop_dir.glob(f"*_{date_str}_{hhmm}.csv"))
    if len(matches) != 1:
        raise FileNotFoundError(f"无法唯一定位 population 文件：{window_id}，匹配到：{[m.name for m in matches]}")
    return matches[0]


def _circle_latlon(lat0: float, lon0: float, radius_km: float, *, n: int = 360) -> tuple[np.ndarray, np.ndarray]:
    """
    生成经纬度圆（用于静态图上的 25km 圈），球面近似。
    """
    r = 6371.0
    lat0r = np.radians(float(lat0))
    lon0r = np.radians(float(lon0))
    d = float(radius_km) / r
    bearings = np.linspace(0, 2 * np.pi, int(n), endpoint=True)
    lat = np.arcsin(np.sin(lat0r) * np.cos(d) + np.cos(lat0r) * np.sin(d) * np.cos(bearings))
    lon = lon0r + np.arctan2(np.sin(bearings) * np.sin(d) * np.cos(lat0r), np.cos(d) - np.sin(lat0r) * np.sin(lat))
    return np.degrees(lat), np.degrees(lon)


def _load_and_filter(pop_path: Path, *, cfg: Config) -> pd.DataFrame:
    df = load_population_file(pop_path)
    df["n_baseline"] = pd.to_numeric(df["n_baseline"], errors="coerce")
    df["n_crisis"] = pd.to_numeric(df["n_crisis"], errors="coerce")
    df["distance_km"] = haversine_km(
        df["lat"].to_numpy(dtype=float),
        df["lon"].to_numpy(dtype=float),
        cfg.epicenter_lat,
        cfg.epicenter_lon,
    )
    df = df[df["distance_km"].to_numpy(dtype=float) < float(cfg.max_distance_km)].copy()
    df["quadkey"] = df["quadkey"].astype("string")
    return df


def _is_pre_zero(n_crisis_pre: float, *, cfg: Config) -> bool:
    if not np.isfinite(float(n_crisis_pre)):
        return True
    return float(n_crisis_pre) <= float(cfg.pre_crisis_max)


def run(cfg: Config) -> None:
    pop_dir = cfg.data_root / "population"
    if not pop_dir.exists():
        raise FileNotFoundError(f"未找到目录：{pop_dir}")

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

    pre_path = _find_unique_file(pop_dir, cfg.pre_window)
    post_path = _find_unique_file(pop_dir, cfg.post_window)
    _, _, pre_ts = _parse_window_id(cfg.pre_window)
    _, _, post_ts = _parse_window_id(cfg.post_window)

    pre = _load_and_filter(pre_path, cfg=cfg)
    post = _load_and_filter(post_path, cfg=cfg)

    pre_idx = pre.dropna(subset=["quadkey"]).copy()
    pre_idx["quadkey"] = pre_idx["quadkey"].astype(str)
    pre_map = dict(zip(pre_idx["quadkey"].to_numpy(), pre_idx["n_crisis"].to_numpy(dtype=float), strict=False))

    post_idx = post.dropna(subset=["quadkey"]).copy()
    post_idx["quadkey"] = post_idx["quadkey"].astype(str)

    post_ok = post_idx[pd.to_numeric(post_idx["n_crisis"], errors="coerce") >= float(cfg.post_crisis_min)].copy()
    post_ok["n_crisis_pre"] = post_ok["quadkey"].map(pre_map).astype(float)
    activated_mask = post_ok["n_crisis_pre"].apply(lambda x: _is_pre_zero(float(x) if pd.notna(x) else np.nan, cfg=cfg))
    new_tiles = post_ok[activated_mask].copy()
    new_tiles = new_tiles.sort_values("n_crisis", ascending=False, kind="stable")

    new_keys = set(new_tiles["quadkey"].astype(str).tolist())

    out_csv = out.tables / "new_tiles_coordinates.csv"
    new_tiles[
        [
            "quadkey",
            "lat",
            "lon",
            "distance_km",
            "n_baseline",
            "n_crisis",
            "n_crisis_pre",
            "n_difference",
            "z_score",
            "percent_change",
        ]
    ].to_csv(out_csv, index=False)

    # 时间演化：把 new_tiles 在后续窗口的 n_crisis 拉出来（默认扫描全部窗口）
    evo_rows: list[pd.DataFrame] = []
    scanned_windows_count = 0
    if new_keys:
        files = sorted(pop_dir.glob("*.csv"))
        if cfg.evolution_windows and not cfg.evolution_all_windows:
            files = []
            for wid in cfg.evolution_windows:
                try:
                    files.append(_find_unique_file(pop_dir, wid))
                except FileNotFoundError:
                    continue
        if cfg.evolution_max_files is not None:
            files = files[: int(cfg.evolution_max_files)]
        scanned_windows_count = int(len(files))

        for p in files:
            ts = parse_window_start_pt(p)

            df = load_population_file(p)
            df["quadkey"] = df["quadkey"].astype("string")
            sub = df[df["quadkey"].astype(str).isin(new_keys)][["quadkey", "n_baseline", "n_crisis"]].copy()
            if sub.empty:
                continue
            sub["window_start_pt"] = pd.Timestamp(ts)
            sub["n_baseline"] = pd.to_numeric(sub["n_baseline"], errors="coerce")
            sub["n_crisis"] = pd.to_numeric(sub["n_crisis"], errors="coerce")
            evo_rows.append(sub.rename(columns={"quadkey": "quadkey"}))

    evo = pd.concat(evo_rows, ignore_index=True) if evo_rows else pd.DataFrame(columns=["quadkey", "window_start_pt", "n_baseline", "n_crisis"])
    evo["quadkey"] = evo["quadkey"].astype(str)
    evo = evo.sort_values(["quadkey", "window_start_pt"], kind="stable")
    out_evo = out.tables / "new_tiles_evolution.csv"
    evo.to_csv(out_evo, index=False)

    summary_rows: list[dict] = []
    if not evo.empty:
        total_windows = int(scanned_windows_count) if int(scanned_windows_count) > 0 else int(evo["window_start_pt"].nunique())
        for q, sub in evo.groupby("quadkey", sort=False):
            sub = sub.sort_values("window_start_pt", kind="stable")
            present = sub["n_crisis"].notna()
            present_n = int(present.sum())
            first_ts = sub.loc[present, "window_start_pt"].min()
            last_ts = sub.loc[present, "window_start_pt"].max()
            duration_h = float((last_ts - first_ts).total_seconds() / 3600.0) if pd.notna(first_ts) and pd.notna(last_ts) else float("nan")
            summary_rows.append(
                {
                    "quadkey": str(q),
                    "windows_total_scanned": int(total_windows),
                    "windows_present": int(present_n),
                    "presence_ratio": float(present_n / total_windows) if total_windows > 0 else float("nan"),
                    "first_seen_pt": first_ts,
                    "last_seen_pt": last_ts,
                    "duration_hours": duration_h,
                    "n_crisis_peak": float(pd.to_numeric(sub["n_crisis"], errors="coerce").max()),
                    "n_crisis_mean": float(pd.to_numeric(sub["n_crisis"], errors="coerce").mean()),
                }
            )

    summary = pd.DataFrame(summary_rows)
    out_summary = out.tables / "new_tiles_evolution_summary.csv"
    summary.to_csv(out_summary, index=False)

    # 静态图
    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)

        # 背景：post 0-25km 的所有 tiles（浅灰）
        ax.scatter(
            post["lon"].to_numpy(dtype=float),
            post["lat"].to_numpy(dtype=float),
            s=10,
            alpha=0.18,
            color=ps.OKABE_ITO["gray"],
            linewidths=0,
            rasterized=True,
            label="post (all tiles, 0-25km)",
        )

        # 新激活 tiles（蓝色）
        if not new_tiles.empty:
            size = pd.to_numeric(new_tiles["n_crisis"], errors="coerce").to_numpy(dtype=float)
            # 用 sqrt 缩放到点面积，保证静态图可读（interactive map 仍按 radius_divisor 输出）
            s = 18.0 + 90.0 * np.sqrt(np.clip(size, 0, np.nanmax(size))) / (np.sqrt(np.nanmax(size)) + 1e-9)
            ax.scatter(
                new_tiles["lon"].to_numpy(dtype=float),
                new_tiles["lat"].to_numpy(dtype=float),
                s=s,
                alpha=0.75,
                color=ps.OKABE_ITO["blue"],
                linewidths=0,
                rasterized=True,
                label="new tiles (post only)",
            )

        # 震中 + 25km 圈
        ax.scatter([cfg.epicenter_lon], [cfg.epicenter_lat], s=90, c=ps.OKABE_ITO["yellow"], edgecolors="black", linewidths=1.0, zorder=5, label="epicenter")
        clat, clon = _circle_latlon(cfg.epicenter_lat, cfg.epicenter_lon, cfg.max_distance_km, n=240)
        ax.plot(clon, clat, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.2, alpha=0.8, label=f"{int(cfg.max_distance_km)}km")

        # POI：Gaziantep Airport（文档给定）
        ax.scatter([37.478], [36.947], s=70, c=ps.OKABE_ITO["vermillion"], edgecolors="black", linewidths=0.8, zorder=5, label="Gaziantep Airport")

        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.set_title(f"New activated tiles within {int(cfg.max_distance_km)}km (post {post_ts:%Y-%m-%d %H:%M} vs pre {pre_ts:%Y-%m-%d %H:%M})")
        ax.legend(frameon=False, loc="upper right")
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out.figures / "new_tiles_static.png")
        plt.close(fig)

    # 交互式地图（可选 folium）
    html_path = out.root / "new_tiles_map.html"
    folium_ok = True
    try:
        import folium  # type: ignore
    except ModuleNotFoundError:
        folium_ok = False

    if folium_ok:
        m = folium.Map(location=[cfg.epicenter_lat, cfg.epicenter_lon], zoom_start=10, tiles="OpenStreetMap")
        folium.Marker([cfg.epicenter_lat, cfg.epicenter_lon], popup="Epicenter", icon=folium.Icon(color="red")).add_to(m)
        folium.Circle([cfg.epicenter_lat, cfg.epicenter_lon], radius=int(cfg.max_distance_km * 1000), color="gray", dash_array="5").add_to(m)

        # POI marker
        folium.Marker([36.947, 37.478], popup="Gaziantep Airport", icon=folium.Icon(color="orange")).add_to(m)

        for _, row in new_tiles.iterrows():
            n = float(row["n_crisis"]) if pd.notna(row["n_crisis"]) else 0.0
            radius = n / float(cfg.radius_divisor) if float(cfg.radius_divisor) > 0 else n
            radius = float(np.clip(radius, 2.0, float(cfg.max_marker_radius)))
            folium.CircleMarker(
                location=[float(row["lat"]), float(row["lon"])],
                radius=radius,
                popup=f"quadkey={row['quadkey']}; n_crisis={n:.0f}",
                color="blue",
                fill=True,
                fill_opacity=0.65,
            ).add_to(m)

        m.save(str(html_path))

    # README
    readme = f"""# Tile Validation (Task A)

目标：对 0–{int(cfg.max_distance_km)}km 范围内 “震前 n_crisis≈0（或缺失）但震后 n_crisis>0” 的 tiles 进行地图标注与时间演化分析，用于验证“救援/安置设施”假说。

## 输入窗口（PT）

- pre: {pre_ts:%Y-%m-%d %H:%M}  (`{cfg.pre_window}`)
- post: {post_ts:%Y-%m-%d %H:%M} (`{cfg.post_window}`)

## 激活判定口径

- pre: `n_crisis_pre <= {float(cfg.pre_crisis_max)}` 或 `n_crisis_pre` 缺失
- post: `n_crisis_post >= {float(cfg.post_crisis_min)}`（用于排除隐私阈值导致的缺失）

## 结果文件

- `tables/new_tiles_coordinates.csv`：新激活 tiles 坐标与 n_crisis 等字段
- `tables/new_tiles_evolution.csv`：新激活 tiles 在扫描窗口中的 (n_baseline, n_crisis) 时间序列
- `tables/new_tiles_evolution_summary.csv`：每个 tile 的出现持续性摘要（first/last/presence_ratio/peak）
- `figures/new_tiles_static.*`：静态图（含 25km 圈、震中、Gaziantep Airport 标注）
- `new_tiles_map.html`：交互式地图（需要 folium；若环境无 folium 则不会生成）

## 摘要

- new tiles 数量：{len(new_tiles)}
- 过滤：distance_km < {float(cfg.max_distance_km)}
"""
    if cfg.evolution_windows and not cfg.evolution_all_windows:
        readme += f"\n- 时间演化：仅使用 {len(cfg.evolution_windows)} 个指定窗口\n"
    else:
        readme += "\n- 时间演化：扫描 population/ 下的全部窗口（可用 --evolution-max-files 截断）\n"

    readme += """

- 交互式地图依赖 `folium`：可用 `pip install folium` 或 conda 安装。
"""
    (out.root / "README.md").write_text(readme, encoding="utf-8")

    print(f"Done. Wrote: {out_csv}")
    if folium_ok:
        print(f"Done. Wrote: {html_path}")
    else:
        print("Skip folium map: 未安装 folium（仅输出 CSV 与静态图）。")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("Data/Turkiye Turkey Earthquake Full Country Version Feb 8 2023"),
        help="数据根目录（包含 population/ 子目录）",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/turkiye_earthquake_2023/new_tiles_validation"), help="输出目录")
    parser.add_argument("--max-distance-km", type=float, default=25.0, help="距离阈值（km），默认 25")
    parser.add_argument("--pre-window", type=str, default="2023-02-05_0800", help="pre 窗口（YYYY-MM-DD_HHMM）")
    parser.add_argument("--post-window", type=str, default="2023-02-06_0800", help="post 窗口（YYYY-MM-DD_HHMM）")
    parser.add_argument("--pre-crisis-max", type=float, default=1.0, help="pre 窗口的 n_crisis 阈值（<=视为≈0/未激活）")
    parser.add_argument("--post-crisis-min", type=float, default=10.0, help="post 窗口的 n_crisis 阈值（>=视为已激活）")
    parser.add_argument(
        "--evolution-windows",
        type=str,
        nargs="*",
        default=[],
        help="用于时间演化的窗口列表（YYYY-MM-DD_HHMM）。默认扫描全部窗口；若指定且 --no-evolution-all-windows，则只扫描这些窗口。",
    )
    parser.add_argument("--no-evolution-all-windows", action="store_true", help="关闭“扫描全部窗口”，仅使用 --evolution-windows")
    parser.add_argument("--evolution-max-files", type=int, default=None, help="最多扫描多少个窗口文件（用于加速/冒烟测试）")
    parser.add_argument("--radius-divisor", type=float, default=5.0, help="folium marker 半径缩放：radius=n_crisis/divisor")
    parser.add_argument("--max-marker-radius", type=float, default=40.0, help="folium marker 最大半径（像素）")
    args = parser.parse_args()

    cfg = Config(
        data_root=args.data_root,
        output_dir=args.output_dir,
        max_distance_km=float(args.max_distance_km),
        pre_window=str(args.pre_window),
        post_window=str(args.post_window),
        pre_crisis_max=float(args.pre_crisis_max),
        post_crisis_min=float(args.post_crisis_min),
        evolution_all_windows=not bool(args.no_evolution_all_windows),
        evolution_windows=tuple(str(x) for x in args.evolution_windows),
        evolution_max_files=int(args.evolution_max_files) if args.evolution_max_files is not None else None,
        radius_divisor=float(args.radius_divisor),
        max_marker_radius=float(args.max_marker_radius),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()
