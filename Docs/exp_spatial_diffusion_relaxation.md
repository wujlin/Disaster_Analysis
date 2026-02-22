# 实验路线：空间扩散-弛豫框架（Direction C）

> **目标**：用径向扩散-弛豫 PDE 作为理论论证工具，从初始空间 profile δ(r, t_peak) 的形状**推导出** α 与 δ_near 负相关的必然性，而非精确 predict 每个事件的 α 值。
>
> **核心论点**：α-δ_near 相关不是巧合的统计相关，而是扩散-弛豫动力学的必然结果——初始扰动的空间形状决定了 D(t) 的衰减速率。
>
> **定位**：Nature Communications 级别的 method contribution。Langevin（bin 级独立演化）已被 falsified；本框架引入空间耦合，是本质性的升级。

---

## 背景与动机

### Langevin 路线为什么失败

Langevin 模型假设每个 r-bin 独立演化：$d\delta_i/dt = -k_i \delta_i$。用拟合出的 $(k, \gamma)$ 参数做模拟，ρ(α, δ_near) ≈ 0.057（实际为 -0.53）——**模型在自己的参数空间里都无法复现宏观统计特征**。

根本原因：α 是事件级的 D(t) = ⟨|δ(r,t)|⟩ 的 log-log 衰减斜率。它取决于 50 个 bin 的 |δ(r,t)| 如何协同衰减，而不是每个 bin 独立的恢复速率参数。**空间耦合**（人口从一个区域流向另一个区域）被完全忽略了。

### 诊断性分析发现了什么

对 16 个 Route B 事件的 δ(r, t_peak) 径向 profile 分析发现：

| 指标 | vs δ_near | vs α |
|---|---|---|
| pos_frac（正区域面积占比） | ρ=+0.842, p<0.0001 | ρ=-0.523, p=0.038 |
| c₀（贝塞尔零阶系数） | ρ=+0.782, p=0.0003 | — |
| radial_slope | ρ=-0.618, p=0.011 | — |

**关键洞见**：EVAC 主导事件的 profile 几乎全为负值（人口流失），INFL 主导事件几乎全为正值（人口涌入）。空间 profile 的正负结构**系统性地**与 δ_near 耦合，而 profile 形状直接决定 D(t) 的衰减特征。

用两参数 PDE $(k, D_s)$ 的初步预测：α_predicted vs α_empirical Spearman ρ=0.541, p=0.030。**排序关系保持了，但绝对值匹配差**。说明框架方向对，实现需要优化。

---

## 实验总体设计

### 逻辑链

```
Exp 0: 数据准备（提取 profile + 标准化）
  ↓
Exp 1: 经验层——profile 形状特征 vs α 的系统性分析
  ↓
Exp 2: 理论层——PDE 解析推导 + 简化模型的定性预测
  ↓
Exp 3: 数值层——完整 PDE 数值求解，从 δ(r,0) predict α
  ↓
Exp 4: 综合验证——模拟 + 反事实实验
```

### 不做什么

- 不做 bin 级 Langevin/ODE 拟合（已 falsified）
- 不试图精确 predict 每个事件的 α 绝对值（数据精度不支持）
- 不引入事件级参数（避免 overfitting）

---

## Exp 0: 数据准备

### 目标

为每个 Route B 事件提取标准化的径向 profile δ(r, t_peak)，作为后续所有实验的输入。

### 具体步骤

1. **读取 Route B 16 事件**：从 `Dt_routeB_sample_flags.csv` 获取 slug 列表、t_peak_hours、alpha、near_delta、D_peak。

2. **对每个事件加载 phi_rt_long.csv**：路径为 `outputs/{slug}/phi_heatmap/tables/phi_rt_long.csv`。

3. **计算 δ(r, t)**：`delta = phi_overlap - 1.0`。过滤条件：r_bin_km ≤ 200, n_tiles_overlap ≥ 3。

4. **提取 t_peak 时刻的径向 profile**：找最接近 t_peak_hours 的时间快照 t_snap，取该时刻所有 r_bin 的 delta 值。记录 t_snap 与 t_peak 的偏差。

5. **提取完整后峰时序**：t > t_peak 的所有 (r_bin, t, delta) 数据，用于 Exp 3。

