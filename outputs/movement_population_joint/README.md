# Movement-Population Joint Analysis (08:00 windows)

本目录对应 `Docs/research_plan_network_redistribution.md` 的 **Task 3**：
把 Movement（OD）与 Population（tile）合并，检验“网络重组 ↔ 人口再分布”的空间关联。

## 口径

- 仅使用 PT 08:00 窗口
- population phi_ratio = n_crisis / n_baseline
- movement net_inflow = sum(inflow n_crisis) - sum(outflow n_crisis)（按 quadkey 聚合）
- hub：degree > 2.0 * avg_degree（在无向 OD 图上，度为 unweighted degree）
- 长距离：length_km > 10.0 km

## 代表性窗口（按 hours_since_quake 最近匹配）

-8h, 16h, 40h, 88h, 160h, 328h, 832h

## 输出

- `tables/tile_level_joint_metrics.csv`：代表性窗口的 tile-level phi_ratio + (inflow/outflow/net_inflow)
- `tables/phi_vs_net_inflow_correlation.csv`：每个代表性窗口的相关系数
- `tables/hub_comparison.csv`：震前/震后 hub 与 new_hubs
- `tables/long_distance_destinations.csv`：长距离 OD 的主要目的地（post window）
