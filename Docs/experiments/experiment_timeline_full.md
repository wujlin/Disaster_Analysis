# 实验时序日志（全量目录，防重复版）

- 生成时间：2026-02-28 14:12:16
- 覆盖实验条目：161
- 覆盖实验键：160
- 时间范围：2026-01-29 23:42:21 ~ 2026-02-28 09:41:41
- 日期来源优先级：目录名时间戳 > 日志/元数据文件时间 > 目录时间

## 防重复建议

1. 新实验前先查 `experiment_timeline_key_summary_full.csv` 的 `key` 是否已存在。
2. 若已存在同 `key`，新结果目录必须带新时间戳或新参数后缀。
3. 复现实验请复用最近 `latest_path`，避免重复跑同参数。

## 重复运行最多的实验键（Top 20）

|root|key|n_runs|first|last|latest_path|
|---|---|---:|---|---|---|
|outputs|_tmp_h3a_track_report|2|2026-02-08 20:54:16|2026-02-08 20:54:17|`/mnt/e/newdesktop/Disaster/outputs/_runs/trackpath/v2/_tmp_h3a_track_report`|
|outputs|Dt_decay|1|2026-02-22 20:12:32|2026-02-22 20:12:32|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay`|
|outputs|Dt_decay_42audit|1|2026-02-23 00:00:00|2026-02-23 00:00:00|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_42audit_20260223`|
|outputs|Dt_decay_42audit_fullpost|1|2026-02-23 00:00:00|2026-02-23 00:00:00|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_42audit_fullpost_20260223`|
|outputs|Dt_decay_AB_newHEAD_on_h0816|1|2026-02-23 00:00:00|2026-02-23 00:00:00|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_AB_newHEAD_on_h0816_20260223`|
|outputs|Dt_decay_AB_old008a4f5_on_h0816|1|2026-02-23 00:00:00|2026-02-23 00:00:00|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_AB_old008a4f5_on_h0816_20260223`|
|outputs|Dt_decay_config_main|1|2026-02-23 00:00:00|2026-02-23 00:00:00|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_config_main_20260223`|
|outputs|Dt_decay_expanded_current_static_h0816|1|2026-02-23 00:00:00|2026-02-23 00:00:00|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_expanded_current_static_h0816_20260223`|
|outputs|Dt_decay_main_current_h0816|1|2026-02-23 00:00:00|2026-02-23 00:00:00|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_main_current_h0816_20260223`|
|outputs|Dt_decay_partial_gt_round2_included32|1|2026-02-24 13:32:40|2026-02-24 13:32:40|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_partial_gt_round2_included32_20260224_133240`|
|outputs|Dt_decay_partial_gt_round2_included32_fullpost|1|2026-02-24 15:38:22|2026-02-24 15:38:22|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_partial_gt_round2_included32_fullpost_20260224_153822`|
|outputs|Dt_decay_rmax100_unified_h8_mtw5_mpp4|1|2026-02-27 09:41:45|2026-02-27 09:41:45|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rmax100_unified_h8_mtw5_mpp4`|
|outputs|Dt_decay_rmax150_unified_h8_mtw5_mpp4|1|2026-02-27 09:42:03|2026-02-27 09:42:03|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rmax150_unified_h8_mtw5_mpp4`|
|outputs|Dt_decay_rmax200_unified_h8_mtw5_mpp4|1|2026-02-27 09:42:18|2026-02-27 09:42:18|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rmax200_unified_h8_mtw5_mpp4`|
|outputs|Dt_decay_rmax250_unified_h8_mtw5_mpp4|1|2026-02-27 09:42:36|2026-02-27 09:42:36|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rmax250_unified_h8_mtw5_mpp4`|
|outputs|Dt_decay_rmax50_unified_h8_mtw5_mpp4|1|2026-02-27 09:41:29|2026-02-27 09:41:29|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rmax50_unified_h8_mtw5_mpp4`|
|outputs|Dt_decay_rnear100_unified_h8_mtw5_mpp4|1|2026-02-27 09:47:27|2026-02-27 09:47:27|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rnear100_unified_h8_mtw5_mpp4`|
|outputs|Dt_decay_rnear30_unified_h8_mtw5_mpp4|1|2026-02-27 09:46:16|2026-02-27 09:46:16|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rnear30_unified_h8_mtw5_mpp4`|
|outputs|Dt_decay_rnear50_unified_h8_mtw5_mpp4|1|2026-02-27 09:46:50|2026-02-27 09:46:50|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rnear50_unified_h8_mtw5_mpp4`|
|outputs|Dt_decay_rnear75_unified_h8_mtw5_mpp4|1|2026-02-27 09:47:08|2026-02-27 09:47:08|`/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rnear75_unified_h8_mtw5_mpp4`|

