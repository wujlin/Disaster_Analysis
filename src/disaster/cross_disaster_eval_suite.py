from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise SystemExit("缺少依赖：pandas。请先运行 `pip install -r requirements.txt`（或用 conda 安装）。") from e

from disaster.binning_sensitivity_tau import Config as BinningConfig
from disaster.binning_sensitivity_tau import run as run_binning
from disaster.business_activity_recovery_by_distance import Config as BusinessConfig
from disaster.business_activity_recovery_by_distance import run as run_business
from disaster.cross_disaster_phi_tau import auto_t0_and_center, detect_three_phase, load_catalog, write_phase_summary_md
from disaster.population_io import resolve_subdir
from disaster.movement_recovery_by_distance import Config as MovementConfig
from disaster.movement_recovery_by_distance import run as run_movement
from disaster.network_coverage_validation import Config as NetworkCoverageConfig
from disaster.network_coverage_validation import run as run_network_coverage
from disaster.nonparametric_tau_tests import Config as NonparamConfig
from disaster.nonparametric_tau_tests import run as run_nonparametric
from disaster.physical_model_phi_rt import Config as PhysicalConfig
from disaster.physical_model_phi_rt import run as run_physical
from disaster.population_redistribution import Config as RedistributionConfig
from disaster.population_redistribution import run as run_redistribution
from disaster.tau_continuous_fit import Config as TauContinuousConfig
from disaster.tau_continuous_fit import run as run_tau_continuous


@dataclass(frozen=True)
class SuiteOutput:
    root: Path
    population_redistribution: Path
    physical_model: Path
    tau_continuous_fit: Path
    binning_sensitivity_tau: Path
    nonparametric_tau_tests: Path
    movement_recovery_by_distance: Path
    network_coverage_validation: Path
    business_activity_recovery_by_distance: Path


def _out_dirs(output_root: Path, slug: str) -> SuiteOutput:
    root = output_root / slug
    return SuiteOutput(
        root=root,
        population_redistribution=root / "population_redistribution",
        physical_model=root / "physical_model",
        tau_continuous_fit=root / "tau_continuous_fit",
        binning_sensitivity_tau=root / "binning_sensitivity_tau",
        nonparametric_tau_tests=root / "nonparametric_tau_tests",
        movement_recovery_by_distance=root / "movement_recovery_by_distance",
        network_coverage_validation=root / "network_coverage_validation",
        business_activity_recovery_by_distance=root / "business_activity_recovery_by_distance",
    )


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _nearest(values: np.ndarray, target: float) -> float:
    if values.size == 0:
        return float("nan")
    idx = int(np.argmin(np.abs(values - float(target))))
    return float(values[idx])


def _phase_for_disaster(
    *,
    slug: str,
    name: str,
    event_type: str,
    phi_matrix_csv: Path,
    eps: float,
    times_hours: tuple[float, ...],
) -> dict:
    if not phi_matrix_csv.exists():
        return {"slug": slug, "name": name, "event_type": event_type, "phase_eps": float(eps), "phase_times_hours": list(times_hours), "rows": []}

    phi_df = pd.read_csv(phi_matrix_csv)
    if "hours_since_quake" not in phi_df.columns:
        return {"slug": slug, "name": name, "event_type": event_type, "phase_eps": float(eps), "phase_times_hours": list(times_hours), "rows": []}

    phi_df["hours_since_quake"] = pd.to_numeric(phi_df["hours_since_quake"], errors="coerce")
    phi_df = phi_df.dropna(subset=["hours_since_quake"]).copy()
    hours = phi_df["hours_since_quake"].to_numpy(dtype=float)
    band_cols = [c for c in phi_df.columns if c != "hours_since_quake"]

    rows: list[dict] = []
    for t in times_hours:
        if hours.size == 0:
            continue
        t_used = _nearest(hours, float(t))
        sub = phi_df[phi_df["hours_since_quake"] == t_used]
        if sub.empty:
            continue
        vec = sub.iloc[0][band_cols].to_numpy(dtype=float)
        ok, raw, collapsed = detect_three_phase(vec, eps=float(eps))
        rows.append(
            {
                "t_req_hours": float(t),
                "t_used_hours": float(t_used),
                "three_phase_ok": int(ok),
                "pattern_raw": raw,
                "pattern_collapsed": collapsed,
            }
        )

    return {
        "slug": slug,
        "name": name,
        "event_type": event_type,
        "phase_eps": float(eps),
        "phase_times_hours": [float(x) for x in times_hours],
        "rows": rows,
    }


