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

from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    output_root: Path
    slug: str
    out_dir: Path
    value_col: str = "phi_overlap"
    r_max_km: float = 200.0
    time_min: float | None = None
    time_max: float | None = None
    complete_only: bool = True


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _svd_energy_fracs(s: np.ndarray, k: int = 8) -> list[dict]:
    s = np.asarray(s, dtype=float)
    e = np.square(s)
    e_sum = float(np.sum(e)) if e.size else float("nan")
    rows: list[dict] = []
    cum = 0.0
    for i, sv in enumerate(s.tolist()[:k], start=1):
        ev = float(sv) ** 2
        cum += ev
        rows.append(
            {
                "k": int(i),
                "sigma": float(sv),
                "energy_frac": float(ev / e_sum) if np.isfinite(e_sum) and e_sum > 0 else float("nan"),
                "energy_cum": float(cum / e_sum) if np.isfinite(e_sum) and e_sum > 0 else float("nan"),
            }
        )
    return rows


def _load_phi_rt_long(output_root: Path, slug: str) -> pd.DataFrame:
    p = Path(output_root) / slug / "phi_heatmap" / "tables" / "phi_rt_long.csv"
    if not p.exists():
        raise FileNotFoundError(f"未找到：{p}")
    df = pd.read_csv(p)
    need = {"hours_since_quake", "r_bin_km", "phi_overlap", "phi_aggregate"}
    miss = sorted(need - set(df.columns))
    if miss:
        raise SystemExit(f"{p} 缺少列：{miss}")
    df["hours_since_quake"] = pd.to_numeric(df["hours_since_quake"], errors="coerce")
    df["r_bin_km"] = pd.to_numeric(df["r_bin_km"], errors="coerce")
    for c in ["phi_overlap", "phi_aggregate", "n_tiles_overlap"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["hours_since_quake", "r_bin_km"]).copy()
    return df


