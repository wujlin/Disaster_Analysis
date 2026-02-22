# Methods

> **项目**：Disaster Recovery Dynamics  
> **版本**：v1.0（基于方案 E / Route B 决策链）  
> **对应代码**：`src/disaster/dt_decay.py` + `scripts/dt_decay.py`

---

## 1. 数据

### 1.1 数据源

我们使用 **Meta/Facebook Disaster Maps (FBDM)** 提供的 Population 数据。该数据通过匿名化的移动设备定位信号，以 Bing Tile Level 14（约 2.4 km × 2.4 km）的空间分辨率和 8 小时的时间分辨率（00:00, 08:00, 16:00 PT），估计各瓦片（tile）的人口密度。

每条记录包含：

| 字段 | 含义 |
|------|------|
| `quadkey` | Bing tile 唯一标识（空间索引） |
| `latitude`, `longitude` | 瓦片中心坐标 |
| `n_baseline` | 灾前 45 天同时段平均人口 |
| `n_crisis` | 当前时段观测人口 |
| `z_score` | 标准化偏离（clipped to $[-4, 4]$） |

### 1.2 样本

分析覆盖 **38 个自然灾害事件**（地震、飓风、台风、洪水、野火），涵盖全球多个地理区域。每个事件经独立预处理后纳入跨灾难比较。最终统计样本为 **$n = 16$ 个事件**（排除规则见 §4）。

### 1.3 空间预处理：tile → 径向距离分箱

对每个事件，以灾害参考点（震中坐标或风暴轨迹）为原点，通过 Haversine 公式计算每个 tile 到参考点的距离 $r$，并以 $\Delta r = 10$ km 为步长离散化：

$$r_{\text{bin}} = \lfloor r / \Delta r \rfloor \cdot \Delta r$$

生成 50 个距离分箱（0, 10, 20, ..., 490 km）。在每个 $(r_{\text{bin}}, t)$ 格点上，计算**覆盖率加权的 order parameter**：

$$\phi_{\text{overlap}}(r, t) = \frac{\sum_{i \in \text{tiles}(r)} n_{\text{crisis}, i}(t)}{\sum_{i \in \text{tiles}(r)} n_{\text{baseline}, i}}$$

其中求和仅包含在时刻 $t$ 和灾前基线期均有观测的 tile（"overlap"条件），并要求每个分箱内至少有 `min_tiles_overlap = 3` 个重叠 tile。

此步骤将高维度的瓦片级数据压缩为中间产物 `phi_rt_long.csv`（每行对应一个 $(r_{\text{bin}}, t)$ 格点），保留了径向空间结构与时间动态。

### 1.4 日均平滑

原始数据的 8 小时分辨率引入了显著的日内周期噪声（commuting pattern）。当原始中位时间步长 $< 16$ 小时时，按 24 小时窗口做日均平均：

$$D_{\text{daily}}(d) = \frac{1}{|\{t : t \in \text{day } d\}|} \sum_{t \in \text{day } d} D(t)$$

该步骤将 turkiye 等高频事件的时间分辨率从 8h 降至 ~24h，有效抑制日内周期伪影。**敏感性验证**：跳过日均平滑后，所有下游统计量的信号完全消失（$\rho \approx 0$），确认该预处理是必要的。

---

## 2. 核心观测量

### 2.1 聚合位移幅度 $D(t)$

对每个时刻 $t$，在 $r \leq r_{\max}$ 范围内的所有距离分箱上取绝对偏离的均值：

$$D(t) = \langle |\delta(r, t)| \rangle_{r \leq r_{\max}}, \qquad \delta(r, t) \equiv \phi_{\text{overlap}}(r, t) - 1$$

其中 $\delta(r,t) > 0$ 表示人口增加，$\delta(r,t) < 0$ 表示人口减少。取绝对值后，$D(t)$ 衡量系统偏离稳态的**总幅度**，不区分增减方向。

**默认参数**：$r_{\max} = 200$ km，每个时刻至少需要 `min_r_bins = 5` 个有效分箱。

### 2.2 近场位移方向 $\delta_{\text{near}}$

在灾害中心附近（$r \leq r_{\text{near}}$），人口偏移的**有符号均值**反映位移的方向性：

$$\delta_{\text{near}} = \langle \delta(r, t) \rangle_{r \leq r_{\text{near}}, \, t \in \mathcal{T}_{\text{peak}}}$$

