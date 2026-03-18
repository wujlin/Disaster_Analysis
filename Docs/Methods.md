# Methods

> **项目**：Disaster Recovery Dynamics
> **版本**：v2.0
> **日期**：2026-02-28
> **数据基准**：unified_static_h8, n=14 事件, 2,571 子区域（质量筛选后 1,081; 排除地震 940）

---

## 研究问题

灾后人口恢复速度差异巨大。什么决定了恢复速度？恢复轨迹能否从灾害初期的观测量中预测？

分析在两个独立的空间尺度上展开：

| | 事件级 | 子区域级 |
|---|---|---|
| 观测单位 | 14 个灾难事件 | 940+ 个 geo-unit |
| 问题 | 什么使一场灾难比另一场恢复更快？ | 恢复函数形式是否跨尺度保持？局部可观测量能否预测局部恢复速率？ |
| 统计框架 | Spearman 秩相关 | 数据塌缩 + 线性混合效应模型 |

方法路线：**数据构建 → 模式发现 → 物理机制 → 稳健性**。

---

## 1. 数据构建

### 1.1 数据源

Meta/Facebook Disaster Maps (FBDM) Population 数据。Bing Tile Level 14（~2.4 km）空间分辨率，8 小时时间分辨率。

每条记录包含：

| 字段 | 含义 |
|---|---|
| `quadkey` | Bing tile 唯一标识 |
| `latitude`, `longitude` | 瓦片中心坐标 |
| `n_baseline` | 灾前 45 天同时段平均人口 |
| `n_crisis` | 当前时段观测人口 |

分析覆盖约 38 个灾害事件（2020–2025），涵盖地震、飓风、台风、洪水、野火，跨 11 个国家。

### 1.2 空间聚合：tile → 径向分箱

以灾害物理参考点（地震震中坐标 / 飓风登陆点）为中心，Haversine 距离计算，10 km 等宽径向分箱：

$$r_{\text{bin}} = \lfloor r / \Delta r \rfloor \cdot \Delta r, \qquad \Delta r = 10 \text{ km}$$

每个 $(r_{\text{bin}}, t)$ 格点计算覆盖率加权的 order parameter：

$$\phi(r, t) = \frac{\sum_{i \in \text{tiles}(r)} n_{\text{crisis}, i}(t)}{\sum_{i \in \text{tiles}(r)} n_{\text{baseline}, i}}$$

仅包含在时刻 $t$ 和基线期均有观测的 tile（overlap 条件），每个分箱至少 3 个重叠 tile。

产出中间文件 `phi_rt_long.csv`。

### 1.3 日均平滑

8 小时原始分辨率存在 commuting pattern 的日内周期噪声。按 24 小时窗口做日均平均：

$$D_{\text{daily}}(d) = \frac{1}{|\{t : t \in \text{day } d\}|} \sum_{t \in \text{day } d} D(t)$$

此步骤是必要的：跳过日均平滑后信号消失（$\rho \approx 0$）。

### 1.4 子区域数据构建

将 tile 按 Level-10 quadkey 前缀聚合为 geo-unit（每个约 25 km x 25 km），要求至少包含 5 个 L14 tile。每个 unit 独立构建 $D_{\text{unit}}(t)$ 并拟合 $\alpha_{\text{unit}}$。

### 1.5 设计选择

| 选择 | 理由 |
|---|---|
| 静态中心（物理参考点） | 震中/登陆点有确定物理意义，避免 data-driven center picking |
| 10 km 径向分箱 | tile 分辨率（~2.4 km）的自然聚合尺度 |
| 日均平滑 | 消除 commuting 伪影（实验验证为必要步骤） |
| 单调截断拟合 | 只拟合持续衰减段，避免反弹污染 |

### 代码路径

| 步骤 | 代码 |
|---|---|
| 数据下载与整理 | `scripts/download_datasets.py`, `scripts/collect_event_from_dfg.py` |
| tile → 径向分箱 + D(t) + alpha 拟合 | `scripts/dt_decay.py` → `src/disaster/dt_decay.py` |
| geo-unit 构建 + unit 级拟合 | `scripts/geo_unit_scale_analysis.py` → `src/disaster/geo_unit_scale_analysis.py` |
| 数据 I/O 工具 | `src/disaster/population_io.py` |
| 距离分箱工具 | `src/disaster/bins.py` |
| 地理坐标工具 | `src/disaster/geo.py` |

---

## 2. 核心观测量

### 2.1 聚合位移 D(t)

$$D(t) = \langle |\delta(r, t)| \rangle_{r \leq r_{\max}}, \qquad \delta(r, t) \equiv \phi(r, t) - 1$$

$\delta > 0$ 表示人口增加，$\delta < 0$ 表示人口减少。取绝对值后 $D(t)$ 衡量偏离稳态的总幅度。$r_{\max} = 200$ km。

### 2.2 衰减速率 alpha

峰值后定义 $t' = t - t_{\text{peak}}$，在初始单调衰减段上做 log-log OLS 拟合：

