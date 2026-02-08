# 实验总结与迭代记录（Disaster_Analysis）

> 目的：把当前仓库里**已经跑过/验证过**的分析，按“科学问题→证据→结论→局限”整理成一份可复用的记录；所有结论均给出可追溯的**输出文件路径**与**代码入口**。
>
> 覆盖灾害事件（FBDM）：Turkey 2023（地震）、Beryl 2024（飓风）、Moldova 2024（洪水）、Park Fire 2024（野火）。

---

## 1. 项目概述

- 数据来源：Meta/Facebook Disaster Maps（FBDM）
- 数据类型（本仓库主要用到）：
  - Population：`n_crisis` 与 `n_baseline`（用于构造人口强度/比值指标）
  - Movement：OD（起点 tile → 终点 tile）+ `n_crisis`/`n_baseline`（用于方向性/净流等）
- 研究目标（最初版本）：寻找灾后人口恢复的“普适规律”（跨灾害、跨空间尺度）。

---

## 2. 分析迭代记录（按模块）

> 时间以 outputs 中文件时间为准（2026-01-31 ~ 2026-02-06）。

### 2.1 Population：φ（n_crisis / n_baseline）与基础现象

**时间**：2026-01-31（及后续持续复用）  
**核心定义**：
- tile-level：`phi = n_crisis / n_baseline`
- band-level（聚合）：`phi_aggregate = sum(n_crisis) / sum(n_baseline)`

**主要输出**：
- 跨灾害/单灾害聚合表：`outputs/<slug>/population_redistribution/tables/redistribution_by_distance_band.csv`
- 以“偏离强度”衡量信号大小（用于后续拟合）：`outputs/_tmp_cross_recovery_dynamics/tables/recovery_fit_all_disasters.csv` 的 `max_abs_dev`

**关键结果（可核查事实）**：
- “Population 信号强弱差异”在 `max_abs_dev` 上非常明显：  
  - Turkey：各距离带 `max_abs_dev≈0.64–1.09`（见 `outputs/_tmp_cross_recovery_dynamics/tables/recovery_fit_all_disasters.csv`）  
  - Beryl/Moldova/Park Fire：`max_abs_dev≈0.05–0.18`（同上）
- 这支持了“Turkey 事件更有强信号，其它灾害在当前口径下信号弱”的经验结论（**这是强度大小层面的事实**，不等价于机制结论）。

**相关代码入口**：
- `scripts/population_redistribution.py`
- `src/disaster/population_redistribution.py`

---

### 2.2 Population：恢复拟合（z_score/φ）、τ(r) 与稳健性诊断

这部分经历了多轮口径切换：先用 `z_score` 做“弛豫/机制分区”主线（后被指出存在强烈的边界/分箱伪像风险），再转向 `φ` 与 tile-level 的连续 τ(r) 来处理“分箱人为性”。

#### 2.2.1 z_score 的模型竞争与“机制分区”（被批判的版本）

**时间**：2026-01-31  
**核心定义**：
- 距离带聚合的 `z_score_mean(t)`，对每个距离 bin 做多模型拟合（exponential / stretched_exp / power_law / log），以 BIC 选最优。

**主要输出**（50km bins）：
- 目录：`outputs/pop_relax_50km/`
- 最优模型与参数（含 at_bounds）：`outputs/pop_relax_50km/fits/regime_fit_z_score_best_bic.csv`
- 全模型明细：`outputs/pop_relax_50km/fits/regime_fit_z_score_all_models.csv`
- bootstrap 胜率：`outputs/pop_relax_50km/fits/regime_bootstrap_winrates_z_score.csv`
- 可视化：`outputs/pop_relax_50km/figures/regime_map_z_score.png`、`outputs/pop_relax_50km/figures/regime_bootstrap_winrates_z_score.png`

**关键结果（可核查事实）**：
- “撞边界”普遍存在：例如多处 `tau=6696h`、`beta≈2.0` 且 `at_bounds=True`（见 `outputs/pop_relax_50km/fits/regime_fit_z_score_best_bic.csv`）。
- 模型类型频繁切换，且部分 bin 的 bootstrap 胜率接近（提示“分区边界”更像噪声而非清晰机制分化；证据见 `outputs/pop_relax_50km/fits/regime_bootstrap_winrates_z_score.csv`）。

