from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.cross_band_net_flow import Config as NetFlowConfig
from disaster.cross_band_net_flow import run as run_net_flow
from disaster.cross_disaster_phi_tau import auto_t0_and_center, load_catalog


@dataclass(frozen=True)
class Config:
    catalog: Path
    output_root: Path
    only_hour_pt: int = 8
    min_hours: float = -16.0
    max_hours: float = 832.0
    distance_bins_km: tuple[float, ...] = (0.0, 25.0, 50.0, 100.0, 200.0, float("inf"))
    min_flow: float = 1.0


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def run(cfg: Config, *, max_files: int | None = None) -> None:
    specs = load_catalog(cfg.catalog)
    _ensure_dir(cfg.output_root)

    for spec in specs:
        t0_pt, center_lat, center_lon, meta = auto_t0_and_center(spec)
        (cfg.output_root / spec.slug).mkdir(parents=True, exist_ok=True)
        (cfg.output_root / spec.slug / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        out_dir = cfg.output_root / spec.slug / "cross_band_net_flow"
        _ensure_dir(out_dir)

        pop_band = cfg.output_root / spec.slug / "population_redistribution" / "tables" / "redistribution_by_distance_band.csv"
        pop_band_csv = pop_band if pop_band.exists() else None

        nc_cfg = NetFlowConfig(
            data_root=spec.data_root,
            output_dir=out_dir,
            center_lat=float(center_lat),
            center_lon=float(center_lon),
            t0_pt=pd.Timestamp(t0_pt),
            slug=str(spec.slug),
            only_hour_pt=int(cfg.only_hour_pt),
            min_hours=float(cfg.min_hours),
            max_hours=float(cfg.max_hours),
            distance_bins_km=tuple(float(x) for x in cfg.distance_bins_km),
            min_flow=float(cfg.min_flow),
            population_by_band_csv=pop_band_csv,
        )
        print(f"[cross_disaster_cross_band_net_flow] {spec.slug}: computing cross-band net flow...")
        run_net_flow(nc_cfg, max_files=max_files)


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog.csv"), help="灾难配置表（CSV）")
    parser.add_argument("--output-root", type=Path, default=Path("outputs"), help="输出根目录（默认 outputs/）")
    parser.add_argument("--only-hour-pt", type=int, default=8, help="仅使用该小时（PT）的窗口（默认 08:00）")
    parser.add_argument("--min-hours", type=float, default=-16.0, help="最小 hours_since_quake（默认 -16）")
    parser.add_argument("--max-hours", type=float, default=832.0, help="最大 hours_since_quake（默认 832）")
    parser.add_argument("--distance-bins-km", type=float, nargs="*", default=[0, 25, 50, 100, 200], help="距离带边界（km，不含 inf）")
    parser.add_argument("--min-flow", type=float, default=1.0, help="保留的最小 n_crisis（默认 1）")
    parser.add_argument("--max-files", type=int, default=None, help="最多处理多少个窗口文件（每个灾害，冒烟测试用）")
    args = parser.parse_args()

    bins = [float(x) for x in args.distance_bins_km]
    if not bins or bins[0] != 0.0:
        bins = [0.0] + bins
    bins = sorted(set(bins))
    bins.append(float("inf"))

    cfg = Config(
        catalog=args.catalog,
        output_root=args.output_root,
        only_hour_pt=int(args.only_hour_pt),
        min_hours=float(args.min_hours),
        max_hours=float(args.max_hours),
        distance_bins_km=tuple(float(x) for x in bins),
        min_flow=float(args.min_flow),
    )
    run(cfg, max_files=int(args.max_files) if args.max_files is not None else None)


if __name__ == "__main__":
    cli_main()

