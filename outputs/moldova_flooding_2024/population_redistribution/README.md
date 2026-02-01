# Population Redistribution (08:00 windows)

本目录对应 `Docs/research_plan_network_redistribution.md` 的 **Task 2**：
用“空间再分布”而非“relaxation”视角刻画人口变化。

## 口径

- 仅使用 PT 08:00 的 population 文件（控制时段周期性）
- phi_ratio = n_crisis / n_baseline
- outflow：phi_ratio < 0.9
- inflow：phi_ratio > 1.1

## 全局信息

- 处理窗口数：28
- 时间跨度（PT）：2024-09-16 08:00:00 → 2024-10-13 08:00:00

## 主要产物

- `tables/redistribution_by_window.csv`：每个窗口的再分布指标（tile 计数、质心、净变化）
- `tables/redistribution_by_distance_band.csv`：按距离带的 phi_aggregate / net_change 时间序列
- `tables/flow_classification_summary.csv`：outflow/stable/inflow 的 tile 计数
- `figures/phi_aggregate_heatmap.*`：phi_aggregate(distance,time) 热力图
- `tables/redistribution_by_distance_band.csv` 额外列：
  - `n_tiles_crisis` / `crisis_mean` / `tile_coverage_ratio`（crisis 端可见性代理）
  - `n_tiles_overlap` / `crisis_mean_overlap` / `tile_overlap_ratio`（baseline∩crisis overlap 子集，避免新 tiles 稀释）