其中 peak 时间窗口定义为 $\mathcal{T}_{\text{peak}} = \{t : D(t) \geq f_{\text{peak}} \cdot D_{\text{peak}}\}$，$f_{\text{peak}} = 0.5$。

- $\delta_{\text{near}} < 0$：近场人口减少——疏散型（evacuation-dominated）
- $\delta_{\text{near}} > 0$：近场人口增加——聚集型（influx-dominated）

**默认参数**：$r_{\text{near}} = 50$ km，每个时刻至少需要 `min_near_bins = 2` 个有效近场分箱。

$\delta_{\text{near}}$ 是一个**连续变量**，在正负之间平滑过渡，不做离散分类。

### 2.3 扰动峰值 $D_{\text{peak}}$

$$D_{\text{peak}} = \max_t D(t)$$

衡量灾害引起的最大总位移幅度。$D_{\text{peak}}$ 越大，社会系统偏离稳态越远。

### 2.4 残余位移 $D_\infty$

$$D_\infty = \frac{1}{|\mathcal{T}_{\text{tail}}|} \sum_{t \in \mathcal{T}_{\text{tail}}} D_{\text{norm}}(t), \qquad D_{\text{norm}}(t) = D(t) / D_{\text{peak}}$$

其中 $\mathcal{T}_{\text{tail}}$ 为 post-peak 序列的最后 $1/3$ 时间点。$D_\infty$ 衡量观测窗口结束时系统的残余扰动水平。

---

## 3. 初始衰减率 $\alpha$

### 3.1 定义

在 $D(t)$ 达到峰值后，定义 post-peak 时间 $t' = t - t_{\text{peak}}$。在初始单调衰减段上对归一化衰减曲线 $D_{\text{norm}}(t')$ 做 log-log OLS 线性拟合：

$$\ln D_{\text{norm}} = -\alpha \cdot \ln t' + \ln A$$

$\alpha$ 即 log-log 空间中的**负斜率**，描述灾后初始阶段扰动衰减的速率。

- $\alpha$ 大 → 衰减快（系统快速恢复）
- $\alpha$ 小 → 衰减慢（扰动持续）

单调衰减段的确定方式：从 peak 后第一个数据点（$t' = 24\text{h}$）起，保留满足 $D_{\text{norm},i+1} \leq 1.05 \cdot D_{\text{norm},i}$ 的连续段，首次 >5% 反弹即截断（`tol_up = 1.05`）。窗口起点统一为 $t' = 24\text{h}$（排除峰值附近的混沌动力学），终点 $t'_{\text{end}}$ 由数据决定（范围 72–144 h，中位数 96 h）。

**关键设计决策**：