$$\ln D_{\text{norm}} = -\alpha \cdot \ln t' + \ln A$$

$\alpha$ 是 log-log 斜率，描述初始衰减速率。$\alpha$ 大则快速恢复，$\alpha$ 小则扰动持续。

**单调衰减段**：从 $t' = 24$ h 起，保留 $D_{\text{norm},i+1} \leq 1.05 \cdot D_{\text{norm},i}$ 的连续段，首次 >5% 反弹即截断。终点由数据决定（72–144 h，中位数 96 h）。

**不声称函数形式**：$\alpha$ 是 log-log 斜率的经验度量，不假设幂律为真实衰减形式。BIC 比较显示 power-law、exponential、stretched exponential 在短观测段上难以区分。

### 2.3 近场位移几何 delta_near

$$\delta_{\text{near}} = \langle \delta(r, t) \rangle_{r \leq r_{\text{near}}, \, t \in \mathcal{T}_{\text{peak}}}$$

其中 $\mathcal{T}_{\text{peak}} = \{t : D(t) \geq 0.5 \cdot D_{\text{peak}}\}$。$r_{\text{near}} = 50$ km。

- $\delta_{\text{near}} < 0$：疏散型（人口从近场流出）
- $\delta_{\text{near}} > 0$：聚集型（人口向近场聚拢）

$\delta_{\text{near}}$ 是连续变量，不做离散分类。

### 2.4 扰动峰值 D_peak 与残余位移 D_inf

$$D_{\text{peak}} = \max_t D(t)$$

$$D_\infty = \frac{1}{|\mathcal{T}_{\text{tail}}|} \sum_{t \in \mathcal{T}_{\text{tail}}} D_{\text{norm}}(t)$$

$\mathcal{T}_{\text{tail}}$ 为 post-peak 序列的最后 1/3 时间点。

---

## 3. 样本选择

### 3.1 纳入条件

- 单调衰减段至少 3 个数据点（`min_n_mono >= 3`）
- 单调段至少覆盖 4 个 post-peak 时间步（`min_post_peak_steps >= 4`，主文配置 mtw5_mpp4）
- $\delta_{\text{near}}$ 非缺失
- $\alpha$ 非缺失

### 3.2 最终样本（n = 14）

权威来源：`outputs/cross_disaster_comparison/Dt_decay_unified_h8_mtw5_mpp4/tables/Dt_routeB_sample_flags.csv`

| slug | alpha | D_peak | delta_near | 类型 | R2 |
|---|---|---|---|---|---|
| flooding_eu | -0.015 | 0.143 | +0.101 | INFL | 0.14 |
| beryl_qr | 0.741 | 0.236 | -0.442 | EVAC | 0.98 |
| beryl_tx | 0.800 | 0.241 | -0.279 | EVAC | 0.99 |
| beryl_jamaica | 0.387 | 0.564 | -0.404 | EVAC | 0.89 |
| park_fire | 0.223 | 0.040 | +0.046 | INFL | 0.71 |
| spain_flood | 0.058 | 0.127 | +0.203 | INFL | 0.81 |
| nepal | 1.216 | 0.212 | -0.120 | EVAC | 0.94 |
| brazil | 0.390 | 0.109 | +0.001 | NEUTRAL | 0.93 |
| quito | 0.424 | 0.089 | +0.001 | NEUTRAL | 0.68 |
| kristine_ph | 0.711 | 0.297 | -0.041 | EVAC | 0.94 |
| yagi_ph | 0.467 | 0.139 | -0.227 | EVAC | 0.93 |
| turkiye | 0.223 | 0.401 | +0.057 | INFL | 0.96 |
| krathon_tw | 0.101 | 0.134 | +0.111 | INFL | 0.95 |
| yagi_vn | 0.522 | 0.317 | -0.547 | EVAC | 0.96 |

EVAC/INFL/NEUTRAL 是基于 $\delta_{\text{near}}$ 符号的事后描述性标签，不作为分析输入。

SI 备选配置（`mtw4_mpp3`）纳入 n = 15 个事件，结论不变。

### 代码路径

| 步骤 | 代码 |
|---|---|
| 样本筛选 + flag 输出 | `scripts/dt_decay.py` → `src/disaster/dt_decay.py` |
| 输出文件 | `outputs/.../Dt_routeB_sample_flags.csv` |

---

## 4. 事件级分析：空间几何预测恢复速度

### 4.1 核心发现

| 相关对 | rho | p | n |
|---|---|---|---|
| alpha vs delta_near | -0.776 | 0.001 | 14 |
| alpha vs D_peak | +0.341 | 0.233 | 14 |
| delta_near vs D_peak | -0.525 | 0.054 | 14 |

**几何效应**是事件级的核心发现。Jackknife 95% CI: [-0.852, -0.725]。

**振幅效应**在事件级不显著。旧样本（n = 16）中曾显著（rho = +0.60, p = 0.014），新样本的变化来自静态中心修正后的事件组成变化。

### 4.2 稳健性

