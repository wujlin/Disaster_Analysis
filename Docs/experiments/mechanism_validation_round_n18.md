# Mechanism Validation（n=18）重跑总结

## 1. 实验目标与口径
本轮不是追求“2参数 PDE 精确预测 α”，而是验证机制链条：
- 空间形状（剖面几何）是否与恢复速度 α 同向变化；
- 该关系是否在反事实中被破坏；
- 子区域显著性是否受事件异质性主导。

统一输入：
- `dt`: `outputs/cross_disaster_comparison/Dt_decay_unified_static_h8_gtfix_mtw5_mpp4/tables`
- `phi`: `outputs/_runs/unified_static_h8_gtfix`
- 样本：`route_b_selected=True` 的 18 个事件。

---

## 2. 代码与计算逻辑

### 2.1 Subregion 诊断
- 入口：`scripts/subregion_diagnostic.py`
- 逻辑：
  1) 先做 RI（随机截距）模型 `alpha_unit ~ D_peak_unit`；
  2) 再做 Random Slope、Mundlak within-between、控制 `n_mono/r2`；
  3) 再做 two-stage meta 与 leave-one-event-out（含 ALL_BERYL）。
- 输出：`outputs/cross_disaster_comparison/subregion_diagnostic_unified_static_h8_gtfix_mtw5_mpp4/`

### 2.2 Data collapse（子区域）
- 入口：`scripts/subregion_collapse_final.py`
- 逻辑：
  1) unit 级筛选（`n_mono>=4 & r2>=0.5`）；
  2) 用 `tau/t_half` 与 `D/D_peak` 构建坍缩；
  3) 分别报告 all_events 与 excl_earthquake。
- 输出：`outputs/cross_disaster_comparison/subregion_collapse_unified_static_h8_gtfix_mtw5_mpp4/`

### 2.3 机制实验（扩散框架）
- 入口：`scripts/spatial_diffusion.py`
- 核心：`src/disaster/spatial_diffusion.py`
- 逻辑：
  1) 从 `phi_rt_long` 提取峰时径向剖面并做 Bessel 分解；
  2) 参数网格 + 优化得到 `(k, Ds)`；
  3) 生成 `alpha_pred` 并做反事实：`Ds=0`、`c0-only`、shuffle；
  4) synthetic profile（受控剖面）验证形状->α单调性。
- 输出：`outputs/cross_disaster_comparison/spatial_diffusion_unified_static_h8_gtfix_mtw5_mpp4/`

### 2.4 Gao baseline 三模型比较
- 入口：`scripts/gao_baseline_comparison.py`
- 逻辑：同一单调衰减段比较 `PowerLaw / Exponential / StretchedExp` 的 BIC。
- 输出：`outputs/cross_disaster_comparison/gao_baseline_unified_static_h8_gtfix_mtw5_mpp4/`

### 2.5 PDE 参数重估
- 入口：`scripts/nonlinear_pde_experiment.py`
- 逻辑：全局拟合 `dD/dt' = -(k0 + gamma D)D`，并与 per-event power law 做 BIC 对比，附 LOO。
- 输出：`outputs/cross_disaster_comparison/nonlinear_pde_unified_static_h8_gtfix_mtw5_mpp4/`

---

## 3. 关键结果

### 3.1 Event-level 主信号仍显著
- `ρ(α, δ_near) = -0.6945, p = 0.00138, n=18`
- 文件：`outputs/cross_disaster_comparison/Dt_decay_unified_static_h8_gtfix_mtw5_mpp4/tables/Dt_routeB_alpha_delta_spearman.csv`

### 3.2 Subregion：RI 显著，但稳健性不完全
- RI: `β(D_peak_unit)=+0.205, p=0.0104`（显著）
- Random Slope: `p=0.201`（不显著）
- Two-stage meta: `uw_mean_beta=-0.347, p=0.304`（不显著）
- LOO: 去掉 `beryl_jamaica` 后符号翻转（`beta=-0.164, p=0.214`）
- 文件：
  - `.../subregion_diagnostic_unified_static_h8_gtfix_mtw5_mpp4/part6_verdict.csv`
  - `.../part3_meta_summary.csv`
  - `.../part4_loo.csv`

### 3.3 Data collapse：功能形式稳定，跨事件坍缩中等
- all_events: `Q_global=0.7522`, `Q_within=0.3290`, `beta_master=0.2601`, `R2=0.8717`
- excl_earthquake: `Q_global=0.7807`, `Q_within=0.3914`, `beta_master=0.3094`, `R2=0.8622`
- 文件：
  - `.../subregion_collapse_unified_static_h8_gtfix_mtw5_mpp4/run.log`
  - `.../collapse_final_summary.csv`

### 3.4 反事实机制验证（本轮最关键）
`counterfactual_results.csv`：
- empirical: `ρ=-0.6945`（真实信号）
- pde_predicted: `ρ=-0.3560`（方向一致但弱）
- shuffle profiles: `ρ=-0.0145`（近0）
- no diffusion (`Ds=0`): `ρ=0`
- uniform profile (`c0 only`): `ρ=0`

解释：去掉扩散或去掉空间形状后，相关性消失；机制证据成立（必要条件层面）。

文件：`outputs/cross_disaster_comparison/spatial_diffusion_unified_static_h8_gtfix_mtw5_mpp4/tables/counterfactual_results.csv`

### 3.5 Synthetic profiles（受控因果链）
- `|delta_near|` 与 `alpha_predicted`：`ρ=0.943, p=0.0048`（6个受控剖面）
- 说明：在受控方程下，几何/梯度更陡 -> α 更大，方向清晰。
- 文件：`.../tables/analytic_predictions_synthetic.csv`

### 3.6 Gao baseline
- BIC 胜者计数（18事件）：
  - Stretched Exp: 7
  - Exponential: 6
  - Power Law: 5
- 结论：并非单一 power-law 主导，模型族混合。
- 文件：`.../gao_baseline_unified_static_h8_gtfix_mtw5_mpp4/model_comparison.csv`

### 3.7 2参数 PDE 预测层面（仍不作为主证据）
- 全局拟合：`k0=0.032509`, `gamma≈1e-14`（近0）
- `R2_total=-0.3596`（预测解释力差）
- 与 per-event PL 比较：`ΔBIC(ODE-PL)=-20.21`（参数惩罚下 ODE 有利，但拟合解释力并不强）
- 文件：`.../nonlinear_pde_unified_static_h8_gtfix_mtw5_mpp4/tables/exp_n2_global_fit.csv`

---

## 4. 结论（面向论文叙事）
1. 事件级主结论（`δ_near -> α`）在 n=18 上保持稳定且显著。  
2. 子区域的 `D_peak_unit` 显著存在，但依赖建模假设（RI vs random slope）；不宜单独作为“机制定量定论”。  
3. 机制层面最稳的证据来自“反事实破坏 + synthetic受控实验”：去扩散/去形状后信号消失，支持“空间形状驱动恢复速度”的解释路径。  
4. 2参数 PDE 作为精确预测器仍不稳，不应作为主结论，仅可保留为补充对照。
