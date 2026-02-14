#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


FACEBOOK_SLUG_FOLDER_OVERRIDES = {
    "spain_flood": "Spain fllood",
    "mountain_fire_in_california": "Mountain fire in California",
}

DATASETS_SLUG_FOLDER_OVERRIDES = {
    "global_earthquake_model_research_2025_sep_18": "Global_Earthquake_Model_Research_2025_Sep_18",
    "hurricane_melissa_10_27_2025": "Hurricane_Melissa_10_27_2025",
    "hurricane_melissa_aftermath_2025_11_03": "Hurricane_Melissa_Aftermath_2025_11_03",
    "the_earthquake_across_central_mexico": "The_Earthquake_Across_Central_Mexico",
    "the_earthquake_across_dhaka_division_bangladesh": "The_Earthquake_Across_Dhaka_Division_Bangladesh",
}


def _normalize(s: str) -> str:
    s1 = str(s or "").strip().lower()
    s1 = re.sub(r"[^a-z0-9]+", "", s1)
    return s1


def _index_dirs(root: Path) -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = {}
    if not root.exists():
        return out
    for p in sorted(root.iterdir(), key=lambda x: x.name):
        if not p.is_dir():
            continue
        key = _normalize(p.name)
        out.setdefault(key, []).append(p)
    return out


def _first_exists(paths: list[Path]) -> Path | None:
    for p in paths:
        if p is not None and p.exists() and p.is_dir():
            return p
    return None


def _resolve_one(
    row: pd.Series,
    *,
    fb_root: Path,
    ds_root: Path,
    fb_idx: dict[str, list[Path]],
    ds_idx: dict[str, list[Path]],
    prefer: str,
) -> tuple[Path | None, str, str]:
    slug = str(row.get("slug", "")).strip()
    name = str(row.get("name", "")).strip()
    old_root = Path(str(row.get("data_root", "")).strip()) if str(row.get("data_root", "")).strip() else None

    candidates_fb: list[Path] = []
    candidates_ds: list[Path] = []

    if slug in FACEBOOK_SLUG_FOLDER_OVERRIDES:
        candidates_fb.append(fb_root / FACEBOOK_SLUG_FOLDER_OVERRIDES[slug])
    candidates_fb.append(fb_root / name)
    candidates_fb.append(fb_root / Path(name).name)
    if old_root is not None:
        candidates_fb.append(fb_root / old_root.name)
    for k in {_normalize(name), _normalize(slug), _normalize(old_root.name if old_root else "")}:
        if k and k in fb_idx:
            candidates_fb.extend(fb_idx[k])

    if slug in DATASETS_SLUG_FOLDER_OVERRIDES:
        candidates_ds.append(ds_root / DATASETS_SLUG_FOLDER_OVERRIDES[slug])
    candidates_ds.append(ds_root / name)
    candidates_ds.append(ds_root / slug)
    if old_root is not None:
        candidates_ds.append(ds_root / old_root.name)
    for k in {_normalize(name), _normalize(slug), _normalize(old_root.name if old_root else "")}:
        if k and k in ds_idx:
            candidates_ds.extend(ds_idx[k])

    old_ok = old_root.exists() and old_root.is_dir() if old_root is not None else False
    if old_ok:
        return old_root, "legacy_data_root", old_root.name

    if str(prefer).lower() == "datasets":
        picked = _first_exists(candidates_ds) or _first_exists(candidates_fb)
        src = "datasets" if _first_exists(candidates_ds) is not None else "facebook"
    else:
        picked = _first_exists(candidates_fb) or _first_exists(candidates_ds)
        src = "facebook" if _first_exists(candidates_fb) is not None else "datasets"

    if picked is None:
        return None, "missing", ""
    return picked, src, picked.name


def run(
    *,
    catalog_in: Path,
    catalog_out: Path,
    existing_only_out: Path,
    report_out: Path,
    facebook_root: Path,
    datasets_root: Path,
    prefer: str,
) -> None:
    if not catalog_in.exists():
        raise FileNotFoundError(f"未找到 catalog：{catalog_in}")
    df = pd.read_csv(catalog_in)
    required = {"slug", "name", "data_root"}
    miss = sorted(required - set(df.columns))
    if miss:
        raise SystemExit(f"catalog 缺少列：{miss}")

    fb_idx = _index_dirs(facebook_root)
    ds_idx = _index_dirs(datasets_root)

    out_rows = []
    for _, row in df.iterrows():
        new_root, source, folder = _resolve_one(
            row,
            fb_root=facebook_root,
            ds_root=datasets_root,
            fb_idx=fb_idx,
            ds_idx=ds_idx,
            prefer=prefer,
        )
        rr = row.copy()
        rr["data_root_old"] = str(row.get("data_root", ""))
        rr["data_root"] = str(new_root) if new_root is not None else str(row.get("data_root", ""))
        rr["path_exists"] = int(new_root is not None and Path(new_root).exists())
        rr["resolved_source"] = str(source)
        rr["resolved_folder"] = str(folder)
        out_rows.append(rr)

    out = pd.DataFrame(out_rows)
    out.to_csv(catalog_out, index=False)
    out.to_csv(report_out, index=False)

    keep = out[out["path_exists"] == 1].copy()
    keep = keep.drop(columns=["path_exists", "resolved_source", "resolved_folder"], errors="ignore")
    keep.to_csv(existing_only_out, index=False)

    missing = out[out["path_exists"] == 0].copy()
    print(f"total={len(out)}")
    print(f"exists={len(keep)}")
    print(f"missing={len(missing)}")
    if not missing.empty:
        print("missing slugs:")
        for s in missing["slug"].astype(str).tolist():
            print(f"- {s}")
    print(f"written: {catalog_out}")
    print(f"written: {existing_only_out}")
    print(f"written: {report_out}")


def cli_main() -> None:
    p = argparse.ArgumentParser(description="重映射 cross-disaster catalog 的 data_root，适配数据迁移后的路径。")
    p.add_argument("--catalog-in", type=Path, default=Path("Docs/cross_disaster_catalog_extended.csv"))
    p.add_argument("--catalog-out", type=Path, default=Path("Docs/cross_disaster_catalog_extended_wsa.csv"))
    p.add_argument(
        "--existing-only-out",
        type=Path,
        default=Path("Docs/cross_disaster_catalog_extended_wsa_existing_only.csv"),
        help="仅保留路径存在事件（推荐分析直接用这个）。",
    )
    p.add_argument("--report-out", type=Path, default=Path("Docs/cross_disaster_catalog_extended_wsa_path_check.csv"))
    p.add_argument("--facebook-root", type=Path, required=True)
    p.add_argument("--datasets-root", type=Path, required=True)
    p.add_argument("--prefer", type=str, choices=["facebook", "datasets"], default="facebook")
    args = p.parse_args()

    run(
        catalog_in=Path(args.catalog_in),
        catalog_out=Path(args.catalog_out),
        existing_only_out=Path(args.existing_only_out),
        report_out=Path(args.report_out),
        facebook_root=Path(args.facebook_root),
        datasets_root=Path(args.datasets_root),
        prefer=str(args.prefer),
    )


if __name__ == "__main__":
    cli_main()