**相关代码入口**：
- `scripts/regime_differentiation.py`
- `src/disaster/` 下对应实现：`src/disaster/population_relaxation.py`、`src/disaster/relaxation_fit.py` 等

#### 2.2.2 z_score 的全局拟合快照（PI review 用）

**时间**：2026-01-31  
**主要输出**：
- 目录：`outputs/population_relaxation/`
- 拟合汇总：`outputs/population_relaxation/tables/population_relaxation_postfit_summary.csv`
- 最优 BIC 参数：`outputs/population_relaxation/fits/population_relaxation_fit_best_bic.csv`
- β 稳健性（0–50km, stretched exp）：`outputs/population_relaxation/fits/beta_robustness_summary_z_score_mean_0-50km.csv`

**关键结果（可核查事实）**：
- 0–50km 的 stretched exp 拟合 β 非常稳定：`beta_median≈1.6820` 且 IQR 极小（见 `outputs/population_relaxation/fits/beta_robustness_summary_z_score_mean_0-50km.csv`）。

**相关代码入口**：
- `scripts/population_relaxation.py`
- `scripts/population_postfit_analysis.py`
- `scripts/beta_robustness.py`

#### 2.2.3 以 φ_aggregate 拟合“距离带 τ(r)”（早期 τ(r) 现象来源）

**时间**：2026-02-01  
**核心定义**：对每个距离带的 `phi_aggregate(t)` 做指数形式的 τ 拟合（按脚本实现口径）。  

**主要输出**：
- `outputs/turkiye_earthquake_2023/physical_model/tables/relaxation_fit_by_band.csv`

**关键结果（可核查事实）**：
- Turkey（单位为小时）：  
  - 25–50km：`tau≈348.77h`（≈14.53天）  
  - 50–100km：`tau≈146.82h`（≈6.12天）  
  - 100–200km：`tau≈392.26h`（≈16.34天）  
  - 0–25km：`tau=9999h`（触顶/不可解释风险）  
  - 证据见：`outputs/turkiye_earthquake_2023/physical_model/tables/relaxation_fit_by_band.csv`

**相关代码入口**：
- `scripts/physical_model_phi_rt.py`
- `src/disaster/physical_model_phi_rt.py`

#### 2.2.4 连续 τ(r)：tile-level 拟合与 bootstrap 置信带（回应“分箱人为性”）

**时间**：2026-02-01  
**核心定义**：
- 对每个 tile 拟合 `phi_i(t)=n_crisis/n_baseline` 的指数时间常数 `tau_i`
- 在连续距离上拟合 `log tau = a + b log r + c (log r)^2`，并 bootstrap 得到曲线置信带与 `r*`

**主要输出**：
- Turkey：`outputs/turkiye_earthquake_2023/tau_continuous_fit/`
  - tile-level：`outputs/turkiye_earthquake_2023/tau_continuous_fit/tables/tile_level_tau.csv`
  - 连续拟合：`outputs/turkiye_earthquake_2023/tau_continuous_fit/tables/tau_r_fit_quadratic.csv`
  - `r*` bootstrap：`outputs/turkiye_earthquake_2023/tau_continuous_fit/tables/tau_r_star_bootstrap.csv`
  - 曲线置信带：`outputs/turkiye_earthquake_2023/tau_continuous_fit/tables/tau_r_curve_ci.csv`

**相关代码入口**：
- `scripts/tau_continuous_fit.py`
- `src/disaster/tau_continuous_fit.py`

#### 2.2.5 τ 的“最简假设检验”与诊断（tile overlap vs crisis mean）

**时间**：2026-02-01  
**核心定义**：
- 在每个距离带上，用“overlap tile 数量比值”与“crisis_mean_ratio”等 proxy 检验“通达性 vs 强度恢复”的差异（按脚本实现口径）

**主要输出**：
- `outputs/_tmp_tau_interpretation/tau_interpretation_test/tables/tau_interpretation_hypothesis_test.csv`

**关键结果（可核查事实）**（Turkey）：
- 到达阈值 `tile_ratio>=0.95` 的时间（小时）：  
  - 50–100km：`40h`；25–50km：`64h`；0–25km：`88h`；200km+：`16h`  
  - 证据见：`outputs/_tmp_tau_interpretation/tau_interpretation_test/tables/tau_interpretation_hypothesis_test.csv`