## 2026-01-29
- 23:42:21 | `/mnt/e/newdesktop/Disaster/outputs/_legacy/output_smoke` | key=`output_smoke` | module | dir_mtime
- 23:42:57 | `/mnt/e/newdesktop/Disaster/outputs/_legacy/output_smoke2` | key=`output_smoke2` | module | dir_mtime

## 2026-01-30
- 00:17:43 | `/mnt/e/newdesktop/Disaster/outputs/_legacy/output_smoke_style` | key=`output_smoke_style` | module | dir_mtime
- 00:19:35 | `/mnt/e/newdesktop/Disaster/outputs/_legacy/output_population` | key=`output_population` | module | dir_mtime
- 09:42:21 | `/mnt/e/newdesktop/Disaster/outputs/_legacy/output_smoke_struct` | key=`output_smoke_struct` | module | dir_mtime
- 09:42:41 | `/mnt/e/newdesktop/Disaster/outputs/_legacy/output_smoke_wrapper` | key=`output_smoke_wrapper` | module | dir_mtime
- 09:45:07 | `/mnt/e/newdesktop/Disaster/outputs/_legacy/output_population_refactored` | key=`output_population_refactored` | module | dir_mtime

## 2026-01-31
- 07:44:04 | `/mnt/e/newdesktop/Disaster/outputs/population_relaxation` | key=`population_relaxation` | module | dir_mtime
- 12:28:35 | `/mnt/e/newdesktop/Disaster/outputs/pop_relax_50km_smoke` | key=`pop_relax_50km_smoke` | module | dir_mtime
- 17:16:14 | `/mnt/e/newdesktop/Disaster/outputs/pop_relax_50km` | key=`pop_relax_50km` | module | dir_mtime

## 2026-02-01
- 10:50:24 | `/mnt/e/newdesktop/Disaster/outputs/movement_criticality` | key=`movement_criticality` | module | dir_mtime
- 12:35:52 | `/mnt/e/newdesktop/Disaster/outputs/movement_network_structure` | key=`movement_network_structure` | module | dir_mtime
- 12:36:39 | `/mnt/e/newdesktop/Disaster/outputs/population_redistribution` | key=`population_redistribution` | module | dir_mtime
- 12:37:24 | `/mnt/e/newdesktop/Disaster/outputs/movement_population_joint` | key=`movement_population_joint` | module | dir_mtime
- 13:50:41 | `/mnt/e/newdesktop/Disaster/outputs/tile_validation` | key=`tile_validation` | module | dir_mtime
- 13:51:02 | `/mnt/e/newdesktop/Disaster/outputs/physical_model` | key=`physical_model` | module | dir_mtime

