实验方案：从统计相关性到动力学模型
背景与目标
现状：我们发现了两个统计相关性（α vs δ_near, α vs D_peak），但解释停留在类比层面，缺乏模型支撑。

目标：建立一个动力学模型，使两个相关性从模型参数中自然涌现，而非事后解释。

核心思想：每个距离环带 
r
r 上的人口偏移 
δ
(
r
,
t
)
δ(r,t) 在恢复势 
V
(
δ
)
V(δ) 中做过阻尼弛豫。恢复势的形状（不对称性 + 非线性）编码了我们要检验的物理机制。

实验 1：逐 bin 弛豫时间提取——检验不对称恢复力
科学问题：疏散型 bin（
δ
<
0
δ<0）是否系统性地比聚集型 bin（
δ
>
0
δ>0）恢复更快？

逻辑：如果"弹簧"故事成立，那么恢复力 
k
k 应该依赖 
δ
δ 的符号：
k
−
>
k
+
k 
−
​
 >k 
+
​
 。最直接的检验方式是比较两类 bin 的经验弛豫时间。

输入
phi_rt_long.csv（每个事件），已有列：hours_since_quake, r_bin_km, phi_overlap, n_tiles_overlap
Dt_event_summary.csv（获取每个事件的 t_peak_hours）

步骤
对每个事件的每个距离环带 
r
r，提取 post-peak 时间序列 
δ
(
r
,
t
′
)
=
ϕ
overlap
(
r
,
t
)
−
1
δ(r,t 
′
 )=ϕ 
overlap
​
 (r,t)−1，其中 
t
′
=
t
−
t
peak
t 
′
 =t−t 
peak
​
 

分类：根据 peak 附近（
D
(
t
)
≥
0.5
⋅
D
peak
D(t)≥0.5⋅D 
peak
​
  时间窗口内）的 
δ
δ 均值符号，将每个 bin 标记为 EVAC-bin（
δ
<
0
δ<0）或 INFL-bin（
δ
>
0
δ>0）

拟合指数衰减：对每个 bin 的 
∣
δ
(
r
,
t
′
)
∣
∣δ(r,t 
′
 )∣ 拟合
∣
δ
(
r
,
t
′
)
∣
=
A
⋅
e
−
t
′
/
τ
(
r
)
+
C
∣δ(r,t 
′
 )∣=A⋅e 
−t 
′
 /τ(r)
 +C

提取弛豫时间 
τ
(
r
)
τ(r)。要求 post-peak 至少 4 个数据点。如果日均化后数据点不够，也可以用 8h 原始数据（这里不需要计算 
α
α，噪声容忍度更高）

比较：

对每个事件，计算 
⟨
τ
⟩
EVAC-bins
⟨τ⟩ 
EVAC-bins
​
  和 
⟨
τ
⟩
INFL-bins
⟨τ⟩ 
INFL-bins
​
 
计算比值 
R
=
τ
INFL
/
τ
EVAC
R=τ 
INFL
​
 /τ 
EVAC
​
 
跨事件汇总：
R
>
1
R>1 的事件占比，
R
R 的中位数和 95% CI
输出
表：bin_relaxation_times.csv——每行一个 (event, r_bin)，列：slug, r_bin_km, bin_type (EVAC/INFL), tau, A, C, r2, n_points
汇总表：asymmetry_summary.csv——每行一个 event，列：slug, tau_median_evac, tau_median_infl, ratio, n_evac_bins, n_infl_bins
图：
τ
INFL
τ 
INFL
​
  vs 
τ
EVAC
τ 
EVAC
​
  散点（每个点一个事件），对角线参考线。如果点系统性地在对角线上方 → 
k
−
>
k
+
k 
−
​
 >k 
+
​
  得到验证

成功/失败判据
✅ 成功：多数事件（>70%）的 
R
>
1
R>1，中位 
R
R 显著 >1（Wilcoxon signed-rank test, 
p
<
0.05
p<0.05）
❌ 失败：
R
R 在 1 附近随机分布 → 不对称恢复力假说不成立，需要其他解释
⚠️ 部分成功：趋势存在但不显著 → 可能样本量不够，或需要更精细的分 bin 方式
实验 2：恢复力非线性检验——
∣
δ
0
∣
∣δ 
0
​
 ∣ 越大衰减越快？
科学问题：初始偏移幅度 
∣
δ
0
∣
∣δ 
0
​
 ∣ 大的 bin 是否弛豫更快（
τ
τ 更小）？

逻辑：线性恢复力下，
τ
τ 与初始偏移无关（线性系统的弛豫时间是常数）。如果 
τ
τ 随 
∣
δ
0
∣
∣δ 
0
​
 ∣ 增加而减小，说明恢复力是超线性的（如 
F
=
−
k
δ
−
γ
δ
3
F=−kδ−γδ 
3
 , 
