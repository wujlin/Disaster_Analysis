from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

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


def _svd_energy_frac1(s: np.ndarray) -> float:
    s = np.asarray(s, dtype=float)
    if s.size == 0 or not np.isfinite(s[0]):
        return float("nan")
    e = np.sum(np.square(s[np.isfinite(s)]))
    if not np.isfinite(e) or e <= 0:
        return float("nan")
    return float((s[0] ** 2) / e)


def _null_row_shuffle_sigma1_energy(dev: np.ndarray, rng: np.random.Generator) -> float:
    """
    Null model（行 permutation）：
    - 对每一行（固定 r）独立打乱列顺序（t 的对应关系被破坏）
    - 注意：仅仅“重排整行/整列（reorder rows/cols）”不会改变奇异值；这里必须打乱行内元素。
    """
    x = np.asarray(dev, dtype=float)
    if x.ndim != 2 or x.size == 0:
        return float("nan")
    n_r, n_t = x.shape
    y = np.empty_like(x)
    for i in range(n_r):
        y[i, :] = x[i, rng.permutation(n_t)]
    s = np.linalg.svd(y, full_matrices=False, compute_uv=False)
    return _svd_energy_frac1(s)


def _null_col_shuffle_sigma1_energy(dev: np.ndarray, rng: np.random.Generator) -> float:
    """
    Null model（列 permutation）：
    - 对每一列（固定 t）独立打乱行顺序（r 的对应关系被破坏）
    - 同上：必须打乱列内元素，而不是重排整列。
    """
    x = np.asarray(dev, dtype=float)
    if x.ndim != 2 or x.size == 0:
        return float("nan")
    n_r, n_t = x.shape
    y = np.empty_like(x)
    for j in range(n_t):
        y[:, j] = x[rng.permutation(n_r), j]
    s = np.linalg.svd(y, full_matrices=False, compute_uv=False)
    return _svd_energy_frac1(s)


def _null_stats(vals: list[float], obs: float) -> dict:
    a = np.asarray([v for v in vals if np.isfinite(v)], dtype=float)
    if a.size < 5 or not np.isfinite(obs):
        return {
            "null_n": int(a.size),
            "null_mean": float("nan"),
            "null_std": float("nan"),
            "null_p_ge_obs": float("nan"),
            "null_z": float("nan"),
        }
    mu = float(np.mean(a))
    sd = float(np.std(a, ddof=1)) if a.size >= 2 else float("nan")
    p_ge = float(np.mean(a >= float(obs)))
    z = float((float(obs) - mu) / sd) if np.isfinite(sd) and sd > 0 else float("nan")
    return {
        "null_n": int(a.size),
        "null_mean": mu,
        "null_std": sd,
        "null_p_ge_obs": p_ge,
        "null_z": z,
    }


def _discover_events(output_root: Path) -> list[EventRef]:
    root = Path(output_root)
    if not root.exists():
        return []
    out: list[EventRef] = []
    for d in sorted(root.iterdir(), key=lambda x: x.name):
        if not d.is_dir():
            continue
        if d.name.startswith("_"):
            continue
        p = d / "phi_heatmap" / "tables" / "phi_rt_long.csv"
        if p.exists():
            out.append(EventRef(output_root=root, slug=d.name))
    return out


def _load_metadata(output_root: Path, slug: str) -> tuple[str, str]:
    """
    返回 (name, event_type)。若 metadata.json 不存在，则用 slug 做兜底。
    """
    meta_p = Path(output_root) / slug / "metadata.json"
    if meta_p.exists():
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            name = str(meta.get("name") or slug)
            event_type = str(meta.get("event_type") or slug.split("_", 1)[0])
            return name, event_type
        except Exception:
            pass
    return slug, slug.split("_", 1)[0]


