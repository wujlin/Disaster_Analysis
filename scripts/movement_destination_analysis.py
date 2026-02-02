#!/usr/bin/env python3
"""
可复现入口：Movement 终点分析（按起点距离带 + cos_alpha 方向筛选）
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
    from disaster.movement_destination_analysis import cli_main

    cli_main()


if __name__ == "__main__":
    main()