## 2026-02-02
- 12:22:38 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/phi_fss_collapse` | key=`phi_fss_collapse` | cross_disaster | dir_mtime

## 2026-02-08
- 20:54:11 | `/mnt/e/newdesktop/Disaster/outputs_trackpath_v3/_tmp_phase0` | key=`_tmp_phase0` | tmp | dir_mtime
- 20:54:11 | `/mnt/e/newdesktop/Disaster/outputs_trackpath_v3/_tmp_phase1_minTiles0` | key=`_tmp_phase1_minTiles0` | tmp | dir_mtime
- 20:54:11 | `/mnt/e/newdesktop/Disaster/outputs_trackpath_v3/_tmp_phase1_minTiles50` | key=`_tmp_phase1_minTiles50` | tmp | dir_mtime
- 20:54:11 | `/mnt/e/newdesktop/Disaster/outputs/_runs/centerfix` | key=`centerfix` | run_batch | anchor_file_mtime
- 20:54:11 | `/mnt/e/newdesktop/Disaster/outputs/_runs/centerfix/_tmp_universality_scaling_centerfix6` | key=`_tmp_universality_scaling_centerfix6` | run_batch | anchor_file_mtime
- 20:54:16 | `/mnt/e/newdesktop/Disaster/outputs/_runs/dfg/batch1/_tmp_universality_scaling_dfg_batch1` | key=`_tmp_universality_scaling_dfg_batch1` | run_batch | anchor_file_mtime
- 20:54:16 | `/mnt/e/newdesktop/Disaster/outputs/_runs/dfg/batch1` | key=`batch1` | run_batch | dir_mtime
- 20:54:16 | `/mnt/e/newdesktop/Disaster/outputs/_runs/dfg` | key=`dfg` | run_batch | dir_mtime
- 20:54:16 | `/mnt/e/newdesktop/Disaster/outputs/_runs/dfg/batch1_anchor/_tmp_universality_scaling_dfg_batch1_anchor` | key=`_tmp_universality_scaling_dfg_batch1_anchor` | run_batch | anchor_file_mtime
- 20:54:16 | `/mnt/e/newdesktop/Disaster/outputs/_runs/dfg/batch1_anchor` | key=`batch1_anchor` | run_batch | dir_mtime
- 20:54:16 | `/mnt/e/newdesktop/Disaster/outputs/_runs/trackpath/v1` | key=`v1` | run_batch | anchor_file_mtime
- 20:54:16 | `/mnt/e/newdesktop/Disaster/outputs/_runs/trackpath/v1/_tmp_h3a_mechanism` | key=`_tmp_h3a_mechanism` | run_batch | dir_mtime
- 20:54:16 | `/mnt/e/newdesktop/Disaster/outputs/_runs/trackpath/v1/_tmp_h3a_track_collapse` | key=`_tmp_h3a_track_collapse` | run_batch | anchor_file_mtime
- 20:54:16 | `/mnt/e/newdesktop/Disaster/outputs/_runs/trackpath/v1/_tmp_h3a_track_collapse_min50` | key=`_tmp_h3a_track_collapse_min50` | run_batch | dir_mtime
- 20:54:16 | `/mnt/e/newdesktop/Disaster/outputs/_runs/trackpath/v1/_tmp_h3a_track_report` | key=`_tmp_h3a_track_report` | run_batch | dir_mtime
- 20:54:17 | `/mnt/e/newdesktop/Disaster/outputs/_runs/trackpath/v2` | key=`v2` | run_batch | anchor_file_mtime
- 20:54:17 | `/mnt/e/newdesktop/Disaster/outputs/_runs/trackpath/v2/_tmp_h3a_track_report` | key=`_tmp_h3a_track_report` | run_batch | anchor_file_mtime
- 20:54:17 | `/mnt/e/newdesktop/Disaster/outputs/_runs/trackpath/v2/_tmp_phase2_minTiles0` | key=`_tmp_phase2_minTiles0` | run_batch | anchor_file_mtime
- 20:54:17 | `/mnt/e/newdesktop/Disaster/outputs/_runs/trackpath/v2/_tmp_phase2_minTiles50` | key=`_tmp_phase2_minTiles50` | run_batch | anchor_file_mtime
- 20:54:17 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/svd_separability_nullN50` | key=`svd_separability_nullN50` | cross_disaster | anchor_file_mtime
- 21:58:06 | `/mnt/e/newdesktop/Disaster/outputs/_runs/trackpath` | key=`trackpath` | run_batch | dir_mtime
- 21:58:12 | `/mnt/e/newdesktop/Disaster/outputs/_runs/trackpath/v4_yagi_fix` | key=`v4_yagi_fix` | run_batch | anchor_file_mtime
- 22:01:23 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/svd_modes` | key=`svd_modes` | cross_disaster | dir_mtime
- 22:04:25 | `/mnt/e/newdesktop/Disaster/outputs/_runs/trackpath/v3` | key=`v3` | run_batch | anchor_file_mtime
- 22:04:54 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/svd_separability` | key=`svd_separability` | cross_disaster | anchor_file_mtime
- 22:04:59 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/svd_separability_nullN200` | key=`svd_separability_nullN200` | cross_disaster | anchor_file_mtime
- 22:05:06 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/svd_sensitivity_rmax` | key=`svd_sensitivity_rmax` | cross_disaster | anchor_file_mtime
- 22:05:14 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/rank1_dynamics` | key=`rank1_dynamics` | cross_disaster | anchor_file_mtime

## 2026-02-09
- 17:10:29 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/g1_model_comparison_tier1` | key=`g1_model_comparison_tier1` | cross_disaster | anchor_file_mtime
- 22:58:13 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/time_alignment` | key=`time_alignment` | cross_disaster | anchor_file_mtime
- 22:59:49 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/rank1_dynamics_sigma070` | key=`rank1_dynamics_sigma070` | cross_disaster | anchor_file_mtime
- 23:00:41 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/rank1_dynamics_sigma070_min4` | key=`rank1_dynamics_sigma070_min4` | cross_disaster | anchor_file_mtime
- 23:02:49 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/g1_timeseries_viz_helene_milton` | key=`g1_timeseries_viz_helene_milton` | cross_disaster | dir_mtime
- 23:06:50 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/g1_model_comparison_all` | key=`g1_model_comparison_all` | cross_disaster | anchor_file_mtime
- 23:11:52 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/fr_mode_time0_72` | key=`fr_mode_time0_72` | cross_disaster | anchor_file_mtime

