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

### 3.1 定义（主方法：固定时间窗口）

在 $D(t)$ 达到峰值后，定义 post-peak 时间 $t' = t - t_{\text{peak}}$，并对归一化衰减曲线 $D_{\text{norm}}(t')$ 在固定时间窗口 $[24\text{h}, 120\text{h}]$ 上做 log-log OLS 线性拟合：

$$\ln D_{\text{norm}} = -\alpha \cdot \ln t' + \ln A$$

$\alpha$ 即 log-log 空间中的**负斜率**，描述灾后初始阶段（1–5天）扰动衰减的速率。

- $\alpha$ 大 → 衰减快（系统快速恢复）
- $\alpha$ 小 → 衰减慢（扰动持续）

**关键设计决策**：

1. **不声称函数形式**：$\alpha$ 纯粹是 log-log 斜率的经验度量，不假设 $D(t') \sim t'^{-\alpha}$ 为真实的幂律衰减。这避免了对函数形式的过度承诺——BIC 比较显示，power-law、exponential、stretched exponential 在短单调段上难以区分。

2. **固定时间窗口**：选择 $[24\text{h}, 120\text{h}]$ 而非自适应单调截断（见 §3.2），消除了"选择最佳行为区间"的审稿人质疑。窗口起点 24h 排除峰值附近的混沌动力学；终点 120h（5天）覆盖初始衰减的核心阶段。

3. **多窗口稳健性**：$[24\text{h}, 72\text{h}]$、$[24\text{h}, 96\text{h}]$、$[24\text{h}, 144\text{h}]$ 均给出相似的 $\alpha$ 值与下游相关性（见 §5.3）。

### 3.2 备选方法：单调截断（SI 稳健性检验）

Pipeline 原始实现使用自适应单调截断：从 peak 后第一个点起，要求 $D_{\text{norm},i+1} \leq 1.05 \cdot D_{\text{norm},i}$（`tol_up = 1.05`），遇到首次 >5% 的反弹即截断，在截断段上做同样的 log-log OLS。

两种方法的比较：
- Pearson 相关：$r = 0.97$（两种 $\alpha$ 几乎等价）
- 固定窗口 $\alpha$ vs $\delta_{\text{near}}$：$\rho = -0.538, p = 0.032$
- 单调截断 $\alpha$ vs $\delta_{\text{near}}$：$\rho = -0.526, p = 0.036$

固定窗口方法作为主方法，单调截断结果在 SI 中报告以证明稳健性。

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
| $\alpha$ vs $\delta_{\text{near}}$ | $-0.538$ | $0.032$ | 疏散型事件恢复更快 |
| $\alpha$ vs $D_{\text{peak}}$ | $+0.600$ | $0.014$ | 更大扰动恢复更快 |
| $D_{\text{peak}}$ vs $\delta_{\text{near}}$ | $+0.003$ | $0.99$ | 两个预测变量相互独立 |

散点图中叠加 **Theil-Sen 回归线**（非参数，抗离群值）作为趋势可视化。

### 5.2 偏相关

$\alpha$ 的两个预测变量（$\delta_{\text{near}}$ 和 $D_{\text{peak}}$）相互独立（$\rho = 0.003$），可以分别计算偏相关以确认各自的独立贡献：

| 偏相关 | 值 |
|--------|-----|
| $\alpha$ vs $\delta_{\text{near}} \mid D_{\text{peak}}$ | $\rho_{\text{partial}} = -0.660$ |
| $\alpha$ vs $D_{\text{peak}} \mid \delta_{\text{near}}$ | $\rho_{\text{partial}} = +0.708$ |

两个偏相关均大于对应的零阶相关，表明两个预测变量解释的是 $\alpha$ 的不同维度，彼此不存在混淆。

### 5.3 稳健性检验矩阵

| 检验项 | 方法 | 结果 | 结论 |
|--------|------|------|------|
| **留一法 Jackknife** | 逐一移除每个事件，重算 $\rho$ | 95% CI 不穿越 0 | 无单一事件驱动 |
| **$R^2$ 分层** | 仅保留 $R^2 \geq 0.8$ 的事件 | $n=11$，$\rho=-0.673$，$p=0.023$ | 信号在高质量子集增强 |
| **$r_{\text{near}}$ 扫描** | 10–200 km 逐步改变 $r_{\text{near}}$ | $\rho$ 始终为负（$[-0.48, -0.34]$） | 符号 100% 稳定 |
| **$r_{\max}$ 扫描** | 50–400 km 改变 $r_{\max}$ | 100–150 km 处 $\rho$ 更强（~$-0.6$） | 200 km 为保守选择 |
| **多时间窗口** | 24-72h, 24-96h, 24-120h, 24-144h | 所有窗口 $p < 0.05$ | 窗口选择无影响 |
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
| $\alpha$ 时间窗口 | — | [24h, 120h] | 固定窗口 log-log 拟合范围 |
| 单调容忍度 | `tol_up` | 1.05 | 备选方法中的反弹容忍阈值 |

---

## 7. 软件与可复现性

- **语言**：Python 3.9+
- **核心依赖**：pandas, numpy, scipy (spearmanr, theilslopes, curve_fit), matplotlib
- **管线入口**：`python scripts/dt_decay.py --output-root outputs/`
- **中间产物**：`phi_rt_long.csv`（tile→距离分箱聚合）、`Dt_all_events.csv`（日均 D(t) 序列）
- **输出表格**：`Dt_powerlaw_fits.csv`（$\alpha$ 拟合）、`Dt_event_summary.csv`（事件级汇总）、`Dt_routeB_*.csv`（相关性与稳健性统计）

---

*文档版本：v1.0*  
*最后更新：2025-01*
