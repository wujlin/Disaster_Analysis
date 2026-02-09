from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e


@dataclass(frozen=True)
class EventRef:
    output_root: Path
    slug: str


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _parse_event_ref(s: str) -> EventRef:
    s = str(s).strip()
    if ":" not in s:
        raise SystemExit(f"--event 格式错误：{s}（期望 <output_root>:<slug>）")
    root, slug = s.split(":", 1)
    root_p = Path(root)
    if not root_p.exists():
        raise SystemExit(f"--event output_root 不存在：{root_p}")
    slug = slug.strip()
    if not slug:
        raise SystemExit(f"--event slug 为空：{s}")
    return EventRef(output_root=root_p, slug=slug)


def _discover_events(output_root: Path) -> list[EventRef]:
    root = Path(output_root)
    if not root.exists():
        return []
    out: list[EventRef] = []
    for d in sorted(root.iterdir(), key=lambda x: x.name):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        # Use center_by_window.csv as the "processed windows" signal.
        p = d / "phi_heatmap" / "tables" / "center_by_window.csv"
        if p.exists():
            out.append(EventRef(output_root=root, slug=d.name))
    return out


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ts(s: object) -> pd.Timestamp | None:
    if s is None:
        return None
    try:
        t = pd.Timestamp(str(s))
        return t if pd.notna(t) else None
    except Exception:
        return None


def _dt_hours(a: pd.Timestamp | None, b: pd.Timestamp | None) -> float:
    if a is None or b is None:
        return float("nan")
    return float((a - b).total_seconds() / 3600.0)


def run(*, roots: list[Path], events: list[EventRef], out_dir: Path) -> None:
    out_dir = Path(out_dir)
    tabs = out_dir / "tables"
    _ensure_dir(tabs)

    refs: dict[str, EventRef] = {}
    for r in roots:
        for ref in _discover_events(r):
            refs[ref.slug] = ref
    for ref in events:
        refs[ref.slug] = ref
    if not refs:
        raise SystemExit("未发现任何可用事件（请检查 --root/--event 或 svd_separability 的 metadata.json）")

    rows: list[dict] = []
    for slug in sorted(refs.keys()):
        ref = refs[slug]
        meta_p = Path(ref.output_root) / slug / "metadata.json"
        meta = _read_json(meta_p) if meta_p.exists() else {}

        cbw_p = Path(ref.output_root) / slug / "phi_heatmap" / "tables" / "center_by_window.csv"
        cbw = pd.read_csv(cbw_p) if cbw_p.exists() else pd.DataFrame()
        if not cbw.empty and "window_start_pt" in cbw.columns:
            w = pd.to_datetime(cbw["window_start_pt"], errors="coerce")
            first_heatmap = pd.Timestamp(w.min()) if w.notna().any() else None
            last_heatmap = pd.Timestamp(w.max()) if w.notna().any() else None
            n_heatmap_windows = int(len(cbw))
        else:
            first_heatmap = None
            last_heatmap = None
            n_heatmap_windows = 0

        t0_pt = _ts(meta.get("t0_pt"))
        first_pop = _ts(meta.get("first_population_window_pt"))
        anchor_pt = _ts(meta.get("track_anchor_pt"))
        t0_snap_pt = _ts(meta.get("t0_snap_window_pt"))

        row = {
            "slug": str(slug),
            "event_type": str(meta.get("event_type", "")),
            "output_root": str(ref.output_root),
            "data_root": str(meta.get("data_root", "")),
            "only_hour_pt": meta.get("only_hour_pt"),
            "t0_pt": str(t0_pt) if t0_pt is not None else "",
            "t0_method": str(meta.get("t0_method", "")),
            "t0_snap_window_pt": str(t0_snap_pt) if t0_snap_pt is not None else "",
            "t0_snap_delta_hours": meta.get("t0_snap_delta_hours", float("nan")),
            "first_population_window_pt": str(first_pop) if first_pop is not None else "",
            "first_heatmap_window_pt": str(first_heatmap) if first_heatmap is not None else "",
            "last_heatmap_window_pt": str(last_heatmap) if last_heatmap is not None else "",
            "n_heatmap_windows": int(n_heatmap_windows),
            "track_anchor_pt": str(anchor_pt) if anchor_pt is not None else "",
            "track_anchor_status": str(meta.get("track_anchor_status", "")),
            "track_anchor_method": str(meta.get("track_anchor_method", "")),
            "track_anchor_to_t0_hours": meta.get("track_anchor_to_t0_hours", float("nan")),
            "t0_minus_anchor_hours": _dt_hours(t0_pt, anchor_pt),
            "first_heatmap_minus_anchor_hours": _dt_hours(first_heatmap, anchor_pt),
            "t0_minus_first_heatmap_hours": _dt_hours(t0_pt, first_heatmap),
            "first_pop_minus_anchor_hours": _dt_hours(first_pop, anchor_pt),
            "t0_minus_first_pop_hours": _dt_hours(t0_pt, first_pop),
            "first_heatmap_minus_first_pop_hours": _dt_hours(first_heatmap, first_pop),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        t0_sort = pd.to_datetime(df["t0_pt"], errors="coerce")
        df.insert(0, "_t0_sort", t0_sort)
        df = df.sort_values(["_t0_sort", "slug"], kind="stable").drop(columns=["_t0_sort"])

    out_csv = tabs / "time_alignment_by_event.csv"
    df.to_csv(out_csv, index=False)

    meta = {"n_events": int(len(df)), "roots": [str(p) for p in roots], "events": [f"{e.output_root}:{e.slug}" for e in events]}
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_default_roots_and_events() -> tuple[list[Path], list[EventRef]]:
    meta_p = Path("outputs/cross_disaster_comparison/svd_separability/metadata.json")
    if not meta_p.exists():
        return [Path("outputs/_runs/trackpath/v3"), Path("outputs/_runs/trackpath/v4_yagi_fix")], [EventRef(Path("outputs"), "turkiye_earthquake_2023")]
    meta = _read_json(meta_p)
    roots = [Path(p) for p in meta.get("roots", []) if str(p).strip()]
    events = []
    for s in meta.get("events", []) or []:
        try:
            events.append(_parse_event_ref(str(s)))
        except SystemExit:
            continue
    return roots, events


def cli_main() -> None:
    parser = argparse.ArgumentParser(description="输出每个事件的 t0/首窗/landfall(anchor) 对齐表（不做解释）")
    parser.add_argument("--root", type=Path, action="append", default=[], help="扫描的输出根目录（可多次提供）")
    parser.add_argument("--event", type=str, action="append", default=[], help="额外事件：<output_root>:<slug>")
    parser.add_argument("--out-dir", type=Path, default=Path("outputs/cross_disaster_comparison/time_alignment"), help="输出目录")
    args = parser.parse_args()

    if args.root:
        roots = [Path(p) for p in args.root]
        events = [_parse_event_ref(s) for s in (args.event or [])]
    else:
        roots, events = _load_default_roots_and_events()
        if args.event:
            events = events + [_parse_event_ref(s) for s in args.event]

    run(roots=roots, events=events, out_dir=Path(args.out_dir))


if __name__ == "__main__":
    cli_main()
