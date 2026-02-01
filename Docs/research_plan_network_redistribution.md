# 研究方案：灾害诱导的网络重组与人口再分布

> **核心发现**：土耳其地震数据显示，灾后网络连通性**增强**而非碎片化（GCC 规模扩大 3.5 倍）。这与传统"灾害破坏网络"假设相反，暗示灾害可能诱导网络从分布式向中心化重组。

---

## 研究目标

验证并量化"灾害诱导网络集中化"现象，建立 Movement 网络结构变化与 Population 空间再分布的关联。

---

## 任务一：Movement 网络结构深度分析

### 1.1 目标

用多种网络指标验证"集中化"pattern，排除采样偏差的可能性。

### 1.2 需要计算的指标

对每个时间窗口计算以下指标：

```python
# 基础结构指标
- n_nodes: 节点数
- n_edges: 边数  
- density: 网络密度 = 2*n_edges / (n_nodes * (n_nodes-1))
- avg_degree: 平均度 = 2*n_edges / n_nodes

# 连通性指标
- gcc_fraction: 最大连通分量占比（已有）
- n_components: 连通分量数量
- component_size_std: 连通分量大小的标准差

# 中心化指标（关键！）
- degree_centralization: 度中心化指数 = sum(max_degree - degree_i) / max_possible
- top10_degree_share: 度数最高的10%节点占所有边的比例
- hub_count: 度数 > 2*avg_degree 的节点数

# 空间结构指标
- avg_edge_distance: 平均 OD 距离（km）
- long_distance_edge_fraction: 距离 > 10km 的边占比
- distance_p90: OD 距离的 90 分位数
```

### 1.3 实现要点

```python
# 使用 networkx 计算
import networkx as nx

def compute_network_metrics(G, edge_distances):
    """
    G: networkx Graph (undirected, weighted by n_crisis)
    edge_distances: dict {(u,v): distance_km}
    """
    metrics = {}
    
    # 基础指标
    metrics['n_nodes'] = G.number_of_nodes()
    metrics['n_edges'] = G.number_of_edges()
    metrics['density'] = nx.density(G)
    metrics['avg_degree'] = 2 * G.number_of_edges() / G.number_of_nodes()
    
    # 连通性
    components = list(nx.connected_components(G))
    metrics['n_components'] = len(components)
    component_sizes = [len(c) for c in components]
    metrics['gcc_fraction'] = max(component_sizes) / G.number_of_nodes()
    metrics['component_size_std'] = np.std(component_sizes)
    
    # 度中心化
    degrees = [d for n, d in G.degree()]
    max_degree = max(degrees)
    n = G.number_of_nodes()
    metrics['degree_centralization'] = sum(max_degree - d for d in degrees) / ((n-1)*(n-2))
    
    # Hub 分析
    avg_deg = metrics['avg_degree']
    metrics['hub_count'] = sum(1 for d in degrees if d > 2 * avg_deg)
    
    # Top 10% 节点的边占比
    sorted_degrees = sorted(degrees, reverse=True)
    top_10_pct = int(0.1 * n) or 1
    metrics['top10_degree_share'] = sum(sorted_degrees[:top_10_pct]) / sum(degrees)
    
    # 空间指标
    distances = list(edge_distances.values())
    metrics['avg_edge_distance'] = np.mean(distances)
    metrics['distance_p90'] = np.percentile(distances, 90)
    metrics['long_distance_edge_fraction'] = sum(1 for d in distances if d > 10) / len(distances)
    
    return metrics
```

### 1.4 输出文件

```
outputs/movement_network_structure/
├── tables/
│   ├── network_metrics_extended.csv          # 每个窗口的完整指标
│   └── network_metrics_summary.csv           # 震前/震后/恢复期对比
├── figures/
│   ├── centralization_timeseries.png         # 中心化指数随时间变化
│   ├── hub_count_timeseries.png              # Hub 数量随时间变化
│   └── distance_distribution_comparison.png  # 震前/震后 OD 距离分布对比
└── README.md
```

### 1.5 关键假设检验

| 假设 | 预期结果（如果"集中化"成立） | 验证方法 |
|------|------------------------------|----------|
| H1: 网络变得更中心化 | degree_centralization 震后 > 震前 | 时间序列对比 |
| H2: Hub 节点增加 | hub_count 震后 > 震前 | 时间序列对比 |
| H3: 远距离流动增加 | long_distance_edge_fraction 震后 > 震前 | 时间序列对比 |
| H4: 连通分量合并 | n_components 震后 < 震前 | 时间序列对比 |

---

## 任务二：Population 空间再分布分析

### 2.1 目标

放弃"relaxation"框架，改用**空间再分布**视角分析人口变化。

### 2.2 核心问题

1. 人口从哪里流出？流向哪里？
2. 流出/流入的空间pattern是什么？（距震中距离？城市等级？）
3. 再分布的timescale是多少？

