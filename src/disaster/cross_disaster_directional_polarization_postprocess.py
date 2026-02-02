from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from disaster.cross_disaster_phi_tau import load_catalog
from disaster.directional_polarization_postprocess import Config as PostConfig
from disaster.directional_polarization_postprocess import run as run_post


@dataclass(frozen=True)
class Config:
    catalog: Path
    output_root: Path
    min_n_od: int = 30
    merge_0_50: bool = True


def run(cfg: Config) -> None:
    specs = load_catalog(cfg.catalog)
    for spec in specs:
        in_csv = cfg.output_root / spec.slug / "directional_polarization" / "tables" / "flow_directional_by_band_time.csv"
        out_dir = cfg.output_root / spec.slug / "directional_polarization"
        if not in_csv.exists():
            print(f"[polarization_postprocess] skip missing: {in_csv}")
            continue
        print(f"[polarization_postprocess] {spec.slug}: postprocess...")
        run_post(
            PostConfig(
                input_csv=in_csv,
                output_dir=out_dir,
                min_n_od=int(cfg.min_n_od),
                merge_0_50=bool(cfg.merge_0_50),
            )
        )


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog.csv"), help="灾难配置表（CSV）")
    parser.add_argument("--output-root", type=Path, default=Path("outputs"), help="outputs 根目录")
    parser.add_argument("--min-n-od", type=int, default=30, help="可靠性阈值：n_od >= 阈值（默认 30）")
    parser.add_argument("--no-merge-0-50", action="store_true", help="不生成合并带 0-50km")
    args = parser.parse_args()

    cfg = Config(
        catalog=args.catalog,
        output_root=args.output_root,
        min_n_od=int(args.min_n_od),
        merge_0_50=not bool(args.no_merge_0_50),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()

