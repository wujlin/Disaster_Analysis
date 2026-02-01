#!/usr/bin/env python3
"""
可复现入口：多灾难全量 eval 套件（φ(r,t)/τ(r) + 连续 τ(r) + 稳健性检验 + 外部验证）

- 配置：Docs/cross_disaster_catalog.csv
- 产物：outputs/<slug>/* + outputs/cross_disaster_comparison/*
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
    from disaster.cross_disaster_eval_suite import cli_main

    cli_main()


if __name__ == "__main__":
    main()

