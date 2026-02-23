#!/usr/bin/env python3
"""
用已生成输出中的 metadata 固化 catalog 的 t0/center，避免后续自动 fallback 漂移。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def _missing(v: object) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return s == "" or s.lower() == "nan"


def run(*, catalog_in: Path, output_root: Path, catalog_out: Path, report_out: Path, mode: str) -> None:
    if not catalog_in.exists():
        raise SystemExit(f"[fail] catalog 不存在: {catalog_in}")
    df = pd.read_csv(catalog_in)
    need = {"slug", "t0_pt", "center_lat", "center_lon"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise SystemExit(f"[fail] catalog 缺少列: {miss}")

    rows: list[dict] = []
    report: list[dict] = []
    for row in df.to_dict(orient="records"):
        slug = str(row["slug"]).strip()
        md_path = output_root / slug / "metadata.json"
        if not md_path.exists():
            report.append({"slug": slug, "status": "missing_metadata", "updated": 0})
            rows.append(dict(row))
            continue
        md = json.loads(md_path.read_text(encoding="utf-8"))

        t0_old = row.get("t0_pt")
        lat_old = row.get("center_lat")
        lon_old = row.get("center_lon")

        t0_new = md.get("t0_pt")
        lat_new = md.get("center_lat")
        lon_new = md.get("center_lon")

        upd_t0 = (mode == "all") or _missing(t0_old)
        upd_center = (mode == "all") or _missing(lat_old) or _missing(lon_old)

        out = dict(row)
        if "t0_source" not in out:
            out["t0_source"] = ""
        if "center_source" not in out:
            out["center_source"] = ""
        if "exclude_reason" not in out:
            out["exclude_reason"] = ""
        changed = 0
        if upd_t0 and not _missing(t0_new):
            out["t0_pt"] = t0_new
            src_t0 = str(md.get("t0_source", "")).strip() or str(md.get("t0_method", "")).strip()
            if src_t0:
                out["t0_source"] = src_t0
            changed += int(str(t0_old) != str(t0_new))
        if upd_center and (not _missing(lat_new)) and (not _missing(lon_new)):
            out["center_lat"] = float(lat_new)
            out["center_lon"] = float(lon_new)
            src_center = str(md.get("center_source", "")).strip() or str(md.get("center_method", "")).strip()
            if src_center:
                out["center_source"] = src_center
            changed += int((str(lat_old) != str(lat_new)) or (str(lon_old) != str(lon_new)))

        rows.append(out)
        report.append(
            {
                "slug": slug,
                "status": "ok",
                "updated": int(changed > 0),
                "updated_t0": int(upd_t0 and not _missing(t0_new)),
                "updated_center": int(upd_center and not _missing(lat_new) and not _missing(lon_new)),
                "old_t0_pt": t0_old,
                "new_t0_pt": out.get("t0_pt"),
                "old_center_lat": lat_old,
                "old_center_lon": lon_old,
                "new_center_lat": out.get("center_lat"),
                "new_center_lon": out.get("center_lon"),
                "t0_method_from_output": md.get("t0_method"),
                "center_method_from_output": md.get("center_method"),
                "t0_source_from_output": md.get("t0_source", ""),
                "center_source_from_output": md.get("center_source", ""),
            }
        )

    out_df = pd.DataFrame(rows)
    rep_df = pd.DataFrame(report)
    catalog_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(catalog_out, index=False)
    rep_df.to_csv(report_out, index=False)
    print(f"[ok] wrote frozen catalog: {catalog_out} (n={len(out_df)})")
    print(f"[ok] wrote report: {report_out}")


def main() -> None:
    p = argparse.ArgumentParser(description="从 outputs metadata 固化 catalog 的 t0/center")
    p.add_argument("--catalog-in", type=Path, required=True)
    p.add_argument("--output-root", type=Path, required=True)
    p.add_argument("--catalog-out", type=Path, required=True)
    p.add_argument("--report-out", type=Path, required=True)
    p.add_argument("--mode", type=str, choices=["missing_only", "all"], default="missing_only")
    args = p.parse_args()
    run(
        catalog_in=args.catalog_in,
        output_root=args.output_root,
        catalog_out=args.catalog_out,
        report_out=args.report_out,
        mode=args.mode,
    )


if __name__ == "__main__":
    main()