## 2026-02-22
- 17:50:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/dynamics_potential_nonparam_exp3_smoke` | key=`dynamics_potential_nonparam_exp3_smoke` | cross_disaster | anchor_file_mtime
- 17:50:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/dynamics_potential_routeB_exp12` | key=`dynamics_potential_routeB_exp12` | cross_disaster | anchor_file_mtime
- 17:50:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/dynamics_potential_routeB_exp12_nonparam_smoke` | key=`dynamics_potential_routeB_exp12_nonparam_smoke` | cross_disaster | anchor_file_mtime
- 17:50:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/dynamics_potential_routeB_nonparam_exp12_strict_smoke` | key=`dynamics_potential_routeB_nonparam_exp12_strict_smoke` | cross_disaster | anchor_file_mtime
- 17:50:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/dynamics_potential_routeB_nonparam_exp3` | key=`dynamics_potential_routeB_nonparam_exp3` | cross_disaster | anchor_file_mtime
- 17:50:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/dynamics_potential_smoke` | key=`dynamics_potential_smoke` | cross_disaster | anchor_file_mtime
- 17:50:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/dynamics_potential_smoke2` | key=`dynamics_potential_smoke2` | cross_disaster | anchor_file_mtime
- 17:50:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/external_covariates` | key=`external_covariates` | cross_disaster | dir_mtime
- 17:50:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/fr_mode_time0_72_nojohn` | key=`fr_mode_time0_72_nojohn` | cross_disaster | anchor_file_mtime
- 17:50:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/g1_timeseries_viz_helene_milton_nojohn` | key=`g1_timeseries_viz_helene_milton_nojohn` | cross_disaster | dir_mtime
- 17:50:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/movement_analysis` | key=`movement_analysis` | cross_disaster | anchor_file_mtime
- 17:50:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/nonlinear_pde` | key=`nonlinear_pde` | cross_disaster | dir_mtime
- 17:50:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/rank1_dynamics_sigma070_min4_nojohn` | key=`rank1_dynamics_sigma070_min4_nojohn` | cross_disaster | anchor_file_mtime
- 17:50:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/rank1_dynamics_sigma090_min4_fill` | key=`rank1_dynamics_sigma090_min4_fill` | cross_disaster | anchor_file_mtime
- 17:50:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/spatial_diffusion_results` | key=`spatial_diffusion_results` | cross_disaster | anchor_file_mtime
- 20:04:34 | `/mnt/e/newdesktop/Disaster/outputs/_runs/dfg_collection` | key=`dfg_collection` | run_batch | dir_mtime
- 20:05:38 | `/mnt/e/newdesktop/Disaster/outputs/_runs/wsa_full_pipeline_mnt_20260222_200540/logs` | key=`logs` | run_batch | anchor_file_mtime
- 20:05:40 | `/mnt/e/newdesktop/Disaster/outputs/_runs/wsa_full_pipeline_mnt_20260222_200540` | key=`wsa_full_pipeline_mnt` | run_batch | name_timestamp
- 20:12:32 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay` | key=`Dt_decay` | cross_disaster | anchor_file_mtime
- 20:13:10 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/dynamics_potential_all` | key=`dynamics_potential_all` | cross_disaster | anchor_file_mtime
- 20:13:43 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/dynamics_potential_routeB` | key=`dynamics_potential_routeB` | cross_disaster | anchor_file_mtime
- 23:18:28 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_routeB_L10` | key=`geo_unit_scale_routeB_L10` | cross_disaster | anchor_file_mtime

## 2026-02-23
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/_runs/expanded_current_h0816_20260223` | key=`expanded_current_h0816` | run_batch | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/_runs/expanded_current_static_h0816_20260223` | key=`expanded_current_static_h0816` | run_batch | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/_runs/main_current_h0816_20260223` | key=`main_current_h0816` | run_batch | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/_runs/routeB16_config_main_20260223` | key=`routeB16_config_main` | run_batch | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/_runs/routeB16_groundtruth_20260223` | key=`routeB16_groundtruth` | run_batch | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_42audit_20260223` | key=`Dt_decay_42audit` | cross_disaster | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_42audit_fullpost_20260223` | key=`Dt_decay_42audit_fullpost` | cross_disaster | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_AB_newHEAD_on_h0816_20260223` | key=`Dt_decay_AB_newHEAD_on_h0816` | cross_disaster | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_AB_old008a4f5_on_h0816_20260223` | key=`Dt_decay_AB_old008a4f5_on_h0816` | cross_disaster | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_config_main_20260223` | key=`Dt_decay_config_main` | cross_disaster | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_expanded_current_static_h0816_20260223` | key=`Dt_decay_expanded_current_static_h0816` | cross_disaster | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_main_current_h0816_20260223` | key=`Dt_decay_main_current_h0816` | cross_disaster | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_routeB16_config_main_20260223` | key=`Dt_decay_routeB16_config_main` | cross_disaster | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_routeB16_groundtruth_20260223` | key=`Dt_decay_routeB16_groundtruth` | cross_disaster | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_truncation_compare_20260223` | key=`Dt_decay_truncation_compare` | cross_disaster | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_truncation_compare_partner_20260223` | key=`Dt_decay_truncation_compare_partner` | cross_disaster | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_routeB16_config_main_L10_20260223` | key=`geo_unit_scale_routeB16_config_main_L10` | cross_disaster | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/phi_AB_old_vs_new_h0816_20260223` | key=`phi_AB_old_vs_new_h0816` | cross_disaster | name_timestamp
- 00:00:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/routeB16_postgate_config_main_20260223` | key=`routeB16_postgate_config_main` | cross_disaster | name_timestamp
- 00:12:47 | `/mnt/e/newdesktop/Disaster/outputs/_runs/unified_radial8h_20260223_001247` | key=`unified_radial8h` | run_batch | name_timestamp
- 00:12:47 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_unified_radial8h_20260223_001247` | key=`Dt_decay_unified_radial8h` | cross_disaster | name_timestamp
- 10:12:20 | `/mnt/e/newdesktop/Disaster/outputs/_runs/routeB16_frozen_radial_20260223_101220` | key=`routeB16_frozen_radial` | run_batch | name_timestamp
- 10:12:20 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_routeB16_frozen_20260223_101220` | key=`Dt_decay_routeB16_frozen` | cross_disaster | name_timestamp
- 10:12:20 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/routeB16_frozen_postgate_20260223_101220` | key=`routeB16_frozen_postgate` | cross_disaster | name_timestamp
- 10:16:24 | `/mnt/e/newdesktop/Disaster/outputs/_runs/routeB16_frozen_radial_h0816_20260223_101624` | key=`routeB16_frozen_radial_h0816` | run_batch | name_timestamp
- 10:16:24 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_routeB16_frozen_h0816_20260223_101624` | key=`Dt_decay_routeB16_frozen_h0816` | cross_disaster | name_timestamp
- 10:16:24 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/routeB16_frozen_postgate_h0816_20260223_101624` | key=`routeB16_frozen_postgate_h0816` | cross_disaster | name_timestamp
- 10:50:10 | `/mnt/e/newdesktop/Disaster/outputs/_runs/phi_AB_old008a4f5_routeB16_h0816_20260223_105010` | key=`phi_AB_old008a4f5_routeB16_h0816` | run_batch | name_timestamp
- 11:55:08 | `/mnt/e/newdesktop/Disaster/outputs/_runs/routeB16_legacy_repro_pinned` | key=`routeB16_legacy_repro_pinned` | run_batch | anchor_file_mtime
- 11:55:08 | `/mnt/e/newdesktop/Disaster/outputs/_runs/routeB16_legacy_repro` | key=`routeB16_legacy_repro` | run_batch | anchor_file_mtime
- 11:55:29 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_routeB16_legacy_repro` | key=`Dt_decay_routeB16_legacy_repro` | cross_disaster | anchor_file_mtime
- 11:56:05 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/routeB16_legacy_repro_postgate` | key=`routeB16_legacy_repro_postgate` | cross_disaster | dir_mtime
- 11:58:15 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_routeB16_legacy_repro_pinned` | key=`Dt_decay_routeB16_legacy_repro_pinned` | cross_disaster | anchor_file_mtime
- 11:58:42 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/routeB16_legacy_repro_pinned_postgate` | key=`routeB16_legacy_repro_pinned_postgate` | cross_disaster | dir_mtime
- 12:00:11 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_routeB16_legacy_repro_L10` | key=`geo_unit_scale_routeB16_legacy_repro_L10` | cross_disaster | anchor_file_mtime
- 12:00:58 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/routeB16_frozen_h0816_postgate` | key=`routeB16_frozen_h0816_postgate` | cross_disaster | dir_mtime
- 12:03:57 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_routeB16_main_current_h0816_L10` | key=`geo_unit_scale_routeB16_main_current_h0816_L10` | cross_disaster | anchor_file_mtime
- 13:57:54 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/routeB16_main_current_h0816_20260223_postgate` | key=`routeB16_main_current_h0816_20260223_postgate` | cross_disaster | dir_mtime
- 14:08:02 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_main_current_h0816_20260223_L10_excl_mexico` | key=`geo_unit_scale_main_current_h0816_20260223_L10_excl_mexico` | cross_disaster | anchor_file_mtime
- 14:09:23 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_expanded_current_static_h0816_20260223_L10` | key=`geo_unit_scale_expanded_current_static_h0816_20260223_L10` | cross_disaster | anchor_file_mtime
- 17:15:36 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/routeB16_postgate_config_main_20260223_expected14` | key=`routeB16_postgate_config_main_20260223_expected14` | cross_disaster | dir_mtime
- 17:25:00 | `/mnt/e/newdesktop/Disaster/outputs/_runs/routeB16_partner_opinion_main_20260223_1725` | key=`routeB16_partner_opinion_main` | run_batch | name_timestamp
- 17:25:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_routeB16_partner_opinion_main_20260223_1725` | key=`Dt_decay_routeB16_partner_opinion_main` | cross_disaster | name_timestamp
- 17:25:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_routeB16_partner_opinion_L10_20260223_1725` | key=`geo_unit_scale_routeB16_partner_opinion_L10` | cross_disaster | name_timestamp
- 17:25:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_routeB16_partner_opinion_L8_20260223_1725` | key=`geo_unit_scale_routeB16_partner_opinion_L8` | cross_disaster | name_timestamp
- 17:25:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/partner_opinion_checklist_20260223_1725` | key=`partner_opinion_checklist` | cross_disaster | name_timestamp
- 17:25:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/routeB16_postgate_partner_opinion_20260223_1725` | key=`routeB16_postgate_partner_opinion` | cross_disaster | name_timestamp
- 17:25:00 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/sensitivity_near_r_rmax_partner_20260223_1725` | key=`sensitivity_near_r_rmax_partner` | cross_disaster | name_timestamp
- 22:39:20 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_routeA_open_20260223_223920` | key=`Dt_decay_routeA_open` | cross_disaster | name_timestamp
- 22:58:21 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_routeB16_groundtruth_L10_20260223_225821` | key=`geo_unit_scale_routeB16_groundtruth_L10` | cross_disaster | name_timestamp
- 22:59:54 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_routeB16_groundtruth_L10_allfits_20260223_225954` | key=`geo_unit_scale_routeB16_groundtruth_L10_allfits` | cross_disaster | name_timestamp
- 23:01:21 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_routeB16_groundtruth_L10_allfits_relaxed_20260223_230121` | key=`geo_unit_scale_routeB16_groundtruth_L10_allfits_relaxed` | cross_disaster | name_timestamp
- 23:10:07 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_routeB16_groundtruth_L10_allfits_peak400_20260223_231007` | key=`geo_unit_scale_routeB16_groundtruth_L10_allfits_peak400` | cross_disaster | name_timestamp
- 23:22:44 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_42_all_20260223_232244` | key=`geo_unit_scale_42_all` | cross_disaster | name_timestamp

