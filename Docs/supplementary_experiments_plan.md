# 补充实验规划：闭合理论–证据链条

## 背景

当前 manuscript 的理论 framing 是：**灾后人口恢复是扰动场的扩散弛豫过程，恢复速率由初始扰动的空间频谱决定**。Bessel 分解给出 $\delta(r,t)=\sum_n c_n J_0(\mu_n r/R)\,e^{-\lambda_n t}$，其中 $\lambda_n = k + D_s(\mu_n/R)^2$，高阶模态衰减更快。

但论文全程只使用了 $\dnear = \langle\delta(r)\rangle_{r<50\,\text{km}}$ 作为**代理量**，从未直接展示谱 $\{c_n\}$。这让 "$\dnear$ 是谱探针" 成为声称而非证据。

本文档列出五项补充实验，按优先级排序。前三项是刊发所需，后两项是加分项。

---

## 实验 A1：谱分解的直接展示 [关键，必做]

### 科学目的

把 $\dnear$ 从"幸运的经验预测器"升级为"有物理依据的谱探针"。直接回答：
1. 每个事件的实际 Bessel 能量谱长什么样？
2. 快恢复事件的能量是否真的集中在高阶模态？
3. 标量指标 $\dnear$ 与更直接的谱指标相比，预测力如何？

### 输入数据

- 18 个事件的 peak 时刻径向 profile $\hat\delta(r_i)$（10-km 分箱，$r_i \in \{5, 15, \ldots, 195\}$ km）
- 已有的 Bessel 拟合代码（现有 PDE 模块已经在算 $\{c_n\}$，见 `scripts/` 下 PDE 相关文件）

### 分析步骤

1. **对每个事件提取归一化谱功率**：
   $$P_n = \frac{c_n^2}{\sum_{m=0}^{N-1} c_m^2}, \quad n = 0, 1, \ldots, 9$$
   得到 18 × 10 的矩阵。

2. **计算两个标量谱指标**：
   - **谱质心** $\bar n = \sum_n n \cdot P_n$（加权平均模态序号）
   - **高频能量占比** $f_{\text{hi}} = \sum_{n \geq 2} P_n$（$c_0, c_1$ 以外的能量占比）

3. **与 $\alpha$ 的关联**：
   - 计算 $\rho(\alpha, \bar n)$ 和 $\rho(\alpha, f_{\text{hi}})$
   - 与基准 $\rho(\alpha, \dnear) = -0.69$ 对比
   - 可选：多元回归 $\alpha \sim \dnear + \bar n$，看 $\dnear$ 的偏相关在控制谱质心后是否消失

4. **$\dnear$–谱 对应关系**：
   - 计算 $\rho(\dnear, \bar n)$ 和 $\rho(\dnear, f_{\text{hi}})$
   - 预期：$\dnear < 0$ 的事件应有更高的 $\bar n$ 和 $f_{\text{hi}}$

### 期望输出

**一个新 figure panel**（最合适位置：Fig 3 中新增 panel，或作为 SI figure）：

- **Panel 1（谱图）**：x 轴 = 模态序号 $n$（0–9），y 轴 = 归一化谱功率 $P_n$。18 条折线，按 $\alpha$ 数值从慢到快用颜色梯度。预期看到：**$\alpha$ 大的事件谱向右偏移**。
- **Panel 2（散点）**：$\alpha$ vs $\bar n$（或 $f_{\text{hi}}$），18 个点，配 Spearman $\rho$ 和 $p$ 值。

**一个 SI 子节**（例如 S3.8）：报告 $\bar n$、$f_{\text{hi}}$、$\dnear$ 三者与 $\alpha$ 的相关性表，以及 $\dnear$ 与谱指标的对应关系。

### 给正文的回报

- Fig 3 或 SI figure 首次把"spectrum 决定 $\alpha$"从断言变成数据展示
- Discussion 和 Abstract 里的 "spectral content" 叙述从此有图支撑
- Intro P3 末句可以改写为："$\dnear$ 的方向和幅度反映扰动的谱权重（SI §S3.8）"，不再是悬空断言

---

## 实验 A2：PDE 预测质量的可视化 [重要，必做]

### 科学目的

当前 SI §S3.5 给出了全局最优参数 $k^* = 0.00418\,\text{h}^{-1}$, $D_s^* = 0.304\,\text{km}^2\text{h}^{-1}$，但正文和图中**从未展示 PDE 的预测 $\apred$ 与观测 $\aemp$ 的对比**。读者看不到 PDE 作为 world model 的预测质量，也看不到它的 limitation。

