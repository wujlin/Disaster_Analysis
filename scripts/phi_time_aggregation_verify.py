#!/usr/bin/env python3
"""
可复现入口：验证 8h→24h 聚合（ratio-of-sums vs mean-of-ratios）。
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
    from disaster.phi_time_aggregation_verify import cli_main

    cli_main()


if __name__ == "__main__":
    main()

