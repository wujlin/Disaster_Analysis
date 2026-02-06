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

from disaster.geo import haversine_km
from disaster.movement_io import load_movement_file
from disaster.population_io import parse_window_start_pt, resolve_subdir
from disaster.viz import save_png_and_pdf


@dataclass(frozen=True)
class Config:
    """
    灾后人口流动方向性系统分析（无预设距离分箱，核心变量为 Δr 与 d_move）。
    """

    data_root: Path
    output_dir: Path

    center_lat: float
    center_lon: float
    t0_pt: pd.Timestamp
    only_hour_pt: int = 8

    min_hours: float = -16.0
    max_hours: float = 832.0

    # 固定展示用的代表性时间点（会选最近的窗口）
    snapshot_hours: tuple[float, ...] = (8.0, 40.0, 168.0)

    # Part2: d_move vs Δr heatmap
    d_move_max_km: float = 150.0
    delta_r_abs_max_km: float = 100.0
    n_bins_d_move: int = 60
    n_bins_delta_r: int = 80

    # Part3: sliding window on r_start
    r_start_min_km: float = 0.0
    r_start_max_km: float = 500.0
    sliding_window_km: float = 20.0
    sliding_step_km: float = 10.0

    # Part5: long-range fraction
    long_move_km: float = 50.0

    # OD 特征输出
    write_od_features: bool = True
    od_format: str = "parquet"  # parquet | csv

    # 图/表输出（可用于快速 smoke test）
    skip_figures: bool = False
    skip_tables: bool = False


@dataclass(frozen=True)
class OutputDirs:
    root: Path
    figures: Path
    tables: Path


def _output_dirs(root: Path) -> OutputDirs:
    return OutputDirs(root=root, figures=root / "figures", tables=root / "tables")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _try_load_metadata_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _parse_movement_window_start(path: Path) -> pd.Timestamp:
    """
    Movement 文件名通常与 population 一致：<id>_YYYY-MM-DD_HHMM.csv
    若解析失败，则回退读取 date_time 首行。
    """

    try:
        return pd.Timestamp(parse_window_start_pt(path))
    except Exception:
        head = pd.read_csv(path, usecols=lambda c: c == "date_time", na_values=["\\N", ""], nrows=1)
        if "date_time" not in head.columns or head.empty:
            raise ValueError(f"无法解析窗口时间（文件名与 date_time 均失败）：{path.name}")
        ts = pd.to_datetime(head["date_time"].iloc[0], errors="coerce")
        if pd.isna(ts):
            raise ValueError(f"无法解析 date_time：{path.name}")
        return pd.Timestamp(ts)


def _list_movement_windows(cfg: Config) -> list[dict]:
    mov_dir = resolve_subdir(Path(cfg.data_root), "movement")

    files = sorted(mov_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"目录为空：{mov_dir}")

    rows: list[dict] = []
    for path in files:
        ts = _parse_movement_window_start(path)
        if int(ts.hour) != int(cfg.only_hour_pt):
            continue
        hs = float((pd.Timestamp(ts) - pd.Timestamp(cfg.t0_pt)).total_seconds() / 3600.0)
        if hs < float(cfg.min_hours) or hs > float(cfg.max_hours):
            continue
        rows.append({"path": path, "window_start_pt": pd.Timestamp(ts), "hours_since_quake": hs})

    rows = sorted(rows, key=lambda r: float(r["hours_since_quake"]))
    if not rows:
        raise FileNotFoundError(f"未找到符合条件的 movement 窗口：hour={cfg.only_hour_pt}, t∈[{cfg.min_hours},{cfg.max_hours}]")
    return rows


def _pick_nearest_windows(windows: list[dict], targets_hours: tuple[float, ...]) -> list[dict]:
    """
    为每个 target_hours 选择最近窗口；允许多个 target 命中同一窗口（不去重）。
    返回的每个元素都附带 target_hours。
    """

    out: list[dict] = []
    if not windows:
        return out
    hs_all = np.array([float(w["hours_since_quake"]) for w in windows], dtype=float)
    for th in targets_hours:
        idx = int(np.argmin(np.abs(hs_all - float(th))))
        picked = dict(windows[idx])
        picked["target_hours"] = float(th)
        out.append(picked)
    return out


