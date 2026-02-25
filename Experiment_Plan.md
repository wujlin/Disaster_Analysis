# Partner 交接 Prompt：灾后人口恢复动力学 — 管线修复与重跑

> Implementation Plan, Task List and Thought in Chinese
> 
> **核心理念**：恪守 KISS 原则，事实为本，渐进式开发。
> **风险提醒**：在移动/删除/归档任何文件或目录前，先确认已有备份或纳入版本控制。

---

## 一、项目背景与科学目标

### 1.1 研究问题

我们用 **Meta/Facebook Disaster Maps (FBDM)** 的人口数据研究灾后社会系统的恢复动力学。核心发现：

- 灾害后人口扰动振幅 $D(t)$ 普遍遵循幂律衰减 $D(t') \sim t'^{-\alpha}$
- **恢复速度 $\alpha$ 由灾害峰值时的空间剖面形状决定**：近场人口净外流（疏散型，$\delta_{\text{near}} < 0$）的事件恢复更快
- 目标期刊：Nature Communications（≤5000 countable words）

### 1.2 核心指标定义

$$D(t) = \frac{1}{N_r} \sum_{r \leq r_{\max}} |\phi(r,t) - 1|$$

其中 $\phi(r,t) = n_{\text{crisis}} / n_{\text{baseline}}$（FBDM 的 crisis/baseline 人口比）。

$$\delta_{\text{near}}(t) = \frac{1}{N_{r \leq r_{\text{near}}}} \sum_{r \leq r_{\text{near}}} (\phi(r,t) - 1)$$

- $D(t)$ 衡量总扰动幅度（绝对值平均）
- $\delta_{\text{near}}$ 衡量近场位移方向（正=涌入，负=疏散）
- $D_{\text{peak}}$ = D(t) 的全局最大值
- $\alpha$ = 峰后单调衰减段的 log-log 斜率（幂律指数）

### 1.3 事件分类

基于 $D > 0.5 \times D_{\text{peak}}$ 时间窗口内的 $\delta_{\text{near}}$ 均值：
- **EVAC**（疏散型）：$\delta_{\text{near}} < -0.02$
- **INFL**（涌入型）：$\delta_{\text{near}} > +0.02$
- **NEUTRAL**：$|\delta_{\text{near}}| \leq 0.02$

---

## 二、项目历史与关键教训（你必须了解）

### 2.1 核心发现的三次震荡

| 阶段 | 样本 | $\rho(\alpha, \delta_{\text{near}})$ | p | 原因 |
|------|------|------|---|------|
| 原始（auto t₀） | n=16 | −0.526 | 0.036 | 16 事件手工挑选 + auto-inferred t₀/center |
| 崩溃 | n=13 | +0.044 | 0.887 | 新数据批次 + auto t₀ 漂移 |
| Route A Open（42事件） | n=18 | −0.088 | 0.729 | 去除所有人为筛选后的全样本分析 |
| **当前（partial_gt_round2）** | **n=9** | **−0.917** | **0.0005** | 32 事件 verified t₀ → 筛选到 9 |

**教训**：
1. **Auto-inference 是万恶之源**：t₀ 和 center 的自动推断在不同数据批次间不一致，导致结果漂移。现在禁止 auto fallback，所有参数必须在 catalog 中显式提供。
2. **样本构成决定结果**：同一管线在不同事件集上可以得到截然相反的结论。必须记录完整的筛选漏斗（PRISMA 式）。
3. **16 事件是手工挑选的**：旧分析中的 "Route B 16 事件" 是硬编码 slug 列表，不是算法筛选。现在已废弃。

### 2.2 子区域分析的逆转

| 阶段 | 事件数 | Mixed-effects $\beta(\delta_{\text{peak\_unit}})$ | p |
|------|--------|------|---|
| 旧（12 事件） | 12 | −0.527 | 5.39×10⁻⁹ |
| **当前（24 事件）** | **24** | **−0.080** | **0.105** |

但新出现了：**$D_{\text{peak\_unit}}$** 显著（$\beta = +0.310, p = 1.5 \times 10^{-6}$）——"位移幅度越大的子区域，恢复越快"。

### 2.3 当前结果状态

**事件级（n=9, monotone_truncated）**：
- $\rho(\alpha, \delta_{\text{near}}) = -0.917, p = 0.0005$（极强）
- Jackknife CI: [−0.948, −0.881]

**事件级（n=12, full_post_peak）**：
- $\rho = -0.517, p = 0.085$（不显著）
- ⚠️ 两种方法的 $\alpha$ 相关性极低（Pearson=0.159），说明方法不可互换

**子区域（24 事件, L10 quadkey）**：
- $\delta_{\text{peak\_unit}}$: 不再显著 (p=0.105)
- $D_{\text{peak\_unit}}$: 显著 ($\beta=+0.310, p<10^{-6}$)

---

## 三、当前管线架构与代码路径

### 3.1 两阶段管线

```
阶段 1: phi_heatmap（空间热图构建）
  脚本入口: scripts/cross_disaster_phi_heatmap.py
  核心实现: src/disaster/cross_disaster_phi_heatmap.py + src/disaster/phi_heatmap.py
  输入: catalog CSV → 每事件的 FBDM population 文件
  输出: outputs/{slug}/phi_heatmap/tables/phi_rt_long.csv
  
阶段 2: dt_decay（D(t) 衰减分析）
  脚本入口: scripts/dt_decay.py
  核心实现: src/disaster/dt_decay.py
  输入: 阶段 1 的 phi_rt_long.csv
  输出: outputs/cross_disaster_comparison/Dt_decay_{run_name}/tables/
  
子区域分析:
  脚本入口: scripts/geo_unit_scale_analysis.py
  核心实现: src/disaster/geo_unit_scale_analysis.py
  输入: catalog + FBDM population 文件（直接从原始数据构建子区域时序）
  输出: outputs/cross_disaster_comparison/geo_unit_scale_{run_name}/tables/
```

### 3.2 关键代码位置

| 功能 | 文件 | 关键行/函数 |
|------|------|-------------|
| D(t) 时间序列构建 | `src/disaster/dt_decay.py` | `_compute_dt_timeseries()` (~L280) |
| 峰值选取 | `src/disaster/dt_decay.py` | `_pick_peak()` (~L380) |
| 事件分类 EVAC/INFL | `src/disaster/dt_decay.py` | `_classify_event()` (~L390) |
| 单调衰减段截取 | `src/disaster/dt_decay.py` | `_monotone_decay_segment()` (~L440) |
| 幂律拟合 | `src/disaster/dt_decay.py` | `_fit_powerlaw_loglog()` (~L460) |
| 质量过滤链 | `src/disaster/dt_decay.py` | L880-L970 |
| phi_heatmap 中心解析 | `src/disaster/cross_disaster_phi_heatmap.py` | `auto_t0_and_center()` (imported from `cross_disaster_phi_tau.py`) |
| phi_heatmap 距离计算 | `src/disaster/phi_heatmap.py` | 中心坐标 → radial/path distance |
| 子区域 mixed-effects | `src/disaster/geo_unit_scale_analysis.py` | `run()` |

### 3.3 当前使用的 Catalog

**主 catalog（42 事件，含排除标记）**：
`Docs/cross_disaster_catalog_extended_partial_gt_round2.csv`

**工作 catalog（32 事件，排除 10 个不可解析的）**：
`Docs/cross_disaster_catalog_extended_partial_gt_round2_included32.csv`
- 所有 32 事件均有外部验证的 t₀ 和 center（来自 USGS、NHC、Copernicus EMS 等）
- `auto_inference_used = 0` 对所有事件

### 3.4 当前参数配置

来自 `metadata.json`：

| 参数 | 值 | 含义 |
|------|-----|------|
| `r_max_km` | 200 | D(t) 计算的最大距离 |
| `near_r_km` | 50 | 近场定义距离 |
| `min_tiles_overlap` | 3 | 每个 r_bin 最少 tile 数 |
| `min_r_bins` | 5 | 每个时间窗口最少距离 bin 数 |
| `min_near_bins` | 2 | 近场最少 bin 数 |
| `min_time_windows` | 5 | L1 筛选：最少时间窗口数 |
| `min_post_peak_steps` | 4 | L2 筛选：峰后最少步数 |
| `fit_method` | monotone_truncated | 主方法：单调截断拟合 |
| `fit_min_tprime_hours` | 24 | 拟合起点 ≥ 24h |
| `mono_tol_up` | 1.05 | 单调容忍度：允许 5% 反弹 |
| `route_b_min_n_mono` | 3 | L3 筛选：单调段最少 3 点 |
| `peak_frac` | 0.5 | 分类用：D > 0.5×D_peak 的窗口 |
| `near_thresh` | 0.02 | 分类用：EVAC/INFL 阈值 |

### 3.5 当前筛选漏斗

```
L0: catalog exclude_reason 为空     42 → 32  （排除 10 个 groundtruth_unresolved 事件）
L1: n_time_windows ≥ 5              32 → 17  （排除 15 个 EXCLUDED_SHORT）
L2: n_post_fit ≥ 4                  17 → 12  （排除 5 个 short_post_peak）
L3: n_mono ≥ 3 且 alpha 非空         12 → 9   （排除 3 个 applicability）
L4: route_b_selected (plot only)     9 → 9    （R² < 0.6 仅影响绘图，不影响统计）
```

---

## 四、已确认的问题（你需要解决的）

### 问题 A：飓风 track center 导致空间过滤吞噬时间窗口

**根因**：飓风/热带风暴事件在 phi_heatmap 阶段使用了动态 track center（随风暴移动的中心）。风暴在登陆后迅速移向内陆，但 FBDM tiles 覆盖的是登陆区域。track center 外推到远离 tiles 的位置后，`r ≤ 200km` 过滤器把后续所有窗口全部排除。

**受影响事件诊断表**（来自 `partial_gt_round2_excluded_short_window_diagnostics.csv`）：

| 事件 | 原始窗口 | r≤200km 后 | 最终 | 问题根因 | 可恢复？ |
|------|---------|-----------|------|---------|---------|
| ernesto_pr | 15 | 0 | 0 | catalog center (15.1,-55.6) 在东加勒比海，离波多黎各 FBDM tiles ~1100km | ✅ 修正 center |
| helene_pre | 12 | 1 | 1 | t=0 时 track center 已到田纳西 (35.55,-84.05)，FBDM tiles 在佛罗里达沿岸 | ✅ 改用 static |
| kristine_ph | 12 | 2 | 2 | track 外推到南海海面 (17.3,117.2)，FBDM tiles 在菲律宾陆地 | ✅ 改用 static |
| beryl_qr | 2 | 1 | 1 | 原始数据仅 2 窗口，track 移到墨西哥湾 | ⚠️ 数据量不足 |
| beryl_tx | 2 | 1 | 1 | 原始数据仅 2 窗口，track 移到阿肯色州 | ⚠️ 数据量不足 |
| yagi_ph | 2 | 1 | 1 | 原始数据仅 2 窗口，track 移到南海 | ⚠️ 数据量不足 |
| milton_fl | 1 | 0 | 0 | min r=210km（刚超 200km 阈值） | ⚠️ 边界情况 |
| beryl_pre | 0 | 0 | 0 | 无 FBDM 数据 | ❌ 不可恢复 |
| mountain_fire | 1 | 1 | 1 | 仅 1 天数据 | ❌ 不可恢复 |

**核心洞见**：ernesto_pr（15个窗口）、helene_pre（12个窗口）、kristine_ph（12个窗口）共 39 个原始窗口因 center 问题几乎全部被丢弃。这三个事件如果修复 center，有望恢复到 n_time_windows ≥ 5。

### 问题 B：3 个事件差 1 个窗口即达标

| 事件 | n_time_windows | 类型 | 说明 |
|------|---------------|------|------|
| melissa_aft | 4 | hurricane | 建议在 L0 排除（非独立后续事件） |
| mexico_eq | 4 | earthquake | 降 min_time_windows 到 4 可恢复 |
| dhaka_eq | 4 | earthquake | 降 min_time_windows 到 4 可恢复 |

### 问题 C：L0 catalog 需要清理

以下事件应在 L0 层添加 exclude_reason：

| 事件 | 建议排除理由 | 说明 |
|------|-------------|------|
| beryl_pre | `pre_landfall_no_impact_data` | FBDM 0 个窗口 |
| helene_pre | `pre_landfall_event` | 研究疏散而非恢复 |
| debby_pre | `pre_landfall_event` | 登陆前数据集 |
| park_fire_2024 | `pseudo_replication` | 与 park_fire_california 是同一场火灾的两个数据集 |
| melissa_aft | `non_independent_aftermath` | 是 melissa 事件的后续数据集 |
| mountain_fire | `fbdm_coverage_insufficient` | 仅 1 天数据 |
| beryl_pre_jamaica | `pre_landfall_event` | 登陆前预警数据 |

### 问题 D：ernesto_pr 的 catalog center 错误

当前 catalog 中 ernesto_pr 的 center 是 `(15.1, -55.6)`，这是风暴形成初期在东加勒比海的位置，距离波多黎各 FBDM 覆盖区约 1100km。需要修正为波多黎各最近接近点或登陆点的坐标。

参考：NHC TCR AL052024 显示 Ernesto 在 8/14 经过波多黎各附近，位置约 `(18.2, -65.9)`。

---

## 五、需要执行的任务

### Task 1：修复 phi_heatmap 阶段的飓风 center 策略

**目标**：对飓风/热带风暴事件，在 D(t) 恢复分析中使用 **static landfall center** 而非 track 插值位置。

**方案**：不需要改代码。在 catalog CSV 的 `center_track_csv` 列清空这些事件的 track 引用，让代码自然走 static center 路径。同时确保 `center_lat/center_lon` 是正确的登陆/受灾点坐标。

**具体步骤**：
1. 复制 `Docs/cross_disaster_catalog_extended_partial_gt_round2_included32.csv` 为 `..._round3.csv`
2. 对以下事件，**清空** `center_track_csv` 列（保留为空）：
   - ernesto_pr：同时修正 center 为 `(18.2, -65.9)`（波多黎各最近接近点）
   - kristine_ph：确认 center `(13.8, 127.0)` 是登陆点
   - helene_pre：如果保留此事件，center 应设为 Big Bend 登陆点 `(29.8, -83.7)`
   - 其他所有有 `center_track_csv` 的飓风事件（beryl_qr, beryl_tx, beryl_jamaica, beryl_pre, debby, milton, john_gue, john_sm, yagi_ph, krathon, yagi_vn）也清空 track，确保都走 static center
3. 对需要在 L0 排除的事件（见问题 C），在 42 事件的完整 catalog `..._partial_gt_round2.csv` 中添加 `exclude_reason`

**验证**：重跑 phi_heatmap 后检查 `_provenance_phi_heatmap.csv`，确认：
- 所有事件 `center_mode = static`
- ernesto_pr 的 n_time_windows 应从 0 恢复到 ~15
- kristine_ph 应从 2 恢复到 ~12

### Task 2：重跑完整管线

**步骤**：

```bash
# Step 1: phi_heatmap（用新 catalog）
python scripts/cross_disaster_phi_heatmap.py \
  --catalog Docs/cross_disaster_catalog_extended_partial_gt_round3_included.csv \
  --output-root outputs/_runs/round3 \
  --distance-mode radial \
  --hours-pt 0 8 16 \
  --on-error skip \
  --require-explicit-t0-center 1 \
  --write-provenance 1

# Step 2: dt_decay
python scripts/dt_decay.py \
  --output-root outputs/_runs/round3 \
  --catalog Docs/cross_disaster_catalog_extended_partial_gt_round3_included.csv \
  --out-dir outputs/cross_disaster_comparison/Dt_decay_round3 \
  --use-catalog-exclude-reason 1 \
  --min-time-windows 5 \
  --min-post-peak-steps 4 \
  --fit-method monotone_truncated

# Step 3: 子区域分析
python scripts/geo_unit_scale_analysis.py \
  --catalog Docs/cross_disaster_catalog_extended_partial_gt_round3_included.csv \
  --output-root outputs/_runs/round3 \
  --dt-flags-csv outputs/cross_disaster_comparison/Dt_decay_round3/tables/Dt_routeB_sample_flags.csv \
  --out-dir outputs/cross_disaster_comparison/geo_unit_scale_round3_L10
```

**输出检查**：
1. `Dt_event_summary.csv` — 检查 ernesto_pr, kristine_ph 的 n_time_windows 是否恢复
2. `Dt_routeB_alpha_delta_spearman.csv` — n_selected 和 ρ
3. `Dt_routeB_sample_flags.csv` — 完整漏斗

### Task 3：min_time_windows 敏感性分析

**目标**：对比 `min_time_windows = 4` vs `5` 的结果差异。

```bash
python scripts/dt_decay.py \
  --output-root outputs/_runs/round3 \
  --catalog Docs/cross_disaster_catalog_extended_partial_gt_round3_included.csv \
  --out-dir outputs/cross_disaster_comparison/Dt_decay_round3_mtw4 \
  --use-catalog-exclude-reason 1 \
  --min-time-windows 4 \
  --min-post-peak-steps 4 \
  --fit-method monotone_truncated
```

**关注点**：mexico_eq 和 dhaka_eq 是否进入 selected 样本？ρ 如何变化？

### Task 4：Full_post_peak 方法验证

**目标**：确认 ρ=−0.917 不完全依赖于 monotone_truncated 方法。

```bash
python scripts/dt_decay.py \
  --output-root outputs/_runs/round3 \
  --catalog Docs/cross_disaster_catalog_extended_partial_gt_round3_included.csv \
  --out-dir outputs/cross_disaster_comparison/Dt_decay_round3_fullpost \
  --use-catalog-exclude-reason 1 \
  --min-time-windows 5 \
  --min-post-peak-steps 4 \
  --fit-method full_post_peak
```

**关注点**：full_post_peak 的 n_selected 通常更大（不需要 n_mono≥3），对比两种方法的 ρ 和 p 值。

### Task 5：输出完整筛选漏斗文档

**目标**：生成一个类似之前 `partial_gt_round2_filter_stack_summary.csv` 的漏斗表，加上：
1. 每层的具体排除事件列表
2. 排除事件的诊断信息（n_time_windows_raw vs n_time_windows_filtered）
3. 与 round2 的对比（哪些事件被恢复了？哪些新进入了？）

建议输出文件：
- `outputs/cross_disaster_comparison/round3_filter_stack_summary.csv`
- `outputs/cross_disaster_comparison/round3_vs_round2_change_log.csv`

---

## 六、数据位置

### FBDM 原始数据

```
旧数据（WSA 工作站挂载）:
  /mnt/e/newdesktop/archive/facebook/disaster data/{event_name}/population/

新数据（本地）:
  datasets/staged/{slug}/population/
  datasets/{slug}/population/
```

Catalog CSV 的 `data_root` 列指定了每个事件的数据路径。

### Storm Track 数据

```
Docs/storm_tracks/nhc_best_track_2024_landfalls.csv
```
包含 Beryl、Milton、Helene、Debby、Ernesto、John、Yagi、Krathon、Trami 的轨迹点。

### 已有输出（当前最新的 round2 结果）

```
phi_heatmap 输出:
  outputs/_runs/partial_gt_round2_included32/{slug}/phi_heatmap/tables/phi_rt_long.csv

dt_decay 输出:
  outputs/cross_disaster_comparison/Dt_decay_partial_gt_round2_included32_20260224_133240/

子区域输出:
  outputs/cross_disaster_comparison/geo_unit_scale_partial_gt_round2_included32_20260224_132836/

漏斗审计:
  outputs/cross_disaster_comparison/partial_gt_round2_filter_stack_summary.csv
  outputs/cross_disaster_comparison/partial_gt_round2_funnel_audit_32_to_9_summary.csv
  outputs/cross_disaster_comparison/partial_gt_round2_excluded_short_window_diagnostics.csv
```

---

## 七、当前 9 个 selected 事件速查

| 事件 | 类型 | event_type | α | R² | δ_near |
|------|------|-----------|-----|-----|--------|
| nepal_fld | flood | EVAC | 1.215 | 0.944 | −0.120 |
| debby_pre | trop_storm | EVAC | 0.651 | 0.896 | −0.044 |
| yagi_vn | typhoon | EVAC | 0.522 | 0.955 | −0.547 |
| rio_grande | flood | NEUTRAL | 0.390 | 0.932 | +0.001 |
| quito_fire | wildfire | NEUTRAL | 0.424 | 0.681 | +0.001 |
| park_fire2 | wildfire | INFL | 0.223 | 0.711 | +0.046 |
| turkiye | earthquake | INFL | 0.223 | 0.959 | +0.057 |
| spain_flood | flood | INFL | 0.058 | 0.813 | +0.203 |
| eu_flood | flood | INFL | −0.015 | 0.141 | +0.101 |

**Spearman ρ = −0.917, p = 0.0005**

---

## 八、优先级排序

1. **🔴 最高优先级**：Task 1（修复 center）+ Task 2（重跑管线）— 这是所有后续分析的基础
2. **🟡 高优先级**：Task 5（漏斗文档）— 结果出来后立即做
3. **🟢 中优先级**：Task 3（敏感性）+ Task 4（full_post_peak 验证）— 重跑完成后做

---

## 九、预期结果与判断标准

### 最佳情况
- ernesto_pr 恢复 15 个窗口 → 通过 L1/L2/L3 → 进入 selected
- kristine_ph 恢复 12 个窗口 → 进入 selected
- n_selected 从 9 增加到 11-13
- ρ 仍然显著（p < 0.05），|ρ| > 0.5

### 可接受情况
- 新事件进入但 ρ 下降到 |ρ| ≈ 0.5, p ≈ 0.05-0.10
- 需要报告两种方法（monotone + full_post_peak）

### 需要警惕的情况
- 新事件的加入导致 ρ 翻转或不显著 → 说明信号不 robust
- ernesto_pr 修正 center 后仍然不通过空间过滤 → 需要进一步调查数据质量

---

## 十、代码风格与约定

- 遵循 `AGENTS.md` 中的原则
- 所有回复和注释用中文
- 输出目录命名格式：`{analysis_type}_{catalog_tag}_{date}`
- 每次运行的参数保存在 `metadata.json` 中
- 可视化风格参考 `Docs/visual_style_guide.md` 和 `src/disaster/plot_style.py`
- **不要删除任何已有输出**，只创建新目录

---

## 附录：环境信息

- 系统：WSL + miniconda, Python 3.10+
- GPU：本地 4060（本分析不需要 GPU）
- 关键依赖：pandas, numpy, scipy, matplotlib, statsmodels（mixed-effects 用）
- 工作目录：`/Users/jinlin/Desktop/project/Disaster_Analysis/`（macOS）或 WSL 挂载路径


Plan: 飓风/台风 center 策略——不是简单删掉 track
核心问题：台风的灾害中心确实在移动，但 D(t) 恢复分析关心的是"受灾区域在恢复"还是"风暴当前位置的人口状态"？这两个问题需要不同的距离定义。当前代码在 distance_mode=radial 下使用了移动中心，导致风暴过后中心飘走、空间过滤杀掉恢复期数据。

物理分析：三种 center 策略的含义
策略 1：Track 移动中心（当前 radial + track）

每个时间窗口的 center 随风暴移动
物理含义："此刻风暴正中心 200km 内的人口状态"
适用场景：研究风暴实时影响（response）
恢复分析的问题：风暴过后中心飘到阿肯色州/南海，r≤200km 内不再有受灾 tiles → 恢复期数据全丢
策略 2：Static 登陆点中心（清空 center_track_csv）

所有窗口使用同一个固定坐标（登陆点）
物理含义："登陆受灾点 200km 内的人口恢复"
适用场景：恢复动力学分析（与地震类似——epicenter 不动）
问题：如果台风沿海岸线扫过 500km（如 Helene），一个点只能代表局部；远离登陆点的受灾区被切掉
策略 3：Path 距离（distance_mode=path + track）

距离 = tile 到 track 折线的最短垂足距离
物理含义："距风暴经过路径 200km 内的人口恢复"
这是物理上最正确的方案：任何曾在风暴 200km 范围内的 tile 始终被纳入——无论风暴当时在路径的哪个位置
问题：(a) 改变了 r_bin 的含义（不再是"到一个点的距离"，而是"到一条线的距离"），与地震事件不可比；(b) 代码已实现但需要 center_track_csv 非空
建议方案
分析	Center 策略	理由
主分析	Static 登陆点	与地震一致，r_bin 定义统一，恢复分析的正确物理选择。代价是飓风的沿途受灾区只覆盖登陆附近
SI robustness	distance_mode=path	对飓风事件最物理正确的距离定义。需保留 center_track_csv 引用。单独跑一组，对比主分析
Steps
在主分析 catalog 中清空所有飓风/台风事件的 center_track_csv 列：这让 phi_heatmap 走 static center 路径。同时确认每个事件的 center_lat/center_lon 是登陆点或最大影响点坐标（而非风暴形成位置）。这解决了"track 外推导致窗口全丢"的核心问题。

修正 ernesto_pr 的 center 坐标：当前 (15.1, -55.6) 是风暴形成位置，不是波多黎各登陆/最近接近点。修改为约 (18.2, -65.9)（NHC TCR 波多黎各影响位置）。

保留一份带 track 引用的 catalog 副本用于 SI path-distance 实验：命名为 ..._round3_with_tracks.csv，distance_mode=path 单独跑。对比两种距离定义下 D(t) 的差异——如果 path 模式显著改变结果，说明沿途受灾区很重要；如果一致，说明 static landfall center 足够。

在论文 Methods 中明确说明选择理由："D(t) measures the recovery of the impact zone. For earthquakes, the epicenter is stationary. For tropical cyclones, we use the landfall coordinate as a static center, as the recovery occurs at the geographically fixed impact area rather than following the moving storm. Path-distance results are reported in SI as a robustness check."

Further Considerations
Krathon (台风) 的特殊情况：Krathon 在台湾登陆后缓慢北上，center 从 (22.2, 119.9) 移到 (23.3, 120.6)，移动距离约 130km。台湾面积较小，移动中心和 static center 的差异不大（都在台湾岛内）。改为 static 后影响应该很小——但建议检查 krathon 的 n_time_windows 是否变化。

是否对 Yagi Vietnam 也需要特殊处理？ Yagi 在越南的影响区域集中在河内一带（登陆点 20.9, 106.9），track 移动距离有限。Static center 应该足够。

beryl_jamaica 的 center (13.5, -64.1) 看起来也有错误——这个坐标在加勒比海东部小安的列斯群岛，远离牙买加。如果保留该事件，需要修正为牙买加附近的坐标。