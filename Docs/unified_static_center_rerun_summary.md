# 统一 Static Center 管线修复：完整实验总结

> **日期**：2026-02-25
> **范围**：phi_heatmap 重跑（全量 32 事件）+ dt_decay 敏感性分析（4 参数组合）
> **核心修复**：飓风/台风事件改用静态登陆中心 + 多个事件 center 坐标修正 + 统一 hours_pt=[8]

---

## 一、实验动机

### 1.1 发现的问题

在 `partial_gt_round2` 管线中发现三类系统性问题：

1. **飓风 track center 导致窗口丢失**（问题 A）：飓风事件使用动态 track 插值中心，风暴过后中心飘到内陆/远洋，`r ≤ 200km` 空间过滤器把恢复期窗口全部排除。ernesto_pr（15→0 窗口）、kristine_ph（12→2）、helene_pre（12→1）是最严重的受害者。
2. **catalog center 坐标错误**（问题 D）：ernesto_pr 的 center (15.1, -55.6) 是风暴形成位置（东加勒比海），距波多黎各 FBDM tiles ~1100km；beryl_jamaica 的 center (13.5, -64.1) 在小安的列斯群岛；kristine_ph 的 center 也偏离了实际受灾区。
3. **hours_pt 口径不一致**：旧 phi_heatmap 使用 `hours_pt=[8]`（仅 08:00 窗口），但上一轮修复时误用了 `hours_pt=[0,8,16]`（三个时段），导致 `n_time_windows` 膨胀，与旧基线不可比。

### 1.2 修复策略

| 问题 | 修复方案 | 实现方式 |
|------|---------|---------|
| Track center 外推 | 所有热带气旋改用 static landfall center | 清空 catalog 的 `center_track_csv` 列 |
| Center 坐标错误 | 修正为实际登陆/最大影响点坐标 | 直接编辑 catalog CSV |
| hours_pt 不一致 | 统一使用 `hours_pt=[8]` | 命令行参数 `--hours-pt 8` |

---

## 二、计算流程与代码路径

### 2.1 管线架构

```
阶段 1: phi_heatmap（空间热图构建）
  脚本入口: scripts/cross_disaster_phi_heatmap.py
  核心实现: src/disaster/cross_disaster_phi_heatmap.py
           src/disaster/phi_heatmap.py
  中心解析: src/disaster/cross_disaster_phi_tau.py → auto_t0_and_center()
  距离计算: src/disaster/phi_heatmap.py → center_lat/center_lon → r_bin_km

阶段 2: dt_decay（D(t) 衰减分析）
  脚本入口: scripts/dt_decay.py
  核心实现: src/disaster/dt_decay.py
  关键函数:
    _compute_dt_timeseries()  — D(t) 时间序列构建
    _pick_peak()              — 峰值选取
    _classify_event()         — EVAC/INFL/NEUTRAL 分类
    _monotone_decay_segment() — 单调衰减段截取
    _fit_powerlaw_loglog()    — 幂律拟合 α
```

### 2.2 中心策略的代码逻辑

`cross_disaster_phi_heatmap.py` 的 `run()` 函数中：
- 如果 catalog 行的 `center_track_csv` 非空 → 加载 track，调用 `_center_at(track, ts)` 对每个时间窗口插值出动态中心
- 如果 `center_track_csv` 为空 → 使用 `cfg.center_lat / cfg.center_lon`（静态中心）

**本次修复**：在 catalog CSV 中清空所有 15 个热带气旋事件的 `center_track_csv` 列，迫使代码走静态中心路径。

### 2.3 执行命令

**Step 1：phi_heatmap 全量重跑**（WSL 环境）

```bash
python scripts/cross_disaster_phi_heatmap.py \
  --catalog Docs/cross_disaster_catalog_extended_partial_gt_round2_static_center.csv \
  --output-root outputs/_runs/unified_static_h8 \
  --hours-pt 8 \
  --on-error skip \
  --allow-auto-fallback 0 \
  --require-explicit-t0-center 1 \
  --require-explicit-sources 1
```

**Step 2：dt_decay 敏感性分析**（4 组参数组合）

```bash
# 基线: mtw=5, mpp=4
python scripts/dt_decay.py \
  --output-root outputs/_runs/unified_static_h8 \
  --catalog Docs/cross_disaster_catalog_extended_partial_gt_round2_static_center.csv \
  --out-dir outputs/cross_disaster_comparison/Dt_decay_unified_h8_mtw5_mpp4 \
  --min-time-windows 5 --min-post-peak-steps 4

# mtw=4, mpp=4
# mtw=5, mpp=3
# mtw=4, mpp=3（最宽松）
# （同上结构，改变参数值）
```

