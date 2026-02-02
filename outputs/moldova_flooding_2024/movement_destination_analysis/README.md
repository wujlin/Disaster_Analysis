# Movement 终点分析（按方向筛选）

本目录用于验证：在指定时间窗口 t、指定起点距离带 start_band 下，方向筛选（cos_alpha）后的流动终点主要落在哪些距离范围/距离带。

## 本次运行配置

- slug: moldova_flooding_2024
- center: (47.1820, 28.5516)
- t0_pt: 2024-09-16 16:00:00
- only_hour_pt: 8
- target_hours: 40（实际选取最近窗口 hs=40）
- start_band: 50-100km
- cos_filter: cos_alpha < 0 (inward)
- distance_bins_km: [0.0, 25.0, 50.0, 100.0, 200.0, inf]

## 输出

- `tables/destination_analysis_summary.csv`：本次筛选的样本量与关键比例
- `tables/destination_band_shares.csv`：终点落入各距离带的流量占比
- `tables/destination_distance_hist.csv`：终点距离分布（按 n_crisis 加权）
- `tables/origin_distance_hist.csv`：起点距离分布（按 n_crisis 加权）
- `figures/destination_distance_hist.*`：终点距离直方图（流量占比）
- `figures/origin_distance_hist.*`：起点距离直方图（流量占比）
