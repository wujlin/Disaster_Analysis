灾害数据的"对齐"维度
维度	问题	当前状态
时间零点	灾害发生时刻 t=0 如何定义？	应该已处理，但需确认
空间零点	中心坐标从哪来？震中/登陆点/人为估计？	可能不一致
φ 的分母	baseline 是灾前几天？历史平均？	需要检查
φ = 0	是 n_crisis=0 还是 n_baseline=0 还是数据缺失？	需要区分
空间覆盖	不同灾害的 tile 密度/范围一样吗？	很可能不一致
可能隐藏的 Insights
Insight 1：φ = 0 可能是"数据黑洞"，不是"人口清零"
如果 φ = 0 意味着 n_crisis = 0（灾后观测到零人口），这可能是：

真实撤离：所有人都离开了
通信中断：基站/网络损坏，无法采集数据
采样偏差：Facebook 用户在该区域不活跃
潜在发现：φ = 0 的空间分布可能反映通信基础设施的脆弱性，而不是人口变化。这本身是一个有意义的 insight。

Insight 2：baseline 的季节性和周周期
如果 baseline 是简单的历史平均，可能忽略了：

周末 vs 工作日的差异
季节性波动（假期、雨季等）
潜在问题：φ 的波动可能部分来自 baseline 估计误差，而非灾害影响。

Insight 3：空间覆盖的边界效应
FBDM 数据的覆盖范围可能有边界：

国境线
网络覆盖边界
人口稀疏区
潜在问题：r 很大时 φ 的异常可能是边界效应，不是真实的距离依赖。

数据对齐的诊断框架
诊断 1：φ 的分布特征
对每个灾害，统计：

frac_phi_zero：φ = 0 的 tile 占比
frac_phi_nan：φ 为 NaN 的 tile 占比
frac_phi_gt_2：φ > 2 的 tile 占比（异常高）
预期：高质量灾害的 frac_phi_zero 应该很小（< 5%）

诊断 2：空间覆盖范围
对每个灾害，计算：

r_max_with_data：有 φ 数据的最大距离
n_tiles_by_r：不同距离带的 tile 数量
预期：如果某个灾害在 r > 200km 处 tile 数量骤降，那里的 φ 值不可靠

诊断 3：baseline 一致性
检查 FBDM 的 baseline 定义：
是固定窗口（如灾前 30 天平均）还是动态窗口？
是否剔除了异常日期？
诊断 4：中心坐标来源
汇总每个灾害的中心坐标：

来源（USGS、官方公告、手动标注）
不确定性（地震震中精确，洪水范围模糊）
给 Partner 的任务
Task: 数据质量与对齐诊断

Part 1: φ 分布诊断

对每个灾害，计算：
n_tiles_total: 总 tile 数
n_tiles_phi_zero: φ = 0 的 tile 数
n_tiles_phi_nan: φ 为 NaN 的 tile 数
n_tiles_phi_gt_2: φ > 2 的 tile 数
frac_phi_zero: 占比
frac_phi_nan: 占比
min_phi_nonzero: 最小非零 φ

Part 2: 空间覆盖诊断

对每个灾害，计算：
按 50km 距离带统计 n_tiles
r_max_with_ge_10_tiles: 至少有 10 个 tile 的最大距离

Part 3: 检查 φ = 0 的空间分布

对 Turkey（信号最强），画：

φ = 0 的 tile 在地图上的位置
φ = 0 的 tile 与震中距离的分布
Part 4: baseline 元数据

检查 FBDM 原始数据或文档：

baseline 是如何定义的？
每个灾害的 baseline 窗口是否相同？
输出：

tables/data_quality_by_disaster.csv
tables/spatial_coverage_by_disaster.csv
figures/turkey_phi_zero_map.png
这个诊断可能带来的 insights
如果 φ = 0 集中在震中附近：可能是通信中断 → 可以研究"灾害导致的数据盲区"

如果 φ = 0 集中在远处：可能是覆盖范围边界 → 需要截断数据范围

如果不同灾害的覆盖范围差异很大：需要定义"可比较的空间范围" → 对齐后可能出现新规律

如果 baseline 定义不一致：需要重新计算 φ，或只做单灾害分析