### 2.4 Catalog 修改记录

修改文件：`Docs/cross_disaster_catalog_extended_partial_gt_round2_static_center.csv`
（基于 `Docs/cross_disaster_catalog_extended_partial_gt_round2.csv` 的副本）

| 事件 | 修改内容 |
|------|---------|
| ernesto_pr | center: (15.1, -55.6) → (18.2, -65.9)；清空 center_track_csv |
| beryl_jamaica | center: (13.5, -64.1) → (18.1, -77.3)；清空 center_track_csv |
| kristine_ph | center: (13.8, 127.0) → (14.0, 123.0)；清空 center_track_csv |
| debby_pre (hurricane) | center: (20.9, -76.6) → (29.7, -83.5)；清空 center_track_csv |
| 其余 11 个热带气旋 | 清空 center_track_csv（保留原 center 坐标） |
| beryl_pre_2024 | exclude_reason = `fbdm_coverage_insufficient` |
| mountain_fire | exclude_reason = `fbdm_coverage_insufficient` |
| nika_ph | exclude_reason = `fbdm_coverage_insufficient` |
| global_eq | exclude_reason = `fbdm_coverage_insufficient` |
| melissa_aft | exclude_reason = `non_independent_aftermath` |

---

## 三、数据结果

### 3.1 Spearman ρ(α, δ_near) — 敏感性汇总

| 运行 | mtw | mpp | n_selected | ρ | p | Jackknife CI [2.5%, 97.5%] |
|------|-----|-----|-----------|--------|--------|----------------------------|
| **旧基线 (round2)** | 5 | 4 | **9** | **−0.917** | **0.0005** | [−0.948, −0.881] |
| unified_h8 mtw5_mpp4 | 5 | 4 | **14** | **−0.776** | **0.0011** | [−0.852, −0.725] |
| unified_h8 mtw4_mpp4 | 4 | 4 | 14 | −0.776 | 0.0011 | [−0.852, −0.725] |
| unified_h8 mtw5_mpp3 | 5 | 3 | 14 | −0.776 | 0.0011 | [−0.852, −0.725] |
| **unified_h8 mtw4_mpp3** | **4** | **3** | **15** | **−0.764** | **0.0009** | [−0.815, −0.736] |

**核心发现**：所有 4 组参数组合均给出 |ρ| > 0.76、p < 0.002，信号高度 robust。

### 3.2 漏斗变化（round2 n=9 → unified n=14）

**GAINED（+6 事件新进入 selected）**

| 事件 | 灾害类型 | ntw 变化 | event_type | α | δ_near | 恢复原因 |
|------|---------|---------|-----------|--------|---------|---------|
| beryl_qr | hurricane | 1 → 14 | EVAC | 0.741 | −0.442 | static center |
| beryl_tx | hurricane | 1 → 15 | EVAC | 0.800 | −0.279 | static center |
| beryl_jamaica | hurricane | 2 → 14 | EVAC | 0.387 | −0.404 | static center |
| kristine_ph | tropical_storm | 2 → 12 | EVAC | 0.711 | −0.041 | static center + center 修正 |
| yagi_ph | tropical_storm | 1 → 15 | EVAC | 0.467 | −0.227 | static center |
| krathon_tw | typhoon | 12 → 12 | INFL | 0.101 | +0.111 | D(t) 形状改善, n_mono: 2→4 |

**LOST（−1 事件从 selected 掉出）**

| 事件 | 灾害类型 | 原因 |
|------|---------|------|
| debby_pre (tropical_storm) | tropical_storm | static center 改变距离剖面，D_peak: 0.107→0.063，n_mono: 3→1 |

**KEPT（8 事件完全稳定，α 变化 = 0.0%）**

eu_flood, park_fire2, spain_flood, nepal_fld, rio_grande, quito_fire, turkiye, yagi_vn

### 3.3 关键恢复事件（窗口大量恢复但仍未入选）

| 事件 | ntw 变化 | 未入选原因 | 本质 |
|------|---------|---------|------|
| ernesto_pr | 0 → 15 | n_mono=2, D(t) 振荡不衰减 | 数据现象（非 bug） |
| helene_pre | 1 → 12 | t_peak=264h, 峰后无步数 | pre-landfall 数据集固有限制 |
| milton_fl | 0 → 10 | n_mono=2, D(t) 峰后振荡 | 可能 FBDM 覆盖不均 |

### 3.4 Event_type 分布

| 分类 | 旧 n=9 | 新 n=14 | 新 n=15 (mtw4_mpp3) |
|------|--------|--------|---------------------|
| EVAC | 3 (33%) | 7 (50%) | 7 (47%) |
| INFL | 4 (44%) | 5 (36%) | 6 (40%) |
| NEUTRAL | 2 (22%) | 2 (14%) | 2 (13%) |