### 2.3 需要计算的指标

```python
# 对每个 tile（空间单元）计算
- phi = n_crisis / n_baseline  # 人口相对变化（已有）
- is_outflow = phi < 0.9       # 人口显著流出（< 10% 下降）
- is_inflow = phi > 1.1        # 人口显著流入（> 10% 上升）

# 对每个时间窗口计算
- outflow_tile_count: 流出 tile 数量
- inflow_tile_count: 流入 tile 数量
- net_population_change: sum(n_crisis - n_baseline) across all tiles
- outflow_centroid: 流出区域的质心（经纬度）
- inflow_centroid: 流入区域的质心（经纬度）
- outflow_avg_distance: 流出区域到震中的平均距离
- inflow_avg_distance: 流入区域到震中的平均距离

# 按距离分层
for each distance_bin (0-25km, 25-50km, 50-100km, 100-200km, >200km):
    - total_baseline_population
    - total_crisis_population  
    - net_change
    - phi_aggregate = sum(n_crisis) / sum(n_baseline)
```

### 2.4 实现要点

```python
def compute_redistribution_metrics(df_population, quake_lat, quake_lon):
    """
    df_population: DataFrame with columns [bing_tile_id, lat, lon, n_baseline, n_crisis]
    """
    # 计算到震中距离
    df_population['distance_km'] = haversine(
        quake_lat, quake_lon, 
        df_population['lat'], df_population['lon']
    )
    
    # 分类
    df_population['phi'] = df_population['n_crisis'] / df_population['n_baseline']
    df_population['flow_type'] = pd.cut(
        df_population['phi'],
        bins=[0, 0.9, 1.1, np.inf],
        labels=['outflow', 'stable', 'inflow']
    )
    
    # 统计
    outflow = df_population[df_population['flow_type'] == 'outflow']
    inflow = df_population[df_population['flow_type'] == 'inflow']
    
    metrics = {
        'outflow_tile_count': len(outflow),
        'inflow_tile_count': len(inflow),
        'outflow_avg_distance': outflow['distance_km'].mean(),
        'inflow_avg_distance': inflow['distance_km'].mean(),
        # weighted centroid
        'outflow_centroid_lat': np.average(outflow['lat'], weights=outflow['n_baseline']),
        'outflow_centroid_lon': np.average(outflow['lon'], weights=outflow['n_baseline']),
    }
    
    # 按距离分层
    distance_bins = [0, 25, 50, 100, 200, np.inf]
    for i in range(len(distance_bins)-1):
        mask = (df_population['distance_km'] >= distance_bins[i]) & \
               (df_population['distance_km'] < distance_bins[i+1])
        subset = df_population[mask]
        bin_name = f"{distance_bins[i]}-{distance_bins[i+1]}km"
        metrics[f'phi_aggregate_{bin_name}'] = subset['n_crisis'].sum() / subset['n_baseline'].sum()
        metrics[f'net_change_{bin_name}'] = (subset['n_crisis'] - subset['n_baseline']).sum()
    
    return metrics
```

### 2.5 输出文件

```
outputs/population_redistribution/
├── tables/
│   ├── redistribution_by_window.csv          # 每个窗口的再分布指标
│   ├── redistribution_by_distance_band.csv   # 按距离带的 phi_aggregate 时间序列
│   └── flow_classification_summary.csv       # outflow/stable/inflow tile 统计
├── figures/
│   ├── net_change_by_distance_timeseries.png # 各距离带净人口变化
│   ├── inflow_outflow_spatial.png            # 流入/流出区域空间分布图
│   └── phi_aggregate_heatmap.png             # phi_aggregate(distance, time) 热力图
└── README.md
```

### 2.6 关键假设检验

| 假设 | 预期结果 | 验证方法 |
|------|----------|----------|
| H1: 近震中区域人口外流 | phi_aggregate(0-50km) < 1 | 时间序列 |
| H2: 远离震中区域人口流入 | phi_aggregate(>100km) > 1 | 时间序列 |
| H3: 存在"安全距离"转折点 | phi_aggregate 随距离单调递增 | 距离曲线 |
| H4: 再分布逐渐恢复 | 各距离带 phi → 1 随时间 | 时间序列 |

---

## 任务三：Movement-Population 联合分析

### 3.1 目标

建立 Movement 网络变化与 Population 再分布的空间关联。

### 3.2 核心问题

1. Movement 增强的区域是否就是 Population 流入区域？
2. Movement 网络的 Hub 节点是否对应避难所/救援点？
3. 长距离 OD 的目的地是否是人口流入热点？

### 3.3 分析方法

#### 3.3.1 空间叠加分析