def _load_phi_rt_long(output_root: Path, slug: str) -> pd.DataFrame:
    p = Path(output_root) / slug / "phi_heatmap" / "tables" / "phi_rt_long.csv"
    if not p.exists():
        raise FileNotFoundError(f"未找到：{p}")
    df = pd.read_csv(p)
    need = {"hours_since_quake", "r_bin_km", "phi_aggregate", "phi_overlap"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise SystemExit(f"{p} 缺少列：{miss}")
    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df["r_bin_km"] = pd.to_numeric(df["r_bin_km"], errors="coerce")
    for c in ["phi_aggregate", "phi_overlap", "n_tiles_overlap"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["hours_since_quake", "r_bin_km"]).copy()
    return df


def _signal_strength_S(pivot: pd.DataFrame) -> float:
    m = pivot.to_numpy(dtype=float)
    dev = m - 1.0
    if dev.size == 0:
        return float("nan")
    return float(np.nanmax(np.abs(dev)))


def _near_tiles_mean(df: pd.DataFrame, *, near_r_max_km: float) -> float:
    if "n_tiles_overlap" not in df.columns:
        return float("nan")
    sub = df[pd.to_numeric(df["r_bin_km"], errors="coerce") <= float(near_r_max_km)].copy()
    if sub.empty:
        return float("nan")
    v = pd.to_numeric(sub["n_tiles_overlap"], errors="coerce").to_numpy(dtype=float)
    return float(np.nanmean(v)) if v.size else float("nan")


def _svd_metrics_from_pivot(*, pivot: pd.DataFrame, complete_only: bool) -> dict:
    m = pivot.to_numpy(dtype=float)
    dev = m - 1.0
    fill_value = 0.0

    nan_frac = float(np.isnan(dev).sum() / dev.size) if dev.size else float("nan")
    mode_used = "drop_complete" if bool(complete_only) else "fill_missing"

    dev_used = dev
    if bool(complete_only):
        ok_r = np.all(np.isfinite(dev), axis=1)
        ok_t = np.all(np.isfinite(dev), axis=0)
        dev_used = dev[np.where(ok_r)[0][:], :][:, np.where(ok_t)[0]]
        if dev_used.size == 0 or dev_used.shape[0] < 2 or dev_used.shape[1] < 2:
            mode_used = "fill_missing_fallback"
            dev_used = np.where(np.isfinite(dev), dev, float(fill_value))
    else:
        dev_used = np.where(np.isfinite(dev), dev, float(fill_value))

    u, s, vt = np.linalg.svd(dev_used, full_matrices=False)
    sigma1 = float(s[0]) if s.size else float("nan")
    frac1 = _svd_energy_frac1(s)
    denom = float(np.linalg.norm(dev_used))
    if dev_used.size and s.size and np.isfinite(denom) and denom > 0:
        rank1 = (s[0] * np.outer(u[:, 0], vt[0, :])).astype(float)
        rel_err = float(np.linalg.norm(dev_used - rank1) / denom)
    else:
        rel_err = float("nan")

    return {
        "n_r_bins_used": int(dev_used.shape[0]),
        "n_time_used": int(dev_used.shape[1]),
        "nan_frac_raw_matrix": float(nan_frac),
        "mode_used": str(mode_used),
        "sigma1": float(sigma1),
        "sigma1_energy_frac": float(frac1),
        "rank1_rel_error": float(rel_err),
        "dev_used": dev_used,
    }


def _parse_event_ref(s: str) -> EventRef:
    s = str(s).strip()
    if ":" not in s:
        raise SystemExit(f"--event 需要形如 <output_root>:<slug>，但收到：{s}")
    root_s, slug = s.split(":", 1)
    root = Path(root_s).expanduser()
    slug = str(slug).strip()
    if not slug:
        raise SystemExit(f"--event 的 slug 为空：{s}")
    return EventRef(output_root=root, slug=slug)


def run(
    *,
    roots: list[Path],
    events: list[EventRef],
    out_dir: Path,
    value_col: str,
    near_r_max_km: float,
    sigma1_threshold: float,
    null_n: int,
    null_seed: int | None,
) -> pd.DataFrame:
    out_dir = Path(out_dir)
    tabs = out_dir / "tables"
    figs = out_dir / "figures"
    _ensure_dir(tabs)
    _ensure_dir(figs)

    # collect event refs (later ones override earlier ones on same slug)
    refs: dict[str, EventRef] = {}
    sources: dict[str, str] = {}

    for root in roots:
        for ref in _discover_events(root):
            refs[ref.slug] = ref
            sources[ref.slug] = f"root:{str(root)}"
    for ref in events:
        refs[ref.slug] = ref
        sources[ref.slug] = f"event:{str(ref.output_root)}"

    if not refs:
        raise SystemExit("未发现任何可用事件（请检查 --root/--event 路径）")

    value_col = str(value_col).strip()
    if value_col not in {"phi_overlap", "phi_aggregate"}:
        raise SystemExit(f"value_col 不支持：{value_col}（仅支持 phi_overlap/phi_aggregate）")

    rows: list[dict] = []
    for slug in sorted(refs.keys()):
        ref = refs[slug]
        name, event_type = _load_metadata(ref.output_root, ref.slug)
        df = _load_phi_rt_long(ref.output_root, ref.slug)

        pivot = df.pivot_table(index="r_bin_km", columns="hours_since_quake", values=value_col, aggfunc="first")
        pivot = pivot.sort_index(axis=0).sort_index(axis=1)

        S = _signal_strength_S(pivot)
        near_tiles = _near_tiles_mean(df, near_r_max_km=float(near_r_max_km))

        m_complete = _svd_metrics_from_pivot(pivot=pivot, complete_only=True)
        m_fill = _svd_metrics_from_pivot(pivot=pivot, complete_only=False)

        null_row = {"null_n": 0, "null_mean": float("nan"), "null_std": float("nan"), "null_p_ge_obs": float("nan"), "null_z": float("nan")}
        null_col = {"null_n": 0, "null_mean": float("nan"), "null_std": float("nan"), "null_p_ge_obs": float("nan"), "null_z": float("nan")}
        if int(null_n) > 0:
            # per-event RNG（保证可复现，同时避免不同事件共享同一序列）
            seed0 = int(null_seed) if null_seed is not None else 0
            rng = np.random.default_rng(seed0 + (abs(hash(str(slug))) % 1_000_000))

            obs = float(m_complete["sigma1_energy_frac"])
            dev_used = np.asarray(m_complete["dev_used"], dtype=float)
            row_vals: list[float] = []
            col_vals: list[float] = []
            for _ in range(int(null_n)):
                row_vals.append(_null_row_shuffle_sigma1_energy(dev_used, rng))
                col_vals.append(_null_col_shuffle_sigma1_energy(dev_used, rng))
            null_row = _null_stats(row_vals, obs)
            null_col = _null_stats(col_vals, obs)

        rows.append(
            {
                "slug": str(slug),
                "name": str(name),
                "event_type": str(event_type),
                "output_root": str(ref.output_root),
                "source": str(sources.get(slug, "")),
                "value_col": str(value_col),
                "S_max_abs_delta": float(S),
                "near_r_max_km": float(near_r_max_km),
                "n_tiles_overlap_near_mean": float(near_tiles),
                "n_r_bins_raw": int(pivot.shape[0]),
                "n_time_raw": int(pivot.shape[1]),
                "svd_complete_sigma1_energy": float(m_complete["sigma1_energy_frac"]),
                "svd_complete_mode_used": str(m_complete["mode_used"]),
                "svd_complete_rank1_rel_error": float(m_complete["rank1_rel_error"]),
                "svd_fill_sigma1_energy": float(m_fill["sigma1_energy_frac"]),
                "svd_fill_mode_used": str(m_fill["mode_used"]),
                "svd_fill_rank1_rel_error": float(m_fill["rank1_rel_error"]),

                # null model calibration (complete matrix, δ=φ-1)
                "null_n": int(null_n),
                "null_seed": int(null_seed) if null_seed is not None else float("nan"),
                "null_row_shuffle_n": int(null_row["null_n"]),
                "null_row_shuffle_mean": float(null_row["null_mean"]),
                "null_row_shuffle_std": float(null_row["null_std"]),
                "null_row_shuffle_p_ge_obs": float(null_row["null_p_ge_obs"]),
                "null_row_shuffle_z": float(null_row["null_z"]),
                "null_col_shuffle_n": int(null_col["null_n"]),
                "null_col_shuffle_mean": float(null_col["null_mean"]),
                "null_col_shuffle_std": float(null_col["null_std"]),
                "null_col_shuffle_p_ge_obs": float(null_col["null_p_ge_obs"]),
                "null_col_shuffle_z": float(null_col["null_z"]),
            }
        )

    out_df = pd.DataFrame(rows).sort_values(["svd_complete_sigma1_energy", "S_max_abs_delta"], ascending=False, kind="stable")
    out_df.to_csv(tabs / "svd_separability_all.csv", index=False)

    thr = float(sigma1_threshold)
    n_total = int(out_df.shape[0])
    n_ge_thr = int(np.sum(pd.to_numeric(out_df["svd_complete_sigma1_energy"], errors="coerce") >= thr))
    summary = {
        "n_events": n_total,
        "sigma1_threshold": thr,
        "n_sigma1_ge_threshold": n_ge_thr,
        "frac_sigma1_ge_threshold": float(n_ge_thr / n_total) if n_total > 0 else float("nan"),
        "value_col": str(value_col),
        "near_r_max_km": float(near_r_max_km),
        "roots": [str(r) for r in roots],
        "events": [f"{str(e.output_root)}:{e.slug}" for e in events],
    }
    (out_dir / "metadata.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # plots (optional)
    try:
        from disaster import plot_style as ps  # type: ignore
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        return out_df

    with ps.paper_style():
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_HALF)
        x = pd.to_numeric(out_df["S_max_abs_delta"], errors="coerce").to_numpy(dtype=float)
        y = pd.to_numeric(out_df["svd_complete_sigma1_energy"], errors="coerce").to_numpy(dtype=float)
        ax.scatter(x, y, s=55, color=ps.OKABE_ITO["blue"], alpha=0.85, linewidths=0)
        ax.axhline(thr, color=ps.OKABE_ITO["vermillion"], lw=1.5, ls="--", label=f"thr={thr:.2f}")
        ax.set_xlabel(r"S = max |$\delta$| ($\delta=\phi-1$)")
        ax.set_ylabel(r"SVD separability: $\sigma_1^2/\sum_k \sigma_k^2$")
        ax.set_title("Separability vs signal strength")
        ax.legend(frameon=False, loc="lower right")
        ps.despine(ax)
        fig.tight_layout()
        fig.savefig(figs / "svd_separability_vs_S.png", dpi=220)
        fig.savefig(figs / "svd_separability_vs_S.pdf")
        plt.close(fig)

    with ps.paper_style():
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_HALF)
        y = pd.to_numeric(out_df["svd_complete_sigma1_energy"], errors="coerce").to_numpy(dtype=float)
        y = y[np.isfinite(y)]
        ax.hist(y, bins=12, color=ps.OKABE_ITO["gray"], alpha=0.85)
        ax.axvline(thr, color=ps.OKABE_ITO["vermillion"], lw=1.5, ls="--")
        ax.set_xlabel(r"$\sigma_1^2/\sum_k \sigma_k^2$ (complete)")
        ax.set_ylabel("#events")
        ax.set_title("SVD separability distribution")
        ps.despine(ax)
        fig.tight_layout()
        fig.savefig(figs / "svd_separability_hist.png", dpi=220)
        fig.savefig(figs / "svd_separability_hist.pdf")
        plt.close(fig)

    return out_df