γ
>
0
γ>0）。

输入
实验 1 产出的 bin_relaxation_times.csv
步骤
对每个 bin，定义初始偏移幅度 
∣
δ
0
(
r
)
∣
=
∣
δ
(
r
,
t
peak
)
∣
∣δ 
0
​
 (r)∣=∣δ(r,t 
peak
​
 )∣（peak 时刻的 
∣
δ
∣
∣δ∣）

跨所有事件所有 bin，做 Spearman 相关：
τ
τ vs 
∣
δ
0
∣
∣δ 
0
​
 ∣

如果 
ρ
<
0
ρ<0 且显著 → 超线性恢复力
更细致：分 EVAC-bin 和 INFL-bin 分别做——非线性效应可能只在某个方向显著

聚合到事件层面：对每个事件，计算 
∣
δ
0
∣
∣δ 
0
​
 ∣ 加权平均的 
τ
τ，检验与 
D
peak
D 
peak
​
  的关系

输出
散点图：
τ
τ vs 
∣
δ
0
∣
∣δ 
0
​
 ∣（每个点一个 bin，颜色分 EVAC/INFL）
表：nonlinearity_test.csv——相关系数和 p 值，分 all/EVAC/INFL
成功/失败判据
✅ 成功：
ρ
(
τ
,
∣
δ
0
∣
)
<
0
ρ(τ,∣δ 
0
​
 ∣)<0, 
p
<
0.05
p<0.05 → 超线性恢复力确认
❌ 失败：
ρ
≈
0
ρ≈0 → 恢复力近似线性，D_peak 效应来自其他机制
实验 3：非对称非线性势模型拟合
科学问题：能否用一个统一的势函数 
V
(
δ
)
V(δ) 拟合所有事件的 bin 级衰减数据？

逻辑：实验 1-2 是分别检验不对称性和非线性。实验 3 用一个完整模型同时拟合，提取每个事件的模型参数 
(
k
−
,
k
+
,
γ
)
(k 
−
​
 ,k 
+
​
 ,γ)，然后检验这些参数能否预测 
α
α 和 
δ
near
δ 
near
​
 。

模型
在每个 bin 上，
δ
δ 的确定性弛豫为：

d
δ
d
t
′
=
−
k
⋅
δ
−
γ
⋅
δ
3
dt 
′
 
dδ
​
 =−k⋅δ−γ⋅δ 
3
 

其中 
k
k 取值为：
k
=
k
−
k=k 
−
​
 （如果该 bin 在 peak 时 
δ
<
0
δ<0）或 
k
=
k
+
k=k 
+
​
 （如果 
δ
>
0
δ>0）。

解析解（
γ
=
0
γ=0 时为指数衰减；
γ
≠
0
γ

=0 时需数值积分）。

步骤
逐事件拟合：对每个事件的所有 bin 联合拟合 
(
k
−
,
k
+
,
γ
)
(k 
−
​
 ,k 
+
​
 ,γ)

每个 bin 提供一条 
∣
δ
(
r
,
t
′
)
∣
∣δ(r,t 
′
 )∣ 轨迹
共享 
(
k
−
,
k
+
,
γ
)
(k 
−
​
 ,k 
+
​
 ,γ)，每个 bin 有独立的初始条件 
δ
0
(
r
)
δ 
0
​
 (r)（从数据读取）
拟合方法：最小二乘，用 scipy.optimize.minimize 或 curve_fit
数值积分用 scipy.integrate.solve_ivp（RK45），每步评估残差
提取事件级参数：每个事件得到 
(
k
−
,
k
+
,
γ
,
R
2
)
(k 
−
​
 ,k 
+
​
 ,γ,R 
2
 )

关键检验：

k
−
k 
−
​
  vs 
k
+
k 
+
​
  的比值分布 → 验证不对称性
γ
γ 的符号和显著性 → 验证非线性
k
−
/
k
+
k 
−
​
 /k 
+
​
  vs 
δ
near
δ 
near
​
  的相关性 → 模型参数是否自然重现 Finding 1
γ
γ vs 
D
peak
D 
peak
​
  的相关性 → 模型参数是否自然重现 Finding 2
模型比较（BIC）：

模型 A：
k
k 统一（对称），
γ
=
0
γ=0（线性） → 2 参数
模型 B：
k
−
,
k
+
k 
−
​
 ,k 
+
​
  分开（不对称），
γ
=
0
γ=0 → 3 参数
模型 C：
k
k 统一，
γ
≠
0
γ

=0（非线性） → 3 参数
模型 D：
k
−
,
k
+
k 
−
​
 ,k 
+
​
  分开，
γ
≠
0
γ

