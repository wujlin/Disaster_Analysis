#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path


FILENAME_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})_(\d{4})\.csv$")


def _safe_slug(s: str) -> str:
    s = str(s).strip().lower()
    out = []
    prev_us = False
    for ch in s:
        ok = ("a" <= ch <= "z") or ("0" <= ch <= "9")
        if ok:
            out.append(ch)
            prev_us = False
        else:
            if not prev_us:
                out.append("_")
                prev_us = True
    slug = "".join(out).strip("_")
    slug = re.sub(r"_+", "_", slug)
    return slug or "event"


def _is_population_header(line: str) -> bool:
    cols = [c.strip().strip('"').strip("'") for c in str(line).strip().split(",")]
    s = {c.lower() for c in cols if c}
    need = {"n_baseline", "n_crisis"}
    has_latlon = ({"latitude", "longitude"}.issubset(s)) or ({"lat", "lon"}.issubset(s))
    return need.issubset(s) and has_latlon


def _iter_candidate_csvs(src: Path, *, max_depth: int, require_population_in_path: bool) -> list[Path]:
    out: list[Path] = []
    for p in src.rglob("*.csv"):
        try:
            rel = p.relative_to(src)
        except Exception:
            continue
        if len(rel.parts) > int(max_depth):
            continue
        if require_population_in_path:
            rel_s = "/".join([x.lower() for x in rel.parts])
            if "population" not in rel_s:
                continue
        if not FILENAME_RE.search(p.name):
            continue
        out.append(p)
    out.sort(key=lambda x: (len(x.parts), x.as_posix()))
    return out


def _read_first_line(p: Path) -> str:
    with p.open("r", encoding="utf-8", errors="replace") as f:
        return f.readline().strip()


def _window_key_from_name(name: str) -> str | None:
    m = FILENAME_RE.search(str(name))
    if not m:
        return None
    return f"{m.group(1)}_{m.group(2)}"


@dataclass(frozen=True)
class StageResult:
    src: Path
    dst: Path
    slug: str
    n_windows: int
    n_duplicates_dropped: int
    example_src_csv: str


def stage_population(
    src: Path,
    dst: Path,
    *,
    mode: str,
    max_depth: int,
    require_population_in_path: bool,
    dry_run: bool,
) -> StageResult:
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError(f"未找到源目录：{src}")
    slug = _safe_slug(dst.name)

    cands = _iter_candidate_csvs(src, max_depth=int(max_depth), require_population_in_path=bool(require_population_in_path))
    if not cands:
        raise SystemExit(f"未找到候选 CSV（max_depth={max_depth}，require_population_in_path={require_population_in_path}）：{src}")

    # Filter to real population CSVs; avoid staging movement/coverage/business by mistake.
    pop_cands: list[Path] = []
    for p in cands:
        try:
            if _is_population_header(_read_first_line(p)):
                pop_cands.append(p)
        except Exception:
            continue
    if not pop_cands:
        raise SystemExit(f"未检测到 population 风格表头（n_baseline/n_crisis/...）：{src}")
    pop_cands.sort(key=lambda x: (len(x.parts), x.as_posix()))
    example = str(pop_cands[0])

    best_by_key: dict[str, Path] = {}
    dropped = 0
    for p in pop_cands:
        key = _window_key_from_name(p.name)
        if key is None:
            continue
        prev = best_by_key.get(key)
        if prev is None:
            best_by_key[key] = p
            continue
        # choose larger file as the representative
        try:
            if p.stat().st_size > prev.stat().st_size:
                best_by_key[key] = p
        except Exception:
            pass
        dropped += 1

    pop_dst = Path(dst) / "population"
    if not dry_run:
        pop_dst.mkdir(parents=True, exist_ok=True)
        # Clean previous staged windows to avoid stale leftovers when re-staging.
        for old in pop_dst.glob("*.csv"):
            try:
                old.unlink()
            except Exception:
                pass

    for key in sorted(best_by_key.keys()):
        src_p = best_by_key[key]
        link_name = f"population_{key}.csv"
        dst_p = pop_dst / link_name
        if dry_run:
            continue
        if mode == "copy":
            dst_p.write_bytes(src_p.read_bytes())
        else:
            # relative symlink for portability within a machine
            target = os.path.relpath(str(src_p), start=str(pop_dst))
            dst_p.symlink_to(target)

    meta = {
        "staged_from": str(src),
        "staged_to": str(dst),
        "mode": str(mode),
        "max_depth": int(max_depth),
        "require_population_in_path": int(bool(require_population_in_path)),
        "n_windows": int(len(best_by_key)),
        "n_candidates": int(len(cands)),
        "n_population_candidates": int(len(pop_cands)),
        "n_duplicates_dropped": int(dropped),
        "example_src_csv": str(example),
    }
    if not dry_run:
        (Path(dst) / "STAGED_FROM.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return StageResult(
        src=src,
        dst=Path(dst),
        slug=slug,
        n_windows=int(len(best_by_key)),
        n_duplicates_dropped=int(dropped),
        example_src_csv=str(example),
    )


def cli_main() -> None:
    p = argparse.ArgumentParser(description="将 archive 事件的 population CSV 归一化到 <dst>/population/*.csv（默认用软链接）。")
    p.add_argument("--src", type=Path, required=True, help="源事件目录（archive 内的某个事件文件夹）")
    p.add_argument("--dst", type=Path, required=True, help="目标 data_root（会创建 <dst>/population/）")
    p.add_argument("--mode", type=str, default="symlink", choices=["symlink", "copy"], help="归一化方式：symlink（默认）或 copy")
    p.add_argument("--max-depth", type=int, default=6, help="扫描 CSV 的最大相对深度（默认 6）")
    p.add_argument(
        "--require-population-in-path",
        action="store_true",
        help="只在路径包含 population 的目录下找 CSV（默认关闭；建议保持关闭以覆盖奇怪命名，但会做表头校验）",
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    res = stage_population(
        src=Path(args.src),
        dst=Path(args.dst),
        mode=str(args.mode),
        max_depth=int(args.max_depth),
        require_population_in_path=bool(args.require_population_in_path),
        dry_run=bool(args.dry_run),
    )
    print(
        json.dumps(
            {
                "slug": res.slug,
                "n_windows": res.n_windows,
                "n_duplicates_dropped": res.n_duplicates_dropped,
                "dst": str(res.dst),
                "example_src_csv": res.example_src_csv,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    cli_main()