def cli_main() -> None:
    p = argparse.ArgumentParser(description="跨事件：对 δ(r,t)=φ(r,t)-1 做 SVD 可分离性检验（rank-1 dominance）")
    p.add_argument(
        "--root",
        type=Path,
        action="append",
        default=None,
        help="扫描该目录下所有 <slug>/phi_heatmap/tables/phi_rt_long.csv（可重复；同名 slug 以后者覆盖前者）",
    )
    p.add_argument(
        "--event",
        type=str,
        action="append",
        default=None,
        help="额外指定单个事件：<output_root>:<slug>（可重复；同名 slug 覆盖）",
    )
    p.add_argument("--out-dir", type=Path, default=Path("outputs/cross_disaster_comparison/svd_separability"), help="输出目录")
    p.add_argument("--value-col", type=str, default="phi_overlap", choices=["phi_overlap", "phi_aggregate"])
    p.add_argument("--near-r-max-km", type=float, default=50.0)
    p.add_argument("--sigma1-threshold", type=float, default=0.80)
    p.add_argument("--null-n", type=int, default=0, help="null model permutation 次数（0=不计算；推荐 200 或 500）")
    p.add_argument("--null-seed", type=int, default=None, help="null model 随机种子（默认 0；不同事件会在此基础上加哈希偏移）")
    args = p.parse_args()

    if args.root:
        roots = [Path(x) for x in args.root]
    else:
        roots = [Path("outputs/_runs/trackpath/v3")]
        yagi_fix_root = Path("outputs/_runs/trackpath/v4_yagi_fix")
        if yagi_fix_root.exists():
            roots.append(yagi_fix_root)

    if args.event:
        events = [_parse_event_ref(x) for x in args.event]
    else:
        # 默认把 Turkey（径向口径）加入同一张表
        events = []
        default_turkey = Path("outputs") / "turkiye_earthquake_2023" / "phi_heatmap" / "tables" / "phi_rt_long.csv"
        if default_turkey.exists():
            events.append(EventRef(output_root=Path("outputs"), slug="turkiye_earthquake_2023"))

    run(
        roots=roots,
        events=events,
        out_dir=Path(args.out_dir),
        value_col=str(args.value_col),
        near_r_max_km=float(args.near_r_max_km),
        sigma1_threshold=float(args.sigma1_threshold),
        null_n=int(args.null_n),
        null_seed=(int(args.null_seed) if args.null_seed is not None else None),
    )


if __name__ == "__main__":
    cli_main()
