from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

def _haversine_between_km(lat0: np.ndarray, lon0: np.ndarray, lat1: np.ndarray, lon1: np.ndarray) -> np.ndarray:
    """
    逐行计算 (lat0,lon0) -> (lat1,lon1) 的 haversine 距离（单位 km）。

    说明：disaster.geo.haversine_km 的接口是“到单个参考点”的距离，
    这里需要 OD 两点之间的距离，因此单独实现一版向量化计算。
    """

    r = 6371.0
    lat0 = np.radians(lat0.astype(float))
    lon0 = np.radians(lon0.astype(float))
    lat1 = np.radians(lat1.astype(float))
    lon1 = np.radians(lon1.astype(float))
    dlat = lat1 - lat0
    dlon = lon1 - lon0
    a = np.sin(dlat / 2) ** 2 + np.cos(lat0) * np.cos(lat1) * np.sin(dlon / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def load_movement_file(path: Path) -> pd.DataFrame:
    """
    读取 Movement Between Places During Crisis (Bing Tiles) 单个窗口文件。

    约定（来自 Docs/facebook_data/movement.md）：
    - 起止点使用 start_* / end_* 字段
    - 关键指标：n_baseline / n_crisis / z_score / percent_change / n_difference
    - 可能包含 length_km（OD 距离）
    """

    wanted = {
        "start_latitude",
        "start_longitude",
        "end_latitude",
        "end_longitude",
        "start_quadkey",
        "end_quadkey",
        "country",
        "date_time",
        "n_baseline",
        "n_crisis",
        "n_difference",
        "percent_change",
        "z_score",
        "length_km",
        "ds",
    }
    df = pd.read_csv(
        path,
        usecols=lambda c: c in wanted,
        na_values=["\\N", ""],
        dtype={"start_quadkey": "string", "end_quadkey": "string"},
    )
    df = df.rename(
        columns={
            "start_latitude": "start_lat",
            "start_longitude": "start_lon",
            "end_latitude": "end_lat",
            "end_longitude": "end_lon",
        }
    )

    for col in [
        "start_lat",
        "start_lon",
        "end_lat",
        "end_lon",
        "n_baseline",
        "n_crisis",
        "n_difference",
        "percent_change",
        "z_score",
        "length_km",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 若缺 length_km，则用起止坐标计算（不依赖 quadkey 解码）
    if "length_km" not in df.columns or df["length_km"].isna().all():
        if {"start_lat", "start_lon", "end_lat", "end_lon"} <= set(df.columns):
            lat0 = df["start_lat"].to_numpy(dtype=float)
            lon0 = df["start_lon"].to_numpy(dtype=float)
            lat1 = df["end_lat"].to_numpy(dtype=float)
            lon1 = df["end_lon"].to_numpy(dtype=float)
            df["length_km"] = _haversine_between_km(lat0, lon0, lat1, lon1)
        else:
            df["length_km"] = np.nan

    return df
