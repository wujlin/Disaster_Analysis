# Movement Network Structure (08:00 windows)

本目录对应 `Docs/research_plan_network_redistribution.md` 的 **Task 1**：
用网络结构指标检验“灾害诱导网络集中化”。

## 口径

- 仅使用 PT 08:00 的 movement 文件（控制时段周期性）
- 节点：quadkey（tile）
- 边：无向边（把 start/end 当作无向连接，双向聚合）
- 边权：n_crisis（聚合求和）
- 自环（A→A）：丢弃
- 最小边权：10.0
- 长距离阈值：10.0 km（用于 long_distance_edge_fraction）

## 全局信息

- 处理窗口数：91
- 时间跨度（PT）：2023-02-05 08:00:00 → 2023-05-09 08:00:00

## 主要产物

- `tables/network_metrics_extended.csv`：每个窗口的完整指标
- `tables/network_metrics_summary.csv`：代表性窗口（按 hours_since_quake 最近匹配）
- `figures/centralization_timeseries.*`：degree_centralization 时间序列
- `figures/hub_count_timeseries.*`：hub_count 时间序列
- `figures/distance_distribution_comparison.*`：代表性窗口边距离分布对比