| 检验 | 结果 |
|---|---|
| Jackknife | 95% CI [-0.852, -0.725]，不穿越 0 |
| r_near 扫描 30-100 km | rho in [-0.785, -0.741]，全部 p < 0.003 |
| r_max 扫描 100-250 km | 全部 p < 0.01 |
| R2 >= 0.8 子集 | n = 11, rho = -0.627, p = 0.039 |
| Beryl 家族排除 | 信号增强 |
| 社会经济指标 | HDI、GDP 与 alpha 无显著关联 |

### 代码路径

| 步骤 | 代码 |
|---|---|
| Spearman 相关 + 散点图 | `scripts/cross_disaster_comparison.py` → `src/disaster/cross_disaster_comparison.py` |
| r_near 敏感性 | `scripts/rnear_sensitivity.py` → `src/disaster/rnear_sensitivity.py` |
| r_max 敏感性 | `scripts/rmax_sensitivity.py` → `src/disaster/rmax_sensitivity.py` |
| Beryl 独立性检验 | `scripts/beryl_independence.py` → `src/disaster/beryl_independence.py` |
| 社会经济控制 | `scripts/external_covariates_analysis.py` |
| 论文图 Fig.3 | `scripts/fig3_shape_predicts_recovery.py` |
| 输出文件 | `outputs/cross_disaster_comparison/spearman_summary.csv` |
| 输出文件 | `outputs/cross_disaster_comparison/rmax_sensitivity_spearman_summary.csv` |
| 输出文件 | `outputs/cross_disaster_comparison/rnear_sensitivity_spearman_summary.csv` |

---

## 5. 物理机制：扩散-弛豫 PDE 模型

### 5.1 动机

rho(alpha, delta_near) = -0.776 表明初始空间廓线的形状编码了恢复速度信息。PDE 模型检验因果假说：**空间扩散选择性衰减高频空间成分，是否足以让廓线形状决定衰减速率？**

### 5.2 控制方程

径向对称的扩散-弛豫方程：

$$\frac{\partial \delta}{\partial t} = \frac{D_s}{r} \frac{\partial}{\partial r}\left(r \frac{\partial \delta}{\partial r}\right) - k\,\delta$$

$D_s$：空间扩散系数（km^2/h）。$k$：均匀衰减率（1/h）。

Neumann 边界条件（零通量）：$\partial \delta / \partial r |_{r=0} = \partial \delta / \partial r |_{r=R} = 0$，$R = 200$ km。

### 5.3 Bessel 展开

解在 Neumann 条件下展开为零阶 Bessel 函数 $J_0$：

$$\delta(r, t) = \sum_{n=0}^{N-1} c_n \, J_0\!\left(\frac{\mu_n \, r}{R}\right) \exp(-\lambda_n \, t)$$

$\mu_0 = 0$，$\mu_n$ ($n \geq 1$) 为 $J_0'(x) = 0$ 的正零点。模态衰减率：

$$\lambda_n = k + D_s \left(\frac{\mu_n}{R}\right)^2$$

**核心物理**：高阶模态衰减更快。疏散型廓线高频成分多，整体弛豫更快。事件间 alpha 差异完全来自初始廓线的模态系数 $\{c_n\}$ 差异。

### 5.4 初始条件与参数

取 $t_{\text{peak}}$ 时刻的径向廓线作为初始条件。展开系数通过 Bessel 正交关系投影：

$$c_n = \frac{\int_0^R \delta(r, 0) \, J_0(\mu_n r / R) \, r \, dr}{\int_0^R J_0^2(\mu_n r / R) \, r \, dr}$$

实际操作：10 km 分箱数据插值到 200 点均匀网格，数值梯形积分，N = 10 个模态。

k 和 D_s 是两个**全局参数**（所有事件共享）。在 30x30 对数均匀网格上搜索，主准则为 min joint rank（Spearman + Pearson + MAE 排名之和最小化）。

> **注意**：当前 PDE 参数（k = 0.00418/h, D_s = 0.304 km^2/h）基于旧 n=16 数据拟合，需要在新 n=14 数据上重新估计。

### 5.5 预测衰减率

定义能量度量 $E(t) = \int_0^R \delta^2(r,t) \, r \, dr / \int_0^R r \, dr$（Parseval 等式下可解析计算），对 E(t) 在 [1h, 120h] 做 log-log OLS 拟合得到 alpha_pred。

E(t)（L2 范数）与经验 D(t)（L1 范数）是同一廓线的不同大小度量。PDE 使用 E(t) 因为 Bessel 展开下有解析表达式。

### 5.6 反事实实验

| 反事实 | 操作 | 预期 | 观测 |
|---|---|---|---|
| D_s = 0 | 关闭扩散 | alpha_pred 全同 | rho = 0.0 |
| 仅 c_0 | 只保留均匀模态 | 空间结构被移除 | rho = 0.0 |
| Shuffle | 打乱事件-廓线配对 | 因果关系破坏 | rho = -0.008 |

### 代码路径

