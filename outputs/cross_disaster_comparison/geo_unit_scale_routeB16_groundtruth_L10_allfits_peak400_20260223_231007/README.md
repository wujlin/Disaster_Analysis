# Geo-unit Scale Analysis (Quadkey L10)

本实验在 Route B 事件集合上，将 L14 tile 通过 `quadkey[:10]` 聚合为子区域（geo-unit），在子区域尺度复现恢复动力学分析。

## 口径（与主分析一致）
- 指标：`phi = sum(n_crisis) / sum(n_baseline)`，`D = |phi - 1|`
- 峰后拟合：`t' >= 24.0h`，单调段（首次反弹截断，`tol_up=1.05`），log-log 斜率 `alpha_unit`
- 严格模式：`require_all_events=0`（有缺失即报错）

## 关键输出
- `tables/geo_unit_timeseries.csv`：子区域时间序列
- `tables/geo_unit_fits.csv`：子区域拟合参数（alpha/D_peak/delta_peak/distance）
- `tables/event_unit_correlations.csv`：事件内相关
- `tables/pooled_unit_correlations.csv`：跨事件汇总相关（含去均值版本）
- `tables/mixed_effects_alpha_unit.csv`：Mixed-effects（event 随机截距）结果
- `tables/event_processing_diagnostics.csv`：预处理诊断
- `tables/geo_unit_fit_diagnostics.csv`：拟合失败原因
- `tables/analysis_availability.csv`：事件可用性
