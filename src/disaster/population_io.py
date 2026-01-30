from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


FILENAME_RE = re.compile(r"^\d+_(\d{4}-\d{2}-\d{2})_(\d{4})\.csv$")


def parse_window_start_pt(path: Path) -> pd.Timestamp:
    m = FILENAME_RE.match(path.name)
    if not m:
        raise ValueError(f"无法解析文件名时间戳：{path.name}")
    date_str, hhmm = m.group(1), m.group(2)
    hh, mm = int(hhmm[:2]), int(hhmm[2:])
    return pd.Timestamp(f"{date_str} {hh:02d}:{mm:02d}")


def load_population_file(path: Path) -> pd.DataFrame:
    usecols = [
        "latitude",
        "longitude",
        "quadkey",
        "country",
        "date_time",
        "n_baseline",
        "n_crisis",
        "n_difference",
        "z_score",
        "percent_change",
    ]
    df = pd.read_csv(path, usecols=usecols, na_values=["\\N", ""])
    return df.rename(columns={"latitude": "lat", "longitude": "lon"})
