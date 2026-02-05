#!/usr/bin/env python3
"""
可复现入口：H3a（飓风路径几何）- 机制层指标（r0 vs 轨迹长度、y_max vs 暴露）
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
    from disaster.h3a_track_mechanism import cli_main

    cli_main()


if __name__ == "__main__":
    main()

