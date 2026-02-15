#!/usr/bin/env python3
"""
可复现入口：Opinion_PI 动力学模型四实验
"""

from __future__ import annotations

import traceback
import sys
from pathlib import Path


def _bootstrap_src() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    error_log = repo_root / "outputs" / "_runs" / "dynamics_potential_last_error.log"
    try:
        _bootstrap_src()
        from disaster.dynamics_potential import cli_main

        cli_main()
    except BaseException as e:  # noqa: BLE001
        error_log.parent.mkdir(parents=True, exist_ok=True)
        msg = f"[dynamics_potential][ERROR] {type(e).__name__}: {e}\n\n{traceback.format_exc()}\n"
        error_log.write_text(msg, encoding="utf-8")
        print(msg, flush=True)
        print(f"[dynamics_potential] 详细错误日志已写入: {error_log}", flush=True)
        return


if __name__ == "__main__":
    main()
