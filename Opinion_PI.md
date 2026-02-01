关于假设站得住脚的批判性分析
你问得非常好：距离带划分是人为的吗？
是的，25/50/100/200km 完全是人为划分。 这是一个严重的方法论问题。

问题所在：

如果我换成 20/60/150km，τ(r) 的排序可能完全不同
当前的"50-100km 恢复最快"可能只是 binning 的产物
子刊审稿人一定会质疑这一点
解决方案：

方法	实施难度	说服力
多 binning 敏感性分析	低	中 - 如果排序在多种 binning 下稳定
连续 τ(r) 拟合	中	高 - 用 tile-level 数据拟合连续函数
非参数检验	中	高 - 不依赖 binning 的排序检验
最优方案：连续 τ(r) 拟合

对每个 tile i：
1. 计算 φᵢ(t) = n_crisis_i(t) / n_baseline_i
2. 拟合指数恢复：τᵢ
3. 得到 τᵢ vs rᵢ (距震中距离)
4. 拟合 τ(r) 的函数形式
5. 检验是否存在"最优距离" r* 使 τ(r*) 最小

Partner Smoke Test 结果解读
关键数据
距离带	tile_ratio_t_geq_0.95	tile_ratio_t_geq_1.0	crisis_mean_ratio_min
0-25km	88h	88h	1.49 (增加，非恢复)
25-50km	64h	88h	0.74
50-100km	40h	64h	0.69
100-200km	64h	88h	0.80
200km+	16h	16h	0.99
Partner 的解读
"50-100km 的 overlap 可达 tiles 恢复最快（到 0.95：40h≈1.7天；到 1.0：64h≈2.7天），而 crisis_mean_overlap 在 88h 仍未回到 0.95（0.926），因此当前最简检验更支持假说 B（通达性）而非 A/C（强度恢复）"

我的评估：这个检验思路正确，但有几个问题：

样本太短 - 只到 88h（3.7 天），τ 拟合需要更长时间
统计显著性缺失 - 只有点估计，没有置信区间
tile_count 恢复 ≠ 通达性 - 可能是因为人口重新聚集而非道路通行
子刊标准下的统计显著性
Nature 子刊的统计标准

效应量 + 置信区间 > p-value
多重检验校正 (Bonferroni, FDR)
稳健性检验 (sensitivity analysis)
可重复性 (不同子样本)
具体实施方案
A. τ(r) 的置信区间
# Bootstrap 置信区间
for band in distance_bands:
    τ_samples = []
    for b in range(1000):  # bootstrap
        # 抽样 tiles within band
        # 拟合 τ
        τ_samples.append(τ_b)
    τ_CI = np.percentile(τ_samples, [2.5, 97.5])


B. 假设 B vs A/C 的统计检验

# 零假设：tile_count 恢复时间 = crisis_mean 恢复时间
# 备择假设：tile_count 恢复更快

# Permutation test
null_distribution = []
for _ in range(10000):
    # 随机打乱 tile_count 和 crisis_mean 标签
    # 计算差异统计量
p_value = (null >= observed).mean()

C. τ(r) 排序的显著性
# 零假设：τ(50-100km) = τ(25-50km)
# 备择假设：τ(50-100km) < τ(25-50km)

# 用 bootstrap 检验
diff_samples = τ_25_50_samples - τ_50_100_samples
p_value = (diff_samples <= 0).mean()

根据你提供的文档，我们有 4 种数据：

数据类型	验证能力	如何使用
Population	✅ 当前主要数据	τ(r) 分析
Movement	✅ 验证"通达性假说"	如果道路中断，OD 流量应该下降
Network Coverage	✅ 验证"通信中断假说"	排除"population 下降是因为手机没信号"
Business Activity	✅ 验证"经济恢复"	作为独立验证 τ(r) 的数据源
具体验证策略
1. Movement 数据验证假说 B（通达性）

如果假说 B 正确：
- 50-100km 的 OD 流量恢复应该比 25-50km 快
- 50-100km 的"入流/出流"恢复应该比 25-50km 快

检验：
- 计算各距离带的 total_inflow(t), total_outflow(t)
- 拟合恢复时间 τ_movement(r)
- 比较 τ_movement(r) 与 τ_population(r) 的形状

混淆假设：Population 下降可能是因为基站损毁，而非人口流失

检验：
- 比较 population 下降区域与 network_coverage_undetected 区域
- 如果高度重叠 → population 数据不可靠
- 如果不重叠 → population 下降是真实疏散

3. Business Activity 独立验证

如果"三相分离"是真实的人口动力学：
- Business Activity 也应该显示类似的空间模式
- 50-100km 的商业活动恢复应该比 25-50km 快

检验：
- 计算各距离带的 activity_quantile(t)
- 拟合恢复时间 τ_business(r)
- 与 τ_population(r) 比较

综合建议：完整验证路径
Phase 1: 基础验证（必须做）
任务	产物	统计方法
连续 τ(r) 拟合	τ(r) 曲线 + 置信带	Bootstrap CI
Binning 敏感性	τ 排序稳定性矩阵	跨 binning 一致率
假说 B vs A 检验	p-value + 效应量	Permutation test
Phase 2: 多数据源验证（增强说服力）
任务	数据	期望结果
Movement τ(r)	movement.csv	形状与 population τ(r) 一致
Network coverage	network_coverage.csv	排除基站损毁混淆
Business activity τ(r)	business_activity.csv	形状与 population τ(r) 一致