def _safe_cos(v_lat: np.ndarray, v_lon: np.ndarray, r_lat: np.ndarray, r_lon: np.ndarray) -> np.ndarray:
    dot = v_lat * r_lat + v_lon * r_lon
    v_norm = np.sqrt(v_lat * v_lat + v_lon * v_lon)
    r_norm = np.sqrt(r_lat * r_lat + r_lon * r_lon)
    denom = v_norm * r_norm
    cos = np.full(dot.shape, np.nan, dtype=float)
    ok = np.isfinite(dot) & np.isfinite(denom) & (denom > 0)
    cos[ok] = dot[ok] / denom[ok]
    return np.clip(cos, -1.0, 1.0)


def _compute_od_features(df_mov: pd.DataFrame, cfg: Config, *, window_start_pt: pd.Timestamp, hours_since_quake: float) -> pd.DataFrame:
    """
    将单窗口 movement 表转换为 OD 特征表（仅保留分析所需的原生变量）。
    """

    slat = pd.to_numeric(df_mov.get("start_lat", np.nan), errors="coerce").to_numpy(dtype=float)
    slon = pd.to_numeric(df_mov.get("start_lon", np.nan), errors="coerce").to_numpy(dtype=float)
    elat = pd.to_numeric(df_mov.get("end_lat", np.nan), errors="coerce").to_numpy(dtype=float)
    elon = pd.to_numeric(df_mov.get("end_lon", np.nan), errors="coerce").to_numpy(dtype=float)

    nb = pd.to_numeric(df_mov.get("n_baseline", np.nan), errors="coerce").to_numpy(dtype=float)
    nc = pd.to_numeric(df_mov.get("n_crisis", np.nan), errors="coerce").to_numpy(dtype=float)
    d_move = pd.to_numeric(df_mov.get("length_km", np.nan), errors="coerce").to_numpy(dtype=float)

    keep = np.isfinite(slat) & np.isfinite(slon) & np.isfinite(elat) & np.isfinite(elon) & np.isfinite(d_move)
    keep = keep & (np.isfinite(nb) | np.isfinite(nc))
    if not np.any(keep):
        return pd.DataFrame(
            {
                "window_start_pt": pd.to_datetime([], utc=False),
                "hours_since_quake": np.array([], dtype=float),
                "r_start_km": np.array([], dtype=float),
                "r_end_km": np.array([], dtype=float),
                "delta_r_km": np.array([], dtype=float),
                "d_move_km": np.array([], dtype=float),
                "cos_alpha": np.array([], dtype=float),
                "n_crisis": np.array([], dtype=float),
                "n_baseline": np.array([], dtype=float),
            }
        )

    slat = slat[keep]
    slon = slon[keep]
    elat = elat[keep]
    elon = elon[keep]
    nb = nb[keep]
    nc = nc[keep]
    d_move = d_move[keep]

    r_start = haversine_km(slat, slon, float(cfg.center_lat), float(cfg.center_lon))
    r_end = haversine_km(elat, elon, float(cfg.center_lat), float(cfg.center_lon))
    delta_r = r_end - r_start

    v_lat = elat - slat
    v_lon = elon - slon
    rr_lat = slat - float(cfg.center_lat)
    rr_lon = slon - float(cfg.center_lon)
    cos_alpha = _safe_cos(v_lat, v_lon, rr_lat, rr_lon)

    out = pd.DataFrame(
        {
            "window_start_pt": pd.Timestamp(window_start_pt),
            "hours_since_quake": float(hours_since_quake),
            "r_start_km": r_start.astype(float),
            "r_end_km": r_end.astype(float),
            "delta_r_km": delta_r.astype(float),
            "d_move_km": d_move.astype(float),
            "cos_alpha": cos_alpha.astype(float),
            "n_crisis": nc.astype(float),
            "n_baseline": nb.astype(float),
        }
    )
    out = out[np.isfinite(out["r_start_km"]) & np.isfinite(out["r_end_km"]) & np.isfinite(out["delta_r_km"]) & np.isfinite(out["d_move_km"])].copy()
    return out


