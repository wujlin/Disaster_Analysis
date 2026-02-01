#!/usr/bin/env python3
"""
可复现入口：Movement 网络临界性可行性评估（Turkey Earthquake 2023）

约定：
- 业务逻辑在 src/disaster/ 下
- scripts/ 只做参数解析与调用
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
    from disaster.movement_criticality import cli_main

    cli_main()


if __name__ == "__main__":
    main()

