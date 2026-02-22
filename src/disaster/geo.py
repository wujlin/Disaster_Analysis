from __future__ import annotations

from typing import Iterable

import numpy as np


def quadkey_to_latlon(quadkey: str) -> tuple[float, float]:
    qk = str(quadkey or "").strip()
    if not qk:
        raise ValueError("quadkey 不能为空")
    if any(ch not in "0123" for ch in qk):
        raise ValueError(f"quadkey 非法：{quadkey}")

    level = len(qk)
    tile_x = 0
    tile_y = 0
    for i, ch in enumerate(qk):
        bit = level - i - 1
        mask = 1 << bit
        digit = int(ch)
        if digit & 1:
            tile_x |= mask
        if digit & 2:
            tile_y |= mask

    n = float(1 << level)
    x = (tile_x + 0.5) / n
    y = (tile_y + 0.5) / n
    lon = x * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1.0 - 2.0 * y))))
    return float(lat), float(lon)


def haversine_km(lat: np.ndarray, lon: np.ndarray, lat0: float, lon0: float) -> np.ndarray:
    r = 6371.0
    lat1 = np.radians(lat.astype(float))
    lon1 = np.radians(lon.astype(float))
    lat2 = np.radians(float(lat0))
    lon2 = np.radians(float(lon0))
    dlat = lat1 - lat2
    dlon = lon1 - lon2
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def distance_bin_labels(bins: Iterable[float]) -> list[str]:
    bins = list(bins)
    labels: list[str] = []
    for i in range(len(bins) - 1):
        left, right = bins[i], bins[i + 1]
        if np.isinf(right):
            labels.append(f"{int(left)}km+")
        else:
            labels.append(f"{int(left)}-{int(right)}km")
    return labels
