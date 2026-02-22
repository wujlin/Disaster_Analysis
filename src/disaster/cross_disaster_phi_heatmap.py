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
    path_distance_method: str = "equirect"
    hours_pt: tuple[int, ...] = (0, 8, 16)
    min_hours: float = -16.0
    max_hours: float = 832.0
    distance_bin_km: float = 10.0
    max_distance_km: float = 500.0
    phase_eps: float = 0.05
    path_clip_pad_hours: float = 24.0
    path_clip_spatial_pad_km: float = 100.0
    path_sector_n: int = 0
    track_dt_default_hours: float = 6.0
    track_gap_factor: float = 1.5
    slugs: tuple[str, ...] = ()
    on_error: str = "fail"  # fail | skip


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def run(cfg: Config, *, max_files: int | None = None) -> None:
    specs = load_catalog(cfg.catalog)
    _ensure_dir(cfg.output_root)

    distance_mode = str(cfg.distance_mode).strip().lower() or "radial"
    if distance_mode not in {"radial", "path"}:
        raise SystemExit(f"不支持的 distance_mode：{cfg.distance_mode}（仅支持 radial/path）")

    on_error = str(cfg.on_error).strip().lower() or "fail"
    if on_error not in {"fail", "skip"}:
        raise SystemExit(f"不支持的 on_error：{cfg.on_error}（仅支持 fail/skip）")

    skipped: list[dict] = []
    for spec in specs:
        if cfg.slugs and spec.slug not in set(cfg.slugs):
            continue
        if distance_mode == "path" and spec.center_track_csv is None:
            msg = "distance_mode=path 需要 catalog 提供 center_track_csv"
            skipped.append({"slug": spec.slug, "name": spec.name, "reason": msg})
            print(f"[cross_disaster_phi_heatmap] {spec.slug}: skipped ({msg})")
            continue

        try:
            t0_pt, center_lat, center_lon, meta = auto_t0_and_center(spec)
        except (FileNotFoundError, SystemExit, ValueError) as e:
            msg = str(e)
            out_dir = cfg.output_root / spec.slug / "phi_heatmap"
            _ensure_dir(out_dir)
            (out_dir / "SKIPPED.txt").write_text(msg + "\n", encoding="utf-8")
            skipped.append({"slug": spec.slug, "name": spec.name, "reason": msg})
            print(f"[cross_disaster_phi_heatmap] {spec.slug}: skipped ({msg})")
            if on_error == "fail":
                raise SystemExit(f"[cross_disaster_phi_heatmap] 配置/数据错误并已停止：{spec.slug}\n{msg}")
            continue
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
            path_distance_method=str(cfg.path_distance_method),
            t0_pt=pd.Timestamp(t0_pt),
            path_clip_pad_hours=float(cfg.path_clip_pad_hours),
            path_clip_spatial_pad_km=float(cfg.path_clip_spatial_pad_km),
            path_sector_n=int(cfg.path_sector_n),
            hours_pt=tuple(int(h) for h in cfg.hours_pt),
            min_hours=float(cfg.min_hours),
            max_hours=float(cfg.max_hours),
            distance_bin_km=float(cfg.distance_bin_km),
            max_distance_km=float(cfg.max_distance_km),
            phase_eps=float(cfg.phase_eps),
            track_dt_default_hours=float(cfg.track_dt_default_hours),
            track_gap_factor=float(cfg.track_gap_factor),
        )
        try:
            run_heatmap(hm_cfg, max_files=max_files)
        except (FileNotFoundError, SystemExit, ValueError) as e:
            msg = str(e)
            (out_dir / "SKIPPED.txt").write_text(msg + "\n", encoding="utf-8")
            skipped.append({"slug": spec.slug, "name": spec.name, "reason": msg})
            print(f"[cross_disaster_phi_heatmap] {spec.slug}: skipped ({msg})")
            if on_error == "fail":
                raise SystemExit(f"[cross_disaster_phi_heatmap] 计算错误并已停止：{spec.slug}\n{msg}")
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
    parser.add_argument(
        "--path-distance-method",
        type=str,
        default="equirect",
        choices=["equirect", "geodesic"],
        help="distance_mode=path 时：点到轨迹距离算法（默认 equirect；geodesic 更精确但更慢）",
    )
    parser.add_argument("--hours-pt", type=int, nargs="*", default=[0, 8, 16], help="使用哪些 PT 小时窗口（默认 0 8 16）")
    parser.add_argument("--min-hours", type=float, default=-16.0, help="最小 hours_since_quake（默认 -16）")
    parser.add_argument("--max-hours", type=float, default=832.0, help="最大 hours_since_quake（默认 832）")
    parser.add_argument("--distance-bin-km", type=float, default=10.0, help="距离 bin 宽度（km，默认 10）")
    parser.add_argument("--max-distance-km", type=float, default=500.0, help="最大距离（km，默认 500）")
    parser.add_argument("--phase-eps", type=float, default=0.05, help="三相分离判定 eps（默认 0.05）")
    parser.add_argument("--path-clip-pad-hours", type=float, default=24.0, help="distance_mode=path 时：以 t0/landfall 为 anchor 的时间裁剪半径（小时，默认 24）")
    parser.add_argument(
        "--path-clip-spatial-pad-km",
        type=float,
        default=100.0,
        help="distance_mode=path 时：空间裁剪 padding（km，默认 100；总半径=max_distance_km+pad）",
    )
    parser.add_argument("--path-sector-n", type=int, default=0, help="distance_mode=path 时角向覆盖率诊断：扇区数（0=不计算，默认 0）")
    parser.add_argument("--track-dt-default-hours", type=float, default=6.0, help="track 点时间间隔估计失败时的默认 dt（小时，默认 6）")
    parser.add_argument("--track-gap-factor", type=float, default=1.5, help="track 连续段判定：gap_thr = dt_est * factor（默认 1.5）")
    parser.add_argument("--max-files", type=int, default=None, help="最多处理多少个窗口文件（每个灾害，冒烟测试用）")
    parser.add_argument("--slugs", type=str, nargs="*", default=[], help="可选：只跑指定 slugs（默认跑全表）")
    parser.add_argument(
        "--on-error",
        type=str,
        choices=["fail", "skip"],
        default="fail",
        help="错误策略：fail=遇到错误立即停止（默认）；skip=写SKIPPED并继续下一个事件",
    )
    args = parser.parse_args()

    cfg = Config(
        catalog=args.catalog,
        output_root=args.output_root,
        distance_mode=str(args.distance_mode),
        path_distance_method=str(args.path_distance_method),
        hours_pt=tuple(int(x) for x in args.hours_pt),
        min_hours=float(args.min_hours),
        max_hours=float(args.max_hours),
        distance_bin_km=float(args.distance_bin_km),
        max_distance_km=float(args.max_distance_km),
        phase_eps=float(args.phase_eps),
        path_clip_pad_hours=float(args.path_clip_pad_hours),
        path_clip_spatial_pad_km=float(args.path_clip_spatial_pad_km),
        path_sector_n=int(args.path_sector_n),
        track_dt_default_hours=float(args.track_dt_default_hours),
        track_gap_factor=float(args.track_gap_factor),
        slugs=tuple(str(s) for s in args.slugs) if args.slugs else (),
        on_error=str(args.on_error),
    )
    run(cfg, max_files=int(args.max_files) if args.max_files is not None else None)


if __name__ == "__main__":
    cli_main()
