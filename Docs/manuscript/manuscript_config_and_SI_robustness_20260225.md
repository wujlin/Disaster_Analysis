# 主文配置与 SI 鲁棒性收尾（2026-02-25）

## 1) 主文配置决策

- 主文采用：`mtw5_mpp4`（`n_selected=14`）。
- SI 敏感性采用：`mtw4_mpp3`（`n_selected=15`）。
- 理由：两组口径方向一致且均显著，`mtw5_mpp4` 更保守，`mtw4_mpp3` 用于展示样本门槛敏感性。

对应结果文件：

- `outputs/cross_disaster_comparison/unified_static_h8_spearman_summary.csv`
- `outputs/cross_disaster_comparison/si_robustness_matrix_unified_static_h8.csv`

## 2) eu_flood 低 R² 的处理方式

- 不做手动剔除，采用 `R strata` 分层报告。
- 在 `mtw5_mpp4` 下：
  - 全样本：`rho=-0.7758, p=0.0011, n=14`
  - `R²>=0.8`：`rho=-0.6273, p=0.0388, n=11`
- 结论：方向保持一致，显著性仍在。

对应结果文件：

- `outputs/cross_disaster_comparison/Dt_decay_unified_h8_mtw5_mpp4/tables/Dt_routeB_alpha_delta_r2_strata.csv`

## 3) beryl_jamaica 身份决策

- 事件：`hurricane_beryl_jamaica_western_caribbean_pre_landfall_2024_07_03`
- 判定：`pre_landfall_valid_event`（保留在 event-level）
- 依据：
  - 锚点来自 NHC 预警发布时刻（catalog 已显式来源）；
  - 在当前口径下拟合可用（`n_time_windows=14, n_total_post=13, n_mono=9`）；
  - `near_delta_peak_windows_mean=-0.4043`，信号充足。
- 执行：不并入 `pre_landfall_only` 排除组；slug 暂不改名，在 SI 注明“预警锚点事件”。

对应结果文件：

- `outputs/cross_disaster_comparison/beryl_jamaica_identity_decision.csv`
- `outputs/cross_disaster_comparison/Dt_decay_unified_h8_mtw4_mpp3/tables/pre_landfall_policy_review.csv`

## 4) SI robustness 矩阵（已合并）

已整合以下模块到一张表：

- 4 组 `mtw/mpp` 敏感性
- `Beryl leave-two-out`
- `R strata`
- `path-distance` 负结果
- `full_post_peak / WLS` 对照

统一汇总文件：

- `outputs/cross_disaster_comparison/si_robustness_matrix_unified_static_h8.csv`

## 5) “WSL 缺失文件同步”状态

- 目标 6 组结果已全部存在（本轮无缺失，无需额外复制）。
- 同步核查表：
  - `outputs/cross_disaster_comparison/wsl_sync_check_6groups.csv`

核查组包括：

1. `beryl_independence`
2. `path_h8`
3. `geo_unit_relaxed`
4. `alpha_truncation`
5. `krathon_compare`
6. `pre_landfall_policy`

