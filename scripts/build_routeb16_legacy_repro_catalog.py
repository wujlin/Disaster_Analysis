#!/usr/bin/env python3
"""
构建 RouteB16 的 legacy_repro catalog（用于复现 008a4f5 旧结论）。

规则：
- 事件集合来自基准 catalog（默认 Docs/cross_disaster_catalog_routeB16_frozen.csv）；
- t0_pt、center_lat、center_lon 覆盖为旧提交 outputs/<slug>/metadata.json 中的值；
- center_track_* 清空，确保主分析是静态中心口径；
- 其他字段（name/data_root/event_type/only_hour_pt/阈值）保持基准 catalog。
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd


def _read_old_meta(*, old_commit: str, old_output_root: str, slug: str) -> dict:
    repo_path = f"{old_output_root.rstrip('/')}/{slug}/metadata.json"
    try:
        raw = subprocess.check_output(["git", "show", f"{old_commit}:{repo_path}"])
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"[fail] 无法读取旧 metadata: {repo_path} @ {old_commit}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[fail] 旧 metadata 不是合法 JSON: {repo_path} @ {old_commit}") from exc


def _to_float(value: object, *, field: str, slug: str) -> float:
    try:
        return float(value)
    except Exception as exc:
        raise SystemExit(f"[fail] {slug} 的 {field} 无法转为数值: {value}") from exc


def run(
    *,
    base_catalog: Path,
    out_catalog: Path,
    out_report: Path,
    old_commit: str,
    old_output_root: str,
) -> None:
    if not base_catalog.exists():
        raise SystemExit(f"[fail] 基准 catalog 不存在: {base_catalog}")

    df = pd.read_csv(base_catalog)
    need = {"slug", "t0_pt", "center_lat", "center_lon"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise SystemExit(f"[fail] 基准 catalog 缺少列: {miss}")

    rows: list[dict] = []
    rep: list[dict] = []
    for row in df.to_dict(orient="records"):
        slug = str(row["slug"]).strip()
        old_meta = _read_old_meta(old_commit=old_commit, old_output_root=old_output_root, slug=slug)

        old_t0 = str(old_meta.get("t0_pt", "")).strip()
        if old_t0 == "":
            raise SystemExit(f"[fail] {slug} 旧 metadata 缺少 t0_pt")
        old_lat = _to_float(old_meta.get("center_lat"), field="center_lat", slug=slug)
        old_lon = _to_float(old_meta.get("center_lon"), field="center_lon", slug=slug)

        new_row = dict(row)
        new_row["t0_pt"] = old_t0
        new_row["center_lat"] = old_lat
        new_row["center_lon"] = old_lon
        new_row["center_track_csv"] = ""
        new_row["center_track_to_tz"] = ""
        new_row["center_track_storm_name"] = ""
        rows.append(new_row)

        rep.append(
            {
                "slug": slug,
                "base_t0_pt": row.get("t0_pt"),
                "legacy_t0_pt": old_t0,
                "base_center_lat": row.get("center_lat"),
                "base_center_lon": row.get("center_lon"),
                "legacy_center_lat": old_lat,
                "legacy_center_lon": old_lon,
                "old_t0_method": old_meta.get("t0_method"),
                "old_center_method": old_meta.get("center_method"),
                "old_data_root": old_meta.get("data_root"),
            }
        )

    out_df = pd.DataFrame(rows)
    rep_df = pd.DataFrame(rep)
    out_catalog.parent.mkdir(parents=True, exist_ok=True)
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_catalog, index=False)
    rep_df.to_csv(out_report, index=False)

    print(f"[ok] wrote legacy catalog: {out_catalog} (n={len(out_df)})")
    print(f"[ok] wrote build report: {out_report}")


def main() -> None:
    p = argparse.ArgumentParser(description="构建 RouteB16 的 legacy_repro catalog")
    p.add_argument("--base-catalog", type=Path, default=Path("Docs/cross_disaster_catalog_routeB16_frozen.csv"))
    p.add_argument("--out-catalog", type=Path, default=Path("Docs/cross_disaster_catalog_routeB16_legacy_repro.csv"))
    p.add_argument(
        "--out-report",
        type=Path,
        default=Path("Docs/cross_disaster_catalog_routeB16_legacy_repro_build_report.csv"),
    )
    p.add_argument("--old-commit", type=str, default="008a4f5")
    p.add_argument("--old-output-root", type=str, default="outputs")
    args = p.parse_args()
    run(
        base_catalog=Path(args.base_catalog),
        out_catalog=Path(args.out_catalog),
        out_report=Path(args.out_report),
        old_commit=str(args.old_commit),
        old_output_root=str(args.old_output_root),
    )


if __name__ == "__main__":
    main()
