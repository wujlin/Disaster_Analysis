from __future__ import annotations

from typing import Iterable

import numpy as np


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
