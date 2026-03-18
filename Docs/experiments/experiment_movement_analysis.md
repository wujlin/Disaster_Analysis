# Movement 数据分析实验方案：D_peak → α 的疏散-回流机制

> **背景**：Population 数据分析已建立两条预测通道：δ_near → α（PDE 验证）和 D_peak → α（机制开放）。Path 1 的内源性分析表明 D_peak 本质上是扰动振幅（ρ(E_total, D_peak)=0.885），β>0 的方向性稳健（P=98.5%），但 event-specific k_i 模型在 n=16 上过拟合。Movement 数据提供了检验 D_peak 机制的直接证据——通过量化疏散流的规模与空间结构。

---

## 科学问题

**D_peak 为什么能预测恢复速度？** 两个竞争假设：

- **H1（有组织疏散假设）**：D_peak 大的事件伴随更大规模的定向疏散流，这些有组织的流动加速了恢复（人们知道去哪里、何时回来）
- **H2（扰动振幅假设）**：D_peak 大单纯因为扰动振幅大，恢复快是因为更强的社会动员（与流动结构无关）

Movement 数据可区分二者：H1 预测疏散流的结构特征（方向性、集中度）与 α 相关；H2 预测流的总量与 α 相关但结构特征无关。

---

## 数据

### 来源

DFG Movement Between Places During Crisis (Bing Tiles)，路径在 WSA 工作站上：
```
/mnt/e/newdesktop/archive/facebook/disaster data/<event_folder>/
```

### 16 个 Route B 事件

| slug | event_type | data_root (参考 catalog) |
|------|-----------|-----------|
| flooding_in_central_and_eastern_europe_sept_16_2024 | flood | 查 catalog |
| hurricane_beryl_across_quintana_roo_and_yucatan_mexico | hurricane | 已在 centerfix6 |
| hurricane_beryl_across_southeastern_texas_us | hurricane | 已在 centerfix6 |
| hurricane_beryl_pre_landfall_2024 | hurricane | 已在 centerfix6 |
| hurricane_john_across_southeastern_guerrero_mexico | hurricane | 查 catalog |
| hurricane_john_southern_mexico_25_september_2024 | hurricane | 查 catalog |
| hurricane_milton_across_florida_us | hurricane | 查 catalog |
| moldova_flooding_2024 | flood | 已在 catalog |
| spain_flood | flood | 查 catalog |
| the_earthquake_across_central_mexico | earthquake | 查 catalog |
| the_flooding_across_bagmati_and_koshi_provinces_nepal | flood | 查 catalog |
| the_flooding_across_eastern_bangladesh | flood | 查 catalog |
| the_flooding_across_gujarat_india | flood | 查 catalog |
| turkiye_earthquake_2023 | earthquake | 已在 catalog |
| typhoon_yagi_across_northeastern_vietnam | hurricane | 查 catalog |
| wildfires_in_boise_county_idaho_27_august_2024 | wildfire | 查 catalog |

### Movement CSV 字段（完整 codebook 见 `Docs/facebook_data/movement.md`）

| 字段 | 用途 |
|------|------|
| start_quadkey, end_quadkey | OD 对的空间标识 |
| start_latitude, start_longitude | 起点坐标 |
| end_latitude, end_longitude | 终点坐标 |
| length_km | OD 向量距离 |
| n_baseline | 基线期该 OD 对的平均流量 |
| n_crisis | 危机期观测流量 |
| n_difference | n_crisis - n_baseline |
| percent_change | 变化百分比 |
| z_score | 标准化偏离 |
| date_time | 时间窗口（PT 时区） |

**重要限制**：
- n_baseline 和 n_crisis 均 <10 的向量被移除（隐私保护）
- 不含跨国界流动
- start_quadkey == end_quadkey 表示原地不动的人

---

## 实验设计

### Exp-M1：疏散流总量指标（对应 D_peak 的幅度效应）

**目标**：构造每个事件的 movement-derived 疏散总量指标，检验其与 D_peak 和 α 的关系。

**步骤**：

1. **时间对齐**：使用各事件的 t_peak（从 population 分析中已知的 D(t) 峰值时刻）。取 t_peak 前后各 24h 的时间窗口。