def run_suite(
    *,
    catalog: Path,
    output_root: Path,
    summary_dir: Path,
    fit_min_hours: float,
    fit_max_hours: float | None,
    plot_times_hours: tuple[float, ...],
    phase_eps: float,
    phase_times_hours: tuple[float, ...],
    tau_cont_bootstrap_samples: int,
    tau_cont_min_points: int,
    nonparam_bootstrap: int,
    nonparam_permutation: int,
    allow_auto_fallback: bool,
) -> None:
    specs = load_catalog(catalog)
    _ensure_dir(summary_dir)

    all_band_fit: list[pd.DataFrame] = []
    phases: list[dict] = []
    tau_cont_fit_rows: list[pd.DataFrame] = []
    rstar_summary_rows: list[dict] = []
    tau_range_rows: list[pd.DataFrame] = []
    vis_int_rows: list[pd.DataFrame] = []
    step_status_rows: list[dict] = []

    def _record_step(*, spec_slug: str, spec_name: str, spec_type: str, step: str, ok: bool, error_type: str = "", error: str = "") -> None:
        step_status_rows.append(
            {
                "slug": spec_slug,
                "name": spec_name,
                "event_type": spec_type,
                "step": step,
                "ok": int(bool(ok)),
                "error_type": str(error_type),
                "error": str(error),
            }
        )

    def _run_step(spec, step: str, fn) -> bool:
        try:
            fn()
        except SystemExit as e:
            msg = str(e).strip()
            print(f"[eval_suite] {spec.slug}: {step} skipped: {msg}")
            _record_step(spec_slug=spec.slug, spec_name=spec.name, spec_type=spec.event_type, step=step, ok=False, error_type="SystemExit", error=msg)
            return False
        except Exception as e:
            msg = str(e).strip()
            et = type(e).__name__
            print(f"[eval_suite] {spec.slug}: {step} failed: {et}: {msg}")
            _record_step(spec_slug=spec.slug, spec_name=spec.name, spec_type=spec.event_type, step=step, ok=False, error_type=et, error=msg)
            return False
        _record_step(spec_slug=spec.slug, spec_name=spec.name, spec_type=spec.event_type, step=step, ok=True)
        return True

    for spec in specs:
        out = _out_dirs(output_root, spec.slug)
        _ensure_dir(out.root)

        t0_pt, center_lat, center_lon, meta = auto_t0_and_center(
            spec,
            allow_auto_fallback=bool(allow_auto_fallback),
        )
        (out.root / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"[eval_suite] {spec.slug}: population_redistribution")
        red_cfg = RedistributionConfig(
            data_root=spec.data_root,
            output_dir=out.population_redistribution,
            epicenter_lat=float(center_lat),
            epicenter_lon=float(center_lon),
            t0_pt=pd.Timestamp(t0_pt),
            only_hour_pt=int(spec.only_hour_pt),
            outflow_phi_threshold=float(spec.outflow_phi_threshold),
            inflow_phi_threshold=float(spec.inflow_phi_threshold),
        )
        _run_step(spec, "population_redistribution", lambda: run_redistribution(red_cfg))

        print(f"[eval_suite] {spec.slug}: physical_model_phi_rt")
        input_csv = out.population_redistribution / "tables" / "redistribution_by_distance_band.csv"
        phy_cfg = PhysicalConfig(
            input_csv=input_csv,
            output_dir=out.physical_model,
            fit_min_hours=float(fit_min_hours),
            fit_max_hours=float(fit_max_hours) if fit_max_hours is not None else None,
            plot_times_hours=tuple(float(x) for x in plot_times_hours),
        )
        _run_step(spec, "physical_model_phi_rt", lambda: run_physical(phy_cfg))

        fit_csv = out.physical_model / "tables" / "relaxation_fit_by_band.csv"
        if fit_csv.exists():
            df_fit = pd.read_csv(fit_csv)
            df_fit.insert(0, "slug", spec.slug)
            df_fit.insert(1, "name", spec.name)
            df_fit.insert(2, "event_type", spec.event_type)
            all_band_fit.append(df_fit)

        ph = _phase_for_disaster(
            slug=spec.slug,
            name=spec.name,
            event_type=spec.event_type,
            phi_matrix_csv=out.physical_model / "tables" / "phi_rt_matrix.csv",
            eps=float(phase_eps),
            times_hours=tuple(float(x) for x in phase_times_hours),
        )
        phases.append(ph)

        print(f"[eval_suite] {spec.slug}: tau_continuous_fit")
        tau_cfg = TauContinuousConfig(
            data_root=spec.data_root,
            output_dir=out.tau_continuous_fit,
            epicenter_lat=float(center_lat),
            epicenter_lon=float(center_lon),
            t0_pt=pd.Timestamp(t0_pt),
            only_hour_pt=int(spec.only_hour_pt),
            fit_min_hours=float(fit_min_hours),
            fit_max_hours=float(fit_max_hours) if fit_max_hours is not None else None,
            min_points=int(tau_cont_min_points),
            bootstrap_samples=int(tau_cont_bootstrap_samples),
        )
        _run_step(spec, "tau_continuous_fit", lambda: run_tau_continuous(tau_cfg))

        # 连续 τ(r) 汇总
        cont_fit_csv = out.tau_continuous_fit / "tables" / "tau_r_fit_quadratic.csv"
        if cont_fit_csv.exists():
            cfit = pd.read_csv(cont_fit_csv)
            cfit.insert(0, "slug", spec.slug)
            cfit.insert(1, "name", spec.name)
            cfit.insert(2, "event_type", spec.event_type)
            tau_cont_fit_rows.append(cfit)

        rstar_csv = out.tau_continuous_fit / "tables" / "tau_r_star_bootstrap.csv"
        if rstar_csv.exists():
            rs = pd.read_csv(rstar_csv)
            rs["r_star_km"] = pd.to_numeric(rs.get("r_star_km", np.nan), errors="coerce")
            x = rs["r_star_km"].to_numpy(dtype=float)
            x = x[np.isfinite(x) & (x > 0)]
            if x.size:
                rstar_summary_rows.append(
                    {
                        "slug": spec.slug,
                        "name": spec.name,
                        "event_type": spec.event_type,
                        "bootstrap_n": int(x.size),
                        "r_star_median_km": float(np.nanmedian(x)),
                        "r_star_ci025_km": float(np.nanpercentile(x, 2.5)),
                        "r_star_ci975_km": float(np.nanpercentile(x, 97.5)),
                    }
                )

        print(f"[eval_suite] {spec.slug}: binning_sensitivity_tau")
        tile_tau_csv = out.tau_continuous_fit / "tables" / "tile_level_tau.csv"
        if tile_tau_csv.exists():
            _run_step(spec, "binning_sensitivity_tau", lambda: run_binning(BinningConfig(input_csv=tile_tau_csv, output_dir=out.binning_sensitivity_tau)))
        else:
            _record_step(
                spec_slug=spec.slug,
                spec_name=spec.name,
                spec_type=spec.event_type,
                step="binning_sensitivity_tau",
                ok=False,
                error_type="missing_input",
                error="missing tile_level_tau.csv",
            )

        print(f"[eval_suite] {spec.slug}: nonparametric_tau_tests")
        if tile_tau_csv.exists():
            _run_step(
                spec,
                "nonparametric_tau_tests",
                lambda: run_nonparametric(
                    NonparamConfig(
                        input_csv=tile_tau_csv,
                        output_dir=out.nonparametric_tau_tests,
                        bootstrap_samples=int(nonparam_bootstrap),
                        permutation_samples=int(nonparam_permutation),
                    )
                ),
            )

            tau_range_csv = out.nonparametric_tau_tests / "tables" / "tau_range_comparisons.csv"
            if tau_range_csv.exists():
                tr = pd.read_csv(tau_range_csv)
                tr.insert(0, "slug", spec.slug)
                tr.insert(1, "name", spec.name)
                tr.insert(2, "event_type", spec.event_type)
                tau_range_rows.append(tr)

            vis_int_csv = out.nonparametric_tau_tests / "tables" / "visibility_vs_intensity_tests.csv"
            if vis_int_csv.exists():
                vi = pd.read_csv(vis_int_csv)
                vi.insert(0, "slug", spec.slug)
                vi.insert(1, "name", spec.name)
                vi.insert(2, "event_type", spec.event_type)
                vis_int_rows.append(vi)
        else:
            _record_step(
                spec_slug=spec.slug,
                spec_name=spec.name,
                spec_type=spec.event_type,
                step="nonparametric_tau_tests",
                ok=False,
                error_type="missing_input",
                error="missing tile_level_tau.csv",
            )

        # Movement / Network coverage / Business activity（可用则跑）
        try:
            resolve_subdir(spec.data_root, "movement")
            _has_movement = True
        except FileNotFoundError:
            _has_movement = False
        if _has_movement:
            print(f"[eval_suite] {spec.slug}: movement_recovery_by_distance")
            _run_step(
                spec,
                "movement_recovery_by_distance",
                lambda: run_movement(
                    MovementConfig(
                        data_root=spec.data_root,
                        output_dir=out.movement_recovery_by_distance,
                        epicenter_lat=float(center_lat),
                        epicenter_lon=float(center_lon),
                        t0_pt=pd.Timestamp(t0_pt),
                        only_hour_pt=int(spec.only_hour_pt),
                        fit_min_hours=float(fit_min_hours),
                        fit_max_hours=float(fit_max_hours) if fit_max_hours is not None else None,
                    )
                ),
            )
        else:
            _record_step(
                spec_slug=spec.slug,
                spec_name=spec.name,
                spec_type=spec.event_type,
                step="movement_recovery_by_distance",
                ok=False,
                error_type="missing_input",
                error="missing movement/ directory",
            )

        try:
            resolve_subdir(spec.data_root, "network coverage")
            _has_network = True
        except FileNotFoundError:
            _has_network = False
        if _has_network:
            print(f"[eval_suite] {spec.slug}: network_coverage_validation")
            pop_band_csv = out.population_redistribution / "tables" / "redistribution_by_distance_band.csv"
            pop_band_csv = pop_band_csv if pop_band_csv.exists() else None
            _run_step(
                spec,
                "network_coverage_validation",
                lambda: run_network_coverage(
                    NetworkCoverageConfig(
                        data_root=spec.data_root,
                        output_dir=out.network_coverage_validation,
                        epicenter_lat=float(center_lat),
                        epicenter_lon=float(center_lon),
                        t0_pt=pd.Timestamp(t0_pt),
                        population_by_band_csv=pop_band_csv,
                    )
                ),
            )
        else:
            _record_step(
                spec_slug=spec.slug,
                spec_name=spec.name,
                spec_type=spec.event_type,
                step="network_coverage_validation",
                ok=False,
                error_type="missing_input",
                error="missing network coverage/ directory",
            )

        try:
            resolve_subdir(spec.data_root, "business activity")
            _has_business = True
        except FileNotFoundError:
            _has_business = False
        if _has_business:
            print(f"[eval_suite] {spec.slug}: business_activity_recovery_by_distance")
            _run_step(
                spec,
                "business_activity_recovery_by_distance",
                lambda: run_business(
                    BusinessConfig(
                        data_root=spec.data_root,
                        output_dir=out.business_activity_recovery_by_distance,
                        epicenter_lat=float(center_lat),
                        epicenter_lon=float(center_lon),
                        t0_pt=pd.Timestamp(t0_pt),
                        only_vertical="all",
                    )
                ),
            )
        else:
            _record_step(
                spec_slug=spec.slug,
                spec_name=spec.name,
                spec_type=spec.event_type,
                step="business_activity_recovery_by_distance",
                ok=False,
                error_type="missing_input",
                error="missing business activity/ directory",
            )

    # cross-disaster summaries
    if all_band_fit:
        out_tau = summary_dir / "tau_comparison.csv"
        pd.concat(all_band_fit, ignore_index=True).to_csv(out_tau, index=False)
        print(f"Done. Wrote: {out_tau}")

    out_phase = summary_dir / "phase_separation_summary.md"
    write_phase_summary_md(phases, out_phase)
    print(f"Done. Wrote: {out_phase}")

    if tau_cont_fit_rows:
        out_cont = summary_dir / "tau_continuous_quadratic_comparison.csv"
        pd.concat(tau_cont_fit_rows, ignore_index=True).to_csv(out_cont, index=False)
        print(f"Done. Wrote: {out_cont}")

    if rstar_summary_rows:
        out_rstar = summary_dir / "r_star_bootstrap_summary.csv"
        pd.DataFrame(rstar_summary_rows).to_csv(out_rstar, index=False)
        print(f"Done. Wrote: {out_rstar}")

    if tau_range_rows:
        out_tr = summary_dir / "tau_range_comparisons_all.csv"
        pd.concat(tau_range_rows, ignore_index=True).to_csv(out_tr, index=False)
        print(f"Done. Wrote: {out_tr}")

    if vis_int_rows:
        out_vi = summary_dir / "visibility_vs_intensity_tests_all.csv"
        pd.concat(vis_int_rows, ignore_index=True).to_csv(out_vi, index=False)
        print(f"Done. Wrote: {out_vi}")

    if step_status_rows:
        out_status = summary_dir / "eval_suite_step_status.csv"
        pd.DataFrame(step_status_rows).to_csv(out_status, index=False)
        print(f"Done. Wrote: {out_status}")