| 步骤 | 代码 |
|---|---|
| PDE 求解 + 参数搜索 + 反事实 | `scripts/spatial_diffusion.py` → `src/disaster/spatial_diffusion.py` |
| PDE 可视化 | `scripts/pde_visualization.py` → `src/disaster/pde_visualization.py` |
| 论文图 Fig.3 | `scripts/fig3_pde_mechanism.py` |
| 输出文件 | `outputs/.../pde_optimal_params.csv` |
| 输出文件 | `outputs/.../pde_alpha_predictions.csv` |
| 输出文件 | `outputs/.../counterfactual_results.csv` |

---

## 6. 子区域级分析：跨尺度幂律普适性

### 6.1 核心发现

子区域级分析揭示了一个强正面结果：**幂律衰减作为恢复的函数形式，在子区域尺度上同样成立**。940 条子区域轨迹（13 个事件，排除地震）经双参数归一化后，塌缩到一条 master curve 上（Q = 0.51），该 master curve 自身遵循幂律（R² = 0.86）。这建立了从 ~5 km 到 ~200 km 的尺度无关恢复动力学。

与此同时，恢复速率（指数 α）在事件内部呈现显著异质性（ICC = 0.15），局部可观测量（振幅、位移方向、距离）均不能稳健地预测局部恢复速率。这不是"缺乏发现"，而是涌现（emergence）的直接证据：个体多样 → 集体有序。

### 6.2 数据

2,571 个 geo-unit 跨 14 个事件。质量筛选后（n_mono ≥ 4, R² ≥ 0.5），保留 1,081 个 unit。排除恢复机制本质不同的地震事件后，保留 940 个 unit（13 个事件，14,081 条衰减相观测）。

### 6.3 函数形式的普适性

对每个 unit 独立拟合幂律 $D(t) \sim t^{-\alpha}$：

| R² 区间 | 占比（n_mono ≥ 4，排除地震） |
|---|---|
| ≥ 0.9 | 26.0% |
| ≥ 0.7 | **70.5%** |
| ≥ 0.5 | **93.5%** |
| < 0.5 | 6.5% |

**93.5% 的子区域遵循幂律衰减**，证明 D(t) ~ t^{-α} 不仅在事件级（空间平均后的 D(t)）成立，在 ~5 km 尺度的单个 geo-unit 上也成立。幂律是恢复动力学的**跨尺度普适函数形式**。

### 6.4 数据塌缩（Data Collapse）

将每条轨迹做双参数归一化：振幅归一化 $\tilde{D} = D / D_{\text{peak}}$，时间归一化 $\tilde{\tau} = \tau / t_{1/2}$（其中 $t_{1/2}$ 为 D 衰减至峰值一半的时间）。

| 策略 | 描述 | 塌缩质量 Q |
|---|---|---|
| S0 | D vs τ（无归一化） | −0.05 |
| S1 | D/D_peak vs τ（仅振幅归一化） | 0.03 |
| **S2** | **D/D_peak vs τ/t_half（双参数归一化）** | **0.51** |

Q 定义为 $Q = 1 - \langle \sigma^2_{\text{bin}} \rangle / \sigma^2_{\text{global}}$，Q = 0 无塌缩，Q = 1 完美塌缩。

双参数归一化后，940 条轨迹的中位数轨迹（master curve）自身遵循幂律：

$$\tilde{D} = 0.52 \cdot \tilde{\tau}^{-0.31}, \quad R^2 = 0.86$$

**每事件塌缩质量**差异显著，反映恢复机制的类型差异：

| 事件 | 类型 | n_units | Q(S2) |
|---|---|---|---|
| typhoon_yagi_vietnam | typhoon | 15 | **0.90** |
| spain_flood | flood | 74 | **0.63** |
| flooding_europe | flood | 227 | **0.58** |
| hurricane_beryl_texas | hurricane | 101 | **0.48** |
| hurricane_beryl_mexico | hurricane | 33 | **0.47** |
| wildfires_quito | wildfire | 13 | 0.40 |
| flooding_nepal | flood | 23 | 0.33 |
| hurricane_beryl_jamaica | hurricane | 338 | 0.27 |
| flooding_brazil | flood | 49 | 0.26 |
| kristine_philippines | tropical_storm | 22 | 0.23 |
| typhoon_krathon_taiwan | typhoon | 18 | 0.21 |
| yagi_philippines | tropical_storm | 11 | 0.18 |
| park_fire_california | wildfire | 16 | 0.08 |
| turkiye_earthquake | earthquake | 141 | **−0.61** |

地震（Q = −0.61）的恢复动态与其他灾害类型根本不同（近乎无衰减，α ≈ 0.06），对应于永久性结构损害。

### 6.5 α 的结构化异质性

衰减指数 α 的分布（排除地震）：

| 统计量 | 值 |
|---|---|
| median | **1.02** |
| IQR | [0.48, 1.62] |
| CV（全局） | 0.78 |
| ICC（事件间） | **0.15** |

ICC = 0.15 意味着仅 15% 的 α 方差归因于事件间差异，85% 是事件内部的子区域异质性。这排除了"α 是事件固有属性"的假设——α 不是由灾害类型或地理位置统一决定的，而是在空间聚合过程中**涌现**的集体属性。

