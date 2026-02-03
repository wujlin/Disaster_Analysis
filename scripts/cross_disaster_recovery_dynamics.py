#!/usr/bin/env python3
"""
跨灾害恢复动力学比较：
- 对每个灾害/距离带拟合 |phi-1| 的指数衰减与幂律衰减
- 汇总 tau/beta，并用 tau(r) 做时间重标度坍缩
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
    from disaster.cross_disaster_recovery_dynamics import cli_main

    cli_main()


if __name__ == "__main__":
    main()

