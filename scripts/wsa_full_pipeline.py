#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Step:
    name: str
    cmd: list[str]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_json(p: Path, data: dict) -> None:
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _cmd_to_str(cmd: Iterable[str]) -> str:
    return " ".join(shlex.quote(str(x)) for x in cmd)


def _run_step(step: Step, *, cwd: Path, log_dir: Path, master_log: Path) -> int:
    step_log = log_dir / f"{step.name}.log"
    header = f"\n[{_now()}] >>> STEP {step.name}\nCMD: {_cmd_to_str(step.cmd)}\n"
    with master_log.open("a", encoding="utf-8") as m:
        m.write(header)
    with step_log.open("a", encoding="utf-8") as s:
        s.write(header)

    proc = subprocess.Popen(
        step.cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line_out = line.rstrip("\n")
        msg = f"[{_now()}] {line_out}"
        print(msg, flush=True)
        with master_log.open("a", encoding="utf-8") as m:
            m.write(msg + "\n")
        with step_log.open("a", encoding="utf-8") as s:
            s.write(msg + "\n")
    rc = int(proc.wait())
    tail = f"[{_now()}] <<< STEP {step.name} EXIT={rc}\n"
    with master_log.open("a", encoding="utf-8") as m:
        m.write(tail)
    with step_log.open("a", encoding="utf-8") as s:
        s.write(tail)
    return rc


def build_steps(args: argparse.Namespace) -> list[Step]:
    py = sys.executable
    steps: list[Step] = []
    steps.append(
        Step(
            name="01_remap_catalog",
            cmd=[
                py,
                "scripts/remap_catalog_data_roots.py",
                "--catalog-in",
                str(args.catalog_in),
                "--catalog-out",
                str(args.catalog_out),
                "--existing-only-out",
                str(args.catalog_existing_only),
                "--report-out",
                str(args.catalog_report),
                "--facebook-root",
                str(args.facebook_root),
                "--datasets-root",
                str(args.datasets_root),
                "--prefer",
                str(args.prefer),
            ],
        )
    )
    steps.append(
        Step(
            name="02_phi_heatmap",
            cmd=[
                py,
                "scripts/cross_disaster_phi_heatmap.py",
                "--catalog",
                str(args.catalog_existing_only),
                "--output-root",
                str(args.output_root),
                "--distance-mode",
                str(args.distance_mode),
                "--hours-pt",
                "0",
                "8",
                "16",
                "--min-hours",
                str(args.min_hours),
                "--max-hours",
                str(args.max_hours),
                "--distance-bin-km",
                str(args.distance_bin_km),
                "--max-distance-km",
                str(args.max_distance_km),
            ],
        )
    )
    steps.append(
        Step(
            name="03_dt_decay",
            cmd=[
                py,
                "scripts/dt_decay.py",
                "--output-root",
                str(args.output_root),
                "--out-dir",
                str(args.dt_out_dir),
            ],
        )
    )
    steps.append(
        Step(
            name="04_dynamics_all",
            cmd=[
                py,
                "scripts/dynamics_potential.py",
                "--output-root",
                str(args.output_root),
                "--dt-tables-dir",
                str(args.dt_out_dir / "tables"),
                "--out-dir",
                str(args.dyn_all_out_dir),
                "--use-route-b-selected",
                "0",
            ],
        )
    )
    steps.append(
        Step(
            name="05_dynamics_routeB",
            cmd=[
                py,
                "scripts/dynamics_potential.py",
                "--output-root",
                str(args.output_root),
                "--dt-tables-dir",
                str(args.dt_out_dir / "tables"),
                "--out-dir",
                str(args.dyn_routeB_out_dir),
                "--use-route-b-selected",
                "1",
            ],
        )
    )
    return steps


def cli_main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description="WSA 全流程一键运行：路径重映射 + phi_heatmap + Dt + dynamics 四实验")
    p.add_argument("--project-root", type=Path, default=repo_root)
    p.add_argument("--facebook-root", type=Path, default=Path("/home/jinlin/data/Facebook_Disaster"))
    p.add_argument("--datasets-root", type=Path, default=Path("/home/jinlin/projects/Disaster_Analysis/datasets"))
    p.add_argument("--prefer", type=str, choices=["facebook", "datasets"], default="facebook")

    p.add_argument("--catalog-in", type=Path, default=Path("Docs/cross_disaster_catalog_extended.csv"))
    p.add_argument("--catalog-out", type=Path, default=Path("Docs/cross_disaster_catalog_extended_wsa.csv"))
    p.add_argument(
        "--catalog-existing-only",
        type=Path,
        default=Path("Docs/cross_disaster_catalog_extended_wsa_existing_only.csv"),
    )
    p.add_argument("--catalog-report", type=Path, default=Path("Docs/cross_disaster_catalog_extended_wsa_path_check.csv"))

    p.add_argument("--output-root", type=Path, default=Path("outputs"))
    p.add_argument("--distance-mode", type=str, choices=["radial", "path"], default="radial")
    p.add_argument("--min-hours", type=float, default=-16.0)
    p.add_argument("--max-hours", type=float, default=832.0)
    p.add_argument("--distance-bin-km", type=float, default=10.0)
    p.add_argument("--max-distance-km", type=float, default=500.0)

    p.add_argument("--dt-out-dir", type=Path, default=Path("outputs/cross_disaster_comparison/Dt_decay"))
    p.add_argument("--dyn-all-out-dir", type=Path, default=Path("outputs/cross_disaster_comparison/dynamics_potential_all"))
    p.add_argument(
        "--dyn-routeB-out-dir",
        type=Path,
        default=Path("outputs/cross_disaster_comparison/dynamics_potential_routeB"),
    )

    p.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="运行日志目录；默认 outputs/_runs/wsa_full_pipeline_<timestamp>",
    )
    args = p.parse_args()

    project_root = Path(args.project_root).resolve()
    if args.run_dir is None:
        run_name = "wsa_full_pipeline_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = project_root / "outputs" / "_runs" / run_name
    else:
        run_dir = Path(args.run_dir).resolve()
    _ensure_dir(run_dir)
    log_dir = run_dir / "logs"
    _ensure_dir(log_dir)
    master_log = run_dir / "pipeline.log"

    cfg_snapshot = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
    cfg_snapshot["resolved_project_root"] = str(project_root)
    cfg_snapshot["resolved_run_dir"] = str(run_dir)
    _write_json(run_dir / "run_config.json", cfg_snapshot)

    steps = build_steps(args)
    (run_dir / "steps.txt").write_text("\n".join(f"{i+1}. {s.name}: {_cmd_to_str(s.cmd)}" for i, s in enumerate(steps)), encoding="utf-8")

    print(f"[{_now()}] run_dir = {run_dir}")
    print(f"[{_now()}] master_log = {master_log}")
    status = {
        "status": "running",
        "started_at": _now(),
        "finished_at": None,
        "failed_step": None,
        "steps": [],
    }
    _write_json(run_dir / "status.json", status)

    for idx, step in enumerate(steps, start=1):
        rc = _run_step(step, cwd=project_root, log_dir=log_dir, master_log=master_log)
        status["steps"].append({"idx": idx, "name": step.name, "exit_code": int(rc)})
        _write_json(run_dir / "status.json", status)
        if rc != 0:
            status["status"] = "failed"
            status["failed_step"] = step.name
            status["finished_at"] = _now()
            _write_json(run_dir / "status.json", status)
            print(f"[{_now()}] pipeline failed at {step.name}, exit={rc}")
            sys.exit(rc)

    status["status"] = "success"
    status["finished_at"] = _now()
    _write_json(run_dir / "status.json", status)
    print(f"[{_now()}] pipeline finished successfully")


if __name__ == "__main__":
    cli_main()
