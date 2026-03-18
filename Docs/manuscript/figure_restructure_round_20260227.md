# Figure Storyline Restructure (2026-02-27)

## 目标
将主图从“方法/稳健性堆叠”改为“问题驱动三步叙事”：
1. 发生了什么（普遍幂律）
2. 为什么发生（空间机制）
3. 能否跨尺度推广（子区域坍缩）

## 变更摘要

### Fig.2（`scripts/fig2_universal_relaxation.py`）
- 保留 `(a) 地图 + 图标图例`、`(b) 原始 D(t)`、`(c) 归一化 log-log`
- 将原 `(d) Gao ΔBIC` 替换为 `(d) α vs δ_near`（核心发现前置）
- 结果文件：
  - `Essay/figures/fig1_universal_relaxation.pdf`
  - `Essay/figures/fig1_universal_relaxation.png`

### Fig.3（`scripts/fig3_shape_predicts_recovery.py`）
- 重构为机制验证四证据链：
  - (a) 径向廓线对比（仅出现一次）
  - (b) 合成扩散实验
  - (c) 反事实 forest（observed / baseline / counterfactual）
  - (d) 跨尺度一致性 forest（event 显著 vs subregion 不显著）
- 结果文件：
  - `Essay/figures/fig2_shape_predicts_recovery.pdf`
  - `Essay/figures/fig2_shape_predicts_recovery.png`

### Fig.4（`scripts/fig4_cross_scale_collapse.py`）
- 将旧 `(a)+(b)` 合并为单一坍缩主面板（含主曲线拟合）
- 新增 `(c) event α vs median α_unit`
- 保留 `(b) per-event α_unit 分布` 与 `(d) subregion R² CDF`
- 结果文件：
  - `Essay/figures/fig3_cross_scale_collapse.pdf`
  - `Essay/figures/fig3_cross_scale_collapse.png`

## SI 迁移

### `scripts/figS_supplementary.py`
- 新增 S5：`figS5_gao_delta_bic`（原主图 Gao ΔBIC）
- 新增 S6：`figS6_rnear_sensitivity`（原主图 r_near 敏感性）
- SI 输出新增：
  - `Essay/figures_supp/figS5_gao_delta_bic.pdf/png`
  - `Essay/figures_supp/figS6_rnear_sensitivity.pdf/png`

## 本轮使用数据口径
- `Dt_decay_unified_static_h8_gtfix_mtw5_mpp4`
- `spatial_diffusion_unified_static_h8_gtfix_mtw5_mpp4`
- `geo_unit_scale_unified_static_h8_gtfix_mtw5_mpp4`
