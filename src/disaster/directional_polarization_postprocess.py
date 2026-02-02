from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e


@dataclass(frozen=True)
class Config:
    input_csv: Path
    output_dir: Path
    min_n_od: int = 30
    merge_0_50: bool = True


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _safe_cosmetic_band_order(bands: list[str]) -> list[str]:
    # Prefer common schema order; otherwise keep appearance order.
    preferred = ["0-25km", "25-50km", "0-50km", "50-100km", "100-200km", "200km+"]
    if set(preferred) >= set(bands):
        return [b for b in preferred if b in set(bands)]
    return bands


def _sign(x: float) -> int:
    if not np.isfinite(float(x)):
        return 0
    if float(x) > 0:
        return 1
    if float(x) < 0:
        return -1
    return 0


def _merge_0_50(df_long: pd.DataFrame) -> pd.DataFrame:
    required = {"window_start_pt", "hours_since_quake", "only_hour_pt", "distance_band", "n_od", "F_r", "F_total"}
    missing = sorted(required - set(df_long.columns))
    if missing:
        raise ValueError(f"缺少列：{missing}")

    sub = df_long[df_long["distance_band"].astype(str).isin({"0-25km", "25-50km"})].copy()
    if sub.empty:
        return pd.DataFrame(columns=df_long.columns)

    sub["n_od"] = pd.to_numeric(sub["n_od"], errors="coerce").fillna(0).astype(int)
    sub["F_r"] = pd.to_numeric(sub["F_r"], errors="coerce").fillna(0.0).astype(float)
    sub["F_total"] = pd.to_numeric(sub["F_total"], errors="coerce").fillna(0.0).astype(float)

    agg = (
        sub.groupby(["window_start_pt", "hours_since_quake", "only_hour_pt"], observed=True, as_index=False)
        .agg(
            n_od=("n_od", "sum"),
            F_r=("F_r", "sum"),
            F_total=("F_total", "sum"),
        )
        .reset_index(drop=True)
    )
    agg["distance_band"] = "0-50km"
    agg["P"] = np.where(agg["F_total"] > 0, agg["F_r"] / agg["F_total"], np.nan)
    agg["A"] = np.where(agg["F_total"] > 0, np.abs(agg["F_r"]) / agg["F_total"], np.nan)

    # Keep column order consistent with input if possible
    out = agg[df_long.columns.intersection(agg.columns, sort=False).tolist()].copy()
    for col in df_long.columns:
        if col not in out.columns:
            out[col] = np.nan
    out = out[df_long.columns].copy()
    return out


