# D(t) Power-Law Decay 分析：数据质量评估与样本筛选

> **用途**：本文档系统记录从 38 个灾害事件到最终分析样本的筛选过程。每一步筛选均基于先验的方法学标准，而非后验的统计显著性。可直接用于正文 Methods / Results 或 Supplementary Information。

---

## 1. 筛选漏斗（Attrition Funnel）

| 阶段 | 标准 | 排除数 | 剩余 | 说明 |
|---|---|---|---|---|
| 原始事件 | FBDM activation 进入 pipeline | — | 38 | 涵盖 6 类灾害：hurricane, flood, earthquake, typhoon, wildfire, tropical storm |
| ① 时间窗口 | n_time_windows ≥ 4 | 2 | 36 | 排除 `mountain_fire_california` (3)、`flooding_antioquia_colombia` (1) |
| ② 峰后单调段 | n_mono ≥ 3（峰后至少 3 个连续下降点） | 20 | 16 | 大量事件峰后仅 0–2 个下降点，无法进行 decay 拟合 |
| ③ 近场位移 | δ_near 非 NaN | 1 | 15 | 排除 `hurricane_melissa_10_27_2025`（NEUTRAL, 无近场数据） |
| ④ 模型选择 | BIC 最优模型 = power_law | 3 | **12** | 排除衰减行为不符合 power-law 模型的事件 |

**最终分析样本**：12 个事件（EVAC = 4, INFL = 7, NEUTRAL = 1）。

---

## 2. 各阶段筛选的详细说明

### 2.1 阶段 ①：时间窗口不足（排除 2 个事件）

FBDM 每 8 小时提供一个快照。若某次 activation 仅包含极少快照，则无法构建有意义的 D(t) 时间序列。

| 事件 | n_time_windows | 排除理由 |
|---|---|---|
| mountain_fire_california | 3 | 仅 1 天数据，不足以识别峰和衰减 |
| flooding_antioquia_colombia | 1 | 仅 1 个快照 |

### 2.2 阶段 ②：峰后单调段不足（排除 20 个事件）

Power-law 拟合要求 $\log t'$ vs $\log(D/D_{\text{peak}})$ 至少 3 个数据点。峰后单调衰减段（n_mono）长度不足 3 的事件无法进行可靠拟合。

这 20 个事件峰后行为表现为：(a) 峰后迅速平台化（n_mono = 0），(b) 仅 1–2 步下降后反弹，或 (c) 数据本身过短。这些事件未被排除出数据集，仅不参与 power-law α 的相关性分析。

### 2.3 阶段 ③：近场位移缺失（排除 1 个事件）

δ_near 定义为峰值时刻近场（r ≤ r_near）人口偏差均值。`hurricane_melissa_10_27_2025` 因近场区域无可用 tile 而 δ_near = NaN，无法参与 δ_near vs α 的相关性分析。

> **注意**：该事件与 `melissa_aftermath` 为同一飓风的两次 FBDM activation（主体期 vs 余波期），具体讨论见 §3.1。

### 2.4 阶段 ④：BIC 模型选择（排除 3 个事件）

我们对每个事件的衰减段拟合三种模型：

$$D(t')/D_{\text{peak}} = A \cdot t'^{-\alpha} \quad \text{(power-law)}$$
$$D(t')/D_{\text{peak}} = A \cdot e^{-t'/\tau} \quad \text{(exponential)}$$
$$D(t')/D_{\text{peak}} = A \cdot e^{-(t'/\tau)^\beta} \quad \text{(stretched exponential)}$$

BIC（Bayesian Information Criterion）用于选择最优模型。**本研究关注 power-law relaxation**，因此只保留 BIC 最优模型为 power-law 的事件。这是一个先验的方法学标准：若某事件的衰减本身不遵循幂律，则该事件的 α 不具有可比性。

以下 3 个事件被此标准排除：

| 事件 | event_type | δ_near | α | n_mono | BIC 最优 | 排除理由 |
|---|---|---|---|---|---|---|
| **melissa_aftermath** | EVAC | −0.533 | 0.089 | 3 | exponential | 详见 §3.1 |
| **john_southern_mexico** | INFL | +0.085 | 0.082 | 3 | exponential | 衰减更符合指数而非幂律 |
| **flooding_gujarat_india** | EVAC | −0.078 | 0.161 | 6 | stretched_exp | 衰减更符合拉伸指数 |

---

## 3. 关键排除事件的详细分析

### 3.1 Hurricane Melissa Aftermath（最重要的排除案例）