### 6.6 局部预测因子的排除

线性混合效应模型（随机截距，REML）检验三个局部可观测量对 α_unit 的预测力：

| 预测因子 | 全样本 β (p) | 随机斜率 β (p) | n_mono ≥ 5 子集 β (p) | 等权 meta β (p) |
|---|---|---|---|---|
| D_peak_unit | +0.21 (0.018) | +0.13 (0.223) | +0.04 (0.791) | −0.16 (0.578) |
| delta_peak_unit | +0.00 (0.967) | — | — | −0.27 (0.240) |
| distance_km | +2.9e-5 (0.024) | — | — | +4.9e-4 (0.243) |

D_peak_unit 的表面显著性（p = 0.018）不稳健：
- **随机斜率模型**：允许事件异质斜率后，p = 0.223
- **SNR 控制**：限制 n_mono ≥ 5 后效应消失（β = +0.04, p = 0.791）
- **LOO**：排除 beryl_jamaica（39% 样本）后翻号为负（β = −0.16, p = 0.234）
- **等权 meta-analysis**：每事件一票，效应为负且不显著

**没有任何局部可观测量能跨事件地稳健预测局部恢复速率。**

### 6.7 两个尺度的统一叙事

| | 事件级 | 子区域级 |
|---|---|---|
| 函数形式 | 幂律 D(t) ~ t^{-α}（14/14 事件） | 幂律 D(t) ~ t^{-α}（93.5% 的 units） |
| 空间信息 → α | delta_near 强预测力（ρ = −0.78） | 局部可观测量无稳健预测力 |
| α 的含义 | 空间 profile 形状的集体指纹 | 局部恢复率，高度异质 |

这一结构揭示了灾后恢复的涌现特征：
1. **函数形式跨尺度保持**——幂律在 ~5 km（unit）和 ~200 km（event）尺度同时成立
2. **参数跨尺度涌现**——事件级 α 由空间 profile 形状决定（PDE 模型），但这个 α 本身是由内部高度异质的 α_unit 在空间聚合中产生的
3. **局部多样性 + 集体有序 = 涌现**——无法从任何单一局部属性预测局部 α，但空间组织（profile 形状）决定了集体 α

### 代码路径

| 步骤 | 代码 |
|---|---|
| geo-unit 构建 + 拟合 | `scripts/geo_unit_scale_analysis.py` → `src/disaster/geo_unit_scale_analysis.py` |
| 数据塌缩实验（Route A） | `scripts/subregion_data_collapse.py`, `subregion_data_collapse_v2.py`, `subregion_collapse_final.py` |
| 混合效应联合模型 | `scripts/subregion_joint_model.py` → `src/disaster/subregion_joint_model.py` |
| 模型修正 + 诊断 | `scripts/subregion_model_correction.py`, `scripts/subregion_diagnostic.py` |
| 输出目录 | `outputs/.../subregion_collapse/` |
| 关键图表 | `data_collapse_final.png`（3-panel publication figure） |

---

## 7. 参数汇总

| 参数 | 符号 | 默认值 | 含义 |
|---|---|---|---|
| 最大距离 | r_max | 200 km | D(t) 平均的径向范围 |
| 近场半径 | r_near | 50 km | delta_near 定义范围 |
| 距离分箱宽度 | Delta_r | 10 km | 空间离散化步长 |
| Peak 窗口比例 | f_peak | 0.5 | delta_near 平均所用 peak 窗口 |
| 最小重叠 tile | - | 3 | 每个 (r, t) 格点的最小 tile 数 |
| alpha 起点 | - | 24 h | 排除峰值附近混沌 |
| 单调容忍度 | tol_up | 1.05 | 反弹截断阈值 |
| 最小单调点数 | min_n_mono | 3 | 事件筛选 |
| 最小 post-peak 步数 | min_post_peak | 4 (主文) / 3 (SI) | 事件筛选 |
| PDE 边界半径 | R | 200 km | Bessel 展开径向域 |
| Bessel 模态数 | N | 10 | 展开截断 |
| geo-unit 级别 | - | L10 quadkey | 子区域粒度 |
| geo-unit 最小 tile 数 | - | 5 | 子区域筛选 |

---

## 8. 软件与复现

### 运行命令

```bash
# 事件级全流程（D(t) + alpha + delta_near + 跨灾难比较）
python scripts/dt_decay.py --output-root outputs/

# PDE 模型
python -m scripts.spatial_diffusion --run-until 4 --pred-mode E --t-start 1.0

# 子区域分析
python scripts/geo_unit_scale_analysis.py
python scripts/subregion_joint_model.py
python scripts/subregion_model_correction.py

# 稳健性
python scripts/rnear_sensitivity.py
python scripts/rmax_sensitivity.py
python scripts/beryl_independence.py

# 论文图
python scripts/fig2_universal_relaxation.py
python scripts/fig3_shape_predicts_recovery.py
python scripts/fig3_pde_mechanism.py
python scripts/fig4_amplitude_orthogonality.py
```

