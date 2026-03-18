# Supplementary Information (N=18 主分析配套草案)

## 0. 适用口径与产物路径

- 主分析口径：`Dt_decay_unified_static_h8_gtfix_mtw5_mpp4`
- 配套机制口径：`spatial_diffusion_unified_static_h8_gtfix_mtw5_mpp4`
- 子区域口径：`geo_unit_scale_unified_static_h8_gtfix_mtw5_mpp4`
- 主图路径：`Essay/figures/`
- 补图路径：`Essay/figures_supp/`
- SI 表格路径（本轮新增）：`outputs/cross_disaster_comparison/si_tables_n18/`

---

## S1. Event catalog (Table S1)

### S1.1 表格文件
- `outputs/cross_disaster_comparison/si_tables_n18/table_S1_event_catalog_n18.csv`

### S1.2 字段说明
- 事件识别：`slug`, `short_name`, `disaster_type`, `event_type`
- 事件级动力学：`D_peak`, `alpha`, `r2_event`, `delta_near`, `D_inf`
- 拟合窗口信息：`n_time_windows`, `n_mono`, `t_peak_hours`, `t_decay_start`, `t_decay_end`
- Ground-truth 参数：`t0_pt`, `center_lat`, `center_lon`, `t0_source`, `center_source`

### S1.3 当前样本规模
- `route_b_selected = 18`（用于地图与总体样本池）
- `route_b_selected_plot = 16`（用于 `alpha`-相关散点与统计）

---

## S2. 参数敏感性与稳健性细节

### S2.1 汇总表文件
- `outputs/cross_disaster_comparison/si_tables_n18/table_S2_parameter_sensitivity_summary.csv`
- `outputs/cross_disaster_comparison/robustness_rerun_unified_static_h8_gtfix_mtw5_mpp4.csv`

### S2.2 关键结果（可直接写入 SI 文本）

1. **窗口阈值（mtw/mpp）敏感性**  
   - 来源：`unified_static_h8_spearman_summary.csv`
   - 在 `mtw={4,5}`, `mpp={3,4}` 的组合中，`rho(alpha, delta_near)`稳定在 `[-0.776, -0.764]`，`p < 0.002`。

2. **空间半径 `r_max` 敏感性**  
   - 来源：`rmax_sensitivity_spearman_summary.csv`
   - `r_max=100~250 km` 区间，相关仍为负且显著（最弱点 `r_max=100`: `rho=-0.671, p=0.006`）。
   - `r_max=50 km` 降为边缘不显著（`rho=-0.510, p=0.090`），提示过窄空间窗会损失信号。

3. **近场半径 `r_near` 敏感性**  
   - 来源：`rnear_sensitivity_spearman_summary.csv`
   - `r_near=30,50,75,100 km` 下均保持稳定负相关（`rho` 约 `-0.74 ~ -0.78`，均显著）。

---

## S3. Supplementary Figures S1–S6（说明与推荐 caption 要点）

### S1 Individual D(t) panels
- 文件：`Essay/figures_supp/figS1_individual_panels.pdf`
- 内容：逐事件 `D(t)` 曲线与事件级 `alpha`, `R^2`。
- caption 建议增加：`n_events = 18`（显示 panel 数量与缺失 panel 规则）。

### S2 Jackknife robustness
- 文件：`Essay/figures_supp/figS2_jackknife.pdf`
- 内容：`rho(alpha, delta_near)` leave-one-out 分布与全样本基线。
- caption 建议增加：`n_iter = 16`（对应 `route_b_selected_plot`）。

### S3 alpha vs D_inf
- 文件：`Essay/figures_supp/figS3_alpha_vs_dinf.pdf`
- 内容：`alpha` 与 `D_inf` 关系（验证 `alpha` 不是纯噪声）。
- caption 建议增加：样本定义 `route_b_selected_plot`。

### S4 Radial profile gallery
- 文件：`Essay/figures_supp/figS4_profile_gallery.pdf`
- 内容：所有事件峰值时刻径向剖面 `delta(r, t_peak)`。
- caption 建议增加：`r_near = 50 km` 阴影带是定义区，不参与额外拟合。

### S5 Gao baseline (moved out of main text)
- 文件：`Essay/figures_supp/figS5_gao_delta_bic.pdf`
- 内容：`DeltaBIC = BIC_powerlaw - BIC_exponential` 事件对比。
- 作用：方法选择支持材料，不占主叙事面板。

### S6 r_near sensitivity (moved out of main text)
- 文件：`Essay/figures_supp/figS6_rnear_sensitivity.pdf`
- 内容：`rho(alpha, delta_near)` 随 `r_near` 变化曲线。
- 作用：近场定义不敏感性证明。

---

## S4. 社会经济协变量（简版，供 reviewer 问答）

### S4.1 数据文件
- `outputs/cross_disaster_comparison/si_tables_n18/table_S4_socioeconomic_short_summary.csv`
- 原始来源：`outputs/cross_disaster_comparison/external_covariates/tables/`

### S4.2 可直接引用的核心数值（当前可匹配样本 n=16）
- `rho(HDI, delta_near) = +0.339, p = 0.199`
- `rho(GDP_per_capita_PPP, delta_near) = +0.331, p = 0.210`
- `rho(delta_near, alpha) = -0.526, p = 0.036`
- 控制 HDI 后：`rho(delta_near, alpha | HDI) = -0.522, p = 0.046`
- 控制 GDP 后：`rho(delta_near, alpha | GDP) = -0.521, p = 0.046`

### S4.3 解释建议（SI 简述）
- `delta_near` 与 HDI/GDP 本身不显著相关；
- `delta_near -> alpha` 在控制 HDI/GDP 后保持显著，说明核心形状-速率关系不由发展水平变量驱动。
- 该分析目前基于可匹配国家协变量的事件子集（n=16），应在 SI 明确子样本范围。

---

## S5. Caption 细化建议（主文可直接补）

- Fig.1(d)：已给出 `n=16`，建议保留并在 caption 中明确“仅 `route_b_selected_plot` 事件进入散点”。
- Fig.2(b)：补 `n_synthetic=6`。
- Fig.2(c)：补 `n_events=18`（observed/baseline）与 `n_bootstrap=500`。
- Fig.2(d)：补 event-level `n=16`；subregion mixed-effects `n_obs=2836, n_events=16`（当前表中值）。
- Fig.3(a)：补 `n_units=1069, n_events=15`（当前脚本输出口径）。

---

## S6. 可复现命令（本轮）

```bash
python scripts/fig2_universal_relaxation.py
python scripts/fig3_shape_predicts_recovery.py
python scripts/fig4_cross_scale_collapse.py
python scripts/figS_supplementary.py
```

> 说明：`fig1` 依赖 cartopy；当前环境建议设置 `CARTOPY_DATA_DIR=/tmp/cartopy`。