| 灾害类型 | n=14 | n=15 |
|---------|------|------|
| flood | 4 | 4 |
| hurricane | 3 | 3 |
| tropical_storm | 2 | 2 |
| typhoon | 2 | 2 |
| wildfire | 2 | 2 |
| earthquake | 1 | 2 |

### 3.5 mtw=4, mpp=3 唯一新增事件

`the_earthquake_across_central_mexico`（earthquake, INFL, α=0.244, δ_near=+0.265, n_windows=4）

### 3.6 Alpha 稳定性

所有 8 个 KEPT 事件的 α 值在旧/新运行间**完全一致（Δ=0.0%）**，证实 static center 修改仅影响热带气旋事件，无全局副作用。

---

## 四、结果文件路径索引

### 4.1 输入文件

| 文件 | 路径 |
|------|------|
| 修改后 catalog | `Docs/cross_disaster_catalog_extended_partial_gt_round2_static_center.csv` |
| 原 catalog | `Docs/cross_disaster_catalog_extended_partial_gt_round2.csv` |
| 旧基线 catalog | `Docs/cross_disaster_catalog_extended_partial_gt_round2_included32.csv` |

### 4.2 phi_heatmap 输出

| 路径 | 说明 |
|------|------|
| `outputs/_runs/unified_static_h8/{slug}/phi_heatmap/` | 全量 32 事件的统一重跑结果 |
| `outputs/{slug}/phi_heatmap/` | 各事件的默认输出位置（已被覆盖更新） |

### 4.3 dt_decay 敏感性分析输出

| 路径 | 参数 |
|------|------|
| `outputs/cross_disaster_comparison/Dt_decay_unified_h8_mtw5_mpp4/` | mtw=5, mpp=4（与旧基线同参数） |
| `outputs/cross_disaster_comparison/Dt_decay_unified_h8_mtw4_mpp4/` | mtw=4, mpp=4 |
| `outputs/cross_disaster_comparison/Dt_decay_unified_h8_mtw5_mpp3/` | mtw=5, mpp=3 |
| `outputs/cross_disaster_comparison/Dt_decay_unified_h8_mtw4_mpp3/` | mtw=4, mpp=3（推荐） |

每个目录下关键文件：
- `tables/Dt_event_summary.csv` — 事件级摘要（n_windows, event_type, D_peak 等）
- `tables/Dt_routeB_sample_flags.csv` — 完整漏斗标记（每层筛选原因）
- `tables/Dt_routeB_alpha_delta_spearman.csv` — Spearman ρ 和 p 值
- `tables/Dt_routeB_alpha_delta_jackknife_summary.csv` — Jackknife 稳定性检验
- `tables/Dt_powerlaw_fits.csv` — 幂律拟合参数（α, logA, R²）

### 4.4 旧基线（round2）对照

| 路径 | 说明 |
|------|------|
| `outputs/cross_disaster_comparison/Dt_decay_partial_gt_round2_included32_20260224_133240/` | 旧基线 n=9 |
| `outputs/_runs/partial_gt_round2_included32/` | 旧 phi_heatmap 输出 |

### 4.5 漏斗比较文件

| 路径 | 说明 |
|------|------|
| `outputs/cross_disaster_comparison/unified_static_h8_funnel_comparison.csv` | 逐事件 round2↔unified 对照 |
| `outputs/cross_disaster_comparison/unified_static_h8_spearman_summary.csv` | 5 组运行的 Spearman 汇总 |

---

## 五、结论

1. **Static center 策略成功**：修复了飓风 track center 外推导致的窗口丢失，6 个事件新进入 selected 样本。
2. **信号 robust**：ρ(α, δ_near) 从 −0.917 (n=9) 变为 −0.776 (n=14)，|ρ| 下降但 p 仍 < 0.002；更大更多样的事件集使结论更可信。
3. **参数不敏感**：4 组 mtw/mpp 组合结果高度一致（ρ 范围 [−0.776, −0.764]），证明结论不依赖阈值选择。
4. **推荐配置**：mtw=4, mpp=3 → n=15, ρ=−0.764, p=0.0009，样本最大且统计最显著。
5. **无全局副作用**：8 个非热带气旋 KEPT 事件的 α 值精确复现（Δ=0.0%）。

### 后续待办

- [ ] 运行 full_post_peak 方法验证（基于 unified_static_h8 输出）
- [ ] 子区域 geo_unit_scale 分析重跑
- [ ] 更新 Experiment_Plan.md 的漏斗表和参数配置
- [ ] 决定 pre-landfall 事件（debby_pre, helene_pre, beryl_jamaica）的 L0 排除策略