6. **如果某事件的原始数据是 8h 分辨率且 median_step < 16h**：对同一 r_bin 的 delta 做日平均（与现有 pipeline 保持一致）。

### 输出

- `tables/radial_profiles_at_peak.csv`：列 = [slug, short_name, r_bin_km, delta_at_peak, n_tiles, t_snap, t_peak_hours, delta_near, D_peak, alpha, event_type, disaster_type]
- `tables/post_peak_trajectories.csv`：列 = [slug, r_bin_km, hours_since_peak, delta, n_tiles]（用于 Exp 3 的数值拟合）

---

## Exp 1: Profile 形状特征的系统性分析

### 目标

用多个互补的指标量化 δ(r, 0) 的空间形状，建立 profile shape → α 的经验关联图谱。

### 1.1 基础 shape 指标（per event）

对每个事件的 δ(r, t_peak) profile 计算：

| 指标 | 定义 | 物理含义 |
|---|---|---|
| `pos_frac` | ∫ max(δ,0) dr / ∫ \|δ\| dr | 正区域面积占比。=1 全 INFL，=0 全 EVAC |
| `r_centroid` | ∫ r·\|δ(r)\| dr / ∫ \|δ(r)\| dr | 扰动的质心距离 |
| `spatial_cv` | std(δ) / \|mean(δ)\| | 空间变异系数 |
| `radial_slope` | OLS slope of δ(r) ~ a + b·r | 径向梯度方向 |
| `sign_changes` | δ(r) 的符号翻转次数 | profile 的复杂度 |
| `delta_range` | max(δ) - min(δ) | 空间对比度 |
| `gradient_0_100` | δ(r=0) - δ(r=100km) | 近-远场梯度 |

### 1.2 贝塞尔模态分解

在 [0, R_max=200km] 上对 δ(r) 做 J₀ 贝塞尔函数展开：

$$\delta(r) = \sum_{n=0}^{N-1} c_n J_0\!\left(\frac{\alpha_n r}{R_{\max}}\right)$$

其中 α_n 是 J₀ 的第 n 个零点。

计算方法：
1. 将 δ(r) 线性插值到均匀 r 网格（200 点，0 到 200km）
2. 计算展开系数：$c_n = \frac{\int_0^R \delta(r) J_0(\alpha_n r/R)\, r\, dr}{\int_0^R [J_0(\alpha_n r/R)]^2\, r\, dr}$
3. 取 N=10 个模态

对每个事件输出：
- `c_0, c_1, ..., c_9`：各阶模态系数
- `E_n = c_n²`：各阶模态能量
- `E_low_frac = (E_0 + E_1) / E_total`：低阶能量占比
- `E_high_frac = 1 - E_low_frac`：高阶能量占比

### 1.3 相关性分析

计算所有 shape 指标 vs (α, δ_near, D_peak) 的 Spearman 相关矩阵。

**关键检验**：
- pos_frac vs α：预期 ρ < 0（负 profile → 高 α）
- c₀ vs δ_near：预期 ρ > 0（c₀ 是空间均值的直接度量）
- E_high_frac vs α：预期 ρ > 0（如果高阶模态 → 快衰减的理论成立）

### 1.4 Partial correlation

用偏相关检验 shape 指标对 α 的预测是否独立于 δ_near 和 D_peak：
- α ~ pos_frac | δ_near：控制 δ_near 后 pos_frac 是否仍与 α 关联
- α ~ E_high_frac | D_peak

如果 shape 指标完全被 δ_near 吸收（partial ρ ≈ 0），说明 shape 只是 δ_near 的代理变量。如果仍显著，说明 shape 携带了超出 δ_near 的信息。

### 输出

- `tables/profile_shape_metrics.csv`：per event，所有 shape 指标 + α + δ_near + D_peak
- `tables/bessel_coefficients.csv`：per event，c_0 到 c_9 + 能量分布
- `tables/shape_alpha_correlations.csv`：Spearman ρ 和 p
- `tables/shape_alpha_partial_correlations.csv`：偏相关
- `figures/profile_gallery.png`：16 个事件的 δ(r) profile，按 δ_near 排序，2×8 子图

---

