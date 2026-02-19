# Prompt：论文主图与补充图可视化

## 背景

论文 `Essay/main.tex` 已完成初稿，正文包含 4 个主图位（Figure 1–4），目前为 placeholder。现有的分析脚本已产出一些图表（见下文），但**它们是为数据探索而非论文出版设计的**，需要重新制作或大幅改造以满足出版要求。

**关键原则**：每张图必须让读者**一目了然**地获取核心信息，图中的信息量必须与正文叙事严格一致。不能出现"正文说的 A 但图上看到 B"的情况。

---

## 统一风格规范

**必须遵守 `Docs/visual_style_guide.md` 和 `src/disaster/plot_style.py`。**

核心要点：
- **字体**：Times New Roman / STIXGeneral，数学字体 STIX
- **配色**：Okabe–Ito 色盲友好调色板（`src/disaster/plot_style.py::OKABE_ITO`）
- **尺寸**：全栏 `(6.5, 4.0)`，半栏 `(3.2, 2.45)`
- **导出**：PDF 矢量格式，300 DPI，`pdf.fonttype = 42`
- **不使用** `bbox_inches="tight"`
- 面板标签 (a)/(b)/(c) 使用 `add_panel_label()` 放在轴域外
- Legend 优先放轴外下方居中
- 统一使用 `with paper_style():` 上下文

灾害类型配色建议（贯穿全文一致）：

| 灾害类型 | 颜色 | Okabe-Ito key |
|---|---|---|
| Earthquake | `#D55E00` | `vermillion` |
| Hurricane | `#0072B2` | `blue` |
| Flood | `#009E73` | `bluish_green` |
| Wildfire | `#E69F00` | `orange` |

**所有散点图必须用上述配色区分灾害类型**，用 marker shape 区分 event_type（EVAC=▽, INFL=△, NEUTRAL=○）。

---

## 数据来源

所有图表的权威数据来源：

| 数据 | 文件路径 |
|---|---|
| 16 事件的 α, D_peak, δ_near, R², 等 | `outputs/cross_disaster_comparison/Dt_decay/tables/Dt_routeB_sample_flags.csv`（`route_b_selected == True`） |
| D(t) 时间序列 | `outputs/cross_disaster_comparison/Dt_decay/tables/Dt_all_events.csv` |
| Power-law fits | `outputs/cross_disaster_comparison/Dt_decay/tables/Dt_powerlaw_fits.csv` |
| PDE predictions | `outputs/cross_disaster_comparison/spatial_diffusion_results/tables/pde_alpha_predictions.csv` |
| Bessel coefficients | `outputs/cross_disaster_comparison/spatial_diffusion_results/tables/bessel_coefficients.csv` |
| Counterfactual results | `outputs/cross_disaster_comparison/spatial_diffusion_results/tables/counterfactual_results.csv` |
| Bootstrap results | `outputs/cross_disaster_comparison/spatial_diffusion_results/tables/simulation_bootstrap.csv` |
| Radial profiles at peak | `outputs/cross_disaster_comparison/spatial_diffusion_results/tables/radial_profiles_at_peak.csv` |
| Shape-alpha correlations | `outputs/cross_disaster_comparison/spatial_diffusion_results/tables/shape_alpha_correlations.csv` |
| Socioeconomic indicators | `outputs/cross_disaster_comparison/external_covariates/tables/country_level_indicators.csv` |
| Bivariate correlations | `outputs/cross_disaster_comparison/external_covariates/tables/bivariate_spearman.csv` |
| Jackknife results | `outputs/cross_disaster_comparison/Dt_decay/tables/Dt_routeB_alpha_delta_jackknife.csv` |
| Robustness: r_near sweep | `outputs/cross_disaster_comparison/Dt_decay/tables/robustness_near_thresh.csv` |
| Robustness: r_max sweep | `outputs/cross_disaster_comparison/Dt_decay/tables/robustness_r_max.csv` |
| D_peak mechanism | `outputs/cross_disaster_comparison/spatial_diffusion_results/tables/dpeak_mechanism_experiment.csv` |

---

## Figure 1：Universal Relaxation with Diverse Rates（全栏，3 panel）

