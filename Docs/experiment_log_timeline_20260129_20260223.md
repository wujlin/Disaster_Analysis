# 实验日志时间线（2026-01-29 ～ 2026-02-23）

> 目的：按日期记录“做了什么、产出了什么、踩了什么坑、如何避免重踩”。  
> 适用范围：本仓库 `Disaster_Analysis` 的主分析与子区域分析。  
> 口径说明：文中“主分析”默认指 `radial + 固定样本表 + 固定筛选参数` 的流程，不含 path 几何专项实验。

---

## 1) 按日期的关键实验节点

## 2026-01-29 ～ 2026-01-31（起步与 Turkey 主线）
- **主要动作**
  - 建仓与基础管线落地，加入 Turkey 2023 sample/full 数据及 population relaxation 结果。
  - 完成早期 `z_score/phi` 恢复拟合与分距离带输出。
- **代码入口**
  - `scripts/population_relaxation.py`
  - `scripts/regime_differentiation.py`
  - `scripts/population_postfit_analysis.py`
- **关键产出**
  - `outputs/population_relaxation/`
  - `outputs/pop_relax_50km/`
  - `outputs/turkiye_earthquake_2023_sample/`
- **当时问题**
  - 分箱与边界参数（`at_bounds`）导致可解释性不足，为后续“连续化与稳健性”埋下问题。

## 2026-02-01（网络重分布与跨灾害起步）
- **主要动作**
  - 加入 Turkey movement criticality 与 network redistribution 分析。
  - 首轮跨灾害 `phi(t,r)` / `tau(r)` 批处理上线。
- **代码入口**
  - `scripts/cross_disaster_phi_heatmap.py`
  - `scripts/cross_disaster_eval_suite.py`
  - `scripts/physical_model_phi_rt.py`
- **关键产出**
  - `outputs/cross_disaster_comparison/eval_suite_step_status.csv`
  - `outputs/turkiye_earthquake_2023/physical_model/`
- **当时问题**
  - “恢复函数形式”与“机制解释”耦合过深，后续转向问题驱动叙事。

## 2026-02-02（方向性与净流验证 A/B/C）
- **主要动作**
  - 做 directional polarization（`cos_alpha`）与跨带净流分解。
  - 完成 Task A/B/C（目的地、来源、Net 分解）验证。
- **代码入口**
  - `scripts/directional_polarization.py`
  - `scripts/cross_band_net_flow.py`
  - `scripts/movement_destination_analysis.py`
  - `scripts/movement_inflow_source_analysis.py`
- **关键产出**
  - `outputs/turkiye_earthquake_2023/directional_polarization/`
  - `outputs/turkiye_earthquake_2023/cross_band_net_flow/`
- **当时问题**
  - 方向信号与真实跨区净流不完全等价，必须配合目的地结构分析。

## 2026-02-03（无分箱方向分析 + 两阶段动力学）
- **主要动作**
  - 方向分析从分箱切到连续特征（`d_move`, `Δr`）。
  - 启动两阶段动力学与 universality 方向。
- **代码入口**
  - `scripts/movement_direction_systematic.py`（对应实现在 `src/disaster/`）
  - `scripts/two_phase_dynamics.py`（对应实现在 `src/disaster/`）
- **关键产出**
  - `outputs/<slug>/movement_analysis/`（多灾害）
- **当时问题**
  - 多灾害中心定义不一致（点源 vs 路径源）开始暴露。

## 2026-02-04（数据质量与中心修正）
- **主要动作**
  - 做跨灾害 `phi` 质量诊断，补“centerfix6”修正。
  - 引入 `path distance` 实验并初测飓风 track collapse。
- **代码入口**
  - `scripts/phi_data_quality_diagnostics.py`
  - `scripts/cross_disaster_phi_heatmap.py`（path 模式）
- **关键产出**
  - `outputs/cross_disaster_comparison/` 下 quality 与 trackpath 相关目录
- **当时问题**
  - 发现“完整生命周期 track”会污染局部事件距离定义，后续进入修复。

## 2026-02-06（关键修复：track clip + t0 对齐）
- **主要动作**
  - 修复 path-distance 裁剪与时间锚点（t0）对齐问题。
  - 文档化 path universality 运行口径。
- **代码入口**
  - `src/disaster/cross_disaster_phi_heatmap.py`
  - `src/disaster/cross_disaster_phi_tau.py`
- **关键产出**
  - `Docs/workstation_data_path_guide_wsa.md`
  - 相关 rerun 输出目录（track/path 线）