**相关代码入口**：
- `scripts/tau_interpretation_test.py`
- `src/disaster/tau_interpretation_test.py`

---

### 2.3 φ 的有限尺寸标度（FSS）坍缩

**时间**：2026-02-01 ~ 2026-02-02  
**核心定义**：
- 在固定 `t_crisis`（且 only_hour_pt=8）取各灾害、各距离带 tile-level `phi`
- 尺度变换：`x = phi / <phi>^alpha`，扫描 `alpha` 使不同灾害 `p(x)` 尽量坍缩

**主要输出**：
- `outputs/_tmp_phi_fss/`（以及 `outputs/_tmp_phi_fss2/`）
  - 最优 α：`outputs/_tmp_phi_fss/tables/best_alpha_by_band.csv`
  - 残差扫描：`outputs/_tmp_phi_fss/tables/alpha_scan_<band>.csv`

**关键结果（可核查事实）**：
- 扫描网格内出现退化解：所有距离带 `alpha_star=-1.0` 且 `E_min=0.0`（见 `outputs/_tmp_phi_fss/tables/best_alpha_by_band.csv`）。  
  - 这意味着在当前残差定义/分箱策略下，FSS 坍缩没有提供可区分的有效 rescale 结论（至少在该轮设置与可用灾害样本上）。

**相关代码入口**：
- `scripts/phi_fss_collapse.py`
- `src/disaster/phi_fss_collapse.py`

---

### 2.4 Movement：方向极化（cos_alpha → P/A）

**时间**：2026-02-02  
**核心定义**（按距离带与时间窗口聚合）：
- 对每条 OD：`cos_alpha = (v·r)/(|v||r|)`（正=向外，负=向心）
- `F_r = sum(n_crisis * cos_alpha)`；`F_total = sum(n_crisis)`
- `P = F_r / F_total`（方向极化，[-1,1]）
- `A = |F_r| / F_total`（各向异性，[0,1]）
- 增加可靠性标记：以 `n_od>=30` 判定 `reliable`

**主要输出**（以 Turkey 为例）：
- `outputs/turkiye_earthquake_2023/directional_polarization/tables/flow_directional_filtered.csv`
- 汇总：`outputs/turkiye_earthquake_2023/directional_polarization/tables/polarization_summary_filtered.csv`

**关键结果（可核查事实）**（Turkey）：
- 50–100km：`P_min≈-0.114` 出现在 `t≈40h`（见 `polarization_summary_filtered.csv`）
- 25–50km：出现翻转区间 `t_flip_start=64h` 到 `t_flip_end=88h`（同上）
- 0–25km：大量窗口 `reliable=False`（n_od 极小，见 `flow_directional_filtered.csv`）

**相关代码入口**：
- `scripts/directional_polarization.py`
- `scripts/directional_polarization_postprocess.py`
- 对应实现：`src/disaster/directional_polarization.py`、`src/disaster/directional_polarization_postprocess.py`

---

### 2.5 Task A/B/C：用“目的地/净流”检验 cos_alpha 的物理含义

> 目的：区分“方向性信号=跨区域净流（撤离/救援）” vs “方向性信号=带内短程重组”。

**时间**：2026-02-02  

#### Task A：50–100km 向心流的起点/终点分布（Turkey, t≈40h）

**筛选口径**：
- `start_band=50–100km` 且 `cos_alpha<0`（向心）
- 固定时间窗口（实现中对应 `t≈40h`）

**主要输出**：
- 目录：`outputs/turkiye_earthquake_2023/movement_destination_analysis/tables/`
  - `destination_band_shares.csv`
  - `destination_distance_hist.csv`
  - `origin_distance_hist.csv`

**关键结果（可核查事实）**：
- 终点距离带份额：`89.22%` 仍在 `50–100km`，`10.78%` 到 `25–50km`，`0%` 到 `0–25km`（见 `destination_band_shares.csv`）。
- 终点距离直方图峰值在带内边缘（`60–70km` 份额最高，见 `destination_distance_hist.csv`）。

#### Task B：25–50km 的流入来源（Turkey, t≈40h）

**主要输出**：
- `outputs/turkiye_earthquake_2023/movement_inflow_source_analysis/tables/inflow_source_by_band.csv`

**关键结果（可核查事实）**：
- 目的地为 25–50km 的 OD，`99.62%` 起点仍在 25–50km（见 `inflow_source_by_band.csv`）。