def _summary_from_reliable(df_long: pd.DataFrame, *, min_n_od: int) -> pd.DataFrame:
    df = df_long.copy()
    df["n_od"] = pd.to_numeric(df.get("n_od", np.nan), errors="coerce")
    df["P"] = pd.to_numeric(df.get("P", np.nan), errors="coerce")
    df["hours_since_quake"] = pd.to_numeric(df.get("hours_since_quake", np.nan), errors="coerce")

    df["reliable"] = df["n_od"].notna() & (df["n_od"] >= int(min_n_od))
    df_rel = df[df["reliable"] & df["P"].notna() & df["hours_since_quake"].notna()].copy()

    out_rows: list[dict] = []
    bands = df["distance_band"].astype(str).dropna().unique().tolist()
    for band in _safe_cosmetic_band_order(bands):
        sub = df_rel[df_rel["distance_band"].astype(str) == str(band)].sort_values("hours_since_quake", kind="stable")
        hs = sub["hours_since_quake"].to_numpy(dtype=float)
        p = sub["P"].to_numpy(dtype=float)
        row: dict = {"distance_band": str(band), "n_windows": int(p.size)}
        if p.size == 0:
            row.update(
                {
                    "P_max": float("nan"),
                    "t_at_P_max": float("nan"),
                    "P_min": float("nan"),
                    "t_at_P_min": float("nan"),
                    "t_flip_start": float("nan"),
                    "t_flip_end": float("nan"),
                    "P_flip_start": float("nan"),
                    "P_flip_end": float("nan"),
                }
            )
            out_rows.append(row)
            continue

        imax = int(np.nanargmax(p))
        imin = int(np.nanargmin(p))
        row["P_max"] = float(p[imax])
        row["t_at_P_max"] = float(hs[imax])
        row["P_min"] = float(p[imin])
        row["t_at_P_min"] = float(hs[imin])

        sgn = np.array([_sign(float(x)) for x in p], dtype=int)
        nz = sgn != 0
        flip_found = False
        if np.any(nz):
            idxs = np.where(nz)[0]
            for a, b in zip(idxs[:-1], idxs[1:], strict=False):
                if int(sgn[a]) != int(sgn[b]):
                    row["t_flip_start"] = float(hs[a])
                    row["t_flip_end"] = float(hs[b])
                    row["P_flip_start"] = float(p[a])
                    row["P_flip_end"] = float(p[b])
                    flip_found = True
                    break
        if not flip_found:
            row["t_flip_start"] = float("nan")
            row["t_flip_end"] = float("nan")
            row["P_flip_start"] = float("nan")
            row["P_flip_end"] = float("nan")

        out_rows.append(row)

    out = pd.DataFrame(out_rows)
    out["distance_band"] = pd.Categorical(out["distance_band"], categories=_safe_cosmetic_band_order(bands), ordered=True)
    out = out.sort_values(["distance_band"], kind="stable").reset_index(drop=True)
    return out


def run(cfg: Config) -> None:
    if not cfg.input_csv.exists():
        raise FileNotFoundError(f"未找到输入：{cfg.input_csv}")

    _ensure_dir(cfg.output_dir)
    _ensure_dir(cfg.output_dir / "tables")

    df = pd.read_csv(cfg.input_csv)
    df["n_od"] = pd.to_numeric(df.get("n_od", np.nan), errors="coerce").fillna(0).astype(int)
    df["reliable"] = df["n_od"] >= int(cfg.min_n_od)

    out_df = df.copy()
    if bool(cfg.merge_0_50):
        merged = _merge_0_50(df)
        if not merged.empty:
            merged["n_od"] = pd.to_numeric(merged.get("n_od", np.nan), errors="coerce").fillna(0).astype(int)
            merged["reliable"] = merged["n_od"] >= int(cfg.min_n_od)
            out_df = pd.concat([out_df, merged], ignore_index=True)

    # stable ordering
    if "hours_since_quake" in out_df.columns and "distance_band" in out_df.columns:
        out_df["distance_band"] = out_df["distance_band"].astype(str)
        out_df = out_df.sort_values(["hours_since_quake", "distance_band"], kind="stable")

    out_csv = cfg.output_dir / "tables" / "flow_directional_filtered.csv"
    out_df.to_csv(out_csv, index=False)

    summary = _summary_from_reliable(out_df, min_n_od=int(cfg.min_n_od))
    out_sum = cfg.output_dir / "tables" / "polarization_summary_filtered.csv"
    summary.to_csv(out_sum, index=False)

    print(f"Done. Wrote: {out_csv}")
    print(f"Done. Wrote: {out_sum}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-csv", type=Path, required=True, help="输入 flow_directional_by_band_time.csv")
    parser.add_argument("--output-dir", type=Path, required=True, help="输出目录（通常为 outputs/<slug>/directional_polarization）")
    parser.add_argument("--min-n-od", type=int, default=30, help="可靠性阈值：n_od >= 阈值（默认 30）")
    parser.add_argument("--no-merge-0-50", action="store_true", help="不生成合并带 0-50km")
    args = parser.parse_args()

    cfg = Config(
        input_csv=args.input_csv,
        output_dir=args.output_dir,
        min_n_od=int(args.min_n_od),
        merge_0_50=not bool(args.no_merge_0_50),
    )
    run(cfg)


if __name__ == "__main__":
    cli_main()

