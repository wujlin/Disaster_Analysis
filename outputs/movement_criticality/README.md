# Movement Criticality Feasibility (Turkey 2023)

本目录用于回答：**Movement（OD）数据能否支撑“网络临界性/渗流扫描”分析？**

## 数据口径（来自 Docs/facebook_data/movement.md）

- 数据：Movement Between Places During Crisis (Bing Tiles)
- 时间窗：相邻 8 小时窗口之间的“转移”（date_time 多为 08:00 / 16:00 PT）
- 指标：每条 OD（start_quadkey → end_quadkey）提供 n_baseline / n_crisis / z_score / percent_change 等
- 隐私保护：小计数向量会被 drop / 置空（因此**不建议**用 inbound/outbound 求净流入来解释）

## 本次输出（你可以直接看这些文件）

- `tables/movement_window_stats.csv`：每个时间窗口的基本统计（OD 对数量、距离分布、n_baseline/n_crisis量级）
- `tables/movement_network_metrics_by_window.csv`：每个时间窗口的网络指标（GCC fraction 等）
- `tables/movement_percolation_scan_selected_windows.csv`：选定窗口的渗流扫描结果
- `figures/movement_order_parameter_gcc_fraction_over_time.*`：order parameter（GCC fraction）随时间
- `figures/movement_percolation_scan_selected_windows.*`：渗流曲线（选定窗口）
- `figures/movement_network_top_edges_selected_windows.*`：网络可视化（每个窗口 top edges）

## 全局摘要（基于 reservoir sample 近似）

- 时间窗口数：182
- 时间跨度（PT）：2023-02-05 08:00:00 → 2023-05-09 16:00:00
- OD 距离（km）分位数：p50=1.95, p90=9.54, p99=21.84
- n_baseline 分位数：p50=21.50, p90=136.17, p99=1645.53
- n_crisis 分位数：p50=20.00, p90=127.00, p99=1739.01

## 网络构建规则（本脚本）

- 节点：quadkey（tile）
- 边：无向边（把 start/end 当作无向连接，且把双向 OD 聚合到同一条无向边）
- 边权：n_crisis（按无向边聚合后求和）
- 自环（A→A）：丢弃（不影响连通性）
- 最小边权阈值：1.0
- order parameter：最大连通分量占比（GCC fraction）

## 复现命令（全量数据示例）

```bash
python scripts/movement_criticality.py \
  --data-root <FULL_DATA_ROOT> \
  --output-dir outputs/movement_criticality \
  --min-edge-weight 1.0 \
  --snapshot-offset-hours -24 24 168 \
  --percolation-n-thresholds 30 \
  --network-top-edges 300
```