#### Task C：Net 与 φ 的相关 + Net 分解（Turkey）

**主要输出**：
- `outputs/turkiye_earthquake_2023/cross_band_net_flow/tables/net_flow_phi_corr_by_band.csv`
- `outputs/turkiye_earthquake_2023/cross_band_net_flow/tables/net_flow_decomposed_corr.csv`

**关键结果（可核查事实）**：
- 25–50km：`Corr(Net, φ)≈+0.56`（见 `net_flow_phi_corr_by_band.csv`）
- 50–100km：`Corr(Net, φ)≈-0.43`（同上）
- 50–100km 的分解相关：`Corr(Net_external, φ-1)≈-0.446`、`Corr(Net_internal, φ-1)≈-0.231`（见 `net_flow_decomposed_corr.csv`）

**相关代码入口**：
- `scripts/movement_destination_analysis.py`
- `scripts/movement_inflow_source_analysis.py`
- `scripts/cross_band_net_flow.py`
- `scripts/net_flow_decomposition.py`

---

### 2.6 Movement：系统性方向分析（无 binning；Δr + d_move）

**时间**：2026-02-03  
**核心定义**（对每条 OD）：
- `r_start`、`r_end`：起点/终点到震中的距离（km）
- `Δr = r_end - r_start`（正=向外，负=向心）
- `d_move`：起点到终点的 haversine 距离（km）
- 权重 `w = n_crisis`

**主要输出**：
- 每灾害：`outputs/<slug>/movement_analysis/`
  - `tables/flow_length_direction_stats.csv`（target 时刻的 `median_d_move_w`、`mean_delta_r_w`）
  - `tables/diagonal_deviation_stats.csv`（`sigma_delta_r_w`）
  - `tables/long_range_flow_fraction.csv`（`f_long(d_move>50km)`）
  - `tables/delta_r_spacetime_matrix.csv`（滑动窗口的 `mean_Δr(r,t)` 矩阵）
  - 图：`figures/*.png`（2D hist、时空热图、对角散点、长程占比）

**关键结果（可核查事实）**：
- 4 个灾害在 `t≈16h/40h/160h` 的 target snapshot 上均出现：`median_d_move_w=0.0km`（见各自 `flow_length_direction_stats.csv`）。
- Turkey：`mean_delta_r_w≈0.05–0.07km`（同上），且 `sigma_delta_r_w≈2–3.6km`（见 `diagonal_deviation_stats.csv`），显示 `(r_start,r_end)` 强烈集中在对角线附近（短程/近似不动）。
- 长程流动占比极低：Turkey `f_long≈(3–12)×10^-5` 到 `1.2×10^-4`；其他灾害多为 `0` 或 `~10^-4`（见各自 `long_range_flow_fraction.csv`）。

**结论口径（只陈述数据支持的部分）**：
- 在当前数据与口径下，Movement 的 OD 权重主要由“极短程/零距离”贡献主导；跨区域（`d_move>50km`）占比在 8h~数周窗口内都极小。  
  - 这解释了为什么单纯基于 `cos_alpha` 的“向心/向外”信号，必须进一步用 `(r_start,r_end)` 与 `d_move` 来验证其是否对应真实跨区域流动。

**相关代码入口**：
- `scripts/movement_direction_systematic.py`
- `src/disaster/movement_direction_systematic.py`

---

### 2.7 恢复动力学：跨灾害拟合（指数 vs 幂律）与 τ/β 提取

**时间**：2026-02-03  
**核心定义**：
- 目标变量：`y(t)=|phi_aggregate(t)-1|`
- 拟合窗口：按脚本默认 `fit_mode=from_peak`（在 `[t_start,t_end]` 内找 `y(t)` 峰值作为 `t_peak`，用 `t_rel=t-t_peak` 拟合衰减）
- 模型：
  - 指数：`y=A exp(-t_rel/τ)`
  - 幂律：`y=A (t_rel + t_shift)^(-β)`（`t_shift=1h`）
- 模型选择：BIC（`best_model_by_bic`）

**主要输出**：
- 汇总：`outputs/_tmp_cross_recovery_dynamics/tables/recovery_fit_all_disasters.csv`
- 相关性：`outputs/_tmp_cross_recovery_dynamics/tables/correlation_summary.csv`

