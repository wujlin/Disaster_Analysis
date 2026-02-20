Plan: 基于 Quadkey 层级聚合的子区域分析
核心发现：Quadkey 就是现成的地理区划
Quadkey 是 Bing Maps 的四叉树编码，14 位字符 = Level 14。截断前缀 = 空间粗化：

截断位数	对应 Level	近似尺度	每个父 tile 含子 tile
14 位（原始）	L14	~2.4 km	1
12 位	L12	~10 km	4
10 位	L10	~40 km	16
8 位	L8	~150 km	256
实现只需一行：df["geo_unit"] = df["quadkey"].str[:10]——不需要 GADM、不需要 geopandas、不需要空间 join。

可行性判断
维度	评估
数据量	Türkiye 地震单窗口 ~31,000 tiles → Level 10 约 ~1,900 个 geo unit → 其中人口密集区有效单元约数百个。16 个事件合计可能产出 1,000–3,000 个有效子区域
信噪比	Level 10 (40 km) 每个单元含 ~16 个 L14 tile，人口聚合后噪声可接受；Level 12 (10 km) 只有 4 个 tile，对稀疏区域太小
代码改动	Pipeline 已有 tile-level 面板处理（population_relaxation.py 做逐 tile φ(t) 拟合），扩展到 quadkey-L10 聚合约 100–200 行新代码
Quadkey→坐标	需要写一个 ~20 行的 quadkey_to_latlon() 解码函数（Bing Maps 文档有标准算法），用于计算聚合单元的中心坐标
建议的分析层级：Level 10 (~40 km)
理由：

与当前 
δ
near
δ 
near
​
  的 50 km 近场半径在同一数量级，物理直觉一致
聚合 16 个 L14 tile 后信噪比可接受
每个事件产出 ~50–200 个有效 geo unit（取决于灾害空间范围和人口密度）
科学上能回答什么问题？
这是与当前 event-level 分析互补的视角：

当前分析（event-level）	子区域分析（geo-unit-level）
"不同灾难之间，空间形态预测恢复速度"	"同一灾难内，不同位置的恢复速度是否系统性地依赖距离/局部位移强度？"
n
=
16
n=16，跨灾害泛化	
n
=
n=数百–数千，within-event 空间精细结构
测试宏观 scaling law	测试 PDE 模型的空间预测能力（不仅预测整体 
α
α，还预测 
α
(
r
)
α(r)）
最有价值的子区域分析：把 PDE 模型的预测从 event-level 延伸到 spatial-level——模型不仅预测"Türkiye 地震整体恢复慢"，还能预测"距震中 30 km 的区域比 100 km 的区域恢复更慢/更快"。如果这能 work，是一个很强的 validation。

Steps
写 quadkey_to_latlon() 工具函数：在 geo.py 中添加，~20 行，将 14 位 quadkey 解码为 tile 中心 (lat, lon)。
写子区域聚合模块：新建 src/disaster/geo_unit_analysis.py，实现 quadkey 截断 → 分组聚合 → 计算每个 geo unit 的 
D
(
t
)
D(t)、
ϕ
(
t
)
ϕ(t) 时间序列。
对每个 geo unit 拟合 
α
α：复用现有的衰减拟合逻辑（relaxation_fit.py），设定最低 tile 数阈值（如 ≥5 个有效 L14 tile）。
分析 
α
α 的空间分布：
α
α vs 距灾害中心距离、vs 局部 
δ
δ 值，用 mixed-effects model 控制 event 随机效应以处理非独立性。
与主分析对接：如果子区域分析支持 event-level 结论，作为 SI 或 Fig S 呈现；如果发现新 pattern，评估是否纳入主文。