def cli_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("Docs/cross_disaster_catalog.csv"), help="灾难配置表（CSV）")
    parser.add_argument("--output-root", type=Path, default=Path("outputs"), help="输出根目录（默认 outputs/）")
    parser.add_argument("--summary-dir", type=Path, default=Path("outputs/cross_disaster_comparison"), help="跨灾难汇总输出目录")
    parser.add_argument("--fit-min-hours", type=float, default=0.0, help="拟合使用 t>=min（默认 0）")
    parser.add_argument("--fit-max-hours", type=float, default=None, help="拟合使用 t<=max（可选）")
    parser.add_argument("--plot-times-hours", type=float, nargs="*", default=[16, 40, 88, 160, 832], help="φ(r) 曲线时间点（取 nearest）")
    parser.add_argument("--phase-eps", type=float, default=0.05, help="三相分离判定 eps")
    parser.add_argument("--phase-times-hours", type=float, nargs="*", default=[16, 40, 88, 160, 832], help="三相分离判定时间点（取 nearest）")
    parser.add_argument("--tau-cont-bootstrap-samples", type=int, default=1000, help="连续 τ(r) bootstrap 次数")
    parser.add_argument("--tau-cont-min-points", type=int, default=20, help="连续 τ(r) 单 tile 最少点数")
    parser.add_argument("--nonparam-bootstrap-samples", type=int, default=2000, help="非参数检验 bootstrap 次数")
    parser.add_argument("--nonparam-permutation-samples", type=int, default=5000, help="非参数检验 permutation 次数")
    parser.add_argument(
        "--allow-auto-fallback",
        type=int,
        choices=[0, 1],
        default=0,
        help="是否允许 auto t0/center fallback（0=禁用，严格要求 catalog 显式给定；1=允许）",
    )
    args = parser.parse_args()

    run_suite(
        catalog=args.catalog,
        output_root=args.output_root,
        summary_dir=args.summary_dir,
        fit_min_hours=float(args.fit_min_hours),
        fit_max_hours=float(args.fit_max_hours) if args.fit_max_hours is not None else None,
        plot_times_hours=tuple(float(x) for x in args.plot_times_hours),
        phase_eps=float(args.phase_eps),
        phase_times_hours=tuple(float(x) for x in args.phase_times_hours),
        tau_cont_bootstrap_samples=int(args.tau_cont_bootstrap_samples),
        tau_cont_min_points=int(args.tau_cont_min_points),
        nonparam_bootstrap=int(args.nonparam_bootstrap_samples),
        nonparam_permutation=int(args.nonparam_permutation_samples),
        allow_auto_fallback=bool(args.allow_auto_fallback),
    )


if __name__ == "__main__":
    cli_main()