## Exp 2: 扩散-弛豫 PDE 的解析推导

### 目标

在径向对称扩散-弛豫模型下，推导 D(t) 的衰减行为如何取决于初始 profile 的模态组成。产出**解析公式**，建立从 profile shape → α 的理论链条。

### 2.1 模型定义

径向 1D 扩散-弛豫方程（柱坐标）：

$$\frac{\partial \delta}{\partial t} = \frac{D_s}{r}\frac{\partial}{\partial r}\left(r\frac{\partial \delta}{\partial r}\right) - k\,\delta$$

边界条件：
- r=0: ∂δ/∂r = 0（径向对称）
- r=R_max: ∂δ/∂r = 0（Neumann，无净流出）

参数：
- $D_s$：空间扩散系数（单位：km²/h），描述人口在区域间重新分布的速率
- $k$：局部弛豫率（单位：1/h），描述"回家"的驱动力

### 2.2 解析解

在 Neumann BC 下，解为贝塞尔函数展开：

$$\delta(r,t) = \sum_{n=0}^{\infty} c_n\, J_0\!\left(\frac{\alpha_n\, r}{R}\right) \exp\!\left[-\left(k + D_s\frac{\alpha_n^2}{R^2}\right)t\right]$$

其中 c_n 由初始条件 δ(r, 0) 决定（Exp 1 已计算）。

每个模态的衰减率为：

$$\lambda_n = k + D_s\frac{\alpha_n^2}{R^2}$$

- n=0 模态（空间均值）：$\lambda_0 = k$（只受弛豫）
- n≥1 模态：额外受扩散加速，$\lambda_n > k$
- 高阶模态衰减最快

### 2.3 D(t) 的推导

$D(t) = \langle |\delta(r,t)| \rangle_r$

由于涉及绝对值，不能直接求和。但可以做以下近似分析：

**情况 A（全正或全负 profile）**：若 δ(r,0) 不变号，则 δ(r,t) 在衰减过程中也不变号（所有模态同号衰减）。此时：

$$D(t) \approx \sum_n |c_n|\, w_n\, e^{-\lambda_n t}$$

其中 $w_n = \langle |J_0(\alpha_n r/R)| \rangle_r$ 是基函数的径向均值。

D(t) 是多指数衰减的叠加。初期由最快衰减模态主导（高阶），后期由最慢模态主导（n=0）。

**情况 B（正负混合 profile）**：EVAC 主导事件近场 δ<0、远场 δ>0，profile 变号。此时不同模态之间存在相消，D(t) 的衰减更加复杂。

### 2.4 关键理论预测（需用代码验证）

**预测 1**：在全局参数 (k, D_s) 下，EVAC 主导事件（c₀<0, 高阶能量占比高）的 D(t) 初期衰减斜率 α 高于 INFL 主导事件（c₀>0, 低阶主导）。

**推导逻辑**：
- EVAC profile：近场负、远场正 → 大空间梯度 → 高阶贝塞尔模态有显著能量
- INFL profile：几乎全正 → 空间均匀 → 能量集中在低阶模态
- 高阶模态的 λ_n 更大 → 初期衰减更快 → α 更高
- 因此 α 与 δ_near（索引 profile 的正负结构）负相关：Q.E.D.

**预测 2**：α 与 D_peak 正相关的来源——D_peak 大的事件有更大的空间梯度（更大的 |c_n| for n≥1），同样的 (k, D_s) 下模态加权后的 effective 衰减率更高。

**预测 3**：δ_near 和 D_peak 作为两个正交 predictor 的独立性——δ_near 索引 profile 的符号结构（哪些模态的系数为正/负），D_peak 索引 profile 的幅度。符号结构和幅度是两个独立的自由度。

### 实现要求

这一步主要是**公式推导 + 文档**，代码量较少。需要实现：

1. 一个函数 `predict_D_from_profile(c_n, zeros, k, Ds, t_array, R_max, n_r_eval=200)`：
   - 输入：贝塞尔系数 c_n、零点 zeros、参数 k 和 Ds、时间数组
   - 从解析解计算 δ(r, t) 在 r 网格上的值
   - 返回 D(t) = mean_r |δ(r,t)|