## 2026-02-24
- 00:07:12 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_routeB16_groundtruth_all16_peak168_20260224_000712` | key=`geo_unit_scale_routeB16_groundtruth_all16_peak168` | cross_disaster | name_timestamp
- 00:08:52 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_routeB16_groundtruth_all16_peak400_20260224_000852` | key=`geo_unit_scale_routeB16_groundtruth_all16_peak400` | cross_disaster | name_timestamp
- 13:28:24 | `/mnt/e/newdesktop/Disaster/outputs/_runs/partial_gt_round2_included32` | key=`partial_gt_round2_included32` | run_batch | anchor_file_mtime
- 13:28:36 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_partial_gt_round2_included32_20260224_132836` | key=`geo_unit_scale_partial_gt_round2_included32` | cross_disaster | name_timestamp
- 13:32:40 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_partial_gt_round2_included32_20260224_133240` | key=`Dt_decay_partial_gt_round2_included32` | cross_disaster | name_timestamp
- 15:38:22 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_partial_gt_round2_included32_fullpost_20260224_153822` | key=`Dt_decay_partial_gt_round2_included32_fullpost` | cross_disaster | name_timestamp
- 23:30:23 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_static_center_mtw5` | key=`Dt_decay_static_center_mtw5` | cross_disaster | anchor_file_mtime
- 23:30:48 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_static_center_mtw4` | key=`Dt_decay_static_center_mtw4` | cross_disaster | anchor_file_mtime
- 23:31:16 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_static_center_mtw4_mpp3` | key=`Dt_decay_static_center_mtw4_mpp3` | cross_disaster | anchor_file_mtime
- 23:55:40 | `/mnt/e/newdesktop/Disaster/outputs/_runs/unified_static_h8` | key=`unified_static_h8` | run_batch | anchor_file_mtime
- 23:56:56 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_unified_h8_mtw5_mpp4` | key=`Dt_decay_unified_h8_mtw5_mpp4` | cross_disaster | anchor_file_mtime
- 23:57:15 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_unified_h8_mtw4_mpp4` | key=`Dt_decay_unified_h8_mtw4_mpp4` | cross_disaster | anchor_file_mtime
- 23:57:31 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_unified_h8_mtw4_mpp3` | key=`Dt_decay_unified_h8_mtw4_mpp3` | cross_disaster | anchor_file_mtime
- 23:57:47 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_unified_h8_mtw5_mpp3` | key=`Dt_decay_unified_h8_mtw5_mpp3` | cross_disaster | anchor_file_mtime

