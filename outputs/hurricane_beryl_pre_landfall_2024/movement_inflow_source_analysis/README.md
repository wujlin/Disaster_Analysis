# Movement 流入来源分析（按 start_band 分解）

本目录用于验证：目的地落在某个距离带（默认 25-50km）时，其流入主要来自哪些起点距离带。

## 本次运行配置

- slug: hurricane_beryl_pre_landfall_2024
- center: (11.3154, -61.1969)
- t0_pt: 2024-06-30 16:00:00
- only_hour_pt: 8
- target_hours: 40（实际选取最近窗口 hs=40）
- end_band: 25-50km
- distance_bins_km: [0.0, 25.0, 50.0, 100.0, 200.0, inf]

## 输出

- `tables/inflow_source_by_band.csv`：按 start_band 的流量占比（权重 n_crisis）
- `tables/inflow_source_summary.csv`：本次窗口的关键 share 指标