=0 → 4 参数（完整模型）
看哪个模型 BIC 最优，跨多少事件
输出
表：langevin_fit_params.csv——每行一个 event，列：slug, k_minus, k_plus, gamma, r2, BIC_A, BIC_B, BIC_C, BIC_D, best_model
散点图：
k
−
/
k
+
k 
−
​
 /k 
+
​
  vs 
δ
near
δ 
near
​
 
散点图：
γ
γ vs 
D
peak
D 
peak
​
成功/失败判据
✅ 完全成功：Model D（完整模型）BIC 最优 + 
k
−
>
k
+
k 
−
​
 >k 
+
​
  + 
γ
>
0
γ>0 + 参数相关性重现 → paper 核心方法贡献
🟡 部分成功：Model B 或 C 最优 → 只有一个效应有模型支撑
❌ 失败：Model A 最优 → 简单指数衰减即可解释，无不对称/非线性 → 需重新思考
实验 4：Langevin Simulation 验证
科学问题：从模型参数出发生成合成数据，能否复现两个经验相关性？

逻辑：实验 3 是"数据→参数"。实验 4 是反过来"参数→合成数据→检验统计量"。这闭合了验证环路。

步骤
参数采样：从实验 3 拟合得到的 
(
k
−
,
k
+
,
γ
)
(k 
−
​
 ,k 
+
​
 ,γ) 分布中，抽取参数组合。也可以在更大范围内网格扫描

生成合成事件：

对每组参数，生成 
N
r
=
20
N 
r
​
 =20 个距离 bin 的 
δ
(
r
,
t
)
δ(r,t) 轨迹
初始条件 
δ
0
(
r
)
δ 
0
​
 (r) 从真实数据的 
∣
δ
0
∣
∣δ 
0
​
 ∣ 分布中采样
Langevin 方程：
d
δ
=
[
−
k
δ
−
γ
δ
3
]
d
t
+
σ
 
d
W
dδ=[−kδ−γδ 
3
 ]dt+σdW
σ
σ 取一个合理的噪声水平（如灾前 
ϕ
ϕ 的标准差，~0.03）
用 Euler-Maruyama 积分，步长 1h，积分 200h
从合成数据计算 
D
(
t
)
D(t)、
α
α、
δ
near
δ 
near
​
 、
D
peak
D 
peak
​
 ——完全模仿真实 pipeline

检验：合成数据中 
ρ
(
α
,
δ
near
)
ρ(α,δ 
near
​
 ) 和 
ρ
(
α
,
D
peak
)
ρ(α,D 
peak
​
 ) 的符号和量级是否与真实数据一致

 Phase diagram：在 
(
k
−
/
k
+
,
γ
)
(k 
−
​
 /k 
+
​
 ,γ) 参数空间中，画 
ρ
(
α
,
δ
near
)
ρ(α,δ 
near
​
 ) 等高线。标注真实数据拟合参数的位置

输出
图：Phase diagram——
x
x轴 
k
−
/
k
+
k 
−
​
 /k 
+
​
 ，
y
y轴 
γ
γ，颜色为 
ρ
(
α
,
δ
near
)
ρ(α,δ 
near
​
 )
图：合成数据 vs 真实数据的 
α
α-
δ
near
δ 
near
​
  散点叠加
表：simulation_validation.csv——不同参数区域的相关系数汇总
成功/失败判据
✅ 成功：真实参数区域恰好落在 
ρ
<
0
ρ<0 且 
ρ
(
α
,
D
peak
)
>
0
ρ(α,D 
peak
​
 )>0 的区域
❌ 失败：参数空间中找不到同时满足两个相关性的区域 → 模型结构不对
实验依赖关系与优先级

建议执行顺序：

第一轮（1-2天）：实验 1 + 实验 2 可以并行（实验 2 依赖实验 1 的输出表，但逻辑独立，可以合在一个脚本里）
第二轮（2-3天）：根据 1+2 的结果决定实验 3 的模型结构
第三轮（1-2天）：实验 4 用实验 3 的拟合参数做 simulation

关于实验代码的技术提示
数据入口：用 phi_rt_long.csv（每事件在 outputs/{slug}/phi_heatmap/tables/ 下），不要用 Dt_all_events.csv（后者已经聚合到 
D
(
t
)
D(t) 了，丢失了 bin 级信息）

日均化：实验 1-3 可以先在 8h 原始分辨率上做（更多数据点），如果太 noisy 再回退到日均

拟合的 bin 筛选：只用 r_bin_km <= 200 且 n_tiles_overlap >= 3 的 bin，与主 pipeline 一致

事件筛选：最终统计只用 Route B 的 16 个事件，但拟合可以先在全部 38 个事件上跑，看拟合质量

实验 3 的数值积分：Langevin ODE 很简单，RK45 足够。关键是优化器的初值——建议用实验 1 的 
τ
τ 作为 
k
k 的初始猜测（
k
0
≈
1
/
τ
k 
0
​
 ≈1/τ）