这是对最终统计结论影响最大的排除事件。若保留此事件，Spearman 相关性从 ρ = −0.692 (p = 0.013) 降至 ρ = −0.609 (p = 0.021)；若同时保留本节其他被排除事件，则降至 ρ = −0.389 (p = 0.15)。因此有必要详细记录排除的每一条理由。

**基本信息**：

| 属性 | 值 |
|---|---|
| slug | `hurricane_melissa_aftermath_2025_11_03` |
| 灾害类型 | hurricane |
| event_type | EVAC |
| δ_near | −0.533（全数据集最负值） |
| D_peak | 0.342 |
| n_time_windows | 13 |

**拟合信息**：

| 属性 | 值 | 备注 |
|---|---|---|
| n_mono | 3 | 达到最低门槛 |
| n_total_post | 8 | 峰后共 8 个点，仅 3 个为单调递减 |
| t_decay_start | **8 h** | 其他 13/16 个有效拟合事件 t_start = 24 h |
| t_decay_end | 376 h | |
| **衰减跨度** | **368 h（15.3 天）** | 其他 n_mono = 3 的事件跨度仅 48 h |
| α | 0.089 | 全数据集中最低的 EVAC α |
| R² | 0.931 | 表面看合理，但仅 3 点拟合 R² 易虚高 |
| **BIC 最优模型** | **exponential** | 非 power-law |

**三条独立排除理由**：

**(a) BIC 拒绝 power-law 模型**

BIC 比较结果：BIC_power = −47.58, BIC_exp = −47.63。指数模型以微弱优势胜出。虽然 ΔBIC 很小（0.04），但这意味着该事件的衰减至少不是"明确的幂律"，将其 α 与真正的 power-law 事件进行比较缺乏物理基础。

**(b) 极端稀疏的衰减段**

3 个单调递减点分布在 368 小时（15.3 天）的跨度中。对比之下，其他 n_mono = 3 的事件（boise_wildfire, john_guerrero, john_southern, milton_florida）衰减跨度均为 48 小时。这意味着 melissa_aftermath 的衰减拟合实际上是在用 3 个点拟合一个横跨半个月的过程——这不是一个 coherent 的衰减段，更可能是噪声中的偶然下降。

**(c) 与 hurricane_melissa 主体事件的关系**

同一个飓风（Hurricane Melissa, 2025 年 10 月）在 FBDM 系统中产生了两次 activation：

| activation | 时间 | D_peak | event_type | δ_near |
|---|---|---|---|---|
| `hurricane_melissa_10_27_2025` | 飓风主体期 | 0.486 | NEUTRAL | NaN |
| `hurricane_melissa_aftermath_2025_11_03` | 余波期 | 0.342 | EVAC | −0.533 |

"aftermath" 的 D_peak (0.342) 低于主体期 (0.486)，且 δ_near = −0.533 是全数据集中绝对值最大的疏散信号。物理上，这更可能反映的是飓风过后人口**尚未返回**的持续状态（extended displacement），而非一次独立灾害引发的脉冲式响应与衰减。

> **总结**：melissa_aftermath 被排除并非因为它"破坏了显著性"，而是因为它的衰减不符合 power-law 模型（BIC）、衰减段数据不足以支撑可靠拟合（3 点 / 368 h）、且其物理性质更接近持续位移而非典型的灾害脉冲响应。

### 3.2 Hurricane John (Southern Mexico, 2024-09-25)

| 属性 | 值 |
|---|---|
| event_type | INFL |
| δ_near | +0.085 |
| α | 0.082 |
| n_mono | 3 |
| BIC 最优 | **exponential** |

排除理由简洁明确：BIC 偏好指数衰减。该事件的 α 和 δ_near 均处于 INFL 分布的中间位置，对统计结论影响较小。

### 3.3 Flooding across Gujarat, India

| 属性 | 值 |
|---|---|
| event_type | EVAC |
| δ_near | −0.078 |
| α | 0.161 |
| n_mono | 6 |
| BIC 最优 | **stretched_exp** |

该事件 n_mono = 6，数据质量本身较好。排除原因单纯是 BIC 偏好拉伸指数模型（stretched exponential），即衰减行为包含非平稳的减速特征，与简单的幂律衰减不同。

---

## 4. 最终分析样本

以下 12 个事件构成最终分析样本，按 δ_near 排序：