**正文对应**：Results §1 "Post-disaster population displacement relaxes universally but at diverse rates"

**布局**：`fig, (ax_a, ax_b, ax_c) = plt.subplots(1, 3, figsize=(6.5, 2.5))`

### Panel (a): D(t) 时间序列（4–6 个代表性事件）

- **数据**：从 `Dt_all_events.csv` 中选 4–6 个代表不同 hazard type 和不同 α 的事件
  - 建议选：turkiye（earthquake, high α）、beryl_tx（hurricane, high α）、nepal_fld（flood, medium α）、john_gue（hurricane, low α）、spain_flood（flood, medium α）、boise_fire（wildfire）
- **X 轴**：时间（hours since event onset），统一对齐到 $t_{\text{peak}}$
- **Y 轴**：$D(t)$（原始值，不归一化）
- **颜色**：按灾害类型（Okabe-Ito）
- **关键**：清晰标注 peak 位置（虚线或 marker）
- **不要**：画 16 条线（太拥挤），只选有代表性的

### Panel (b): 归一化衰减曲线 $D_{\text{norm}}(t')$（所有 16 事件）

- **数据**：所有 16 事件的 post-peak 归一化曲线
- **X 轴**：$t' = t - t_{\text{peak}}$（hours），log scale
- **Y 轴**：$D_{\text{norm}}(t') = D(t')/D_{\text{peak}}$，log scale
- **颜色**：按 $\delta_{\text{near}}$ 的值做连续色标（colormap，如 `RdBu_r`，蓝=δ_near<0=EVAC，红=δ_near>0=INFL）
  - **这是关键视觉线索**：读者应该能一眼看出"蓝色线衰减快、红色线衰减慢"
- **附加**：右侧 colorbar 标注 $\delta_{\text{near}}$
- **不要**：画拟合直线（会太拥挤），但可以标注 α 范围的文字 annotation

### Panel (c): 全球地图

- **数据**：16 事件的经纬度（需从事件数据中提取或手工查找）
- **Marker**：按灾害类型着色（同配色方案），marker 大小正比于 $D_{\text{peak}}$
- **底图**：简洁的世界地图轮廓（可用 `cartopy` 或简单的 `basemap`；如果依赖复杂可用简化方案：不画底图只画散点+国境线轮廓）
- **标注**：可选择性地对 2–3 个重要事件标注名称

**⚠️ 一致性检查**：
- Panel (b) 的线条数量 = 16，且颜色渐变确实与 $\delta_{\text{near}}$ 值一致
- α 的范围 (−0.02 to 1.14) 应该在视觉上对应最平和最陡的线

---

## Figure 2：Shape Predicts Recovery Speed（半栏或全栏，2 panel）

**正文对应**：Results §2 "The spatial shape of initial displacement predicts recovery speed"

**布局**：`fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(6.5, 2.8))`

### Panel (a): α vs δ_near 散点图

- **数据**：`Dt_routeB_sample_flags.csv`，`alpha` vs `near_delta_peak_windows_mean`
- **Marker**：按灾害类型着色 + 按 event_type 区分形状
- **趋势线**：Theil-Sen 回归线（灰色虚线）
- **统计标注**：在图的角落标注 `ρ = −0.526, p = 0.036`
- **低 R² 事件**（$R^2 < 0.6$）：用半透明或空心 marker 区分
- **不要**：用 Pearson 回归线（我们报告的是 Spearman）

### Panel (b): 代表性径向剖面对比

- **数据**：`radial_profiles_at_peak.csv` 中选 2 个对比事件
  - 一个高 α 事件（evacuation 型，$\delta_{\text{near}} < 0$），如 beryl_tx
  - 一个低 α 事件（influx 型，$\delta_{\text{near}} > 0$），如 flooding_eu 或 john_gue
- **X 轴**：距离 $r$（km），0 到 200
- **Y 轴**：$\delta(r, t_{\text{peak}}) = \phi(r) - 1$
- **视觉**：高 α 事件的剖面应该在近场为负（人口流出）；低 α 事件在近场为正
- **零线**：水平虚线 $\delta = 0$
- **阴影区**：标注 $r \leq 50$ km 的近场区域

