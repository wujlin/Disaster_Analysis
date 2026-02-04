from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.cross_disaster_phi_tau import auto_t0_and_center, load_catalog
from disaster.phi_heatmap import Config as HeatmapConfig
from disaster.phi_heatmap import run as run_heatmap


@dataclass(frozen=True)
class Config:
    catalog: Path
    output_root: Path
    distance_mode: str = "radial"
    hours_pt: tuple[int, ...] = (0, 8, 16)
    min_hours: float = -16.0
    max_hours: float = 832.0
    distance_bin_km: float = 10.0
    max_distance_km: float = 500.0
    phase_eps: float = 0.05


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def run(cfg: Config, *, max_files: int | None = None) -> None:
    specs = load_catalog(cfg.catalog)
    _ensure_dir(cfg.output_root)

    distance_mode = str(cfg.distance_mode).strip().lower() or "radial"
    if distance_mode not in {"radial", "path"}:
        raise SystemExit(f"不支持的 distance_mode：{cfg.distance_mode}（仅支持 radial/path）")

    skipped: list[dict] = []
    for spec in specs:
        if distance_mode == "path" and spec.center_track_csv is None:
            msg = "distance_mode=path 需要 catalog 提供 center_track_csv"
            skipped.append({"slug": spec.slug, "name": spec.name, "reason": msg})
            print(f"[cross_disaster_phi_heatmap] {spec.slug}: skipped ({msg})")
            continue

        t0_pt, center_lat, center_lon, meta = auto_t0_and_center(spec)
        out_dir = cfg.output_root / spec.slug / "phi_heatmap"
        _ensure_dir(out_dir)
        (cfg.output_root / spec.slug / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"[cross_disaster_phi_heatmap] {spec.slug}: computing heatmap...")
        hm_cfg = HeatmapConfig(
            data_root=spec.data_root,
            output_dir=out_dir,
            center_lat=float(center_lat),
            center_lon=float(center_lon),
            center_track_csv=spec.center_track_csv,
            center_track_to_tz=str(spec.center_track_to_tz),
            center_track_storm_name=str(spec.center_track_storm_name) if spec.center_track_storm_name else None,
            distance_mode=str(distance_mode),
            t0_pt=pd.Timestamp(t0_pt),
            hours_pt=tuple(int(h) for h in cfg.hours_pt),
            min_hours=float(cfg.min_hours),
            max_hours=float(cfg.max_hours),
            distance_bin_km=float(cfg.distance_bin_km),
            max_distance_km=float(cfg.max_distance_km),
            phase_eps=float(cfg.phase_eps),
        )
        try:
            run_heatmap(hm_cfg, max_files=max_files)
        except FileNotFoundError as e:
            msg = str(e)
            (out_dir / "SKIPPED.txt").write_text(msg + "\n", encoding="utf-8")
            skipped.append({"slug": spec.slug, "name": spec.name, "reason": msg})
            print(f"[cross_disaster_phi_heatmap] {spec.slug}: skipped ({msg})")
            continue

    if skipped:
        pd.DataFrame(skipped).to_csv(cfg.output_root / "_skipped_phi_heatmap.csv", index=False)


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog.csv"), help="灾难配置表（CSV）")
    parser.add_argument("--output-root", type=Path, default=Path("outputs"), help="输出根目录（默认 outputs/）")
    parser.add_argument(
        "--distance-mode",
        type=str,
        default="radial",
        choices=["radial", "path"],
        help="距离定义：radial=到中心点（static/track）；path=到轨迹折线最近距离（仅对有 center_track_csv 的灾害有效）",
    )
    parser.add_argument("--hours-pt", type=int, nargs="*", default=[0, 8, 16], help="使用哪些 PT 小时窗口（默认 0 8 16）")
    parser.add_argument("--min-hours", type=float, default=-16.0, help="最小 hours_since_quake（默认 -16）")
    parser.add_argument("--max-hours", type=float, default=832.0, help="最大 hours_since_quake（默认 832）")
    parser.add_argument("--distance-bin-km", type=float, default=10.0, help="距离 bin 宽度（km，默认 10）")
    parser.add_argument("--max-distance-km", type=float, default=500.0, help="最大距离（km，默认 500）")
    parser.add_argument("--phase-eps", type=float, default=0.05, help="三相分离判定 eps（默认 0.05）")
    parser.add_argument("--max-files", type=int, default=None, help="最多处理多少个窗口文件（每个灾害，冒烟测试用）")
    args = parser.parse_args()

    cfg = Config(
        catalog=args.catalog,
        output_root=args.output_root,
        distance_mode=str(args.distance_mode),
        hours_pt=tuple(int(x) for x in args.hours_pt),
        min_hours=float(args.min_hours),
        max_hours=float(args.max_hours),
        distance_bin_km=float(args.distance_bin_km),
        max_distance_km=float(args.max_distance_km),
        phase_eps=float(args.phase_eps),
    )
    run(cfg, max_files=int(args.max_files) if args.max_files is not None else None)


if __name__ == "__main__":
    cli_main()
