#!/usr/bin/env python3
"""
兼容入口：

历史脚本位于 `analysis/population_relaxation.py`，现在推荐使用 `scripts/population_relaxation.py`。
这里保留一个薄封装，避免老路径失效；核心逻辑在 `src/disaster/`。
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from disaster.population_relaxation import cli_main

    cli_main()


if __name__ == "__main__":
    main()