class _OdFeatureWriter:
    def __init__(self, path: Path, *, fmt: str) -> None:
        self.path = Path(path)
        self.fmt = str(fmt)
        self._writer = None
        self._csv_header_written = False

    def write(self, df: pd.DataFrame) -> None:
        if df.empty:
            return
        if self.fmt == "csv":
            self._write_csv(df)
        elif self.fmt == "parquet":
            self._write_parquet(df)
        else:
            raise ValueError(f"不支持的 od_format：{self.fmt}（仅支持 parquet/csv）")

    def close(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception:
                pass
        self._writer = None

    def _write_csv(self, df: pd.DataFrame) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if not self._csv_header_written else "a"
        df.to_csv(self.path, mode=mode, header=not self._csv_header_written, index=False)
        self._csv_header_written = True

    def _write_parquet(self, df: pd.DataFrame) -> None:
        try:
            import pyarrow as pa  # type: ignore
            import pyarrow.parquet as pq  # type: ignore
        except ModuleNotFoundError as e:
            raise SystemExit("缺少依赖：pyarrow（写 parquet 需要）。请在 conda 环境中安装 `pyarrow`。") from e

        self.path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df, preserve_index=False)
        if self._writer is None:
            # 选择兼容性更好的压缩（多数环境默认支持）
            self._writer = pq.ParquetWriter(str(self.path), table.schema, compression="snappy")
        self._writer.write_table(table)


def _weighted_quantile(x: np.ndarray, w: np.ndarray, q: float) -> float:
    """
    加权分位数（q∈[0,1]），用于“以流量为权重”的典型尺度估计。
    """

    x = np.asarray(x, dtype=float)
    w = np.asarray(w, dtype=float)
    ok = np.isfinite(x) & np.isfinite(w) & (w > 0)
    if not np.any(ok):
        return float("nan")
    x = x[ok]
    w = w[ok]
    order = np.argsort(x, kind="mergesort")
    x = x[order]
    w = w[order]
    cw = np.cumsum(w)
    total = float(cw[-1])
    if not np.isfinite(total) or total <= 0:
        return float("nan")
    t = float(q) * total
    idx = int(np.searchsorted(cw, t, side="left"))
    idx = max(0, min(idx, int(x.size) - 1))
    return float(x[idx])


