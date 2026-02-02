#!/usr/bin/env python3
"""
可复现入口：方向极化结果后处理

- 添加 reliable 列（n_od >= threshold）
- 合并 0-25km 与 25-50km 为 0-50km（可选）
- 只用 reliable 数据重算 summary
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
    from disaster.directional_polarization_postprocess import cli_main

    cli_main()


if __name__ == "__main__":
    main()