2. 一个函数 `fit_alpha_from_D(D_array, t_array, t_start=24, t_end=120)`：
   - 在 [t_start, t_end] 窗口内拟合 log-log slope
   - 与现有 pipeline 的 α 定义一致（fixed-window method）

3. 用这两个函数在**人工构造的 profile**上验证理论预测：
   - 构造一组纯负 profile（模拟 EVAC）
   - 构造一组纯正 profile（模拟 INFL）
   - 构造一组混合 profile
   - 在同一 (k, Ds) 下计算 α_predicted
   - 验证 EVAC → 高 α、INFL → 低 α

### 输出

- `tables/analytic_predictions_synthetic.csv`：人工 profile 的 α_predicted 表
- `figures/synthetic_D_decay_comparison.png`：EVAC vs INFL 的 D(t) 衰减对比
- `figures/mode_decay_schematic.png`：各阶模态衰减率 λ_n 的示意图

---

## Exp 3: 数值求解——从真实 δ(r, 0) 预测 α

### 目标

用 16 个事件的真实 δ(r, t_peak) profile 作为初始条件，数值求解扩散-弛豫 PDE，预测 α_predicted，与 α_empirical 比较。

### 3.1 PDE 数值求解

**不要自己写 PDE solver**。用贝塞尔展开的解析解即可（这是线性 PDE，解析解是精确的）：

```python
def predict_D_from_profile(c_n, zeros, k, Ds, t_array, R_max=200.0, n_r_eval=200):
    """
    从贝塞尔系数计算 D(t)
    δ(r,t) = Σ c_n J₀(α_n r/R) exp(-λ_n t)
    D(t) = mean_r |δ(r,t)|
    """
    from scipy.special import j0
    r_eval = np.linspace(0, R_max, n_r_eval)
    D_vals = []
    for t in t_array:
        delta_r = np.zeros_like(r_eval)
        for n in range(len(c_n)):
            lam_n = k + Ds * (zeros[n] / R_max) ** 2
            delta_r += c_n[n] * j0(zeros[n] * r_eval / R_max) * np.exp(-lam_n * t)
        D_vals.append(np.mean(np.abs(delta_r)))
    return np.array(D_vals)
```

### 3.2 全局参数估计

**关键设计决策**：k 和 D_s 是全局参数（所有事件共享），不是事件级参数。

估计方法——网格搜索 + Spearman 最大化：

1. 定义 k 网格：np.logspace(-4, 0, 30)
2. 定义 D_s 网格：np.logspace(-2, 3, 30)
3. 对每组 (k, D_s)：
   a. 对 16 个事件各自计算 α_predicted
   b. 计算 Spearman ρ(α_predicted, α_empirical) 和 Pearson r
   c. 记录 MAE(α_predicted, α_empirical)
4. 选择使 Spearman ρ 最大的 (k*, D_s*)
5. 同时报告使 MAE 最小的 (k*, D_s*) 以及使 Pearson r 最大的 (k*, D_s*)

**额外估计方法**——联合最小二乘：
- 用 scipy.optimize.minimize 优化 Σ_i (α_predicted_i - α_empirical_i)²
- 这会给一个不同的 (k, D_s) 估计，报告两种结果

### 3.3 预测质量评估

对最优 (k*, D_s*) 下的预测，报告：

| 指标 | 定义 |
|---|---|
| Spearman ρ(α_pred, α_emp) | 排序一致性 |
| Pearson r(α_pred, α_emp) | 线性相关 |
| MAE | 绝对误差均值 |
| ρ(α_pred, δ_near) | 模型是否保留了 α-δ_near 关联 |
| ρ(α_pred, D_peak) | 模型是否保留了 α-D_peak 关联 |

### 3.4 Leave-one-out 交叉验证

- 每次去掉 1 个事件，用剩余 15 个估计 (k, D_s)
- 预测被去掉事件的 α
- 报告 LOO 的 MAE 和 ρ（防止 overfitting）

### 3.5 参数空间热图

在 (k, D_s) 二维网格上画三个热图：
1. Spearman ρ(α_pred, α_emp) 的等值线
2. ρ(α_pred, δ_near) 的等值线
3. MAE 的等值线

