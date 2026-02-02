# Movement 方向极化分析

本目录实现 PI 提案的 **Movement 方向极化** 指标：

- 对每条 OD（i→j），定义
  - 流动向量：v = (lat_j-lat_i, lon_j-lon_i)
  - 径向向量：r = (lat_i-lat_c, lon_i-lon_c)
  - cos_alpha = (v·r)/(|v||r|)
- 按 (distance_band, time_window) 聚合：
  - F_r = Σ n_crisis · cos_alpha
  - F_total = Σ n_crisis
  - P = F_r / F_total ∈ [-1,1]（>0 外流；<0 内流）
  - A = |F_r| / F_total ∈ [0,1]

## 配置

- slug: hurricane_beryl_pre_landfall_2024
- center: (11.3154, -61.1969)
- t0_pt: 2024-06-30 16:00:00
- only_hour_pt: 8
- time range (hours_since_quake): [-16.0, 832.0]
- distance_bins_km: [0.0, 25.0, 50.0, 100.0, 200.0, inf]

## 输出

- `tables/flow_directional_by_band_time.csv`：长表（band×time 的 F_r/F_total/P/A）
- `tables/polarization_time_series.csv`：宽表（每行一个窗口，列为各距离带的 P）
- `tables/polarization_summary.csv`：每距离带的峰值与首次方向反转（相邻窗口符号翻转）
- `figures/polarization_heatmap_hurricane_beryl_pre_landfall_2024.*`：P(r,t) 热图
- `figures/polarization_time_series.*`：P(t) 时间序列（多距离带）
- `figures/polarization_vs_distance_t*h.*`：选定时间点的 P(r)

## 覆盖时间（PT）

- 2024-06-30 08:00:00 → 2024-07-31 08:00:00