2. **计算每个事件的疏散指标**：
   ```python
   # 对每个事件，在 [t_peak - 24h, t_peak + 24h] 的时间窗内：
   
   # (a) 总异常流量
   F_total = sum(|n_difference|)  # 所有 OD 对的绝对异常流量
   
   # (b) 净流出量（从近场流出）
   # 近场定义：start 距灾害中心 < 50km
   F_out_near = sum(n_difference)  # 仅取近场起点、远场终点的 OD 对
   
   # (c) 净流入量（向远场流入）
   F_in_far = sum(n_difference)   # 仅取远场起点、远场终点的 OD 对
   
   # (d) 异常长距离流动量
   F_long = sum(n_crisis[length_km > 50]) - sum(n_baseline[length_km > 50])
   ```

3. **关键检验**：
   - ρ(F_total, D_peak): F_total 是否就是 D_peak 在 movement 空间的镜像？
   - ρ(F_total, α): 疏散总量是否直接预测恢复速度？
   - ρ(F_out_near, α): 近场流出量是否更有预测力？
   - 偏相关 ρ(α, F_total | D_peak): 控制 D_peak 后流量是否仍有独立贡献？

**预期**：如果 D_peak 的机制就是有组织疏散的规模，F_total 应与 D_peak 高度相关，且 ρ(α, F_total | D_peak) ≈ 0。

---

### Exp-M2：疏散流的空间结构指标（区分 H1 vs H2）

**目标**：量化疏散流的方向性和集中度——这是区分"有组织疏散"和"随机扰动"的关键。

**步骤**：

1. **提取峰值时段的 OD 矩阵**：取 t_peak 附近最近的 2-3 个时间窗，构建 OD 异常流矩阵（仅保留 |n_difference| > 0 的向量）。

2. **计算结构指标**：
   ```python
   # (a) 流动方向性 — 加权平均方位角的一致性
   # 对每个 OD 对计算从起点到终点的方位角 θ_ij
   # 对所有近场起点（< 50km）的向量：
   θ_mean, R_bar = circular_mean_resultant(θ_ij, weights=|n_difference_ij|)
   # R_bar ∈ [0,1]: 0=各方向均匀流动, 1=完全单向疏散
   
   # (b) 疏散方向与远离灾害中心方向的一致性
   # 计算每个 OD 对的方位角 θ_ij 与"从灾害中心向外"方位角 θ_radial 的夹角
   cos_alignment = mean(cos(θ_ij - θ_radial), weights=|n_difference_ij|)
   # cos_alignment > 0: 流动以远离为主; < 0: 流动以靠近为主
   
   # (c) 目的地集中度
   # 对所有从近场出发的异常流向量，统计终点 tile 的分布
   dest_tiles = unique(end_quadkey)
   # Herfindahl 指数
   HHI_dest = sum((flow_to_tile_j / total_flow)^2)
   # HHI 高 → 疏散目的地集中于少数区域
   
   # (d) 疏散距离分布
   d_median = weighted_median(length_km, weights=|n_difference|)
   d_p90 = weighted_percentile(length_km, 90, weights=|n_difference|)
   ```

3. **关键检验**：
   - ρ(R_bar, α): 更有方向性的疏散 → 更快恢复？
   - ρ(cos_alignment, α): 径向一致性更强 → 更快恢复？
   - ρ(HHI_dest, α): 目的地更集中 → 更快恢复？
   - ρ(d_median, α): 疏散距离更远 → 更快还是更慢恢复？
   - 以上全部控制 D_peak 的偏相关

**预期**：
- H1 成立 → R_bar 和/或 cos_alignment 与 α 显著正相关（有组织的定向疏散 → 快速恢复）
- H2 成立 → 上述结构指标均不显著，仅流量总量有效

---

### Exp-M3：回流动态与恢复轨迹的直接关联

**目标**：从 movement 数据中直接测量"回流速率"，与 population-derived 的 α 对比。

**步骤**：

1. **定义回流**：
   ```python
   # 在 t > t_peak 的时间段：
   # "回流向量" = end_quadkey 在近场（< 50km）且 n_difference > 0
   # 即：相比基线，有更多人流回近场
   
   # 回流率时间序列
   R_return(t) = sum(n_difference[回流向量]) / F_out_near  # 归一化
   ```

2. **回流衰减指标**：
   ```python
   # 对 R_return(t) 做与 D(t) 类似的 log-log 拟合
   α_return = -slope(log R_return vs log t')  # t' = t - t_peak
   ```

3. **关键检验**：
   - ρ(α_return, α): movement-derived 回流速率是否与 population-derived α 一致？
   - 如果 α_return ≈ α（高相关），则 movement 和 population 测量的是同一过程的两个面
   - 如果 α_return 与 α 不相关，则 population 恢复和实际人口回流是两个不同过程

