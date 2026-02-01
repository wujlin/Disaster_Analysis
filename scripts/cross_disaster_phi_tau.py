#!/usr/bin/env python3
"""
可复现入口：多灾难 φ(r,t) + τ(r) 批量分析

- 配置：Docs/cross_disaster_catalog.csv
- 产物：outputs/<slug>/{population_redistribution,physical_model}/ + outputs/cross_disaster_comparison/
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
    from disaster.cross_disaster_phi_tau import cli_main

    cli_main()


if __name__ == "__main__":
    main()