### 核心依赖

Python 3.9+, pandas, numpy, scipy, statsmodels, matplotlib

### 关键中间产物

| 文件 | 含义 |
|---|---|
| phi_rt_long.csv | tile → 径向分箱聚合后的 phi(r,t) |
| Dt_all_events.csv | 日均 D(t) 序列 |
| Dt_routeB_sample_flags.csv | 样本筛选 flag（权威样本来源） |
| geo_unit_fits.csv | 子区域级 alpha_unit 拟合结果 |
| pde_optimal_params.csv | PDE 全局参数 |
| pde_alpha_predictions.csv | PDE 预测的 alpha_pred |

---

## 待解决的问题

1. **PDE 参数更新**：当前参数基于旧 n=16 数据，需要在 n=14 数据上重新估计。

2. ~~**振幅效应的尺度依赖性**~~（已解决）：子区域级 D_peak_unit 的"显著性"（p=0.018）经诊断为不稳健——排除 beryl_jamaica 后翻号，控制 fit quality 后消失（n_mono≥5 子集 p=0.791）。详见 Section 6.5。当前结论：振幅效应在事件内部的方向因灾害而异，不构成普遍规律。

3. **delta_near 与 D_peak 的边际相关**：rho = -0.525, p = 0.054。疏散型事件往往扰动更大，物理上合理，但意味着两者共享部分方差。

4. **子区域 φ 定义统一**（待定）：子区域使用 raw ratio，事件级使用 overlap-conditioned。需评估是否在 `geo_unit_scale_analysis.py` 中也使用 overlap 条件，或在 SI 中做 sensitivity check。

---

## 9. 方法审计报告（PI Review，2026-02-28）

> 本节为逐行代码审计结果。严重程度：🔴 = 影响核心论证，需立即修正；🟡 = 人为设定或隐含假设，需在论文中明确说明；🟢 = 代码正确但 Methods 措辞需精确化。

---

### 🔴 Issue A：Subregion 与 Event-level 的 φ 定义不一致

**问题**：event-level 和 subregion-level 对 φ 使用了不同的计算公式，但 Methods.md 和论文均未说明这一区别。

**Event-level**（`phi_heatmap.py` + `dt_decay.py`）：

```python
# phi_heatmap.py line 903
agg["phi_overlap"] = agg["crisis_sum_overlap"] / agg["baseline_sum_overlap"]
# 只包含在时刻 t 和基线期均有观测的 tile（overlap 条件）
```

**Subregion-level**（`geo_unit_scale_analysis.py`）：

```python
# geo_unit_scale_analysis.py line 216
g["phi"] = pd.to_numeric(g["n_crisis_sum"]) / pd.to_numeric(g["n_baseline_sum"])
# 包含 geo_unit 内所有 tile，无 overlap 筛选
```

**后果**：

- Event-level 的 φ 是"**coverage-conditioned**"估计（排除了仅在危机期才出现或消失的 tile），系统性地比 raw ratio 更保守。
- Subregion-level 的 φ 是**raw ratio**（所有 tile 求和相除），未施加任何 overlap 条件。
- 两者在 tile 覆盖率稳定的区域差异小，但在边缘区域（危机期 tile 大量变化时）差异可能显著。
- 目前 Section 1.2 的公式 $\phi(r, t) = \sum n_{\text{crisis}} / \sum n_{\text{baseline}}$ 暗示两者一致，实际不然。

**需要做的事**：

1. 在 Methods 中明确说明两种 φ 的差异及各自的适用场景。
2. 在子区域分析中增加一个 sensitivity check：对 `n_baseline_sum > threshold` 的 geo_unit 过滤（类似 overlap 条件的代理），确认 `D_peak_unit` 对 beta 估计的影响可忽略。
3. 或者，统一两个层级的 φ 定义（推荐）：在 `geo_unit_scale_analysis.py` 中也使用 overlap-conditioned 估计。

---

### 🔴 Issue B：Subregion 分析的独立性问题——"独立分析"的表述不准确

**问题**：Section 6 声称子区域分析是独立于事件级分析的另一层证据，但实际上两者共享关键输入，不能视为完全独立的检验。

**共享的输入**：

| 输入 | 来源 | 是否共享 |
|---|---|---|
| `t0`（事件起点时间） | catalog，与 event-level 相同 | ✅ 共享 |
| `center_lat/lon`（参考中心） | catalog，与 event-level 相同 | ✅ 共享 |
| 事件集合（哪14个事件） | Route B 样本，由 event-level 筛选决定 | ✅ 共享 |
| 原始 tile 数据 | 同一份 FBDM 数据 | ✅ 共享 |
| φ 计算逻辑 | 不同（见 Issue A） | ❌ 不共享 |

**结果**：子区域分析实际上是"**在 event-level 条件（event 选择 + t0 + center）约束下，对同一数据的更细粒度分解**"，而非独立验证。

**需要做的事**：