- **当时问题**
  - 旧实验结果与新口径结果可比性下降，需要后续“回放核验”。

## 2026-02-08 ～ 2026-02-09（SVD/Rank-1 与 g1 拟合）
- **主要动作**
  - 完成 SVD separability、null model、`r_max` 灵敏度。
  - 补 time alignment 与 g1 模型 BIC 比较。
- **代码入口**
  - `scripts/svd_separability.py`
  - `scripts/rank1_dynamics.py`
  - `scripts/g1_model_comparison.py`
- **关键产出**
  - `outputs/cross_disaster_comparison/svd_separability*/`
  - `outputs/cross_disaster_comparison/rank1_dynamics*/`
  - `outputs/cross_disaster_comparison/g1_model_comparison*/`
- **当时问题**
  - 事件窗口覆盖差异造成可分离性对样本敏感。

## 2026-02-10 ～ 2026-02-11（Dt_decay 扩展与批量增量）
- **主要动作**
  - `Dt_decay` 扩展到 27 事件，再扩至新增 11 事件。
  - 合并 archive 数据并做地图类型审计。
- **代码入口**
  - `scripts/dt_decay.py`
  - `scripts/stage_archive_population.py`
  - `scripts/remap_catalog_data_roots.py`
- **关键产出**
  - `outputs/cross_disaster_comparison/Dt_decay/`
  - `Docs/cross_disaster_catalog_extended.csv`
  - `Docs/archive_missing_datasets_audit.csv`
- **当时问题**
  - 数据增量触发自动 fallback（t0/center）漂移风险尚未彻底隔离。

## 2026-02-14（历史参考基线）
- **主要动作**
  - 形成后续对比基线（commit `008a4f5`）。
- **关键产出**
  - 后续用于 AB 回放比较的 old 口径结果（见 2/23 的对照文件）。
- **当时问题**
  - 该基线包含 auto 推断路径，后续可复现但不够“冻结”。

## 2026-02-15（非参数 Exp1/2/3 + 空间扩散 Exp0-4）
- **主要动作**
  - 完成 dynamics_potential 实验 1/2（非参数）+ 实验 3（Langevin 事件级）。
  - 完成 spatial_diffusion 全套 Exp0–Exp4。
- **代码入口**
  - `scripts/dynamics_potential.py`
  - `scripts/spatial_diffusion.py`
- **关键产出**
  - `outputs/cross_disaster_comparison/dynamics_potential_routeB_nonparam_exp3/`
  - `outputs/cross_disaster_comparison/spatial_diffusion_results/`
- **当时问题**
  - 部分事件（如 Central Mexico）时间窗过短，后续在 strict 模式中会被明确剔除并记录原因。

## 2026-02-18（Movement 跨灾害批处理）
- **主要动作**
  - movement_analysis 跑通并加入 warning registry。
  - 以 Route B 事件集为基准得到可用 14 事件结果。
- **代码入口**
  - `scripts/movement_analysis.py`
- **关键产出**
  - `outputs/cross_disaster_comparison/movement_analysis/tables/movement_data_availability.csv`
  - `outputs/cross_disaster_comparison/movement_analysis/tables/movement_evacuation_metrics.csv`
  - `outputs/cross_disaster_comparison/movement_analysis/tables/movement_warning_registry.csv`
- **当时问题**
  - 数据目录存在 zip 未解压、命名不规范、部分事件无 movement 原始文件。

## 2026-02-22（mnt 全量重跑 + 子区域）
- **主要动作**
  - mnt 环境全量重跑（42 事件入口），并推进子区域（L10）分析。
- **代码入口**
  - `scripts/cross_disaster_phi_heatmap.py`
  - `scripts/dt_decay.py`
  - `scripts/geo_unit_scale_analysis.py`
- **关键产出**
  - `outputs/cross_disaster_comparison/Dt_decay/`
  - `outputs/cross_disaster_comparison/geo_unit_scale_routeB_L10/`
- **当时问题**
  - 与旧基线比较时出现“同数据不同结果”，触发 2/23 的根因排查。

## 2026-02-23（不一致根因闭环 + 双轨对照）
- **主要动作**
  - 完成 old vs new 的 AB 回放、参数漂移审计、冻结 catalog 与 pre/post gate。
  - 建立 `legacy_repro_pinned` 与 `main_current_h0816` 双轨对照。