def _weighted_mean(x: np.ndarray, w: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    w = np.asarray(w, dtype=float)
    ok = np.isfinite(x) & np.isfinite(w) & (w > 0)
    if not np.any(ok):
        return float("nan")
    return float(np.sum(x[ok] * w[ok]) / np.sum(w[ok]))


def _weighted_std(x: np.ndarray, w: np.ndarray) -> float:
    """
    加权标准差（population-weighted），用于 σ_{Δr}。
    """

    x = np.asarray(x, dtype=float)
    w = np.asarray(w, dtype=float)
    ok = np.isfinite(x) & np.isfinite(w) & (w > 0)
    if not np.any(ok):
        return float("nan")
    ww = w[ok]
    xx = x[ok]
    mu = float(np.sum(xx * ww) / np.sum(ww))
    m2 = float(np.sum((xx * xx) * ww) / np.sum(ww))
    var = max(0.0, m2 - mu * mu)
    return float(np.sqrt(var))


def _sliding_weighted_mean_delta_r(
    r_start: np.ndarray,
    delta_r: np.ndarray,
    w: np.ndarray,
    *,
    r_min: float,
    r_max: float,
    window_km: float,
    step_km: float,
) -> pd.DataFrame:
    """
    用滑动窗口在 r_start 上估计 ⟨Δr⟩_w(r)：
    - 窗口宽度 window_km
    - 步长 step_km
    实现方式：对 r_start 排序 + 前缀和 + searchsorted（避免 O(N×M) 扫描）。
    """

    r_start = np.asarray(r_start, dtype=float)
    delta_r = np.asarray(delta_r, dtype=float)
    w = np.asarray(w, dtype=float)

    ok = np.isfinite(r_start) & np.isfinite(delta_r) & np.isfinite(w) & (w > 0)
    if not np.any(ok):
        return pd.DataFrame({"r_left_km": [], "r_right_km": [], "r_center_km": [], "mean_delta_r_w": [], "sum_w": [], "n_od": []})

    r = r_start[ok]
    dr = delta_r[ok]
    ww = w[ok]

    order = np.argsort(r, kind="mergesort")
    r = r[order]
    dr = dr[order]
    ww = ww[order]

    cw = np.concatenate([[0.0], np.cumsum(ww)])
    cwdr = np.concatenate([[0.0], np.cumsum(ww * dr)])

    window = float(window_km)
    step = float(step_km)
    lefts = np.arange(float(r_min), float(r_max) - window + 1e-9, step, dtype=float)

    rows: list[dict] = []
    for left in lefts:
        right = float(left + window)
        i0 = int(np.searchsorted(r, left, side="left"))
        i1 = int(np.searchsorted(r, right, side="left"))
        sum_w = float(cw[i1] - cw[i0])
        sum_wdr = float(cwdr[i1] - cwdr[i0])
        mean = (sum_wdr / sum_w) if sum_w > 0 else float("nan")
        rows.append(
            {
                "r_left_km": float(left),
                "r_right_km": float(right),
                "r_center_km": float(left + window / 2.0),
                "mean_delta_r_w": float(mean),
                "sum_w": float(sum_w),
                "n_od": int(i1 - i0),
            }
        )
    return pd.DataFrame(rows)


def _plot_dmove_vs_deltar(
    snapshots: list[dict],
    feats_by_path: dict[str, pd.DataFrame],
    cfg: Config,
    *,
    out_path: Path,
    plot: bool = True,
) -> pd.DataFrame:
    """
    Part2：P(d_move, Δr) 2D 直方图（n_crisis 加权）。
    返回用于表格的统计行（每个 snapshot 一行）。
    """

    x_edges = np.linspace(0.0, float(cfg.d_move_max_km), int(cfg.n_bins_d_move) + 1, dtype=float)
    y_edges = np.linspace(-float(cfg.delta_r_abs_max_km), float(cfg.delta_r_abs_max_km), int(cfg.n_bins_delta_r) + 1, dtype=float)

    panels = int(len(snapshots))
    if panels <= 0:
        return pd.DataFrame([])

    stats_rows: list[dict] = []
    h_list: list[np.ndarray] = []

    for s in snapshots:
        path = str(s["path"])
        df = feats_by_path.get(path)
        if df is None or df.empty:
            h_list.append(np.zeros((int(cfg.n_bins_d_move), int(cfg.n_bins_delta_r)), dtype=float))
            stats_rows.append(
                {
                    "target_hours": float(s["target_hours"]),
                    "window_start_pt": str(s["window_start_pt"]),
                    "hours_since_quake": float(s["hours_since_quake"]),
                    "n_od": 0,
                    "total_flow_crisis": 0.0,
                    "median_d_move_w": float("nan"),
                    "mean_delta_r_w": float("nan"),
                }
            )
            continue

        d_move = df["d_move_km"].to_numpy(dtype=float)
        delta_r = df["delta_r_km"].to_numpy(dtype=float)
        w = df["n_crisis"].to_numpy(dtype=float)
        ok = np.isfinite(d_move) & np.isfinite(delta_r) & np.isfinite(w) & (w > 0)
        d_move = d_move[ok]
        delta_r = delta_r[ok]
        w = w[ok]

        h, _, _ = np.histogram2d(d_move, delta_r, bins=[x_edges, y_edges], weights=w)
        h_list.append(h.astype(float))

        stats_rows.append(
            {
                "target_hours": float(s["target_hours"]),
                "window_start_pt": str(s["window_start_pt"]),
                "hours_since_quake": float(s["hours_since_quake"]),
                "n_od": int(d_move.size),
                "total_flow_crisis": float(np.sum(w)),
                "median_d_move_w": _weighted_quantile(d_move, w, 0.5),
                "mean_delta_r_w": _weighted_mean(delta_r, w),
            }
        )

    # 统一色标：使用 log10(1+H)
    log_h = [np.log10(1.0 + hh) for hh in h_list]
    if plot:
        try:
            from disaster import plot_style as ps  # type: ignore
        except ModuleNotFoundError as e:
            if e.name == "matplotlib":
                raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
            raise

        vmax = float(np.nanmax([np.nanmax(x) for x in log_h])) if log_h else 1.0
        with ps.paper_style():
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, panels, figsize=(ps.FIGSIZE_FULL[0] * 1.55, ps.FIGSIZE_FULL[1] * 0.95), sharey=True)
            if panels == 1:
                axes = [axes]

            for ax, s, img in zip(axes, snapshots, log_h, strict=False):
                im = ax.imshow(
                    img.T,
                    origin="lower",
                    aspect="auto",
                    extent=[float(x_edges[0]), float(x_edges[-1]), float(y_edges[0]), float(y_edges[-1])],
                    cmap="magma",
                    vmin=0.0,
                    vmax=vmax,
                )
                ax.axhline(0.0, color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.7)
                ax.set_xlabel(r"$d_{\mathrm{move}}$ (km)")
                ax.set_title(f"t≈{float(s['target_hours']):g}h (picked {float(s['hours_since_quake']):g}h)")
                ps.despine(ax)

            axes[0].set_ylabel(r"$\Delta r = r_{\mathrm{end}} - r_{\mathrm{start}}$ (km)")

            cb = fig.colorbar(im, ax=axes, shrink=0.86)
            cb.set_label(r"$\log_{10}(1 + \sum w)$")

            fig.tight_layout()
            save_png_and_pdf(ps, fig, out_path)
            plt.close(fig)

    return pd.DataFrame(stats_rows)