**⚠️ 一致性检查**：
- 散点图的 ρ 值必须是 −0.526（不是 −0.538，那是 fixed [24,120h] 的值）
- 两个代表事件的 δ_near 和 α 值必须在散点图中可以定位到

---

## Figure 3：PDE Mechanism（全栏，3 panel）

**正文对应**：Results §3 "A diffusion–relaxation model provides a physical mechanism"

**布局**：`fig, (ax_a, ax_b, ax_c) = plt.subplots(1, 3, figsize=(6.5, 2.5))`

### Panel (a): PDE 模型示意图（Bessel mode decomposition）

- **内容**：概念示意图，不是数据驱动的
- 展示一个初始径向剖面如何分解为 $J_0$ 模态
- 展示高阶模态衰减更快的概念
- 可以画 3–4 条 Bessel $J_0(\mu_n r/R)$ 曲线，标注 $\lambda_0 < \lambda_1 < \lambda_2 < ...$
- **参考**：已有 `outputs/cross_disaster_comparison/spatial_diffusion_results/figures/mode_decay_schematic.png`，可在此基础上改造

### Panel (b): α_pred vs δ_near（模型预测 vs 空间形状）

- **数据**：`pde_alpha_predictions.csv`（α_pred 列）+ `Dt_routeB_sample_flags.csv`（δ_near 列）
- **主图**：散点图，α_pred vs δ_near，标注 ρ = −0.553, p = 0.026
- **Inset**：bootstrap 分布的直方图
  - 数据：`simulation_bootstrap.csv`
  - X 轴：bootstrap ρ 值
  - 标注 95% CI = [−0.76, −0.08]，竖线标注 ρ = 0
  - 阴影显示 98.4% < 0

### Panel (c): 反事实实验

- **数据**：`counterfactual_results.csv`
- **形式**：条形图或点+误差棒图
- 4 个条件：Baseline (ρ = −0.553)，No diffusion (ρ = 0.0)，$c_0$-only (ρ = 0.0)，Shuffled (ρ ≈ 0, CI [−0.52, +0.52])
- **颜色**：Baseline 用主色，三个反事实用灰色系
- **误差棒**：Shuffled 的 95% CI
- **参考线**：ρ = 0 水平虚线

**⚠️ 一致性检查**：
- Panel (b) 是 α_pred（模型预测值），不是 α_emp
- α_pred 范围很窄 [0.22, 0.29]，Y 轴 scale 会和 Figure 2 很不同 → 需要在 caption 中说明
- 确保 bootstrap inset 中 ρ = 0 的竖线位置正确

---

## Figure 4：Amplitude Effect + Orthogonality（全栏，2–3 panel）

**正文对应**：Results §4 "Perturbation amplitude independently accelerates recovery" + §5 socioeconomic invariance

**布局建议**：`fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(6.5, 2.8))`  
或 3 panel 版本加入 2D prediction framework。

### Panel (a): α vs D_peak 散点图

- **数据**：`Dt_routeB_sample_flags.csv`，`alpha` vs `D_peak`
- **Marker**：按灾害类型着色 + 按 event_type 区分形状（与 Figure 2a 一致）
- **趋势线**：Theil-Sen 回归线（灰色虚线）
- **统计标注**：ρ = +0.600, p = 0.014
- **低 R² 事件**同上处理

### Panel (b): 偏相关可视化 或 2D prediction framework

**方案 A（偏相关）**：
- 两个小散点图：
  - 左：$\alpha$ 残差 vs $\delta_{\text{near}}$ 残差（控制 $D_{\text{peak}}$ 后），标注 $\rho_{\text{partial}} = -0.566$
  - 右：$\alpha$ 残差 vs $D_{\text{peak}}$ 残差（控制 $\delta_{\text{near}}$ 后），标注 $\rho_{\text{partial}} = +0.631$
- 残差的计算：对各变量分别关于控制变量做秩回归，取残差

