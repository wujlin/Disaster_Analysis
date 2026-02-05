#!/usr/bin/env python3
"""
可复现入口：H3a（飓风路径几何）报告 - 原始 φ(d_path) 曲线 + 坍缩图
"""

from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_src() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def main() -> None:
    _bootstrap_src()
    from disaster.h3a_track_report import cli_main

    cli_main()


if __name__ == "__main__":
    main()