def _sign_fix(u: np.ndarray, vt: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """
    SVD 的符号有二义性。这里用“u_k 的和为正”做一个稳定化（纯展示用）。
    """
    u = np.asarray(u, dtype=float)
    vt = np.asarray(vt, dtype=float)
    if k < 0 or k >= u.shape[1]:
        return u, vt
    s = float(np.nansum(u[:, k]))
    if np.isfinite(s) and s < 0:
        u[:, k] *= -1.0
        vt[k, :] *= -1.0
    return u, vt


def run(cfg: Config) -> None:
    out_dir = Path(cfg.out_dir)
    tabs = out_dir / "tables"
    figs = out_dir / "figures"
    _ensure_dir(tabs)
    _ensure_dir(figs)

    df = _load_phi_rt_long(Path(cfg.output_root), str(cfg.slug))

    value_col = str(cfg.value_col).strip()
    if value_col not in {"phi_overlap", "phi_aggregate"}:
        raise SystemExit(f"value_col 不支持：{value_col}")

    sub = df.copy()
    if np.isfinite(float(cfg.r_max_km)):
        sub = sub[pd.to_numeric(sub["r_bin_km"], errors="coerce") <= float(cfg.r_max_km)].copy()
    if cfg.time_min is not None:
        sub = sub[pd.to_numeric(sub["hours_since_quake"], errors="coerce") >= float(cfg.time_min)].copy()
    if cfg.time_max is not None:
        sub = sub[pd.to_numeric(sub["hours_since_quake"], errors="coerce") <= float(cfg.time_max)].copy()
    if sub.empty:
        raise SystemExit("过滤后数据为空（请检查 r_max/time_min/time_max）")

    pivot = sub.pivot_table(index="r_bin_km", columns="hours_since_quake", values=value_col, aggfunc="first")
    pivot = pivot.sort_index(axis=0).sort_index(axis=1)
    r = pivot.index.to_numpy(dtype=float)
    t = pivot.columns.to_numpy(dtype=float)
    m = pivot.to_numpy(dtype=float)
    dev = m - 1.0

    nan_frac = float(np.isnan(dev).sum() / dev.size) if dev.size else float("nan")
    mode_used = "drop_complete" if bool(cfg.complete_only) else "fill_missing"
    r_used = r
    t_used = t
    dev_used = dev
    if bool(cfg.complete_only):
        ok_r = np.all(np.isfinite(dev), axis=1)
        ok_t = np.all(np.isfinite(dev), axis=0)
        dev_used = dev[np.where(ok_r)[0][:], :][:, np.where(ok_t)[0]]
        r_used = r[ok_r]
        t_used = t[ok_t]
        if dev_used.size == 0 or dev_used.shape[0] < 2 or dev_used.shape[1] < 2:
            mode_used = "fill_missing_fallback"
            dev_used = np.where(np.isfinite(dev), dev, 0.0)
            r_used = r
            t_used = t
    else:
        dev_used = np.where(np.isfinite(dev), dev, 0.0)

    u, s, vt = np.linalg.svd(dev_used, full_matrices=False)
    u, vt = _sign_fix(u, vt, 0)
    u, vt = _sign_fix(u, vt, 1)

    sigma1_energy = float((s[0] ** 2) / np.sum(np.square(s))) if s.size and np.sum(np.square(s)) > 0 else float("nan")
    sigma2_energy = float((s[1] ** 2) / np.sum(np.square(s))) if s.size >= 2 and np.sum(np.square(s)) > 0 else float("nan")

    # modes
    u1 = u[:, 0] if u.shape[1] >= 1 else np.array([], dtype=float)
    u2 = u[:, 1] if u.shape[1] >= 2 else np.array([], dtype=float)
    v1 = vt[0, :] if vt.shape[0] >= 1 else np.array([], dtype=float)
    v2 = vt[1, :] if vt.shape[0] >= 2 else np.array([], dtype=float)
    g1 = float(s[0]) * v1 if s.size >= 1 else np.array([], dtype=float)
    g2 = float(s[1]) * v2 if s.size >= 2 else np.array([], dtype=float)

    pd.DataFrame({"r_bin_km": r_used, "u1": u1, "u2": u2}).to_csv(tabs / "u_modes.csv", index=False)
    pd.DataFrame({"hours_since_quake": t_used, "v1": v1, "v2": v2, "g1": g1, "g2": g2}).to_csv(tabs / "v_modes.csv", index=False)
    pd.DataFrame(_svd_energy_fracs(s, k=12)).to_csv(tabs / "svd_spectrum.csv", index=False)

    meta = {
        "slug": str(cfg.slug),
        "output_root": str(cfg.output_root),
        "value_col": value_col,
        "r_max_km": float(cfg.r_max_km),
        "time_min": cfg.time_min,
        "time_max": cfg.time_max,
        "complete_only": int(bool(cfg.complete_only)),
        "mode_used": str(mode_used),
        "shape_raw": [int(dev.shape[0]), int(dev.shape[1])],
        "shape_used": [int(dev_used.shape[0]), int(dev_used.shape[1])],
        "nan_frac_raw_matrix": float(nan_frac),
        "sigma1_energy": float(sigma1_energy),
        "sigma2_energy": float(sigma2_energy),
        "sigma1": float(s[0]) if s.size else float("nan"),
        "sigma2": float(s[1]) if s.size >= 2 else float("nan"),
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # figures (optional)
    try:
        from disaster import plot_style as ps  # type: ignore
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        return

    with ps.paper_style():
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_HALF)
        if r_used.size:
            ax.plot(r_used, u1, color=ps.OKABE_ITO["blue"], lw=2.0, label="u1(r)")
            ax.plot(r_used, u2, color=ps.OKABE_ITO["vermillion"], lw=2.0, label="u2(r)")
        ax.set_xlabel("r (km)")
        ax.set_ylabel("u_k")
        ax.set_title(f"{cfg.slug}: spatial modes (r_max={float(cfg.r_max_km):.0f}km)")
        ax.legend(frameon=False, fontsize=8)
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, figs / "u_modes.png")
        plt.close(fig)

    with ps.paper_style():
        fig, ax = plt.subplots(figsize=ps.FIGSIZE_HALF)
        if t_used.size:
            ax.plot(t_used, g1, color=ps.OKABE_ITO["blue"], lw=2.0, marker="o", ms=4, label="g1(t)=σ1·v1(t)")
            ax.plot(t_used, g2, color=ps.OKABE_ITO["vermillion"], lw=2.0, marker="o", ms=4, label="g2(t)=σ2·v2(t)")
        ax.axhline(0, color=ps.OKABE_ITO["gray"], lw=1.0, ls="--", alpha=0.7)
        ax.set_xlabel("t (hours since t0)")
        ax.set_ylabel("g_k")
        ax.set_title(f"{cfg.slug}: temporal modes (σ1_energy={sigma1_energy:.3f})")
        ax.legend(frameon=False, fontsize=7)
        ps.despine(ax)
        fig.tight_layout()
        save_png_and_pdf(ps, fig, figs / "g_modes.png")
        plt.close(fig)


def cli_main() -> None:
    p = argparse.ArgumentParser(description="Q2: 可视化 SVD 的 u_k(r), v_k(t)（重点看 σ2）")
    p.add_argument("--output-root", type=Path, required=True)
    p.add_argument("--slug", type=str, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--value-col", type=str, default="phi_overlap", choices=["phi_overlap", "phi_aggregate"])
    p.add_argument("--r-max-km", type=float, default=200.0)
    p.add_argument("--time-min", type=float, default=None)
    p.add_argument("--time-max", type=float, default=None)
    p.add_argument("--complete-only", action="store_true")
    args = p.parse_args()

    run(
        Config(
            output_root=Path(args.output_root),
            slug=str(args.slug),
            out_dir=Path(args.out_dir),
            value_col=str(args.value_col),
            r_max_km=float(args.r_max_km),
            time_min=(float(args.time_min) if args.time_min is not None else None),
            time_max=(float(args.time_max) if args.time_max is not None else None),
            complete_only=bool(args.complete_only),
        )
    )


if __name__ == "__main__":
    cli_main()