目的：展示结果对参数选择的敏感度。如果存在一个宽的"高 ρ 谷"，说明结论是 robust 的。

### 3.6 D(t) 曲线对比

对每个事件，在同一张图上画：
- D_empirical(t)：实际数据
- D_predicted(t)：PDE 模型预测
- 标注 α_emp 和 α_pred

选 4 个代表性事件（2 EVAC + 2 INFL）做大图，其余放 SI。

### 输出

- `tables/pde_alpha_predictions.csv`：per event，α_emp, α_pred, residual
- `tables/pde_optimal_params.csv`：k*, D_s*, 各评估指标
- `tables/pde_param_grid.csv`：完整网格搜索结果
- `tables/pde_loo_results.csv`：LOO 交叉验证
- `figures/pde_param_heatmap.png`：参数空间热图
- `figures/pde_D_comparison_gallery.png`：D(t) 对比
- `figures/pde_alpha_scatter.png`：α_pred vs α_emp 散点图

---

## Exp 4: 综合验证

### 4.1 模拟验证（Forward Simulation）

**目的**：证明扩散-弛豫 PDE 在合理的 (k, D_s) 参数下能**泛化地**产生 α 与 δ_near 的负相关。

方法：
1. 用最优 (k*, D_s*)
2. 从 16 个事件的真实 δ(r, 0) profile 中 bootstrap 抽样
3. 对每个抽样 profile 添加随机扰动（±20% 幅度缩放 + 微小高斯噪声）
4. 计算 α_predicted 和对应的 δ_near
5. 重复 500 次
6. 统计 ρ(α_predicted, δ_near) 的分布

**成功标准**：模拟的 ρ(α, δ_near) 分布的 95% CI 应包含实际观测值 ρ ≈ -0.53。

### 4.2 反事实实验（Counterfactual）

**目的**：证明 α-δ_near 关联确实来自空间 profile 的形状差异，而不是其他混杂因素。

**反事实 A（Profile 置换）**：
- 保持每个事件的 D_peak 不变
- 随机打乱 16 个事件之间的 δ(r, 0) profile（保持幅度但打乱形状）
- 计算 α_predicted
- 检验打乱后 ρ(α_pred, δ_near) 是否消失

**反事实 B（消除扩散）**：
- 令 D_s = 0（只有弛豫，无空间耦合）
- 用相同 k 计算 α_predicted
- 检验此时 α 是否还与 δ_near 相关
- 预期：D_s=0 时所有事件的 α 都相同（因为只有 exp(-kt)），相关性消失

**反事实 C（均匀化 profile）**：
- 将每个事件的 δ(r, 0) 替换为其空间均值（即只保留 c₀，删除所有高阶模态）
- 计算 α_predicted
- 预期：α 变化范围大幅缩小，与 D_peak 的关联消失

### 4.3 与 Langevin 模型的正式对比

输出一个对比表：

| 指标 | Langevin | 扩散-弛豫 |
|---|---|---|
| ρ(α_pred, α_emp) | N/A（无法直接 predict） | 填入结果 |
| ρ(param, δ_near) | k_ratio: 0.272, p=0.308 | 填入结果 |
| 模拟复现 ρ(α, δ_near) | 0.057 [-0.71, 0.70] | 填入结果 |
| 反事实 D_s=0 | N/A | 填入结果 |
| 全局参数数 | 2-4 per event | 2 global |

### 输出

- `tables/simulation_bootstrap.csv`：500 次模拟的 ρ 值
- `tables/counterfactual_results.csv`：三种反事实的 ρ 值
- `tables/langevin_vs_pde_comparison.csv`：正式对比表
- `figures/counterfactual_panel.png`：反事实实验可视化

---

## 代码组织

### 新模块

在 `src/disaster/` 下创建 `spatial_diffusion.py`（与 `dynamics_potential.py` 平级，不修改后者）。

模块结构：