**关键结果（可核查事实）**：
- 产生有效 τ/β 的组合主要来自：
  - Turkey：5 个距离带均可拟合（`n_points_total=35`/带）
  - Beryl：3 个距离带可拟合
  - Moldova（每带 `n_points_total=9`）与 Park Fire（峰值落在序列末端导致仅 1 点）在该口径下**无有效拟合输出**（见 `recovery_fit_all_disasters.csv` 的 `*_fit_ok` 字段）。
- 在“指数与幂律都成功拟合”的 8 条记录中，`best_model_by_bic` 全为 `power_law`（8/8，见 `recovery_fit_all_disasters.csv`）。
- Turkey 的幂律指数：`β≈0.197–0.356`（见 `recovery_fit_all_disasters.csv` 的 `pl_beta`），且 `corr(β, log r)≈+0.857`（见 `correlation_summary.csv`）。

**相关代码入口**：
- `scripts/cross_disaster_recovery_dynamics.py`
- `src/disaster/cross_disaster_recovery_dynamics.py`

---

### 2.8 Response vs Recovery（救援强度 proxy vs 恢复速度）

**时间**：2026-02-01  
**核心定义**（简化版）：
- `response_intensity = phi_max(0–25km) - 1`
- `recovery_speed = 1 / tau_median_days_0_25`
  - 其中 `tau_median_days_0_25` 来自 tile-level `tau`（`distance<25km` 的 median）

**主要输出**：
- `outputs/_tmp_response_vs_recovery/tables/response_vs_recovery_by_disaster.csv`
- `outputs/_tmp_response_vs_recovery/tables/correlation_summary.csv`

**关键结果（可核查事实）**：
- Turkey：`phi_max_0_25≈1.709`（`t≈160h`），`tau_median_days_0_25≈62.97`（见 `response_vs_recovery_by_disaster.csv`）。
- 在有结果的 3 个灾害（Turkey、Moldova、Park Fire）上：`pearson_r≈-0.906`、`spearman_rho=-1.0`（见 `correlation_summary.csv`；注意 n=3）。

**相关代码入口**：
- `scripts/response_vs_recovery.py`
- `src/disaster/response_vs_recovery.py`

---

### 2.9 Storm 轨迹（distance_mode=path）：φ(d_path,t) 与“路径组”普适性检验

> 问题：对飓风/台风等“中心随时间移动”的灾害，若仍用静态中心距离 r，会把轨迹漂移混进空间结构里。  
> 回答：把距离改为 **到轨迹的路径距离** `d_path`，并只取局部 track 段做 φ heatmap 与普适性检验（Phase0/1/2）。

**时间**：2026-02-06  
**关键口径（可复现设置）**：
- `distance_mode=path` + `only_hour_pt=8`（只用 08:00 PT 窗口）
- `path_distance_method=equirect`（默认；可用 `geodesic` 做 robustness check）
- track 裁剪：时间 `±24h` + 空间半径 `max_distance_km+100km`
- Phase1/2 过滤：`max_track_anchor_gap_hours=24`（避免 t0 与 track anchor 明显错位）

**主输出根目录**：
- `outputs/_runs/trackpath/v3/`

#### 2.9.1 φ heatmap（path）

**每灾害输出**：
- `outputs/_runs/trackpath/v3/<slug>/phi_heatmap/tables/phi_rt_long.csv`
- `outputs/_runs/trackpath/v3/<slug>/phi_heatmap/tables/center_by_window.csv`

**跳过（预期行为）**：
- path 口径要求 catalog 提供 `center_track_csv`；无 track 的灾害会被跳过并落表：`outputs/_runs/trackpath/v3/_skipped_phi_heatmap.csv`
  - 例如 Turkey、洪水、野火、Enteng 等都在该表中（它们需要静态中心口径，不应混用 path）。

**快速自检（可核查事实）**：
- 对 Beryl/Milton/Helene：`center_by_window.csv` 中 `path_track_clip_kind` 为 `time_and_spatial`（非 `full`），且 `path_track_length_ratio_to_rmax` 显著小于 `path_track_length_total_ratio_to_rmax`。

#### 2.9.2 普适性 Phase0/1/2（path 组）