- **代码入口**
  - `scripts/build_routeb16_frozen_catalog.py`
  - `scripts/routeb16_preflight.py`
  - `scripts/routeb16_postgate.py`
  - `scripts/cross_disaster_eval_suite.py`
- **关键产出**
  - `outputs/cross_disaster_comparison/routeB16_inconsistency_rootcause_precise_20260223.txt`
  - `outputs/cross_disaster_comparison/metadata_old008a4f5_vs_frozen8h_routeB16.csv`
  - `outputs/cross_disaster_comparison/phi_old008a4f5_vs_frozen8h_routeB16.csv`
  - `outputs/cross_disaster_comparison/track_execution_summary_20260223.csv`
- **结论（已确认）**
  - 根因不是“代码随机坏了”，而是**数据增量 + auto fallback 联合作用**导致 `t0/center/窗口集合` 漂移。
  - `legacy_repro_pinned` 可恢复到 16 事件且复现核心相关（`rho=-0.526, p=0.036`）；`main_current_h0816` 因口径变化仅保留 10 事件。

---

## 2) 已确认的踩坑清单（防重复）

1. **Auto fallback 黑箱漂移**
- 现象：同一事件在不同批次出现 `t0/center` 自动重估，触发 `t_peak`、`near_delta`、`n_mono` 连锁变化。
- 证据：`outputs/cross_disaster_comparison/routeB16_inconsistency_rootcause_precise_20260223.txt`
- 规避：主分析禁用 fallback，catalog 必填 `t0_pt + center_lat/lon + only_hour_pt`。

2. **动态中心外推导致窗口掉光**
- 现象：track 末端外推后中心漂移，`r<=200km` 有效窗口骤减，事件被 `EXCLUDED_SHORT`。
- 规避：主分析使用静态中心；path 实验独立跑，不与主分析混用。

3. **数据目录“存在但不可读”**
- 现象：zip 未解压/目录拼写异常（如 `Spain fllood`）、movement 缺失导致脚本误判无数据。
- 规避：先跑 catalog remap + preflight，再启动主流程。

4. **小时窗口口径漂移（0/8/16 vs 仅8）**
- 现象：窗口数骤降（典型是 Central Mexico），`n_mono` 从可用变不可用。
- 规避：对比实验必须固定小时口径，并在 metadata 里明确记录。

---

## 3) 当前建议的“可复现协议”（执行顺序）

1. **先冻结输入**
- catalog：`Docs/cross_disaster_catalog_routeB16_frozen.csv`
- 样本标记：`outputs/.../Dt_routeB_sample_flags.csv`（固定来源）

2. **跑前 gate**
- `scripts/routeb16_preflight.py`
- 必须检查：事件数、窗口数、中心外推计数、缺字段。

3. **主流程**
- `scripts/cross_disaster_phi_heatmap.py`（`radial`、固定小时）
- `scripts/dt_decay.py`（固定 `min_n_mono`, `r_max`, 排除列表）
- 子区域：`scripts/geo_unit_scale_analysis.py`

4. **跑后 gate**
- `scripts/routeb16_postgate.py`
- 必须检查：`route_b_selected` 计数是否与预期一致；缺失事件列表是否为空（或有明确理由）。

---

## 4) 关键证据文件索引（优先看这些）

- **不一致根因总表**  
  `outputs/cross_disaster_comparison/routeB16_inconsistency_rootcause_precise_20260223.csv`
- **根因文字版**  
  `outputs/cross_disaster_comparison/routeB16_inconsistency_rootcause_precise_20260223.txt`
- **old vs frozen 参数漂移**  
  `outputs/cross_disaster_comparison/metadata_old008a4f5_vs_frozen8h_routeB16.csv`
- **old vs frozen 窗口/结果漂移**  
  `outputs/cross_disaster_comparison/phi_old008a4f5_vs_frozen8h_routeB16.csv`
- **双轨执行摘要（主分析 + 子区域）**  
  `outputs/cross_disaster_comparison/track_execution_summary_20260223.csv`
- **RouteB 双轨对照摘要**  
  `outputs/cross_disaster_comparison/routeB_dual_track_summary_20260223.csv`

---

## 5) 维护规则（后续新增实验统一遵守）

- 不在主分析链路使用 auto fallback；发现缺字段直接报错，不静默补值。  
- path 几何实验与 radial 主分析物理上分轨，禁止混跑。  
- 每轮新数据并入后先做 preflight，不通过不进入统计解释。  
- 结论比较只在“同 catalog + 同窗口口径 + 同筛选参数 + 同脚本版本”下进行。  