```
src/disaster/spatial_diffusion.py

# ── 数据准备 ──
_load_route_b_events() -> list[EventMeta]
_extract_radial_profile(slug, t_peak, output_root) -> dict
_bessel_decomposition(r_bins, delta, R_max, n_modes) -> (coeffs, zeros)
_compute_shape_metrics(r_bins, delta) -> dict

# ── PDE 预测 ──
predict_D_from_profile(c_n, zeros, k, Ds, t_array, R_max) -> np.ndarray
fit_alpha_from_D(D, t, t_start, t_end) -> float
estimate_global_params(profiles, alphas, k_grid, Ds_grid) -> dict
loo_cross_validation(profiles, alphas) -> pd.DataFrame

# ── 模拟与反事实 ──
bootstrap_simulation(profiles, k, Ds, n_iter, rng) -> pd.DataFrame
counterfactual_shuffle(profiles, k, Ds) -> dict
counterfactual_no_diffusion(profiles, k) -> dict
counterfactual_uniform_profile(profiles, k, Ds) -> dict

# ── 主入口 ──
run(*, output_root, dt_tables_dir, out_dir, ...) -> None
cli_main() -> None
```

### 入口脚本

`scripts/spatial_diffusion.py`（与现有 `scripts/population_relaxation.py` 同构）

### CLI 参数

```
--output-root          outputs 根目录 (default: outputs)
--dt-tables-dir        Dt_decay tables 目录
--out-dir              输出目录 (default: outputs/spatial_diffusion_results)
--r-max-km             最大距离 (default: 200)
--min-tiles-overlap    最小 tile 重叠数 (default: 3)
--n-bessel-modes       贝塞尔展开模态数 (default: 10)
--k-grid-n             k 网格点数 (default: 30)
--ds-grid-n            D_s 网格点数 (default: 30)
--k-min / --k-max      k 搜索范围 (default: 1e-4 / 1.0)
--ds-min / --ds-max    D_s 搜索范围 (default: 0.01 / 1000)
--t-start / --t-end    α 拟合窗口 (default: 24 / 120)
--n-bootstrap          模拟次数 (default: 500)
--seed                 随机种子 (default: 42)
--run-until            运行到第几个实验 (1/2/3/4, default: 4)
```

---

## 预期产出与成功标准

### 最低标准（必须达到才算成功）

1. **Exp 1**：pos_frac vs α 的 Spearman |ρ| > 0.4 且 p < 0.1（诊断已确认 ρ=-0.52, p=0.038）
2. **Exp 2**：合成 profile 上，EVAC-like profile 的 α_predicted > INFL-like 的 α_predicted（定性正确）
3. **Exp 3**：α_predicted vs α_empirical Spearman ρ > 0.4 且 p < 0.1
4. **Exp 4**：反事实 B (D_s=0) 使 ρ(α, δ_near) 消失；反事实 A (shuffle) 使 ρ 消失

### 理想标准（支撑 NC 投稿）

1. α_predicted vs α_empirical Spearman ρ > 0.6
2. LOO 交叉验证后 ρ 不大幅下降
3. Bootstrap 模拟的 ρ(α, δ_near) 95% CI 覆盖实际值
4. (k*, D_s*) 的参数空间热图显示宽的高 ρ 平台（而非尖峰）

---

## 注意事项

1. **不要修改** `src/disaster/dynamics_potential.py` 或现有的任何 pipeline 代码。新逻辑全部在 `spatial_diffusion.py` 中。

2. **α 的定义必须与现有 pipeline 完全一致**：fixed-window 24-120h 的 log(D/D_peak) vs log(t-t_peak) 的负斜率。不要发明新的 α 定义。

3. **phi_rt_long.csv 的读取**：使用 `phi_overlap` 列（不是 `phi_aggregate`），与 `_load_phi_rt_long` 保持一致。

4. **Route B 事件列表**始终从 `Dt_routeB_sample_flags.csv` 的 `route_b_selected==True` 读取，不要硬编码 slug。

5. **日平均处理**：与 `dynamics_potential.py` 中 `_prepare_phi` 的逻辑一致——如果 median_step_hours_raw < high_freq_thresh_h (16h)，则对同一 r_bin 按天做日平均。

6. 所有输出表都存为 CSV，所有图保存为 PNG (300 dpi)。图的风格参考 `plot_style.py`。

7. 贝塞尔函数用 `scipy.special.j0` 和 `scipy.special.jn_zeros`。积分用 `numpy.trapezoid`（不是 deprecated 的 `numpy.trapz`）。