---

### Exp-M4：原地不动人口比例（零距离向量）

**目标**：利用 start_quadkey == end_quadkey 的向量（原地不动的人口），补充理解近场扰动的性质。

**步骤**：

1. **定义 stay-put ratio**：
   ```python
   # 对近场 tile（距灾害中心 < 50km）：
   # stay_put_ratio(t) = sum(n_crisis[start==end, 近场tile]) / sum(n_baseline[start==end, 近场tile])
   # <1 表示近场留守人口减少（有人离开）
   # >1 表示近场留守人口增加（有人涌入或原居民返回）
   ```

2. **与 δ_near 的对照**：
   - δ_near（population 数据）衡量的是近场的净人口变化
   - stay_put_ratio（movement 数据）衡量的是近场"不动的人"的变化
   - 二者的差异 = 流动人口的贡献

3. **关键检验**：
   - ρ(stay_put_ratio at t_peak, δ_near): 两个独立数据源的一致性验证
   - ρ(stay_put_ratio, α): 是否是 α 的独立预测量？

---

## 输出规范

### 目录结构
```
outputs/cross_disaster_comparison/movement_analysis/
├── tables/
│   ├── movement_evacuation_metrics.csv     # 每事件一行，所有 Exp-M1/M2 指标
│   ├── movement_return_timeseries.csv      # 回流率时间序列
│   ├── movement_alpha_correlations.csv     # 所有 movement 指标 vs α, D_peak, δ_near
│   └── movement_partial_correlations.csv   # 控制 D_peak 后的偏相关
├── figures/
│   ├── evacuation_flow_vs_alpha.png        # F_total, F_out_near vs α
│   ├── directionality_vs_alpha.png         # R_bar, cos_alignment vs α
│   └── return_rate_comparison.png          # α_return vs α 散点图
└── README.md
```

### 核心输出表 `movement_evacuation_metrics.csv` 的列

```
slug, short_name, alpha, delta_near, D_peak,
F_total, F_out_near, F_in_far, F_long,
R_bar, cos_alignment, HHI_dest, d_median, d_p90,
alpha_return, stay_put_ratio_peak
```

---

## 实现注意事项

1. **时间对齐**：Movement 数据的 date_time 是 PT 时区（太平洋时间），与 population 数据一致。各事件的 t_peak 可从已有的 population 分析结果中读取（`outputs/cross_disaster_comparison/` 下的相关表格）。

2. **灾害中心坐标**：从 `Docs/cross_disaster_catalog_centerfix6.csv` 或 `Docs/cross_disaster_catalog.csv` 中读取 center_lat, center_lon。对于使用 storm track 的飓风事件，使用 t_peak 时刻的 track 坐标。

3. **近场/远场阈值**：与 population 分析一致，近场 = 0–50 km，远场 = 50–200 km。可做 sensitivity check（25km, 100km）。

4. **隐私截断的影响**：n_crisis 和 n_baseline 均 <10 的 OD 对已被移除。对总流量指标影响小（大量小流量的损失被大流量补偿），但对 HHI_dest 可能有偏（小流量目的地被截断会人为提高 HHI）。应在 README 中注明。

5. **数据可用性第一步**：先对 16 个事件检查 movement 数据的存在性和时间覆盖，输出一个 `movement_data_availability.csv`（slug, has_movement, n_timesteps, date_range）。如果某些事件没有 movement 数据，记录并排除。

6. **复用已有代码**：`src/disaster/geo.py` 中的 haversine 函数可直接使用。`Docs/research_plan_network_redistribution.md` 中有部分可参考的代码模式，但该方案的目标（网络结构分析）与本方案不同——这里聚焦的是 movement 指标与 α/D_peak 的相关性，而非网络拓扑本身。

---

## 优先级

| 优先级 | 实验 | 原因 |
|--------|------|------|
| P0 | 数据可用性检查 | 先确认 16 事件中有多少有 movement 数据 |
| P1 | Exp-M1 疏散流总量 | 最直接回答"D_peak 是否等于疏散规模" |
| P2 | Exp-M2 空间结构 | 区分 H1 vs H2，是论文的核心增量 |
| P3 | Exp-M3 回流动态 | 提供 α 的独立验证 |
| P4 | Exp-M4 原地不动比例 | 补充性，视 M1-M3 结果决定是否做 |

---

*文档版本：v1.0*
*日期：2026-02-18*