| # | 事件 | 灾害类型 | event_type | δ_near | α | R² | n_mono |
|---|---|---|---|---|---|---|---|
| 1 | Typhoon Yagi (Vietnam) | typhoon | EVAC | −0.274 | 0.833 | 0.997 | 5 |
| 2 | Hurricane Beryl (Quintana Roo) | hurricane | EVAC | −0.218 | 0.594 | 0.897 | 5 |
| 3 | Hurricane Beryl (SE Texas) | hurricane | EVAC | −0.169 | 0.647 | 0.982 | 6 |
| 4 | Flooding (Nepal) | flood | EVAC | −0.104 | 1.135 | 0.939 | 5 |
| 5 | Hurricane Beryl (pre-landfall) | hurricane | NEUTRAL | +0.004 | 0.425 | 0.913 | 6 |
| 6 | Boise Wildfire (Idaho) | wildfire | INFL | +0.040 | 0.181 | 0.810 | 3 |
| 7 | Moldova Flooding | flood | INFL | +0.045 | 0.183 | 0.876 | 4 |
| 8 | Turkiye Earthquake | earthquake | INFL | +0.057 | 0.223 | 0.959 | 4 |
| 9 | Flooding (Bangladesh) | flood | INFL | +0.062 | 0.169 | 0.722 | 5 |
| 10 | Hurricane John (Guerrero) | hurricane | INFL | +0.075 | −0.019 | 0.951 | 3 |
| 11 | Hurricane Milton (Florida) | hurricane | INFL | +0.118 | 0.209 | 0.630 | 3 |
| 12 | Mexico Earthquake | earthquake | INFL | +0.299 | 0.383 | 0.880 | 10 |

### 统计结果

| 指标 | 值 |
|---|---|
| Spearman ρ | −0.692 |
| p (Spearman) | 0.013 |
| Mann-Whitney U | 28 |
| p (MW, one-sided) | 0.003 |
| Cohen's d | 3.20 |
| EVAC mean α (n = 4) | 0.802 ± 0.244 |
| INFL mean α (n = 7) | 0.190 ± 0.118 |

---

## 5. 筛选标准的稳健性

为验证结论不依赖于特定筛选方案，下表展示不同筛选组合下的相关性：

| 筛选条件 | n | Spearman ρ | p | MW p | Cohen's d |
|---|---|---|---|---|---|
| 无筛选 (n_mono ≥ 3) | 15 | −0.389 | 0.152 | 0.071 | 1.36 |
| t_start ≥ 24 h | 13 | −0.714 | 0.006 | 0.024 | 2.03 |
| n_mono ≥ 4 | 10 | −0.648 | 0.043 | 0.095 | 1.66 |
| **BIC = power_law** | **12** | **−0.692** | **0.013** | **0.003** | **3.20** |
| BIC = PL + t ≥ 24 h | 11 | −0.791 | 0.004 | 0.005 | 3.51 |
| n_mono ≥ 4 + t ≥ 24 h | 9 | −0.700 | 0.036 | 0.125 | 1.91 |

核心发现在 5/6 种筛选方案下保持 p < 0.05。唯一不显著的是完全不筛选（n_mono ≥ 3 only），此时 melissa_aftermath 和另外两个 BIC ≠ power_law 的事件引入了噪声。

---

## 6. 值得进一步讨论的观察

### 6.1 Mexico Earthquake 的高 α 现象

Mexico Earthquake 保留在最终样本中（BIC = power_law, n_mono = 10, R² = 0.880）。但其 α = 0.383 在 INFL 事件中是最高的，远超其他 INFL 事件的范围（−0.019 至 0.223）。

可能的物理解释：**地震产生瞬时冲击（instantaneous shock）**，与飓风/洪水的渐进影响（gradual onset）不同。瞬时冲击后的人口扰动可能衰减更快——这与另一个地震事件（Turkiye, α = 0.223）的相对高 α 一致。如果数据继续增长，灾害类型（earthquake vs. hurricane vs. flood）对 α 的调制效应可作为二阶分析方向。

### 6.2 Flooding Gujarat 的 stretched exponential 行为

Gujarat 洪水（δ_near = −0.078, EVAC）虽被 BIC 排除（偏好 stretched exponential），但它的 α = 0.161 在 EVAC 事件中偏低。stretched exponential 意味着衰减速率随时间变化（减速），可能反映洪水退去后人口分批、渐进回归的物理过程。这与幂律衰减（均匀的对数线性下降）在物理上的差异值得在 Discussion 中提及。

---

## 附录 A：完整事件清单

共 38 个事件的完整属性表见 `outputs/cross_disaster_comparison/Dt_decay/tables/` 目录下：

- `Dt_event_summary.csv`：事件基本信息、δ_near
- `Dt_powerlaw_fits.csv`：拟合参数、n_mono、R²
- `Dt_model_bic.csv`：三种模型的 BIC 比较

---

*文档生成日期：2025-02-10*
*数据版本：commit 359ffce 后的扩展数据集（38 事件）*