def _plot_rstart_vs_rend(
    snapshots: list[dict],
    feats_by_path: dict[str, pd.DataFrame],
    cfg: Config,
    *,
    out_path: Path,
    plot: bool = True,
) -> pd.DataFrame:
    """
    Part4：r_start vs r_end（hexbin，n_crisis 加权），并输出 σ_{Δr}。
    """

    panels = int(len(snapshots))
    if panels <= 0:
        return pd.DataFrame([])

    stats_rows: list[dict] = []

    # 先统计（不依赖 matplotlib）
    for s in snapshots:
        path = str(s["path"])
        df = feats_by_path.get(path)
        if df is None or df.empty:
            stats_rows.append(
                {
                    "target_hours": float(s["target_hours"]),
                    "window_start_pt": str(s["window_start_pt"]),
                    "hours_since_quake": float(s["hours_since_quake"]),
                    "n_od": 0,
                    "total_flow_crisis": 0.0,
                    "mean_delta_r_w": float("nan"),
                    "sigma_delta_r_w": float("nan"),
                }
            )
            continue

        dr = df["delta_r_km"].to_numpy(dtype=float)
        w = df["n_crisis"].to_numpy(dtype=float)
        ok = np.isfinite(dr) & np.isfinite(w) & (w > 0)
        stats_rows.append(
            {
                "target_hours": float(s["target_hours"]),
                "window_start_pt": str(s["window_start_pt"]),
                "hours_since_quake": float(s["hours_since_quake"]),
                "n_od": int(np.sum(ok)),
                "total_flow_crisis": float(np.sum(w[ok])) if np.any(ok) else 0.0,
                "mean_delta_r_w": _weighted_mean(dr, w),
                "sigma_delta_r_w": _weighted_std(dr, w),
            }
        )

    if plot:
        try:
            from disaster import plot_style as ps  # type: ignore
        except ModuleNotFoundError as e:
            if e.name == "matplotlib":
                raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
            raise

        with ps.paper_style():
            import matplotlib.pyplot as plt

            fig, axes = plt.subplots(1, panels, figsize=(ps.FIGSIZE_FULL[0] * 1.55, ps.FIGSIZE_FULL[1] * 0.95), sharey=True, sharex=True)
            if panels == 1:
                axes = [axes]

            hb = None
            for ax, s in zip(axes, snapshots, strict=False):
                path = str(s["path"])
                df = feats_by_path.get(path)
                if df is None or df.empty:
                    ax.set_title(f"t≈{float(s['target_hours']):g}h (empty)")
                    continue

                r0 = df["r_start_km"].to_numpy(dtype=float)
                r1 = df["r_end_km"].to_numpy(dtype=float)
                w = df["n_crisis"].to_numpy(dtype=float)
                ok = np.isfinite(r0) & np.isfinite(r1) & np.isfinite(w) & (w > 0)
                r0 = r0[ok]
                r1 = r1[ok]
                w = w[ok]

                hb = ax.hexbin(
                    r0,
                    r1,
                    C=w,
                    reduce_C_function=np.sum,
                    gridsize=55,
                    mincnt=1,
                    cmap="viridis",
                    linewidths=0.0,
                )

                lim = float(cfg.r_start_max_km)
                ax.plot([0, lim], [0, lim], color=ps.OKABE_ITO["gray"], linestyle="--", linewidth=1.0, alpha=0.8)
                ax.plot([0, lim], [20, lim + 20], color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.0, alpha=0.7)
                ax.plot([0, lim], [-20, lim - 20], color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.0, alpha=0.7)

                ax.set_title(f"t≈{float(s['target_hours']):g}h (picked {float(s['hours_since_quake']):g}h)")
                ax.set_xlabel(r"$r_{\mathrm{start}}$ (km)")
                ps.despine(ax)

            axes[0].set_ylabel(r"$r_{\mathrm{end}}$ (km)")
            if hb is not None:
                cb = fig.colorbar(hb, ax=axes, shrink=0.86)
                cb.set_label(r"$\sum w$ (hexbin)")

            fig.tight_layout()
            save_png_and_pdf(ps, fig, out_path)
            plt.close(fig)

    return pd.DataFrame(stats_rows)