### 输入数据

- 已经计算好的 $\apred$（18 个事件，来自 S3.4 的能量衰减拟合）
- 对应的 $\aemp$（来自主分析）

### 分析步骤

1. 取当前 $k^*, D_s^*$ 下每个事件的 $\apred$ 和 $\aemp$
2. 计算 Pearson $r$、Spearman $\rho$、MAE、以及截距和斜率（OLS）
3. 画 $\apred$ vs $\aemp$ 散点，标 $y = x$ 对角线

### 期望输出

**一个 figure panel**（建议加入 Fig 3 作为第 (b) 或 (e) panel，也可以放 SI）：
- 散点图带 $y=x$ 线，每个点标事件名或灾种颜色
- 标注 Spearman $\rho$、Pearson $r$、MAE
- 如果 PDE 压缩方差（目前 SI 表格显示 $\rho(\apred, \dnear) = -0.356$ 弱于 $\aemp$ 的 $-0.69$），散点会沿 $y=x$ 压扁，这是诚实的 limitation 展示

### 给正文的回报

- Discussion 的 limitation 段"the model recovers event ranking but compresses variance" 得到图的支撑，不再是文字声明
- Methods PDE 子节可以删掉当前的 premature disclaimer "This calibration is used as a parsimonious consistency check..."，让图自己说话

---

## 实验 A3：振幅 vs 形状的分离 [重要，必做]

### 科学目的

$\dnear$ 当前同时包含了"多少人动了"（振幅）和"往哪边走"（方向/几何）。理论强调几何决定速率，但如果不控制振幅，审稿人会问："会不会只是疏散事件总位移更大？"

需要验证：**在控制总振幅后，几何信息仍然预测 $\alpha$**。

### 输入数据

- 每个事件的径向 profile $\delta(r)$ 和 Bessel 系数 $\{c_n\}$
- 每个事件的 $D_{\text{peak}}$（已有）

### 分析步骤

**三个独立检验，任选两个即可**：

1. **偏相关**：计算 $\alpha \sim \dnear + D_{\text{peak}}$ 的 OLS，报告 $\dnear$ 在控制 $D_{\text{peak}}$ 后的偏相关系数和 $p$ 值。预期 $\dnear$ 依然显著，$D_{\text{peak}}$ 不显著。

2. **能量归一化的 $\dnear$**：对每个事件，把 $\delta(r)$ 按能量归一化 $\tilde\delta(r) = \delta(r) / \sqrt{\sum_i r_i \delta(r_i)^2}$（或 $L^2$ 归一化），然后计算 $\tilde{\dnear} = \langle\tilde\delta(r)\rangle_{r<50\,\text{km}}$。检验 $\rho(\alpha, \tilde{\dnear})$ 是否与 $-0.69$ 可比。

3. **归一化谱指标**：使用实验 A1 的 $\bar n$ 或 $f_{\text{hi}}$，这两个指标天然是归一化谱功率的函数，与总振幅无关。如果 A1 中这些指标与 $\alpha$ 强相关，就同时完成了 A3。

### 期望输出

- SI 新子节：报告偏相关和归一化结果
- 如果 A1 的谱指标表现好，正文可以直接引用谱指标（天然振幅无关），A3 自然闭合

### 给正文的回报

- Abstract 和 Discussion 里"geometry not magnitude"的声明得到直接证据
- 排除一个显而易见的混淆变量

---

## 实验 A4：$r_{\text{cut}}$ 连续敏感性 [中等，建议做]

### 科学目的

当前 SI §S5 只给了 $r<50$ / 50–100 / 100–200 km 三个离散区间的 $\rho$ 值。审稿人可能怀疑 50 km 是事后挑选。连续曲线可消除这个 concern。

### 分析步骤

1. 对 $r_{\text{cut}} \in \{20, 30, 40, \ldots, 150\}$ km，每个 step 定义 $\bar\delta(r<r_{\text{cut}}) = \langle\delta(r)\rangle_{r<r_{\text{cut}}}$
2. 对每个 $r_{\text{cut}}$ 计算 $\rho(\alpha, \bar\delta(r<r_{\text{cut}}))$
3. 画曲线

### 期望输出

- SI figure：x 轴 $r_{\text{cut}}$（km），y 轴 $\rho$ 值（及 95% CI 带）。
- 预期：$[40, 80]$ km 之间稳定在 $\rho \in [-0.75, -0.6]$，证明 50 km 不是 cherry-picked

### 给正文的回报