**Phase0：信号强度扫描**
- 输出：`outputs/_runs/trackpath/v3/_tmp_phase0/tables/phase0_signal_strength.csv`
- 事实：`S>=0.5` 的灾害数为 **7**（在 27 灾害表上扫描得到的计数；后续 Phase2 还会因数据可用性/过滤进一步减少）。

**Phase2：坍缩重叠度**
- `minTiles=0`：`outputs/_runs/trackpath/v3/_tmp_phase2_minTiles0/tables/phase2_overlap_metric.csv`
  - `n_disasters_used=5`，`overlap_fraction=0.45`
- `minTiles=50`：`outputs/_runs/trackpath/v3/_tmp_phase2_minTiles50/tables/phase2_overlap_metric.csv`
  - `n_disasters_used=3`，`overlap_fraction≈0.365`

**对齐问题排除（可核查事实）**：
- 在 `outputs/_runs/trackpath/v3/_tmp_phase2_minTiles0/tables/phase2_r0_by_disaster.csv` 中，2 个灾害被标记 `note=t0_misaligned_vs_track_anchor`：
  - `hurricane_john_southern_mexico_25_september_2024`（`track_anchor_to_t0_hours≈35.75h`）
  - `typhoon_yagi_across_northeastern_vietnam`（`track_anchor_to_t0_hours≈29h`）

#### 2.9.3 H3a：3 个飓风的报告/机制与路径叠图（裁剪段口径）

**报告**：
- `outputs/_runs/trackpath/v3/_tmp_h3a_track_report_minTiles0/`
- `outputs/_runs/trackpath/v3/_tmp_h3a_track_report_minTiles50/`

**机制表**：
- `outputs/_runs/trackpath/v3/_tmp_h3a_track_mechanism_minTiles50/`

**路径 overlay**：
- `outputs/_runs/trackpath/v3/_tmp_overlay/figures/*_track_overlay_t0h.png`（同时有 pdf/html）

**相关代码入口**：
- `scripts/cross_disaster_phi_heatmap.py`
- `scripts/universality_scaling.py`
- `scripts/h3a_track_report.py`
- `scripts/h3a_track_mechanism.py`
- `scripts/h3a_track_map_overlay.py`
- `scripts/phi_overlap_stability.py`（诊断 n_tiles_overlap 的时序稳定性）
- `scripts/phi_time_aggregation_verify.py`（诊断 8h→24h 聚合：RoS vs MoR）
- `scripts/path_track_clip_audit.py`（审计 clip_kind 是否退化到 full）

---

### 2.10 SVD 可分离性（rank-1 dominance）：δ(r,t)=φ(r,t)-1 的跨事件检验

> 目的：不再把重点放在“α 是否普适”，而是检验 **人口重分布场是否具有时空可分离结构**（rank-1 dominance）。

**时间**：2026-02-08  
**指标定义**：
- `δ(r,t)=φ(r,t)-1`（默认使用 `phi_overlap`）
- 可分离性：`sigma1_energy = σ1^2 / Σ_k σ_k^2`
- 信号强度：`S = max_{r,t} |δ(r,t)|`
- 近场数据密度 proxy：`n_tiles_overlap_near_mean`（默认 `r<=50km` bins 的均值）

**输入事件**（不挑选不过滤）：
- `outputs/_runs/trackpath/v3/` 下的 13 个风暴/台风类事件
- `outputs/turkiye_earthquake_2023/`（径向口径的地震对照）
- 若存在 `outputs/_runs/trackpath/v4_yagi_fix/`，同名 slug 会自动覆盖旧版 Yagi（用于修复 t0/track 裁剪问题后的结果）

**主要输出**：
- 表：`outputs/cross_disaster_comparison/svd_separability/tables/svd_separability_all.csv`
- 概览：`outputs/cross_disaster_comparison/svd_separability/metadata.json`
  - 当前结果：`n_events=14`，其中 `sigma1_energy>=0.8` 的事件数为 `7`（见 metadata）

**Null model 校正（Permutation；complete δ 矩阵）**：
- 输出：`outputs/cross_disaster_comparison/svd_separability_nullN200/tables/svd_separability_all.csv`
- 关键结果（可核查事实；阈值 `z>3`，`N=200`）：
  - `z_col>3`：`14/14`
  - `z_row>3`：`9/14`
  - `both>3`：`9/14`

**相关代码入口**：
- `scripts/cross_disaster_svd_separability.py`
- `src/disaster/cross_disaster_svd_separability.py`

