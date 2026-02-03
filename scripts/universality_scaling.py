#!/usr/bin/env python3
"""
可复现入口：普适性检验（Phase0 信号扫描 / Phase1 幂律 / Phase2 坍缩）
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
    from disaster.universality_scaling import cli_entry

    cli_entry()


if __name__ == "__main__":
    main()