- SI §S5 从三段离散值升级为连续曲线，变得更有说服力
- Methods 中 $\dnear$ 的 50 km 选择变成 robust 区间中的一个代表点，不是单点

---

## 实验 A5：扩散方程的直接观测验证 [可选，加分项]

### 科学目的

当前证据链是**间接**的：用 PDE 的解拟合观测，反推参数。一个更直接的 world-model 检验是：**直接验证 $\partial_t \delta \propto \nabla^2 \delta - k\delta$ 在数据上成立**。

### 可行性

- FBDM 时间分辨率 8 小时，peak 附近有 $D(t)\geq 0.5 D_{\text{peak}}$ 的 plateau 通常 2–4 步
- 径向 profile $\delta(r, t)$ 已有，可以数值估计 $\partial_t \delta$ 和 $\nabla^2 \delta = \frac{1}{r}\partial_r(r\partial_r \delta)$
- 噪声是主要障碍

### 分析步骤

1. 对每个事件选择相邻两个 time step（例如 $t_{\text{peak}}$ 和 $t_{\text{peak}}+8\,\text{h}$）
2. 用 10-km 分箱的 $\delta(r_i, t)$ 估计：
   - $\partial_t \delta(r_i) \approx [\delta(r_i, t+8\text{h}) - \delta(r_i, t)] / 8$
   - $\nabla^2 \delta(r_i) \approx \frac{1}{r_i}\cdot \frac{r_{i+1/2}[\delta(r_{i+1})-\delta(r_i)] - r_{i-1/2}[\delta(r_i)-\delta(r_{i-1})]}{(\Delta r)^2}$
3. 回归 $\partial_t \delta \sim \nabla^2\delta + \delta$（理论预期系数分别是 $D_s$ 和 $-k$）
4. 检验估计的 $D_s$ 和 $k$ 是否与 S3.5 的全局最优值 $D_s^* = 0.304$, $k^* = 0.00418$ 一致

### 期望输出

- 每个事件的 local $D_s, k$ 估计，以及 $R^2$
- SI figure：$\partial_t \delta$ vs $D_s \nabla^2\delta - k\delta$ 散点图，标对角线

### 风险

- FBDM 空间分辨率和时间分辨率可能不足以可靠估计二阶空间导数
- 如果回归 $R^2$ 很低，不应强推；可以在 SI 里诚实报告"direct PDE verification 受数据噪声限制"

### 给正文的回报

- 如果成功：从"用 PDE 的解拟合"升级为"PDE 本身成立"，论文 world-model 地位大幅提升
- 如果失败：SI 里诚实说明即可，不影响主结论

---

## 执行优先级和预估工作量

| 实验 | 优先级 | 预估工作量 | 是否依赖已有代码 |
|---|---|---|---|
| A1 谱分解展示 | 关键 | 0.5–1 天 | 是（Bessel 拟合已有） |
| A2 $\apred$ vs $\aemp$ 图 | 必做 | 0.5 天 | 是（数据已算好） |
| A3 振幅-形状分离 | 必做 | 0.5 天 | 是 |
| A4 $r_{\text{cut}}$ 扫描 | 建议 | 0.5 天 | 是 |
| A5 直接 PDE 验证 | 可选 | 1–2 天 | 部分（需新计算） |

**最小充分集**：A1 + A2 + A3。完成这三项后，论文的理论–证据链就闭合了，$\dnear$ 作为谱探针的地位从声称变成证据。

---

## 对 manuscript 的修改对照

完成实验后，正文需要联动修改的地方：

1. **Abstract**：可加一句 "Controlled analysis confirms the spectral basis: events with more negative $\dnear$ have spectra dominated by high-frequency Bessel modes (SI §S3.8)."
2. **Intro P3 末句**：把 "serves as a scalar probe of this spectral content" 改为 "directly reflects the spectral weights (SI §S3.8)"
3. **Methods Parameter Extraction**：在定义 $\dnear$ 时补一句解释——高阶 Bessel 模态的空间变化在近场显著，低阶模态近似空间均匀，因此 $\dnear$ 反映谱权重
4. **Results R2**：在 controlled tests 段加一小段，报告谱质心/高频占比与 $\alpha$ 的相关性
5. **Fig 3**：新增 panel 展示谱或 $\apred$ vs $\aemp$
6. **SI §S3**：新增 S3.8 谱展示、S3.9 振幅控制、更新 S5 为连续曲线

完成这些改动后，manuscript 的叙事就真正从**模型预测→数据确证**闭环，而不是**经验相关→事后解释**。
