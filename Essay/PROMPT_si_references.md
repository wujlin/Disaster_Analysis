# Prompt：补全 SI 和 References

## 背景

论文初稿 `Essay/main.tex` 已完成，SI 框架 `Essay/si.tex` 和参考文献 `Essay/references.bib` 已搭建但内容不完整。请根据以下指引补全。

---

## 任务一：补全 `Essay/si.tex`

### S1 Event Catalogue（优先级：高）

从 `outputs/cross_disaster_comparison/Dt_decay/tables/Dt_routeB_sample_flags.csv` 读取 `route_b_selected == True` 的 16 行，填充 Table S1。

**表格列需求**：

| 列 | 来源字段 | 说明 |
|---|---|---|
| Event | `slug` → 人类可读名称（如 "2023 Türkiye–Syria Earthquake"） | 需手工映射 |
| Country | 从 slug 推断 | 如 turkey_earthquake → Türkiye |
| Hazard type | `disaster_type` | earthquake / hurricane / flood / wildfire |
| Event type | `event_type` | EVAC / INFL / NEUTRAL |
| $D_{\text{peak}}$ | `D_peak` | 保留 3 位有效数字 |
| $\alpha$ | `alpha` | 保留 3 位有效数字 |
| $R^2$ | `r2` | 保留 2 位 |
| $\delta_{\text{near}}$ | `near_delta_peak_windows_mean` | 保留 3 位有效数字 |
| Decay window (h) | `t_decay_start`–`t_decay_end` | 如 "24–96" |
| $D_\infty$ | `D_inf` | 保留 2 位 |

**样本完整列表**（16 个事件的 slug）：
```
flooding_in_central_and_eastern_europe_sept_16_2024
hurricane_beryl_across_quintana_roo_and_yucatan_mexico
hurricane_beryl_across_southeastern_texas_us
hurricane_beryl_pre_landfall_2024
hurricane_john_across_southeastern_guerrero_mexico
hurricane_john_southern_mexico_25_september_2024
hurricane_milton_across_florida_us
moldova_flooding_2024
spain_flood
the_earthquake_across_central_mexico
the_flooding_across_bagmati_and_koshi_provinces_nepal
the_flooding_across_eastern_bangladesh
the_flooding_across_gujarat_india
turkiye_earthquake_2023
typhoon_yagi_across_northeastern_vietnam
wildfires_in_boise_county_idaho_27_august_2024
```

表格建议按 hazard type 分组排列（earthquake → hurricane → flood → wildfire），每组内按 $\alpha$ 降序。

### S2 Multi-method Robustness（已基本完成）

当前 si.tex 中的 Table S2 已有数据，无需修改。可以添加一段简短文字说明 Pearson r ≥ 0.88（单调截断 α 与各固定窗口 α 的相关性）。

### S3 PDE Model Details（优先级：高）

从 `Docs/Methods.md` §8 提取以下内容，用 LaTeX 重新排版：

1. **控制方程推导**（§8.2）：柱坐标扩散-弛豫方程，Neumann 边界条件
2. **Bessel 展开的解析解**（§8.3）：包括模态衰减率 $\lambda_n = k + D_s(\mu_n/R)^2$
   - **符号注意**：论文中 Bessel 零点用 $\mu_n$（不是 $\alpha_n$，避免与衰减率 $\alpha$ 混淆）
3. **初始条件的 Bessel 系数投影**（§8.4）：$r$-加权最小二乘公式
4. **$\alpha_{\text{pred}}$ 的计算**（§8.5）：
   - 能量度量 $E(t) = \langle \delta^2 \rangle_r$，Parseval 等式 $E(t) = \sum c_n^2 e^{-2\lambda_n t}$
   - 拟合窗口 [1h, 120h]（不同于经验 α 的 24h 起点，原因：需要在高阶模态快速衰减阶段捕捉动力学）
   - $E(t)$ vs $D(t)$ 的关系说明（$L^2$ vs $L^1$ 范数）
5. **参数搜索**（§8.6）：对数均匀网格，30×30，细化10倍后再30×30；四个准则
6. **最优参数**：$k = 0.00418$ h⁻¹，$D_s = 0.304$ km² h⁻¹
7. **反事实实验设计**（§8.7）：三组实验的操作和结果
8. **Bootstrap 稳健性**（§8.8）：±10% 扰动，500次，95% CI = [−0.763, −0.079]

数据文件参考：
- `outputs/cross_disaster_comparison/spatial_diffusion_results/tables/pde_optimal_params.csv`
- `outputs/cross_disaster_comparison/spatial_diffusion_results/tables/counterfactual_results.csv`
- `outputs/cross_disaster_comparison/spatial_diffusion_results/tables/simulation_bootstrap.csv`
- `outputs/cross_disaster_comparison/spatial_diffusion_results/tables/bessel_coefficients.csv`
- `outputs/cross_disaster_comparison/spatial_diffusion_results/metadata.json`

### S4 Socioeconomic Covariate Analysis（优先级：中）

从以下文件提取数据：
- `outputs/cross_disaster_comparison/external_covariates/tables/bivariate_spearman.csv`
- `outputs/cross_disaster_comparison/external_covariates/tables/country_level_indicators.csv`
- `outputs/cross_disaster_comparison/external_covariates/tables/partial_spearman_dpeak_alpha.csv`
- `outputs/cross_disaster_comparison/external_covariates/tables/partial_spearman_delta_near_alpha.csv`