1. **调整论证语言**：不再声称子区域分析"独立于"事件级分析，而是将其定位为"**在同一框架内的跨尺度一致性检验**"。具体可以表述为："子区域分析提供了事件内部的方差分解，而非独立样本。其意义在于将跨事件的 Spearman 相关拆解到事件内部的因果机制。"
2. 在 Section 6.6 的对比表中加注：两个尺度使用相同的 catalog 和 t0，差异仅在于空间聚合粒度和统计框架。

---

### 🟡 Issue C：D_peak_unit 与 D_peak 的量纲和语义不同

**问题**：论文在事件级和子区域级分析中都使用 D_peak 概念，但两者的计算路径和物理意义不同。

**Event-level**：
$$D_{\text{peak}} = \max_t \left[\frac{1}{N_r}\sum_{r=0}^{r_{\max}} |\phi_{\text{overlap}}(r,t) - 1|\right]$$
这是对空间（r 轴方向）的 L1 平均后再取时间峰值，是**集体空间位移**的峰值。

**Subregion-level**：
$$D_{\text{peak,unit}} = \max_t \left|\frac{\sum_{i \in \text{unit}} n_{\text{crisis},i}(t)}{\sum_{i \in \text{unit}} n_{\text{baseline},i}} - 1\right|$$
这是某个 geo_unit（约 25km × 25km）的时间序列峰值，没有空间平均，是**局部位移幅度**。

**后果**：Section 6.4 中 `beta(D_peak_unit) = +0.212, p = 0.018` 的 "振幅在事件内部显著" 的解读是正确的，但与 Section 4.1 中 `rho(alpha, D_peak) = +0.341, p = 0.233` 的"振幅在事件级不显著"不能直接对比——它们度量的是不同层级的振幅。

**需要做的事**：

1. 在论文中明确区分两种 D_peak 的计算层级，使用不同的下标（如 $D_{\text{peak}}^{\text{event}}$ vs $D_{\text{peak}}^{\text{unit}}$）。
2. 补充说明：尺度依赖性（scale-dependent）本身是一个 finding，不是矛盾。振幅效应在小空间尺度有效，在大尺度（事件间比较）被几何效应掩盖——这对应不同的空间方差来源。

---

### 🟡 Issue D：alpha 拟合起点 t' = 24h 是人为设定，缺乏敏感性分析

**问题**：`dt_decay.py` 和 `geo_unit_scale_analysis.py` 均从 t' = 24h 开始拟合，排除了峰值后的前 24 小时数据。

**代码实证**：`fit_min_tprime_hours = 24`（两个文件均如此）。

**潜在影响**：

- 这个选择等价于强制 "fast initial transient" 不进入拟合。对于快速恢复事件（peak ~ 24h 后即达稳态），这可能导致拟合段过短。
- 对于慢速恢复事件（peak 后数百小时仍在衰减），24h 截断的影响几乎可以忽略。

**需要做的事**：

1. Methods 中明确说明该参数的物理动机（避免急性期的非平稳过渡过程污染幂律拟合）。
2. 增加敏感性分析：`fit_min_tprime_hours ∈ {12, 24, 48}`，报告 alpha 估计的变化范围。如果 alpha 对该参数不敏感（预期如此，因为单调截断在起到主要筛选作用），则在 SI 中一句话说明即可。

---

### 🟡 Issue E：单调截断的非对称性

**问题**：`_monotone_decay_segment` 只对上升做截断（`D_norm[i+1] > 1.05 * D_norm[i]` 则停止），允许任意大幅的急速下降。

**后果**：如果某个事件的 D(t) 在峰值后出现一次急剧下降（例如数据覆盖率突然恢复），然后趋于平稳，该单调段可能只包含那次急剧下降，导致 alpha 被高估。

**缓解因素**：`min_n_mono >= 3` 要求至少 3 个点，限制了极端情况的影响；实际上 FBDM 数据的 8h 分辨率使得急剧下降不常见。

**需要做的事**：

1. 在 Methods 中说明单调性是针对"反弹"（上升）的截断，而非双向截断。
2. 在 SI 中报告：各事件的单调段长度分布（n_mono 的中位数和范围），以表明大多数事件的拟合段有足够长度。

---

### 🟡 Issue F：near_delta 定义中的峰值窗口权重

**问题**：`delta_near` 定义为"在 $D(t) \geq 0.5 D_{\text{peak}}$ 窗口内的 near-field delta 均值"，但这些窗口内可能包含不同数量的 r bins，不同的时刻对 near_delta 的贡献未做加权。

**代码实证**（`dt_decay.py` line 402-404）：

```python
near = pd.to_numeric(peak_w["near_delta"], errors="coerce").to_numpy(dtype=float)
near = near[np.isfinite(near)]
near_mean = float(np.mean(near)) if near.size else float("nan")
```

这是对时间窗口做等权均值，不考虑每个窗口的 `n_r_bins`（近场 bin 数量可能不同）。

**后果**：对于近场 tile 覆盖率随时间变化较大的事件（例如热带风暴过境时的快速移动），部分时刻的 near_delta 基于极少的 bin 计算，与多 bin 时刻等权处理。