```python
def movement_population_overlay(df_movement, df_population):
    """
    对每个 tile，计算：
    - population_phi: 人口变化比
    - in_degree: 该 tile 作为目的地的入度
    - out_degree: 该 tile 作为出发地的出度
    - net_flow: in_degree - out_degree
    """
    # 从 OD 数据计算每个 tile 的 in/out degree
    in_degree = df_movement.groupby('destination_tile')['n_crisis'].sum()
    out_degree = df_movement.groupby('origin_tile')['n_crisis'].sum()
    
    # 合并到 population 数据
    merged = df_population.merge(in_degree, left_on='tile_id', right_index=True, how='left')
    merged = merged.merge(out_degree, left_on='tile_id', right_index=True, how='left')
    
    # 分析相关性
    correlation = merged['phi'].corr(merged['net_flow'])
    return correlation, merged
```

#### 3.3.2 Hub 节点分析

```python
def identify_hubs(G, threshold=2):
    """
    识别网络中的 hub 节点（度数 > threshold * 平均度）
    返回 hub 节点列表及其位置
    """
    avg_degree = 2 * G.number_of_edges() / G.number_of_nodes()
    hubs = [n for n, d in G.degree() if d > threshold * avg_degree]
    return hubs

# 对比震前/震后的 hub 变化
pre_quake_hubs = identify_hubs(G_pre)
post_quake_hubs = identify_hubs(G_post)
new_hubs = set(post_quake_hubs) - set(pre_quake_hubs)  # 震后新增的 hub
```

#### 3.3.3 长距离流动目的地分析

```python
def long_distance_destinations(df_movement, distance_threshold=10):
    """
    分析长距离 OD（>10km）的目的地分布
    """
    long_od = df_movement[df_movement['distance_km'] > distance_threshold]
    destination_counts = long_od.groupby('destination_tile')['n_crisis'].sum()
    top_destinations = destination_counts.nlargest(20)
    return top_destinations
```

### 3.4 输出文件

```
outputs/movement_population_joint/
├── tables/
│   ├── tile_level_joint_metrics.csv          # 每个 tile 的 phi + in/out degree
│   ├── hub_comparison.csv                    # 震前/震后 hub 节点对比
│   └── long_distance_destinations.csv        # 长距离 OD 主要目的地
├── figures/
│   ├── phi_vs_net_inflow_scatter.png         # phi 与 net inflow 的散点图
│   ├── hub_spatial_evolution.png             # Hub 节点的空间分布（震前 vs 震后）
│   └── long_distance_flow_map.png            # 长距离 OD 流向图
└── README.md
```

### 3.5 关键假设检验

| 假设 | 预期结果 | 验证方法 |
|------|----------|----------|
| H1: phi 与 net_inflow 正相关 | correlation > 0.3 | 散点图 + 相关系数 |
| H2: 震后新增 Hub 在远离震中区域 | new_hubs 平均距离 > 50km | 空间分布 |
| H3: 长距离 OD 目的地集中 | top 20 destinations 占 >50% 流量 | 分布统计 |

---

## 执行顺序

```
Phase 1: 并行执行
├── Task 1: Movement 网络结构深度分析
└── Task 2: Population 空间再分布分析

Phase 2: 依赖 Phase 1 结果
└── Task 3: Movement-Population 联合分析

Phase 3: 综合
└── 生成综合报告，提炼核心发现
```

---

## 时间窗口选择

为了控制计算量，建议选择以下代表性时间窗口进行详细分析：

| 阶段 | 时间窗口 | hours_since_quake | 说明 |
|------|----------|-------------------|------|
| 震前 | Feb 5 08:00 | -8h | 唯一震前数据 |
| 应急期 | Feb 6 08:00 | +16h | GCC 峰值 |
| 应急期 | Feb 7 08:00 | +40h | 应急持续 |
| 过渡期 | Feb 9 08:00 | +88h | 开始下降 |
| 恢复期 | Feb 12 08:00 | +160h | 一周后 |
| 恢复期 | Feb 19 08:00 | +328h | 两周后 |
| 稳定期 | Mar 12 08:00 | +832h | 一个月后 |

**注意**：都选 08:00 的数据，排除时段周期性干扰。

---

## 预期产出

完成以上分析后，应该能回答：

1. **灾害是否确实诱导网络集中化？**（多指标验证）
2. **人口再分布的空间规律是什么？**（距离/方向/timescale）
3. **Movement 增强区域是否对应 Population 流入区域？**（空间关联）
4. **这个发现的理论意义是什么？**（与现有文献对话）

---

## 附录：数据位置

```
# Movement 数据
datasets/turkiye_earthquake_2023_sample/raw/movement/

# Population 数据  
datasets/turkiye_earthquake_2023_sample/raw/population/

# 已有输出
outputs/movement_criticality/  # 已完成的网络基础分析
outputs/population_relaxation_sample/  # 已完成的 population 分析
```

---

**Implementation Plan, Task List and Thought in Chinese**

请 partner 按照 Phase 1 → Phase 2 → Phase 3 的顺序执行，每个 Task 完成后生成对应的 README.md 说明主要发现。