1. **不声称函数形式**：$\alpha$ 纯粹是 log-log 斜率的经验度量，不假设 $D(t') \sim t'^{-\alpha}$ 为真实的幂律衰减。这避免了对函数形式的过度承诺——BIC 比较显示，power-law、exponential、stretched exponential 在短观测段上难以区分。

2. **只拟合衰减段**：确保拟合区间内数据行为一致（持续衰减）。在出现结构性反弹后的时间点上强行拟合会稀释 $\alpha$，模糊初始衰减率的物理含义。

### 3.2 多方法稳健性

核心发现在所有合理的 $\alpha$ 计算方法下保持一致。以下四种固定时间窗口拟合与单调截断法之间的 Pearson $r \geq 0.88$：

| 窗口 | $\rho(\alpha, \delta_{\text{near}})$ | $p$ | $\rho(\alpha, D_{\text{peak}})$ | $p$ |
|------|------|------|------|------|
| 单调截断 $[24, 72\text{–}144\text{h}]$ | $-0.526$ | $0.036$ | $+0.600$ | $0.014$ |
| 固定 $[24\text{h}, 72\text{h}]$ | $-0.500$ | $0.049$ | $+0.644$ | $0.007$ |
| 固定 $[24\text{h}, 96\text{h}]$ | $-0.482$ | $0.059$ | $+0.512$ | $0.043$ |
| 固定 $[24\text{h}, 120\text{h}]$ | $-0.538$ | $0.032$ | $+0.491$ | $0.053$ |
| 固定 $[24\text{h}, 144\text{h}]$ | $-0.515$ | $0.041$ | $+0.574$ | $0.020$ |

$\rho(\alpha, \delta_{\text{near}})$ 的符号在**所有方法下 100% 稳定**，显著性波动反映窗口长度对噪声的不同敏感度。$\rho(\alpha, D_{\text{peak}})$ 在五种方法中四种达到 $p < 0.05$。

### 3.3 OLS vs 稳健估计

在固定窗口或单调段上，OLS 与 Theil-Sen 给出几乎完全相同的 $\alpha$（Pearson $r = 0.9914$，最大差异 0.07）。这是因为在所选数据区间上 $R^2$ 普遍较高（中位数 0.88），不存在杠杆点问题。主分析使用 OLS，SI 中报告 Theil-Sen 作为交叉验证。

---

## 4. 样本选择

### 4.1 基础纳入条件

从全部已处理的事件中，要求：
- 单调段至少 3 个数据点（`min_n_mono ≥ 3`）——确保拟合最低可靠性
- $\delta_{\text{near}}$ 非缺失——确保近场有足够 tile 覆盖
- $\alpha$ 非缺失

### 4.2 独立排除

两个事件被预先排除，排除理由与下游统计分析无关（非 post-hoc）：

| 事件 | 排除理由 |
|------|----------|
| `hurricane_melissa_aftermath` | 灾后余波数据，非独立灾害事件；与 melissa 主事件存在时间重叠 |
| `flooding_rio_grande_do_sul` | 多阶段洪水，$D(t)$ 无明确单峰结构，违反"单次淬火→弛豫"分析框架 |

排除后最终样本：**$n = 16$**。

### 4.4 Route B 最终样本清单（$n=16$）

本研究的**唯一权威样本来源**为 `outputs/cross_disaster_comparison/Dt_decay/tables/Dt_routeB_sample_flags.csv` 中 `route_b_selected == True` 的事件。为避免文档漂移，以下仅列出事件标识与方向符号（数值以该表为准）。

| slug | short_name | $\delta_{\text{near}}$ 符号 |
|---|---|---|
| flooding_in_central_and_eastern_europe_sept_16_2024 | flooding_eu | + |
| hurricane_beryl_across_quintana_roo_and_yucatan_mexico | beryl_qr | − |
| hurricane_beryl_across_southeastern_texas_us | beryl_tx | − |
| hurricane_beryl_pre_landfall_2024 | beryl_pre | 0 |
| hurricane_john_across_southeastern_guerrero_mexico | john_gue | + |
| hurricane_john_southern_mexico_25_september_2024 | john_sm | + |
| hurricane_milton_across_florida_us | milton_fl | + |
| moldova_flooding_2024 | moldova | + |
| spain_flood | spain_flood | + |
| the_earthquake_across_central_mexico | mexico_eq | + |
| the_flooding_across_bagmati_and_koshi_provinces_nepal | nepal_fld | − |
| the_flooding_across_eastern_bangladesh | bangladesh_fld | + |
| the_flooding_across_gujarat_india | gujarat_fld | − |
| turkiye_earthquake_2023 | turkiye | + |
| typhoon_yagi_across_northeastern_vietnam | yagi_vn | − |
| wildfires_in_boise_county_idaho_27_august_2024 | boise_fire | + |

### 4.3 低 $R^2$ 事件处理

$R^2 < 0.6$ 的事件保留在统计分析中，但在散点图中以灰色标记，以区分拟合质量高低。这些事件并不改变相关性方向或显著性（$R^2 \geq 0.8$ 子集：$n = 11$，$\rho = -0.673$，$p = 0.023$）。

---

## 5. 统计分析

### 5.1 核心相关性

使用 **Spearman 秩相关** $\rho$ 作为主统计量（不假设线性关系）。核心检验：

| 相关对 | $\rho$ | $p$ | 含义 |
|--------|--------|-----|------|
|| $\alpha$ vs $\delta_{\text{near}}$ | $-0.526$ | $0.036$ | 疏散型事件恢复更快 |
| $\alpha$ vs $D_{\text{peak}}$ | $+0.600$ | $0.014$ | 更大扰动恢复更快 |
|| $D_{\text{peak}}$ vs $\delta_{\text{near}}$ | $-0.129$ | $0.633$ | 两个预测变量统计独立 |

散点图中叠加 **Theil-Sen 回归线**（非参数，抗离群值）作为趋势可视化。

### 5.2 偏相关

$\alpha$ 的两个预测变量（$\delta_{\text{near}}$ 和 $D_{\text{peak}}$）统计独立（$\rho = -0.129, p = 0.633$），可以分别计算偏相关以确认各自的独立贡献：

| 偏相关 | 值 |
|--------|-----|
|| $\alpha$ vs $\delta_{\text{near}} \mid D_{\text{peak}}$ | $\rho_{\text{partial}} = -0.566$ |
|| $\alpha$ vs $D_{\text{peak}} \mid \delta_{\text{near}}$ | $\rho_{\text{partial}} = +0.631$ |

两个偏相关均大于对应的零阶相关，表明两个预测变量解释的是 $\alpha$ 的不同维度，彼此不存在混淆。

### 5.3 稳健性检验矩阵

| 检验项 | 方法 | 结果 | 结论 |
|--------|------|------|------|
| **留一法 Jackknife** | 逐一移除每个事件，重算 $\rho$ | 95% CI 不穿越 0 | 无单一事件驱动 |
| **$R^2$ 分层** | 仅保留 $R^2 \geq 0.8$ 的事件 | $n=11$，$\rho=-0.673$，$p=0.023$ | 信号在高质量子集增强 |
| **$r_{\text{near}}$ 扫描** | 10–200 km 逐步改变 $r_{\text{near}}$ | $\rho$ 始终为负（$[-0.48, -0.34]$） | 符号 100% 稳定 |
| **$r_{\max}$ 扫描** | 50–400 km 改变 $r_{\max}$ | 100–150 km 处 $\rho$ 更强（~$-0.6$） | 200 km 为保守选择 |
| **多时间窗口** | 24-72h, 24-96h, 24-120h, 24-144h | ρ 符号在所有窗口一致（$p$ 范围 0.036–0.059） | 窗口选择无影响 |
| **$D(72)/D(24)$ 比值** | 完全非参数的衰减指标 | $\rho = +0.515$, $p = 0.041$ | 不依赖任何拟合 |
| **OLS vs Theil-Sen** | 两种估计器对比 | Pearson $r = 0.99$ | OLS 无偏差 |
| **已排除的候选预测变量** | 空间集中度、恢复梯度、观测窗口长度 | 均 $|\rho| < 0.15$, $p > 0.5$ | 非混淆因素 |

### 5.4 距离分段分析（补充）

将 $\alpha$ 按距离分段计算：近场（0–50 km）、中场（50–100 km）、远场（100–200 km）。中场 $\alpha$ 与 $\delta_{\text{near}}$ 的相关性最强（$\rho = -0.733$, $p = 0.025$），但由于每段合格事件数降至 $n = 9$，该结果仅在 SI 中报告，不作为主论点。

---

## 6. 参数默认值汇总

| 参数 | 符号 | 默认值 | 含义 |
|------|------|--------|------|
| 最大距离 | $r_{\max}$ | 200 km | $D(t)$ 平均的径向范围 |
| 近场半径 | $r_{\text{near}}$ | 50 km | $\delta_{\text{near}}$ 的定义范围 |
| 距离分箱宽度 | $\Delta r$ | 10 km | 空间离散化步长 |
| Peak 窗口比例 | $f_{\text{peak}}$ | 0.5 | $\delta_{\text{near}}$ 平均所用 peak 窗口 |
| 最小重叠 tile | — | 3 | 每个 $(r, t)$ 格点的最小 tile 数 |
| $\alpha$ 时间窗口 | — | [24h, 72–144h] | 单调衰减段 log-log 拟合范围 |
| 单调容忍度 | `tol_up` | 1.05 | 单调截断的反弹容忍阈值 |
| PDE 径向边界 | $R$ | 200 km | Bessel 展开的径向域 |
| Bessel 模态数 | $N$ | 10 | 展开截断阶数（含基模态） |
| PDE 全局衰减率 | $k$ | 0.00418 h⁻¹ | 网格搜索最优值 |
| PDE 扩散系数 | $D_s$ | 0.304 km² h⁻¹ | 网格搜索最优值 |

---

## 7. 软件与可复现性

- **语言**：Python 3.9+
- **核心依赖**：pandas, numpy, scipy (spearmanr, theilslopes, curve_fit, jn_zeros, j0), matplotlib
- **经验分析管线**：`python scripts/dt_decay.py --output-root outputs/`
- **PDE 模型管线**：`python -m scripts.spatial_diffusion --run-until 4 --pred-mode E --t-start 1.0 --exp2-align-to-exp3 1`
- **中间产物**：`phi_rt_long.csv`（tile→距离分箱聚合）、`Dt_all_events.csv`（日均 D(t) 序列）
- **经验分析输出**：`Dt_powerlaw_fits.csv`、`Dt_event_summary.csv`、`Dt_routeB_*.csv`
- **PDE 模型输出**：`pde_optimal_params.csv`、`pde_alpha_predictions.csv`、`counterfactual_results.csv`

---

## 8. 空间扩散-弛豫 PDE 模型

### 8.1 动机

§5.1 的经验发现——$\rho(\alpha, \delta_{\text{near}}) = -0.526$——表明初始空间剖面的形状编码了恢复速度的信息。但相关性本身不构成机制解释。本节建立一个最小化的偏微分方程模型，检验以下因果假说：**空间扩散与指数衰减的联合作用，是否足以让初始剖面形状决定后续的衰减速率？**

### 8.2 控制方程

将灾害参考点视为原点，假设径向对称，人口偏移场 $\delta(r, t)$ 满足扩散-弛豫方程：

$$\frac{\partial \delta}{\partial t} = \frac{D_s}{r} \frac{\partial}{\partial r}\left(r \frac{\partial \delta}{\partial r}\right) - k \, \delta$$

其中 $D_s$ 为空间扩散系数（km² h⁻¹），$k$ 为均匀衰减率（h⁻¹）。

- **扩散项**描述人口偏移沿径向的空间扩展（Fick 定律在柱坐标下的形式）。
- **衰减项** $-k\delta$ 描述人口向稳态的均匀弛豫（工作恢复、设施重开等驱动力）。

边界条件：Neumann（零通量），$\partial \delta / \partial r |_{r=0} = \partial \delta / \partial r |_{r=R} = 0$，其中 $R = 200$ km。

### 8.3 Bessel 展开与解析解

方程的解在 Neumann 边界条件下可用零阶 Bessel 函数 $J_0$ 展开：

$$\delta(r, t) = \sum_{n=0}^{N-1} c_n \, J_0\!\left(\frac{\alpha_n \, r}{R}\right) \exp(-\lambda_n \, t)$$

> **符号说明**：这里的 $\alpha_n$ 表示 $J_0'(x) = 0$ 的正零点（Bessel 零点），与经验衰减率 $\alpha$（log-log 斜率）不同。正式论文中将使用 $z_n$ 或 $\mu_n$ 表示 Bessel 零点以避免混淆。

其中 $\alpha_0 = 0$，$\alpha_n$（$n \geq 1$）为 $J_0'(x) = 0$ 的正零点，模态衰减率为：

$$\lambda_n = k + D_s \left(\frac{\alpha_n}{R}\right)^2$$

**关键物理机制**：高阶模态（$n \gg 1$）具有更大的空间波数 $\alpha_n/R$，因此衰减更快。不同事件的初始剖面 $\delta(r, 0)$ 具有不同的模态系数 $\{c_n\}$——空间结构越复杂（高阶成分越多），总体衰减越快。这正是为什么初始剖面形状能预测 $\alpha$。

### 8.4 初始条件的确定

对每个事件，取峰值时刻 $t_{\text{peak}}$ 的径向剖面 $\delta(r, t_{\text{peak}})$ 作为 PDE 的初始条件。通过 $r$-加权的最小二乘分解（利用 Bessel 函数的正交关系 $\int_0^R J_0(\alpha_m r/R) J_0(\alpha_n r/R) \, r \, dr = 0, \, m \neq n$）求得展开系数：

$$c_n = \frac{\int_0^R \delta(r, 0) \, J_0(\alpha_n r / R) \, r \, dr}{\int_0^R J_0^2(\alpha_n r / R) \, r \, dr}$$

实际操作中，$\delta(r, 0)$ 先从观测的 10 km 分箱数据插值到 200 点的均匀 $r$ 网格，再用数值梯形积分计算上述投影。展开截断为 $N = 10$ 个模态。

### 8.5 预测衰减率 $\alpha_{\text{pred}}$

给定全局参数 $(k, D_s)$ 和事件特有的系数 $\{c_n\}$，PDE 解可以解析计算任意时刻的空间场 $\delta(r, t)$。定义能量度量：

$$E(t) = \frac{\int_0^R \delta^2(r, t) \, r \, dr}{\int_0^R r \, dr}$$

其中 $r$-加权确保与 Bessel 正交性一致（Parseval 等式）。

> **$E(t)$ 与 $D(t)$ 的关系**：经验指标 $D(t) = \langle |\phi(r,t) - 1| \rangle_r$ 是径向剖面偏移的一阶矩（$L^1$ 范数），$E(t)$ 是二阶矩（$L^2$ 范数的平方）。两者衡量的是同一剖面的不同"大小"度量。PDE 使用 $E(t)$ 而非 $D(t)$ 是因为 Bessel 展开下 $E(t)$ 有解析的 Parseval 表达式（$E(t) = \sum c_n^2 e^{-2\lambda_n t}$），便于理论分析。我们对两者衰减率的排序一致性有信心，但承认这是一个近似。

对 $E(t)$ 在时间窗口 $[1\text{h}, 120\text{h}]$ 做 log-log OLS 拟合，负斜率即为 $\alpha_{\text{pred}}$。

> **注意**：$\alpha_{\text{pred}}$ 的拟合窗口起点（1h）早于经验 $\alpha$ 的起点（24h），因为 PDE 解需要在高阶模态快速衰减的初始阶段捕捉全部动力学。两者的拟合窗口不完全一致，但 $\alpha_{\text{pred}}$ 的主要功能是提供**秩序预测**（$\rho(\alpha_{\text{pred}}, \alpha_{\text{emp}}) = 0.503$），而非绝对值匹配。

**设计要点**：
- 时间采样在 $[0, 24)$ h 使用 1 h 步长（捕捉高阶模态的快速衰减），$[24, 240]$ h 使用 8 h 步长，共 51 个时间点。
- $k$ 和 $D_s$ 是两个**全局参数**，所有事件共享同一组值——事件间的 $\alpha_{\text{pred}}$ 差异完全来自初始剖面的空间结构。

### 8.6 参数估计

在对数均匀的二维网格上搜索最优 $(k, D_s)$。对每组候选参数，计算全部 16 个事件的 $\alpha_{\text{pred}}$，评估四个准则：

1. **max Spearman**：最大化 $\rho(\alpha_{\text{pred}}, \alpha_{\text{emp}})$
2. **max Pearson**：最大化 $r(\alpha_{\text{pred}}, \alpha_{\text{emp}})$
3. **min MAE**：最小化 $|\alpha_{\text{pred}} - \alpha_{\text{emp}}|$ 的均值
4. **min joint rank**（主准则）：三个指标排名之和最小化

主准则 (min joint rank) 的最优参数为 $k = 0.00418$ h⁻¹、$D_s = 0.304$ km² h⁻¹。

### 8.7 反事实实验

为验证 PDE 模型复现 $\rho(\alpha, \delta_{\text{near}})$ 的信号确实源于空间扩散 + 剖面形状的联合作用，设计三组反事实实验：

| 反事实 | 操作 | 预期 | 观测 |
|--------|------|------|------|
| **Ds = 0**（无扩散） | 关闭扩散项，所有模态以相同速率 $k$ 衰减 | $\alpha_{\text{pred}}$ 对所有事件相同 → $\rho = 0$ | $\rho = 0.0$, $p = 1.0$ ✓ |
| **仅基模态** | 只保留 $c_0$（空间均匀成分） | 剖面形状信息被移除 → $\rho = 0$ | $\rho = 0.0$, $p = 1.0$ ✓ |
| **Shuffle 剖面** | 随机打乱事件-剖面的配对 | 破坏因果关系 → $\rho \approx 0$ | $\rho = -0.008$, 95% CI $[-0.52, 0.52]$ ✓ |

三组反事实均符合预期，排除了以下替代解释：
- 信号来自 $k$ 本身（Ds=0 排除）
- 信号来自剖面的整体幅度而非空间结构（c₀-only 排除）
- 信号来自全局参数偏差的伪关联（shuffle 排除）

### 8.8 Bootstrap 稳健性

对初始剖面施加 ±10% 的随机扰动，重复 500 次：

- Bootstrap $\rho$ 均值 = $-0.482$，中位数 = $-0.513$
- 95% CI = $[-0.763, -0.079]$，**不含零**
- 98.4% 的 bootstrap 重复中 $\rho < 0$

---

*文档版本：v2.1*  
*最后更新：2025-02-18*  
*变更：§3 α拟合方法描述与代码对齐（单调截断为主方法，新增§3.2五种窗口/方法的完整稳健性表）；§6参数表更新；§8.4 N→10；§8.5 PDE拟合窗口注明[1h, 120h] + E(t)与D(t)关系说明；§8.3 Bessel零点符号注释*