def _plot_delta_r_spacetime(
    mat: pd.DataFrame,
    cfg: Config,
    *,
    out_path: Path,
) -> None:
    """
    Part3：⟨Δr⟩_w(r,t) 热力图（RdBu_r）。
    """

    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    if mat.empty:
        return

    # pivot to 2D matrix
    mat = mat.copy()
    mat["hours_since_quake"] = pd.to_numeric(mat["hours_since_quake"], errors="coerce")
    mat["r_center_km"] = pd.to_numeric(mat["r_center_km"], errors="coerce")
    mat["mean_delta_r_w"] = pd.to_numeric(mat["mean_delta_r_w"], errors="coerce")
    mat = mat.dropna(subset=["hours_since_quake", "r_center_km"]).copy()

    t_vals = np.array(sorted(mat["hours_since_quake"].unique().tolist()), dtype=float)
    r_vals = np.array(sorted(mat["r_center_km"].unique().tolist()), dtype=float)
    if t_vals.size == 0 or r_vals.size == 0:
        return

    pivot = mat.pivot_table(index="r_center_km", columns="hours_since_quake", values="mean_delta_r_w", aggfunc="mean")
    z = pivot.to_numpy(dtype=float)

    vmax = float(np.nanpercentile(np.abs(z), 95)) if np.isfinite(z).any() else 1.0
    vmax = max(1.0, vmax)

    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        im = ax.imshow(
            z,
            origin="lower",
            aspect="auto",
            extent=[float(t_vals.min()), float(t_vals.max()), float(r_vals.min()), float(r_vals.max())],
            cmap="RdBu_r",
            vmin=-vmax,
            vmax=vmax,
        )
        ax.axvline(0.0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.set_xlabel("Hours since earthquake (PT windows)")
        ax.set_ylabel(r"$r_{\mathrm{start}}$ (km, sliding window centers)")
        ax.set_title(r"Weighted mean radial displacement $\langle \Delta r \rangle_w(r,t)$")
        ps.despine(ax)
        cb = fig.colorbar(im, ax=ax, shrink=0.88)
        cb.set_label(r"$\langle \Delta r \rangle_w$ (km)")
        fig.tight_layout()
        save_png_and_pdf(ps, fig, out_path)
        plt.close(fig)


def _plot_long_range_fraction(ts: pd.DataFrame, *, out_path: Path) -> None:
    try:
        from disaster import plot_style as ps  # type: ignore
    except ModuleNotFoundError as e:
        if e.name == "matplotlib":
            raise SystemExit("缺少依赖：matplotlib。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e
        raise

    if ts.empty:
        return

    ts = ts.copy()
    ts["hours_since_quake"] = pd.to_numeric(ts["hours_since_quake"], errors="coerce")
    ts = ts.dropna(subset=["hours_since_quake"]).sort_values("hours_since_quake", kind="stable")

    with ps.paper_style():
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=ps.FIGSIZE_FULL)
        ax.plot(ts["hours_since_quake"], ts["f_long_crisis"], color=ps.OKABE_ITO["blue"], label=r"$f_{\mathrm{long}}$ (crisis)")
        if "f_long_baseline" in ts.columns:
            ax.plot(ts["hours_since_quake"], ts["f_long_baseline"], color=ps.OKABE_ITO["vermillion"], label=r"$f_{\mathrm{long}}$ (baseline)")
        ax.axvline(0.0, color=ps.OKABE_ITO["gray"], linestyle=":", linewidth=1.2, alpha=0.75)
        ax.set_xlabel("Hours since earthquake (PT windows)")
        ax.set_ylabel(r"Long-range fraction ($d_{\mathrm{move}}>50$ km)")
        ax.set_title("Long-range flow fraction over time")
        ps.despine(ax)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), ncol=2, frameon=False)
        fig.subplots_adjust(bottom=0.25)
        save_png_and_pdf(ps, fig, out_path)
        plt.close(fig)