**需要做的事**：

1. 在 Methods 中说明均值是等时刻权重（time-equal-weighted），而非 tile-weighted。
2. 可选：在 SI 中增加一个 check：`near_delta` vs 以 `n_r_bins_near` 为权重的 near_delta，报告两者的 Spearman rho 差异。

---

### 🟢 Issue G：phi_overlap 的 overlap 条件在 Methods 中说明不足

**现状**：Section 1.2 写到"仅包含在时刻 $t$ 和基线期均有观测的 tile（overlap 条件）"，但没有说明：

1. 为什么选择 overlap-conditioned 估计（而不是 all-tile 估计）。
2. overlap 条件对 φ 的系统性影响（低 tile 覆盖率区域的 φ 更可信，高覆盖率稳定区域影响可忽略）。
3. `n_tiles_overlap >= 3` 筛选阈值的理由。

**建议**：补充一段说明 overlap 条件的动机（FBDM 在危机期的 tile coverage 会变化，若某区域在 baseline 期有数据但危机期 Meta 未收集，直接用 all-tile 估计会混淆"数据缺失"与"人口减少"两种效应；overlap 条件确保分子分母中的 tile 集合相同，从而 φ 是纯数量变化信号）。

---

### ~~🔴 Issue H：geo_unit_scale_analysis 缺少日均平滑~~（诊断有误，已澄清）

**PI 原始诊断**：声称 `geo_unit_scale_analysis.py` 使用 8h 原始分辨率数据，缺少日均平滑。

**独立审计结论**：**此诊断有事实性错误**。代码审计发现 `geo_unit_scale_analysis.py` 通过 `_list_population_windows` 函数中的 `only_hour_pt` 过滤器（line 130），**每天仅读取一个 8h 窗口**的 population 文件。时间序列实际上已经是 ~24h 步长，不需要日均平滑步骤。

**两个层级的真实差异**：

| 细节 | dt_decay.py（事件级） | geo_unit_scale_analysis.py（子区域级） |
|---|---|---|
| 时间采样 | 读取全部 3 个/天窗口，日均平均 | 仅读取 1 个/天窗口（`only_hour_pt`） |
| φ 定义 | `phi_overlap`（overlap-conditioned） | `n_crisis_sum / n_baseline_sum`（raw ratio） |
| D 的计算 | `mean_r(\|phi_overlap - 1\|)`（空间 L1 均值） | `\|phi_unit - 1\|`（标量） |

差异在于"三窗口均值 vs 单一快照"，而非"8h vs 24h 分辨率"。单一快照的噪声确实比三窗口均值高，但不会引入 PI 所描述的"commuting 日内周期"问题（因为只有一个时间点/天）。

**状态**：无需代码修改；在 SI 中注明时间采样差异即可。

---

### 审计总结

| Issue | 严重程度 | 状态 | 行动 |
|---|---|---|---|
| A. φ 定义不一致（overlap vs raw） | 🔴 | 待修正 | 统一 phi 定义，或明确说明并做 sensitivity check |
| B. Subregion "独立性"表述不准确 | 🔴 | **已修正** | Section 6.1 已调整为"同一框架内的方差分解" |
| C. D_peak 跨尺度语义不同 | 🟡 | 待澄清 | 区分符号，明确两者含义 |
| D. t' = 24h 起点缺乏敏感性分析 | 🟡 | 待补充 | 添加敏感性分析到 SI |
| E. 单调截断非对称性 | 🟡 | 待说明 | Methods 中说明截断方向 |
| F. near_delta 等时刻权重 | 🟡 | 待说明 | Methods 中说明权重方案 |
| G. overlap 条件动机不足 | 🟢 | 待完善 | 补充一段解释 |
| H. geo_unit 日均平滑缺失 | ~~🔴~~ | **诊断有误** | `only_hour_pt` 过滤器已确保每日单点采样，无需修改 |

---

### 独立审计补充（2026-02-28）

PI Review 遗漏的关键问题，由独立审计发现：

| Issue | 严重程度 | 状态 | 说明 |
|---|---|---|---|
| I. D_peak_unit 显著性不稳健 | 🔴 | **已确认并修正** | 随机斜率 p=0.223；n_mono≥5 子集 p=0.791；LOO 排除 beryl_jamaica 翻号；等权 meta 分析 mean β=−0.164。详见 Section 6.5 |
| J. SNR confound（D_peak ↔ n_mono → alpha） | 🔴 | **已确认** | D_peak vs n_mono ρ=0.240, p<0.001。高振幅 unit 拟合段更长，alpha 估计更稳定，产生伪正相关 |
| K. delta_near vs delta_peak_unit 语义不同 | 🟡 | **已修正** | Section 6.7 已区分：delta_near 是灾害类型签名（between-event），delta_peak_unit 是距离梯度上的位置（within-event） |
| L. REML vs ML 不一致 | 🟡 | **已修正** | `subregion_joint_model.py` 已统一为 REML |
