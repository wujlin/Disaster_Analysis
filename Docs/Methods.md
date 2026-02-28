# Methods

> **项目**：Disaster Recovery Dynamics
> **版本**：v2.0
> **日期**：2026-02-28
> **数据基准**：unified_static_h8, n=14 事件, 2,571 子区域

---

## 研究问题

灾后人口恢复速度差异巨大。什么决定了恢复速度？恢复轨迹能否从灾害初期的观测量中预测？

分析在两个独立的空间尺度上展开：

| | 事件级 | 子区域级 |
|---|---|---|
| 观测单位 | 14 个灾难事件 | 2,571 个 geo-unit |
| 问题 | 什么使一场灾难比另一场恢复更快？ | 同一灾难内，什么使某区域比另一区域恢复更快？ |
| 统计框架 | Spearman 秩相关 | 线性混合效应模型 |

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
| 论文图 Fig.2 | `scripts/fig2_shape_predicts_recovery.py` |
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

## 6. 子区域级分析：振幅预测事件内部的恢复差异

### 6.1 问题

同一场灾难内部，什么决定了不同子区域恢复速度的差异？

### 6.2 数据

2,571 个 geo-unit 跨 14 个事件。每个 unit 有独立拟合的 alpha_unit、D_peak_unit、delta_peak_unit、distance_km。

### 6.3 模型

线性混合效应模型（随机截距，事件为 group）：

$$\alpha_{\text{unit}} = \beta_1 \cdot D_{\text{peak,unit}} + \beta_2 \cdot \delta_{\text{peak,unit}} + \beta_3 \cdot \text{distance\_km} + u_{\text{event}} + \varepsilon$$

随机截距 $u_{\text{event}}$ 控制事件间系统性差异。beta 估计 within-event 的 pooled 效应。

### 6.4 结果

| 预测因子 | beta | p |
|---|---|---|
| D_peak_unit | +0.212 | 0.018 |
| delta_peak_unit | +0.003 | 0.967 |
| distance_km | +2.9e-5 | 0.024 |

n = 2,571 观测, 14 个事件组。

**振幅在事件内部显著**：扰动更大的子区域恢复更快。

**几何方向在子区域尺度无预测力**（p = 0.967）。

### 6.5 稳健性

| 检验 | 结果 |
|---|---|
| 随机斜率模型 | fixed beta = 0.128, p = 0.223；随机斜率方差 sigma2 = 0.122（14 group 的随机斜率方差估计功效不足） |
| Mundlak within-between | within beta = 0.208, p = 0.012（within-event 效应真实） |

### 6.6 两个尺度的关系

| | 事件级 | 子区域级 |
|---|---|---|
| 几何 delta | 强预测力（rho = -0.776, p = 0.001） | 无预测力（p = 0.967） |
| 振幅 D | 不显著（rho = +0.341, p = 0.233） | 显著（beta = +0.212, p = 0.018） |

几何效应是宏观涌现现象（区分灾害类型），振幅效应是微观驱动力（驱动同一灾害内部的差异）。

### 代码路径

| 步骤 | 代码 |
|---|---|
| geo-unit 构建 + 拟合 | `scripts/geo_unit_scale_analysis.py` → `src/disaster/geo_unit_scale_analysis.py` |
| 混合效应联合模型 | `scripts/subregion_joint_model.py` → `src/disaster/subregion_joint_model.py` |
| 模型修正（随机斜率 + Mundlak） | `scripts/subregion_model_correction.py` → `src/disaster/subregion_model_correction.py` |
| 输出文件 | `outputs/.../geo_unit_fits.csv` |
| 输出文件 | `outputs/.../mixed_effects_joint_3predictor.csv` |
| 输出文件 | `outputs/.../subregion_model_correction_unified_h8/` |

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
python scripts/fig1_universal_relaxation.py
python scripts/fig2_shape_predicts_recovery.py
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

2. **振幅效应的尺度依赖性**：D_peak 在事件级不显著（p = 0.233）但在子区域级显著（p = 0.018）。可能是功效问题（n=14 vs n=2,571），也可能是真实的尺度依赖。

3. **delta_near 与 D_peak 的边际相关**：rho = -0.525, p = 0.054。疏散型事件往往扰动更大，物理上合理，但意味着两者共享部分方差。