def run(cfg: Config) -> None:
    out = _output_dirs(Path(cfg.output_dir))
    _ensure_dir(out.root)
    _ensure_dir(out.figures)
    _ensure_dir(out.tables)

    windows = _list_movement_windows(cfg)
    snapshots = _pick_nearest_windows(windows, cfg.snapshot_hours)
    snapshot_paths = {str(s["path"]) for s in snapshots}
    feats_by_path: dict[str, pd.DataFrame] = {}

    writer = None
    if bool(cfg.write_od_features):
        od_path = out.root / ("od_features.parquet" if cfg.od_format == "parquet" else "od_features.csv")
        writer = _OdFeatureWriter(od_path, fmt=str(cfg.od_format))

    long_rows: list[dict] = []
    space_rows: list[pd.DataFrame] = []

    for meta in windows:
        path = Path(meta["path"])
        ws = pd.Timestamp(meta["window_start_pt"])
        hs = float(meta["hours_since_quake"])

        df = load_movement_file(path)
        feats = _compute_od_features(df, cfg, window_start_pt=ws, hours_since_quake=hs)

        # cache selected snapshots (for Part2/4)
        if str(path) in snapshot_paths and str(path) not in feats_by_path:
            feats_by_path[str(path)] = feats.copy()

        if writer is not None:
            writer.write(feats)

        if feats.empty:
            long_rows.append(
                {
                    "window_start_pt": str(ws),
                    "hours_since_quake": float(hs),
                    "n_od": 0,
                    "total_flow_crisis": 0.0,
                    "total_flow_baseline": 0.0,
                    "f_long_crisis": float("nan"),
                    "f_long_baseline": float("nan"),
                }
            )
            continue

        # Part5: f_long(t)
        d_move = feats["d_move_km"].to_numpy(dtype=float)
        nc = feats["n_crisis"].to_numpy(dtype=float)
        nb = feats["n_baseline"].to_numpy(dtype=float)
        ok_c = np.isfinite(d_move) & np.isfinite(nc) & (nc > 0)
        ok_b = np.isfinite(d_move) & np.isfinite(nb) & (nb > 0)

        total_c = float(np.sum(nc[ok_c])) if np.any(ok_c) else 0.0
        total_b = float(np.sum(nb[ok_b])) if np.any(ok_b) else 0.0
        long_mask = np.isfinite(d_move) & (d_move > float(cfg.long_move_km))
        long_c = float(np.sum(nc[ok_c & long_mask])) if np.any(ok_c & long_mask) else 0.0
        long_b = float(np.sum(nb[ok_b & long_mask])) if np.any(ok_b & long_mask) else 0.0

        long_rows.append(
            {
                "window_start_pt": str(ws),
                "hours_since_quake": float(hs),
                "n_od": int(np.sum(ok_c)),
                "total_flow_crisis": float(total_c),
                "total_flow_baseline": float(total_b),
                "f_long_crisis": float(long_c / total_c) if total_c > 0 else float("nan"),
                "f_long_baseline": float(long_b / total_b) if total_b > 0 else float("nan"),
            }
        )

        # Part3: ⟨Δr⟩_w(r,t) (w = n_crisis)
        r_start = feats["r_start_km"].to_numpy(dtype=float)
        delta_r = feats["delta_r_km"].to_numpy(dtype=float)
        w = feats["n_crisis"].to_numpy(dtype=float)
        slide = _sliding_weighted_mean_delta_r(
            r_start,
            delta_r,
            w,
            r_min=float(cfg.r_start_min_km),
            r_max=float(cfg.r_start_max_km),
            window_km=float(cfg.sliding_window_km),
            step_km=float(cfg.sliding_step_km),
        )
        if not slide.empty:
            slide = slide.assign(window_start_pt=str(ws), hours_since_quake=float(hs))
            space_rows.append(slide)

    if writer is not None:
        writer.close()

    # === tables ===
    long_df = pd.DataFrame(long_rows).sort_values("hours_since_quake", kind="stable")
    space_df = pd.concat(space_rows, ignore_index=True) if space_rows else pd.DataFrame([])

    stats_dmove = pd.DataFrame([])
    stats_diag = pd.DataFrame([])
    if not (bool(cfg.skip_tables) and bool(cfg.skip_figures)):
        stats_dmove = _plot_dmove_vs_deltar(
            snapshots,
            feats_by_path,
            cfg,
            out_path=out.figures / "dmove_vs_deltar_heatmap.png",
            plot=not bool(cfg.skip_figures),
        )
        stats_diag = _plot_rstart_vs_rend(
            snapshots,
            feats_by_path,
            cfg,
            out_path=out.figures / "rstart_vs_rend_scatter.png",
            plot=not bool(cfg.skip_figures),
        )

    if not bool(cfg.skip_tables):
        long_df.to_csv(out.tables / "long_range_flow_fraction.csv", index=False)
        space_df.to_csv(out.tables / "delta_r_spacetime_matrix.csv", index=False)
        stats_dmove.to_csv(out.tables / "flow_length_direction_stats.csv", index=False)
        stats_diag.to_csv(out.tables / "diagonal_deviation_stats.csv", index=False)

    # === figures (依赖 tables 里已有矩阵/序列也可以直接用内存) ===
    if not bool(cfg.skip_figures):
        _plot_long_range_fraction(long_df, out_path=out.figures / "long_range_flow_fraction.png")
        _plot_delta_r_spacetime(space_df, cfg, out_path=out.figures / "delta_r_spacetime_heatmap.png")