---

### 2.11 Q2：σ₁ 差异来源的敏感性检验（r_max / 维度）与 σ₂ 可视化

**时间**：2026-02-08  

#### 2.11.1 σ₁ 对 r_max 的依赖（跨事件 sweep）

**输出**：
- `outputs/cross_disaster_comparison/svd_sensitivity_rmax/tables/svd_sigma1_rmax_sweep.csv`
- `outputs/cross_disaster_comparison/svd_sensitivity_rmax/tables/sigma1_rank_stability_spearman.csv`
- `outputs/cross_disaster_comparison/svd_sensitivity_rmax/tables/sigma1_vs_dimension_corr.csv`
- `outputs/cross_disaster_comparison/svd_sensitivity_rmax/metadata.json`

**关键结果（可核查事实）**：
- Beryl TX：`σ₁` 随 `r_max` 增大单调下降（`0.926@100km → 0.873@200km → 0.820@300km → 0.750@500km`；见 sweep 表）。
- `σ₁` 与 `n_time_used` 存在稳定的负相关（Spearman ρ 约 `-0.56~-0.65`，见 `sigma1_vs_dimension_corr.csv`）。
- 事件排序对 `r_max` 较稳定（例如 `rmax_300 vs rmax_500` Spearman `≈0.991`；见 `sigma1_rank_stability_spearman.csv`）。

**相关代码入口**：
- `scripts/cross_disaster_svd_sensitivity.py`
- `src/disaster/cross_disaster_svd_sensitivity.py`

#### 2.11.2 σ₂ 模态（低 σ₁ 事件的第二结构）

**输出（示例）**：
- `outputs/cross_disaster_comparison/svd_modes/beryl_qr_rmax200/`
- `outputs/cross_disaster_comparison/svd_modes/john_southern_rmax200/`

**关键结果（可核查事实；r_max=200, complete）**：
- Beryl QR：`σ₁≈0.608`、`σ₂≈0.237`（见 `metadata.json`）
- John Southern：`σ₁≈0.547`、`σ₂≈0.403`（见 `metadata.json`）

**相关代码入口**：
- `scripts/svd_mode_viz.py`
- `src/disaster/svd_mode_viz.py`

---

### 2.12 Q3：rank-1 动力学 g₁(t) 的幂律拟合（从可分离性走向时间衰减律）

**时间**：2026-02-08  
**定义**：
- `δ(r,t)=φ(r,t)-1`
- `g₁(t)=σ₁·v₁(t)`（SVD 的第一时间模态振幅；见 `v_modes` 的同一定义）

**关键口径**：
- `value_col=phi_overlap`、`r_max=200km`、`complete_only=1`
- 幂律拟合：对 `|g₁(t)|` 在 `t>=t_start` 的尾部做 `log-log` 线性拟合
  - 默认 `fit_mode=from_peak`（从 `|g₁|` 的峰值后开始拟合）

**输出**：
- `outputs/cross_disaster_comparison/rank1_dynamics/tables/g1_timeseries_long.csv`
- `outputs/cross_disaster_comparison/rank1_dynamics/tables/g1_powerlaw_fits.csv`
- 图：`outputs/cross_disaster_comparison/rank1_dynamics/figures/g1_abs_powerlaw_fits.png`

**关键结果（可核查事实；σ₁≥0.90 的事件）**：
- `σ₁≥0.90` 的事件数：`7`
- 在 `from_peak` + `min_fit_points=4` 的口径下：`6/7` 可完成拟合（Ernesto 因 `n_time_used=2` 失败）
- 拟合得到的 `α` 离散很大（约 `-0.02 ~ 0.81`），且部分事件拟合优度较低（`R²` 可低至 `~0.03`；见 `g1_powerlaw_fits.csv`）

**相关代码入口**：
- `scripts/cross_disaster_rank1_dynamics.py`
- `src/disaster/cross_disaster_rank1_dynamics.py`

---

## 3. 关键教训（从“证伪/诊断”中得到）

### 3.1 方法论层面

- 分箱（distance band）可能制造“最优距离/分区边界”的伪像：需要连续版本（tile-level）或做系统敏感性与显著性诊断（本仓库用连续 τ(r) 与样本量过滤做过一轮回应）。
- 参数“撞边界”会让“最优模型”失去解释力：在 z_score 的多模型竞争中尤为明显（`at_bounds=True` 的比例很高）。
- `cos_alpha` 只描述“方向”，不区分“短程带内重组”与“长程跨区域净流”：必须联合 `d_move`、`Δr`、以及 `(r_start,r_end)` 的结构验证。