## 2026-02-25
- 13:56:45 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/beryl_independence_unified_h8_mtw5_mpp4` | key=`beryl_independence_unified_h8_mtw5_mpp4` | cross_disaster | dir_mtime
- 13:57:09 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_unified_h8_mtw5_mpp4_20260225_135709` | key=`geo_unit_scale_unified_h8_mtw5_mpp4` | cross_disaster | name_timestamp
- 13:59:58 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/alpha_truncation_unified_h8_mtw4_mpp3` | key=`alpha_truncation_unified_h8_mtw4_mpp3` | cross_disaster | anchor_file_mtime
- 14:02:20 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/krathon_unified_vs_round2` | key=`krathon_unified_vs_round2` | cross_disaster | dir_mtime
- 14:14:39 | `/mnt/e/newdesktop/Disaster/outputs/_runs/unified_path_h8_$(date +%Y%m%d_%H%M%S)` | key=`unified_path_h8_$(date +%Y%m%d_%H%M%S)` | run_batch | anchor_file_mtime
- 14:15:04 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_unified_h8_mtw4_mpp3_20260225_141504` | key=`geo_unit_scale_unified_h8_mtw4_mpp3` | cross_disaster | name_timestamp
- 14:16:30 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/geo_unit_scale_unified_h8_mtw4_mpp3_relaxed_20260225_141630` | key=`geo_unit_scale_unified_h8_mtw4_mpp3_relaxed` | cross_disaster | name_timestamp
- 14:18:47 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_unified_path_h8_mtw4_mpp3_$(date +%Y%m%d_%H%M%S)` | key=`Dt_decay_unified_path_h8_mtw4_mpp3_$(date +%Y%m%d_%H%M%S)` | cross_disaster | anchor_file_mtime

## 2026-02-27
- 09:41:29 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rmax50_unified_h8_mtw5_mpp4` | key=`Dt_decay_rmax50_unified_h8_mtw5_mpp4` | cross_disaster | anchor_file_mtime
- 09:41:45 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rmax100_unified_h8_mtw5_mpp4` | key=`Dt_decay_rmax100_unified_h8_mtw5_mpp4` | cross_disaster | anchor_file_mtime
- 09:42:03 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rmax150_unified_h8_mtw5_mpp4` | key=`Dt_decay_rmax150_unified_h8_mtw5_mpp4` | cross_disaster | anchor_file_mtime
- 09:42:18 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rmax200_unified_h8_mtw5_mpp4` | key=`Dt_decay_rmax200_unified_h8_mtw5_mpp4` | cross_disaster | anchor_file_mtime
- 09:42:36 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rmax250_unified_h8_mtw5_mpp4` | key=`Dt_decay_rmax250_unified_h8_mtw5_mpp4` | cross_disaster | anchor_file_mtime
- 09:44:16 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/subregion_joint_model_unified_h8` | key=`subregion_joint_model_unified_h8` | cross_disaster | anchor_file_mtime
- 09:46:16 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rnear30_unified_h8_mtw5_mpp4` | key=`Dt_decay_rnear30_unified_h8_mtw5_mpp4` | cross_disaster | anchor_file_mtime
- 09:46:50 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rnear50_unified_h8_mtw5_mpp4` | key=`Dt_decay_rnear50_unified_h8_mtw5_mpp4` | cross_disaster | anchor_file_mtime
- 09:47:08 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rnear75_unified_h8_mtw5_mpp4` | key=`Dt_decay_rnear75_unified_h8_mtw5_mpp4` | cross_disaster | anchor_file_mtime
- 09:47:27 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/Dt_decay_rnear100_unified_h8_mtw5_mpp4` | key=`Dt_decay_rnear100_unified_h8_mtw5_mpp4` | cross_disaster | anchor_file_mtime

## 2026-02-28
- 09:41:41 | `/mnt/e/newdesktop/Disaster/outputs/cross_disaster_comparison/subregion_model_correction_unified_h8` | key=`subregion_model_correction_unified_h8` | cross_disaster | anchor_file_mtime

