#!/usr/bin/env python3
"""
导出事件级 provenance 表（可直接用于 SI Table S1）。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def _is_missing(v: object) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return s == "" or s.lower() == "nan"


def _read_meta(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run(*, catalog: Path, output_root: Path, out_csv: Path, strict: int) -> None:
    if not catalog.exists():
        raise SystemExit(f"[fail] catalog 不存在：{catalog}")
    df = pd.read_csv(catalog)
    if "slug" not in df.columns:
        raise SystemExit(f"[fail] catalog 缺少 slug 列：{catalog}")

    rows: list[dict] = []
    missing_meta: list[str] = []
    for row in df.to_dict(orient="records"):
        slug = str(row.get("slug", "")).strip()
        if not slug:
            continue
        meta = _read_meta(output_root / slug / "metadata.json")
        if not meta:
            missing_meta.append(slug)

        t0 = str(row.get("t0_pt", "")).strip()
        first_w = str(meta.get("first_population_window_pt", "")).strip()
        t0_delta_h = None
        if t0 and first_w:
            t0_ts = pd.to_datetime(t0, errors="coerce")
            first_ts = pd.to_datetime(first_w, errors="coerce")
            if pd.notna(t0_ts) and pd.notna(first_ts):
                t0_delta_h = float((t0_ts - first_ts).total_seconds() / 3600.0)

        rows.append(
            {
                "slug": slug,
                "name": str(row.get("name", "")).strip(),
                "event_type": str(row.get("event_type", "")).strip(),
                "data_root": str(row.get("data_root", "")).strip(),
                "t0_pt": t0,
                "center_lat": row.get("center_lat", ""),
                "center_lon": row.get("center_lon", ""),
                "t0_source": str(row.get("t0_source", "")).strip(),
                "center_source": str(row.get("center_source", "")).strip(),
                "exclude_reason": str(row.get("exclude_reason", "")).strip(),
                "t0_method_used": str(meta.get("t0_method", "")).strip(),
                "center_method_used": str(meta.get("center_method", "")).strip(),
                "auto_inference_used": int(meta.get("auto_inference_used", 0)) if meta else -1,
                "first_population_window_pt": first_w,
                "t0_minus_first_window_hours": t0_delta_h,
                "track_anchor_method": str(meta.get("track_anchor_method", "")).strip(),
                "track_anchor_pt": str(meta.get("track_anchor_pt", "")).strip(),
            }
        )

    out_df = pd.DataFrame(rows).sort_values("slug", kind="stable")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_csv, index=False)

    if int(strict) == 1:
        errs: list[str] = []
        if missing_meta:
            errs.append(f"缺少 metadata.json: {sorted(missing_meta)}")
        for col in ("t0_source", "center_source", "t0_pt", "center_lat", "center_lon"):
            bad = out_df[out_df[col].apply(_is_missing)]
            if not bad.empty:
                errs.append(f"列 {col} 存在空值: {sorted(bad['slug'].astype(str).tolist())}")
        if not out_df.empty:
            bad_auto = out_df[pd.to_numeric(out_df["auto_inference_used"], errors="coerce") == 1]
            if not bad_auto.empty:
                errs.append(f"strict 模式不允许 auto_inference_used=1: {sorted(bad_auto['slug'].astype(str).tolist())}")
        if errs:
            print(f"[fail] provenance 检查失败，详情见：{out_csv}")
            for e in errs:
                print(f" - {e}")
            raise SystemExit(1)

    print(f"[ok] wrote provenance table: {out_csv} (n={len(out_df)})")


def main() -> None:
    p = argparse.ArgumentParser(description="导出事件级 provenance 表（SI Table S1）")
    p.add_argument("--catalog", type=Path, required=True)
    p.add_argument("--output-root", type=Path, default=Path("outputs"))
    p.add_argument("--out-csv", type=Path, default=Path("outputs/cross_disaster_comparison/provenance_table_s1.csv"))
    p.add_argument("--strict", type=int, choices=[0, 1], default=1, help="1=要求 source 非空且禁止 auto inference")
    args = p.parse_args()
    run(catalog=args.catalog, output_root=args.output_root, out_csv=args.out_csv, strict=int(args.strict))


if __name__ == "__main__":
    main()
