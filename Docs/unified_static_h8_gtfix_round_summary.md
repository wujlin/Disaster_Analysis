# unified_static_h8_gtfix 全量重跑记录（2026-03-01）

## 1) 输入与口径
- catalog: `Docs/cross_disaster_catalog_extended_partial_gt_round2_static_center_included39.csv`
- 事件池：34（由 42 去除 8 个 `exclude_reason`）
- phi heatmap:
  - `distance_mode=radial`
  - `hours_pt=[8]`
  - `min_hours=-16`, `max_hours=832`
  - `distance_bin_km=10`, `max_distance_km=500`
  - `allow_auto_fallback=0`, `require_explicit_t0_center=1`
- dt_decay:
  - `r_max=200`, `near_r=50`
  - `min_time_windows=5`, `min_post_peak_steps=4`
  - `fit_method=monotone_truncated`, `fit_min_tprime_hours=24`
- subregion:
  - `use_route_b_selected=1`
  - `quadkey_level=10`
  - `min_tiles_per_unit=5`, `min_time_windows=6`
  - `min_mono_points=3`, `mono_tol_up=1.05`

## 2) 运行结果
### phi_heatmap
- 输出根目录：`outputs/_runs/unified_static_h8_gtfix`
- 成功产出 `phi_rt_long.csv` 的事件数：33
- skip 事件：1
  - `the_flooding_in_benue_and_kogi_states_nigeria`
  - 原因：未找到符合 `hours_pt=[8]` 且 `t∈[-16,832]` 的 population 窗口

### dt_decay
- 目录：`outputs/cross_disaster_comparison/Dt_decay_unified_static_h8_gtfix_mtw5_mpp4`
- `n_total_fits=30`
- `n_selected=18`（`route_b_selected=True`）
- Spearman（alpha vs near_delta）：
  - `rho=-0.69453`
  - `p=0.001382`

### geo_unit_scale（L10）
- 目录：`outputs/cross_disaster_comparison/geo_unit_scale_unified_static_h8_gtfix_mtw5_mpp4`
- `n_selected_events=18`
- `n_fit_events=16`
- mixed-effects（event 随机截距）：
  - `D_peak_unit`: coef `+0.2054`, p `0.0104`（显著）
  - `distance_km`: coef `+3.0e-05`, p `0.0176`（显著）
  - `delta_peak_unit`: coef `+0.0787`, p `0.2117`（不显著）

## 3) 关键产物路径
- phi 跑批日志：`outputs/_runs/unified_static_h8_gtfix/_log_cross_disaster_phi_heatmap.txt`
- phi provenance：`outputs/_runs/unified_static_h8_gtfix/_provenance_phi_heatmap.csv`
- phi skip 列表：`outputs/_runs/unified_static_h8_gtfix/_skipped_phi_heatmap.csv`
- dt 主表：`outputs/cross_disaster_comparison/Dt_decay_unified_static_h8_gtfix_mtw5_mpp4/tables/Dt_routeB_sample_flags.csv`
- dt 相关性：`outputs/cross_disaster_comparison/Dt_decay_unified_static_h8_gtfix_mtw5_mpp4/tables/Dt_routeB_alpha_delta_spearman.csv`
- subregion mixed-effects：`outputs/cross_disaster_comparison/geo_unit_scale_unified_static_h8_gtfix_mtw5_mpp4/tables/mixed_effects_alpha_unit.csv`
