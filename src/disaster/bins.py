from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import numpy as np


_RANGE_RE = re.compile(r"^(?P<lo>\d+(?:\.\d+)?)-(?P<hi>\d+(?:\.\d+)?)km$")
_OPEN_RE = re.compile(r"^(?P<lo>\d+(?:\.\d+)?)km\+$")


@dataclass(frozen=True)
class KmBin:
    lo: float
    hi: float  # np.inf 表示开区间

    @property
    def is_open_ended(self) -> bool:
        return bool(np.isinf(self.hi))

    def midpoint(self) -> float:
        if self.is_open_ended:
            return float("nan")
        return (self.lo + self.hi) / 2.0


def parse_km_bin(label: str) -> KmBin:
    """
    解析距离分箱标签（与 geo.distance_bin_labels 输出保持一致）：
    - "0-50km"
    - "1000km+"
    """

    label = str(label).strip()
    m = _RANGE_RE.match(label)
    if m:
        return KmBin(lo=float(m.group("lo")), hi=float(m.group("hi")))
    m = _OPEN_RE.match(label)
    if m:
        return KmBin(lo=float(m.group("lo")), hi=float("inf"))
    raise ValueError(f"无法解析距离分箱标签：{label!r}")


def km_bin_midpoint(label: str, *, open_ended_mid_km: Optional[float] = None) -> float:
    b = parse_km_bin(label)
    if b.is_open_ended:
        return float(open_ended_mid_km) if open_ended_mid_km is not None else float("nan")
    return b.midpoint()
