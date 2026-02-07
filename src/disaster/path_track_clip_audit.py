from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e


@dataclass(frozen=True)
class Config:
    output_root: Path
    out_dir: Path


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _infer_slugs(output_root: Path) -> list[str]:
    slugs: list[str] = []
    for p in sorted(output_root.glob("*/phi_heatmap/tables/center_by_window.csv")):
        slugs.append(p.parents[2].name)
    return slugs


def run(cfg: Config) -> None:
    out = Path(cfg.out_dir)
    tabs = out / "tables"
    _ensure_dir(tabs)

    rows: list[dict] = []
    for slug in _infer_slugs(Path(cfg.output_root)):
        p = Path(cfg.output_root) / slug / "phi_heatmap" / "tables" / "center_by_window.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        if df.empty:
            continue
        r = df.iloc[0].to_dict()
        rows.append(
            {
                "slug": str(slug),
                "distance_mode": str(r.get("distance_mode", "")),
                "path_distance_method": str(r.get("path_distance_method", "")),
                "path_track_clip_kind": str(r.get("path_track_clip_kind", "")),
                "path_track_points_used": int(pd.to_numeric(r.get("path_track_points_used", np.nan), errors="coerce")) if r.get("path_track_points_used") is not None else 0,
                "path_track_points_total": int(pd.to_numeric(r.get("path_track_points_total", np.nan), errors="coerce")) if r.get("path_track_points_total") is not None else 0,
                "path_track_length_km": float(pd.to_numeric(r.get("path_track_length_km", np.nan), errors="coerce")),
                "path_track_length_total_km": float(pd.to_numeric(r.get("path_track_length_total_km", np.nan), errors="coerce")),
                "path_track_length_ratio_to_rmax": float(pd.to_numeric(r.get("path_track_length_ratio_to_rmax", np.nan), errors="coerce")),
                "path_track_length_total_ratio_to_rmax": float(pd.to_numeric(r.get("path_track_length_total_ratio_to_rmax", np.nan), errors="coerce")),
            }
        )

    out_df = pd.DataFrame(rows).sort_values(["path_track_clip_kind", "slug"], kind="stable")
    out_df.to_csv(tabs / "path_track_clip_audit.csv", index=False)
    print(f"Done. Wrote: {tabs / 'path_track_clip_audit.csv'}")


def cli_main() -> None:
    p = argparse.ArgumentParser(description="审计 distance_mode=path 的轨迹裁剪情况（是否退化到 full）")
    p.add_argument("--output-root", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, default=Path("outputs/_tmp_path_track_clip_audit"))
    args = p.parse_args()

    run(Config(output_root=Path(args.output_root), out_dir=Path(args.out_dir)))


if __name__ == "__main__":
    cli_main()