**方案 B（2D framework — 推荐）**：
- X 轴：$\delta_{\text{near}}$，Y 轴：$D_{\text{peak}}$
- 颜色：按 $\alpha$ 值连续着色（colormap，如 `viridis` 或 `plasma`）
- 16 个事件散点
- 用象限标注（最快恢复 = 左上，最慢恢复 = 右下）
- 这张图直接展示论文的核心框架

**⚠️ 一致性检查**：
- D_peak 的量纲/范围（约 0.06 到 0.40）要与正文一致
- 偏相关值（−0.566 / +0.631）是 Spearman 偏相关，不是 Pearson

---

## 补充图（SI）

### Figure S1: 16 事件的 D(t) 个体面板

- 4×4 或 5×4 面板，每个事件一个小图
- X 轴：时间，Y 轴：$D(t)$
- 标注事件名、hazard type、α 值
- **已有**：`outputs/cross_disaster_comparison/Dt_decay/figures/Dt_timeseries_panels.pdf`，检查是否满足出版要求

### Figure S2: Robustness parameter sweeps

- (a) $\rho(\alpha, \delta_{\text{near}})$ vs $r_{\text{near}}$（10–200 km）
- (b) $\rho(\alpha, \delta_{\text{near}})$ vs $r_{\max}$（50–400 km）
- 数据：`robustness_near_thresh.csv` 和 `robustness_r_max.csv`
- 显著性阈值线（p = 0.05 对应的 ρ）

### Figure S3: Jackknife distribution

- 16 个 jackknife 值的分布（条形图或点图）
- 标注 95% CI 和均值
- 数据：`Dt_routeB_alpha_delta_jackknife.csv`

### Figure S4: PDE parameter search heatmap

- $(k, D_s)$ 平面上的 Spearman ρ 热力图
- 标注最优点
- **已有**：`outputs/cross_disaster_comparison/spatial_diffusion_results/figures/pde_param_heatmap.png`

### Figure S5: Profile gallery

- 所有 16 事件的峰值径向剖面
- **已有**：`outputs/cross_disaster_comparison/spatial_diffusion_results/figures/profile_gallery.png`

---

## 文件输出

- 主图：保存至 `Essay/figures/fig1_universal_relaxation.pdf` 等
- 补充图：保存至 `Essay/figures_supp/figS1_individual_panels.pdf` 等
- 每张图同时输出 PDF + PNG（PNG 仅供预览）

## 脚本组织

建议为每张主图创建独立脚本：
- `scripts/fig1_universal_relaxation.py`
- `scripts/fig2_shape_predicts_recovery.py`
- `scripts/fig3_pde_mechanism.py`
- `scripts/fig4_amplitude_orthogonality.py`
- `scripts/figS_supplementary.py`（补充图合一）

所有脚本顶部：
```python
import sys
sys.path.insert(0, ".")
from src.disaster.plot_style import (
    paper_style, OKABE_ITO, FIGSIZE_FULL, FIGSIZE_HALF,
    add_panel_label, save_figure,
)
```

---

## ⚠️ 历史教训与检查清单

之前的可视化出现过以下问题，**请务必避免**：

1. **图与正文数值不一致**：散点图上标注的 ρ 值与正文引用的不同（如 −0.538 vs −0.526）
   - **检查**：每张图标注的统计值必须从 `Dt_routeB_sample_flags.csv` 实时计算并验证
   
2. **信息过载**：一张图塞了太多事件/太多注释，读者无法一眼获取核心信息
   - **原则**：每个 panel 传达一个关键信息点

3. **配色不一致**：不同图用不同的灾害类型配色
   - **原则**：全文统一 earthquake=vermillion, hurricane=blue, flood=bluish_green, wildfire=orange

4. **轴标签模糊**：用内部变量名（如 `near_delta_peak_windows_mean`）而非论文符号
   - **原则**：一律使用 LaTeX 符号 $\delta_{\text{near}}$, $D_{\text{peak}}$, $\alpha$

5. **低 R² 事件不区分**：所有点同等对待，但有些 α 拟合质量很低
   - **原则**：$R^2 < 0.6$ 的事件用半透明/空心 marker

6. **Legend 太大或遮挡数据**
   - **原则**：Legend 放轴外下方，字号 9pt