def _parse_metadata_overrides(args, *, cfg_defaults: dict) -> dict:
    out = dict(cfg_defaults)
    if args.metadata_json:
        meta = _try_load_metadata_json(Path(args.metadata_json))
        if meta:
            for k in ["center_lat", "center_lon", "only_hour_pt", "t0_pt"]:
                if k in meta and meta[k] is not None:
                    out[k] = meta[k]
    return out


def cli_main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", type=Path, required=True, help="包含 movement/ 的数据根目录（raw）")
    p.add_argument("--output-dir", type=Path, required=True, help="输出目录（例如 outputs/turkiye_earthquake_2023/movement_analysis）")
    p.add_argument("--metadata-json", type=Path, default=None, help="可选：outputs/<slug>/metadata.json，用于自动填充 t0/center/hour")

    p.add_argument("--center-lat", type=float, default=None, help="震中纬度（metadata-json 未提供时必填）")
    p.add_argument("--center-lon", type=float, default=None, help="震中经度（metadata-json 未提供时必填）")
    p.add_argument("--t0-pt", type=str, default=None, help="t0（例如 '2023-02-05 16:00'；metadata-json 未提供时必填）")
    p.add_argument("--only-hour-pt", type=int, default=None, help="只使用该小时的窗口（默认从 metadata 或 8）")

    p.add_argument("--min-hours", type=float, default=-16.0)
    p.add_argument("--max-hours", type=float, default=832.0)
    p.add_argument("--snapshot-hours", type=str, default="8,40,168", help="代表性窗口小时数（逗号分隔；会取最近窗口）")

    p.add_argument("--od-format", type=str, choices=["parquet", "csv"], default="parquet")
    p.add_argument("--no-od-features", action="store_true", help="不输出 od_features（仅做统计/出图）")
    p.add_argument("--skip-figures", action="store_true", help="跳过出图（只输出表/od_features）")
    p.add_argument("--skip-tables", action="store_true", help="跳过表格输出（只出图/od_features）")
    args = p.parse_args()

    defaults = {"center_lat": args.center_lat, "center_lon": args.center_lon, "t0_pt": args.t0_pt, "only_hour_pt": args.only_hour_pt}
    meta = _parse_metadata_overrides(args, cfg_defaults=defaults)

    if meta.get("center_lat") is None or meta.get("center_lon") is None:
        raise SystemExit("缺少震中坐标：请提供 --center-lat/--center-lon 或 --metadata-json")
    if meta.get("t0_pt") is None:
        raise SystemExit("缺少 t0：请提供 --t0-pt 或 --metadata-json")

    snap = tuple(float(x.strip()) for x in str(args.snapshot_hours).split(",") if str(x).strip())
    cfg = Config(
        data_root=Path(args.data_root),
        output_dir=Path(args.output_dir),
        center_lat=float(meta["center_lat"]),
        center_lon=float(meta["center_lon"]),
        t0_pt=pd.Timestamp(meta["t0_pt"]),
        only_hour_pt=int(meta.get("only_hour_pt") or 8),
        min_hours=float(args.min_hours),
        max_hours=float(args.max_hours),
        snapshot_hours=snap,
        write_od_features=not bool(args.no_od_features),
        od_format=str(args.od_format),
        skip_figures=bool(args.skip_figures),
        skip_tables=bool(args.skip_tables),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()