需要的表格：
1. **Table S4a**：11 国的社会经济指标汇总（HDI, GDP PPP, INFORM Risk, Vulnerability, Lack of Coping）
2. **Table S4b**：完整的二元 Spearman 相关矩阵（所有指标 vs $D_{\text{peak}}$, $\alpha$, $\delta_{\text{near}}$）
3. **Table S4c**：完整偏相关表（控制单个/多个社会经济变量后的 $\rho(D_{\text{peak}}, \alpha | \cdot)$）

文字说明要点：
- $n_{\text{eff}} = 11$（16事件来自11国，同一国家的多事件共享指标值）
- HDI 范围 0.62 (Nepal) → 0.94 (USA)
- 所有相关性均不显著

### S5 Distance-segment Analysis（优先级：低）

从 findings.md §7.3 提取：
- 近场（0–50 km）、中场（50–100 km）、远场（100–200 km）分段结果
- 中场 $\rho = -0.733$, $p = 0.025$, $n = 9$
- 注明样本量下降的原因和该结果的解读限制

### S6 Additional Robustness Details（优先级：中）

从 findings.md §7 和 Methods.md §5.3 提取：
1. **Jackknife 结果**：$\rho$ 的 95% CI 不穿越 0
   - 数据：`outputs/cross_disaster_comparison/Dt_decay/tables/Dt_routeB_alpha_delta_jackknife.csv`
   - 数据：`outputs/cross_disaster_comparison/Dt_decay/tables/Dt_routeB_alpha_delta_jackknife_summary.csv`
2. **$R^2$ 分层**：$R^2 \geq 0.8$ 子集 $n = 11$, $\rho = -0.673$, $p = 0.023$
   - 数据：`outputs/cross_disaster_comparison/Dt_decay/tables/Dt_routeB_alpha_delta_r2_strata.csv`
3. **参数扫描**：$r_{\text{near}}$ 和 $r_{\max}$ 的敏感性
   - 数据：`outputs/cross_disaster_comparison/Dt_decay/tables/robustness_near_thresh.csv`
   - 数据：`outputs/cross_disaster_comparison/Dt_decay/tables/robustness_r_max.csv`
4. **$\alpha$ vs $D_\infty$**：$\rho = -0.703$, $p = 0.002$
5. **排除的候选预测变量**：空间集中度、恢复梯度、观测窗口长度（均 $|\rho| < 0.15$）
6. **$k_i$ 模型（event-specific recovery rate）**：findings.md §3.2 的 3 参数模型结果与 LOO 交叉验证
   - 数据：`outputs/cross_disaster_comparison/spatial_diffusion_results/tables/dpeak_mechanism_experiment.csv`（如有）

---

## 任务二：补全 `Essay/references.bib`

### 当前状态

`references.bib` 已有 17 条，覆盖了 main.tex 中的所有 `\citep{}` 引用。但存在以下问题：

### 需要修正的条目

1. **Maas2019**：缺少 volume/pages/doi。正确信息：
   - 会议：16th International Conference on Information Systems for Crisis Response and Management (ISCRAM 2019)
   - 也可引用 Meta 的 technical report 或 KDD workshop paper
   - 请查找最完整的版本

2. **PatelNosal2016**：key 是 2016 但 year 字段写 2012，且标题和期刊不匹配。这条似乎不会被引用，可删除。

3. **Song2014**：缺少 doi、volume。如果论文不引用可删除。

4. **Wilson2016**：PLoS Currents 已停刊，确认 doi 是否仍有效。

### 需要新增的条目

论文正文虽然目前只引用了已有的条目，但以下几类参考文献在 Introduction 和 Discussion 中可能需要补充（请根据文献综述 `Docs/literature_review.md` 判断）：

1. **FBDM 相关文献**：
   - Jia et al. (2020) "Population flow..." — 多用于 FBDM 灾害研究的标准引用
   - 其他使用 FBDM 数据的灾害研究

2. **灾后人口恢复的经典文献**：
   - Quarantelli (1999) 或类似灾害社会学文献
   - 如果 Discussion 中提到"restoring forces scale super-linearly"，需要更具体的引用

3. **扩散模型在社会系统中的应用**：
   - 除了 Crank1975，是否有更近期的 population diffusion 模型文献？

4. **数据源的原始文档**：
   - UNDP HDI report（已有条目 UNDP2024，但未被引用 → 要么在正文中加 `\citep{UNDP2024}`，要么删除）
   - INFORM Risk（已有条目 INFORM2024，同上）
   - World Bank GDP 数据（目前无条目）

### 格式要求

- 所有 `@article` 必须有 `doi` 字段（如果存在）
- 所有 `@misc` 的 URL 需要 2025 年验证可访问
- 保持现有的字段命名风格（author, title, journal, volume, pages, year, doi）

### 产出

修改后的 `Essay/references.bib`，确保：
1. 所有被 `\citep{}` 引用的条目都存在且正确
2. 所有条目要么被引用，要么有明确理由保留（预留给后续修改）
3. 每条标注来源验证状态（在注释中标 `% verified` 或 `% TODO: verify`）

---

## 风格提醒

- SI 的写作风格应简洁、技术性强，不需要叙事性过渡
- 表格优先于长段文字
- 数值精度与正文一致（Spearman ρ 保留 3 位小数，p 值保留 3 位）
- LaTeX 宏定义与 main.tex 一致（`\dnear`, `\dpeak`, `\apred`, `\aemp`, `\Ds`）
