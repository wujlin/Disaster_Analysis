#!/usr/bin/env python3
"""
可复现入口：φ 分布数据坍缩验证（FSS-style）

示例：
python scripts/phi_fss_collapse.py \
  --catalog Docs/cross_disaster_catalog.csv \
  --output-root outputs \
  --output-dir outputs/cross_disaster_comparison/phi_fss_collapse \
  --t-crisis-mode peak_0_25 --peak-max-hours 832 --only-hour-pt 8
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
    from disaster.phi_fss_collapse import cli_main

    cli_main()


if __name__ == "__main__":
    main()