### 3.2 数据局限层面（就当前样本与口径）

- Movement OD 在本项目设定下被“零距离/极短程”权重主导，导致长程方向信号（`d_move>50km`）在多个灾害窗口内占比极低（多为 `0` 或 `~10^-4`）。
- 非 Turkey 灾害的 Population（φ）偏离幅度整体较小；在“从峰值开始拟合衰减”的口径下，部分灾害会因为时间点太少/峰值在末端而无法给出稳定 τ/β。

---

## 4. 尚未完成但已出现的探索线索（仅记录）

- 序参量与口径：`φ`、`log φ`、`z_score` 的一致性与可解释性（包含 baseline/seasonality 的诊断需求）。
- 恢复动力学的跨灾害比较：当前 τ/β 拟合在部分灾害上因数据点/峰值位置失败，需要更一致的时间覆盖与事件窗口定义。

---

## 5. 代码与输出索引（入口 → 产物）

### Population

- φ 空间再分布：`scripts/population_redistribution.py` → `outputs/<slug>/population_redistribution/`
- z_score/φ 聚合时序：`scripts/population_relaxation.py` → `outputs/population_relaxation/`、`outputs/pop_relax_50km/`
- 机制分区（z_score，多模型竞争）：`scripts/regime_differentiation.py` → `outputs/pop_relax_50km/`
- φ_aggregate 指数 τ（distance band）：`scripts/physical_model_phi_rt.py` → `outputs/<slug>/physical_model/`
- 连续 τ(r)（tile-level）：`scripts/tau_continuous_fit.py` → `outputs/<slug>/tau_continuous_fit/`
- τ 解释/假设检验：`scripts/tau_interpretation_test.py` → `outputs/_tmp_tau_interpretation/tau_interpretation_test/`
- φ FSS：`scripts/phi_fss_collapse.py` → `outputs/_tmp_phi_fss/`、`outputs/_tmp_phi_fss2/`
- 跨灾害恢复拟合（τ/β）：`scripts/cross_disaster_recovery_dynamics.py` → `outputs/_tmp_cross_recovery_dynamics/`、`outputs/<slug>/recovery_dynamics/`
- Response vs Recovery：`scripts/response_vs_recovery.py` → `outputs/_tmp_response_vs_recovery/`

### Movement

- 方向极化（cos_alpha → P/A）：`scripts/directional_polarization.py` → `outputs/<slug>/directional_polarization/`
- 样本量过滤/合并距离带：`scripts/directional_polarization_postprocess.py` → 同上（`flow_directional_filtered.csv` 等）
- 跨带净流（Net=N_in-N_out）：`scripts/cross_band_net_flow.py` → `outputs/<slug>/cross_band_net_flow/`
- Net 分解：`scripts/net_flow_decomposition.py` → `outputs/<slug>/cross_band_net_flow/`
- 目的地/起点分布：`scripts/movement_destination_analysis.py` → `outputs/<slug>/movement_destination_analysis/`
- 25–50km 流入来源：`scripts/movement_inflow_source_analysis.py` → `outputs/<slug>/movement_inflow_source_analysis/`
- 系统性方向分析（无 binning；Δr+d_move）：`scripts/movement_direction_systematic.py` → `outputs/<slug>/movement_analysis/`

### Cross-Disaster Structure

- SVD 可分离性（rank-1 dominance + null）：`scripts/cross_disaster_svd_separability.py` → `outputs/cross_disaster_comparison/svd_separability/`、`outputs/cross_disaster_comparison/svd_separability_nullN200/`
- σ₁ 对 r_max/维度敏感性：`scripts/cross_disaster_svd_sensitivity.py` → `outputs/cross_disaster_comparison/svd_sensitivity_rmax/`
- SVD 模态可视化（u_k/v_k/g_k）：`scripts/svd_mode_viz.py` → `outputs/cross_disaster_comparison/svd_modes/`
- rank-1 动力学 g₁(t) 幂律拟合：`scripts/cross_disaster_rank1_dynamics.py` → `outputs/cross_disaster_comparison/rank1_dynamics/`
