"""
数据 I/O 工具模块

提供:
  - parse_window_start_pt(path)  — 从文件名提取时间戳
  - load_population_file(path)   — 加载 population CSV
  - resolve_subdir(data_root, subdir) — 自动解析数据子目录（兼容旧布局 + DFG 布局）
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


# ─────────────────────────── 文件名解析 ──────────────────────────

# 匹配两种命名格式的时间戳后缀：
#   旧格式: 2172754818300831_2023-02-05_0000.csv
#   新格式: The_Earthquake_..._Facebook_Population_During_Crisis_2026-01-06_0000.csv
# 共同特征：文件名以 _YYYY-MM-DD_HHMM.csv 结尾
FILENAME_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})_(\d{4})\.csv$")


def parse_window_start_pt(path: Path) -> pd.Timestamp:
    """从 CSV 文件名中提取时间窗口起始时间戳。

    支持旧格式 `<id>_YYYY-MM-DD_HHMM.csv` 和
    新 DFG 格式 `<Name>_<Type>_YYYY-MM-DD_HHMM.csv`。
    """
    m = FILENAME_RE.search(path.name)
    if not m:
        raise ValueError(f"无法解析文件名时间戳：{path.name}")
    date_str, hhmm = m.group(1), m.group(2)
    hh, mm = int(hhmm[:2]), int(hhmm[2:])
    return pd.Timestamp(f"{date_str} {hh:02d}:{mm:02d}")


# ─────────────────────────── 数据加载 ──────────────────────────


def load_population_file(path: Path) -> pd.DataFrame:
    """加载单个 population CSV 文件，返回标准化 DataFrame。"""
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


# ─────────────────────────── 目录解析 ──────────────────────────

# DFG 下载目录名 → 分析代码内部使用的短名
_DFG_DIR_MAP: dict[str, str] = {
    "population": "Facebook_Population_During_Crisis",
    "movement": "Movement_Between_Places_During_Crisis",
    "network coverage": "Network_Coverage_Maps",
    "business activity": "Business_Activity_Trends_During_Crisis",
}


def resolve_subdir(data_root: Path, subdir: str) -> Path:
    """自动解析数据子目录，兼容两种布局：

    旧布局（手动整理）:
        data_root/population/*.csv
        data_root/movement/*.csv

    DFG 下载布局:
        data_root/Facebook_Population_During_Crisis/raw/*.csv
        data_root/Movement_Between_Places_During_Crisis/raw/*.csv

    返回包含 CSV 文件的目录 Path，找不到则抛出 FileNotFoundError。
    """
    # 1) 旧布局：data_root/<subdir>/
    direct = data_root / subdir
    if direct.exists() and any(direct.glob("*.csv")):
        return direct

    # 2) 旧布局变体：data_root/raw/<subdir>/
    raw_sub = data_root / "raw" / subdir
    if raw_sub.exists() and any(raw_sub.glob("*.csv")):
        return raw_sub

    # 3) DFG 布局：data_root/<DFG_name>/raw/
    dfg_name = _DFG_DIR_MAP.get(subdir, "")
    if dfg_name:
        dfg_path = data_root / dfg_name / "raw"
        if dfg_path.exists() and any(dfg_path.glob("*.csv")):
            return dfg_path

    raise FileNotFoundError(
        f"未找到 '{subdir}' 数据目录。已检查：\n"
        f"  {direct}\n"
        f"  {raw_sub}\n"
        + (f"  {data_root / dfg_name / 'raw'}\n" if dfg_name else "")
    )
