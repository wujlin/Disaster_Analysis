#!/usr/bin/env python3
"""
可复现入口：P2 - 提取 rank-1 空间模式 f(r)=u1(r) 并做跨事件一致性对比
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
    from disaster.cross_disaster_fr_mode import cli_main

    cli_main()


if __name__ == "__main__":
    main()

