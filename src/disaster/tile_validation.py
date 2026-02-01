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
from disaster.population_io import load_population_file
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
    evolution_windows: tuple[str, ...] = ("2023-02-06_0800", "2023-02-07_0800", "2023-02-12_0800")
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

    pre_keys = set(pre["quadkey"].dropna().astype(str).unique().tolist())
    post_keys = set(post["quadkey"].dropna().astype(str).unique().tolist())
    new_keys = post_keys - pre_keys

    new_tiles = post[post["quadkey"].astype(str).isin(sorted(new_keys))].copy()
    new_tiles = new_tiles.sort_values("n_crisis", ascending=False, kind="stable")

    out_csv = out.tables / "new_tiles_coordinates.csv"
    new_tiles[
        [
            "quadkey",
            "lat",
            "lon",
            "distance_km",
            "n_baseline",
            "n_crisis",
            "n_difference",
            "z_score",
            "percent_change",
        ]
    ].to_csv(out_csv, index=False)

    # 时间演化：把 new_tiles 在后续窗口（若存在）的 n_crisis 拉出来
    evo_rows: list[dict] = []
    for wid in cfg.evolution_windows:
        try:
            p = _find_unique_file(pop_dir, wid)
        except FileNotFoundError:
            continue
        _, _, ts = _parse_window_id(wid)
        df = load_population_file(p)
        df["quadkey"] = df["quadkey"].astype("string")
        df["n_crisis"] = pd.to_numeric(df["n_crisis"], errors="coerce")
        sub = df[df["quadkey"].astype(str).isin(sorted(new_keys))][["quadkey", "n_crisis"]].copy()
        sub = sub.dropna(subset=["quadkey"])
        for q, n in sub.itertuples(index=False):
            evo_rows.append({"quadkey": str(q), "window_start_pt": ts, "n_crisis": float(n) if pd.notna(n) else np.nan})
    evo = pd.DataFrame(evo_rows)
    out_evo = out.tables / "new_tiles_evolution.csv"
    evo.to_csv(out_evo, index=False)

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

目标：对 0–{int(cfg.max_distance_km)}km 范围内 “post 存在但 pre 不存在” 的 tiles 进行地图标注，用于验证“救援营地/救援设施”假说。

## 输入窗口（PT）

- pre: {pre_ts:%Y-%m-%d %H:%M}  (`{cfg.pre_window}`)
- post: {post_ts:%Y-%m-%d %H:%M} (`{cfg.post_window}`)

## 结果文件

- `tables/new_tiles_coordinates.csv`：新激活 tiles 坐标与 n_crisis 等字段
- `tables/new_tiles_evolution.csv`：新激活 tiles 在后续窗口的 n_crisis（窗口缺失则不会出现）
- `figures/new_tiles_static.*`：静态图（含 25km 圈、震中、Gaziantep Airport 标注）
- `new_tiles_map.html`：交互式地图（需要 folium；若环境无 folium 则不会生成）

## 摘要

- new tiles 数量：{len(new_tiles)}
- 过滤：distance_km < {float(cfg.max_distance_km)}

## 备注

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
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/tile_validation"), help="输出目录")
    parser.add_argument("--max-distance-km", type=float, default=25.0, help="距离阈值（km），默认 25")
    parser.add_argument("--pre-window", type=str, default="2023-02-05_0800", help="pre 窗口（YYYY-MM-DD_HHMM）")
    parser.add_argument("--post-window", type=str, default="2023-02-06_0800", help="post 窗口（YYYY-MM-DD_HHMM）")
    parser.add_argument(
        "--evolution-windows",
        type=str,
        nargs="*",
        default=["2023-02-06_0800", "2023-02-07_0800", "2023-02-12_0800"],
        help="用于时间演化的窗口列表（YYYY-MM-DD_HHMM）",
    )
    parser.add_argument("--radius-divisor", type=float, default=5.0, help="folium marker 半径缩放：radius=n_crisis/divisor")
    parser.add_argument("--max-marker-radius", type=float, default=40.0, help="folium marker 最大半径（像素）")
    args = parser.parse_args()

    cfg = Config(
        data_root=args.data_root,
        output_dir=args.output_dir,
        max_distance_km=float(args.max_distance_km),
        pre_window=str(args.pre_window),
        post_window=str(args.post_window),
        evolution_windows=tuple(str(x) for x in args.evolution_windows),
        radius_divisor=float(args.radius_divisor),
        max_marker_radius=float(args.max_marker_radius),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()

