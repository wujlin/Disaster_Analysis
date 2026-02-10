# Partner 分析 Prompt: D(t) 衰减标度律与跨灾难普适性

## 一、背景与核心发现

我们对 14 个已分析事件的原始 δ(r,t) 数据做了 **SVD-free** 的直接诊断，发现了一个比 SVD 分析更清晰、更 robust 的信号：

### 新指标: 总扰动振幅 D(t)

$$D(t) = \frac{1}{N_r}\sum_{r \leq 200\text{km}} |\delta(r,t)|, \quad \delta = \phi_{\text{overlap}} - 1$$

- 不依赖 SVD 分解，直接从原始数据计算
- 物理含义：t 时刻整个近场区域的人口偏离基线的平均程度
- D(t) 从灾难冲击时达到峰值 $D_{\text{peak}}$，然后衰减 → **弛豫过程**

### 关键发现: 两类事件，两种衰减速率

对每个事件取 **post-peak 单调衰减段**（首次反弹即截断），拟合 power-law $D(t')/D_{\text{peak}} \sim t'^{-\alpha}$：

| 类型 | 事件 | 灾难 | α | R² | 衰减段 |
|:---:|:---|:---|:---:|:---:|:---|
| **EVAC** | Nepal Flood | 洪水 | 1.135 | 0.939 | [24, 120]h |
| **EVAC** | Yagi VN | 台风 | 0.833 | 0.997 | [24, 120]h |
| **EVAC** | Beryl TX | 飓风 | 0.647 | 0.982 | [24, 144]h |
| **EVAC** | Beryl QR | 飓风 | 0.594 | 0.897 | [24, 120]h |
| **EVAC** | Gujarat Flood | 洪水 | 0.161 | 0.715 | [24, 144]h |
| **INFL** | Beryl Pre | 飓风 | 0.425 | 0.913 | [24, 144]h |
| **INFL** | Turkiye | 地震 | 0.223 | 0.959 | [24, 96]h |
| **INFL** | Milton | 飓风 | 0.209 | 0.630 | [24, 72]h |
| **INFL** | Bangladesh Flood | 洪水 | 0.169 | 0.722 | [24, 120]h |
| **INFL** | John SM | 飓风 | 0.082 | 0.624 | [24, 72]h |

**统计检验**:
- $\alpha_{\text{EVAC}} = 0.674 \pm 0.356$ vs $\alpha_{\text{INFL}} = 0.222 \pm 0.126$
- Mann-Whitney U: p = 0.048 (显著)
- Cohen's d = 1.69 (极大效应量)
- η² = 0.472 → 事件类型解释了 47% 的 α 方差

### EVAC/INFL 分类标准

基于 D > 0.5×D_peak 时间窗口内的近场 (r ≤ 50km) 平均 δ：
- **EVAC** (疏散型): δ_near < −0.02 → 近场人口减少
- **INFL** (涌入型): δ_near > +0.02 → 近场人口增加

### BIC 模型比较

power-law 是 12/14 事件的 BIC 最优模型 (vs exponential, stretched_exp)。
但 4/14 事件存在多模型不可区分 (ΔBIC < 2)。

---

## 二、需要执行的任务

### Task 1: 全事件 D(t) 计算与分类

**目标**: 对 outputs/ 下 **全部 27 个事件** 计算 D(t)，分类 EVAC/INFL。

**输入数据**: `outputs/{slug}/phi_heatmap/tables/phi_rt_long.csv`
- 必须用 long format，不要用 matrix format（Turkiye 等事件的 matrix 全是 NaN）

**计算步骤**:
```python
# 对每个事件:
df = pd.read_csv(phi_rt_long_path)
df = df[(df['r_bin_km'] <= 200) & (df['n_tiles_overlap'] >= 3)]
df = df.dropna(subset=['phi_overlap'])
df['delta'] = df['phi_overlap'] - 1.0

# 每个时间窗口计算 D 和 near_delta
for t, grp in df.groupby('hours_since_quake'):
    if len(grp) >= 5:  # 至少 5 个径向 bin
        D = np.mean(np.abs(grp['delta']))
        near = grp[grp['r_bin_km'] <= 50]['delta']
        near_delta = near.mean() if len(near) >= 2 else np.nan
```

**分类**: 取 D > 0.5 × D_peak 的时间窗口，计算 near_delta 均值：
- < −0.02 → EVAC
- > +0.02 → INFL

**排除标准**: 
- n_time_windows < 5 的事件排除 (如 Colombia flood 只有 1 个窗口)
- D_peak < 0.03 的事件标记为 "LOW_SIGNAL"

**输出**: `outputs/cross_disaster_comparison/Dt_decay/tables/Dt_all_events.csv`
- 列: slug, short_name, disaster_type, t_hours, D, D_norm (=D/D_peak), near_delta, event_type (EVAC/INFL/LOW_SIGNAL)

### Task 2: 单调衰减段识别与 power-law 拟合

**目标**: 对每个事件识别 post-peak 单调衰减段，拟合 $D/D_{\text{peak}} = A \cdot t'^{-\alpha}$。

**单调衰减段定义**:
1. 找到 D(t) 的全局最大值点 → t_peak, D_peak
2. 取 post-peak 数据 (t > t_peak)
3. 从 peak 后第一个点开始，向后扫描：
   - 如果 D(t_{i+1}) ≤ D(t_i) × 1.05 → 继续（允许 5% 波动）
   - 否则 → 截断
4. 截断后的段 = 单调衰减段 (monotone decay segment)

**拟合**: log(D/D_peak) vs log(t − t_peak), OLS 线性回归
- α = −slope
- 报告 R²
- 最少需要 3 个数据点

**输出**: `outputs/cross_disaster_comparison/Dt_decay/tables/Dt_powerlaw_fits.csv`
- 列: slug, short_name, disaster_type, event_type, D_peak, t_peak_hours, n_mono, n_total_post, alpha, r2, t_decay_start, t_decay_end

### Task 3: 三模型 BIC 比较

**目标**: 对 **整段 post-peak 数据**（不截断）做三模型 BIC 比较。

三个模型:
1. **Power-law**: $D/D_{\text{peak}} = A \cdot t'^{-\alpha}$ (2 参数)
2. **Exponential**: $D/D_{\text{peak}} = A \cdot e^{-t'/\tau}$ (2 参数)
3. **Stretched exponential**: $D/D_{\text{peak}} = A \cdot e^{-(t'/\tau)^\beta}$ (3 参数)

BIC 计算:
$$\text{BIC} = n \ln(\hat{\sigma}^2) + k \ln(n)$$
其中 $\hat{\sigma}^2 = \frac{1}{n}\sum_i (y_i - \hat{y}_i)^2$, k = 参数数量。

**注意**: 
- Power-law 在 real space 拟合（不是 log space），即最小化 Σ(D_obs − A·t'^(-α))²
- 用 scipy.optimize.curve_fit，bounds: A∈[0,5], α∈[-1,3], τ∈[1,2000], β∈[0.01,3]

**输出**: `outputs/cross_disaster_comparison/Dt_decay/tables/Dt_model_bic.csv`
- 列: slug, event_type, n_pts, best_model, BIC_power, BIC_exp, BIC_strexp, ΔBIC_power, ΔBIC_exp, ΔBIC_strexp, alpha_power, tau_exp, tau_strexp, beta_strexp

### Task 4: 数据坍缩 (Data Collapse)

**目标**: 检验 D(t')/D_peak 是否能通过事件特定的时间尺度 τ 坍缩到统一曲线。

**步骤**:
1. 对每个事件定义 τ_50 = D(t') 第一次降至 0.5 × D_peak 的时间
   - 如果观测窗口内 D 从未降至 0.5 以下 → τ_50 = t_max (标记为 "lower_bound")
2. 计算归一化时间 $\tilde{t} = t'/\tau_{50}$
3. 画 D/D_peak vs $\tilde{t}$ 的散点图（所有事件重叠）
4. 分 bin 计算 CV (变异系数):
   - bins: [0, 0.5], [0.5, 1.0], [1.0, 1.5], [1.5, 2.0], [2.0, 2.5], [2.5, 3.0]
   - 每个 bin 需要 ≥ 3 个事件

**坍缩质量判定**:
- CV < 0.3 → ✅ 良好坍缩
- CV 0.3–0.5 → ⚠️ 中等
- CV > 0.5 → ❌ 未坍缩

**分组画图**:
- 全部事件
- EVAC only
- INFL only

**输出**:
- 表: `outputs/cross_disaster_comparison/Dt_decay/tables/Dt_collapse_quality.csv`
- 图: `outputs/cross_disaster_comparison/Dt_decay/figures/Dt_collapse_all.png`
- 图: `outputs/cross_disaster_comparison/Dt_decay/figures/Dt_collapse_by_type.png`

### Task 5: 可视化

需要生成以下图:

**Fig 1: D(t)/D_peak 时间序列 (所有事件)**
- 每个事件一条线，颜色区分 EVAC (红) / INFL (蓝)
- x 轴: t − t_peak (hours), y 轴: D/D_peak
- Log-log 坐标
- 叠加 best-fit power-law 线
- `Dt_decay_all_events_loglog.png`

**Fig 2: α 分布对比**
- 左: EVAC vs INFL 的 α 箱线图 + strip plot
- 右: α vs D_peak 散点图（颜色区分类型，标注事件名）
- `Dt_alpha_comparison.png`

**Fig 3: 数据坍缩图** (Task 4 已包含)

**Fig 4: D(t) 完整时间序列 (绝对值, 线性坐标)**
- 每个事件一个小面板 (4×5 或 3×6 grid)
- 标注 peak 位置和单调衰减段
- 颜色: EVAC 红 / INFL 蓝
- `Dt_timeseries_panels.png`

---

## 三、事件完整清单

### 已完成初步分析 (14 个):

| 简称 | slug | 类型 | 灾难 |
|:---|:---|:---:|:---|
| beryl_tx | hurricane_beryl_across_southeastern_texas_us | EVAC | 飓风 |
| beryl_qr | hurricane_beryl_across_quintana_roo_and_yucatan_mexico | EVAC | 飓风 |
| beryl_pre | hurricane_beryl_pre_landfall_2024 | INFL | 飓风 |
| ernesto | hurricane_ernesto_puerto_rico_14_august_2024 | INFL | 飓风 |
| john_sm | hurricane_john_southern_mexico_25_september_2024 | INFL | 飓风 |
| milton | hurricane_milton_across_florida_us | INFL | 飓风 |
| debby | tropical_storm_debby_united_states_pre_landfall_4_august_2024 | INFL | 热带风暴 |
| krathon | typhoon_krathon_across_taiwan | INFL | 台风 |
| yagi_vn | typhoon_yagi_across_northeastern_vietnam | EVAC | 台风 |
| turkiye | turkiye_earthquake_2023 | INFL | 地震 |
| nepal_fld | the_flooding_across_bagmati_and_koshi_provinces_nepal | EVAC | 洪水 |
| gujarat_fld | the_flooding_across_gujarat_india | EVAC | 洪水 |
| quito_fire | the_wildfires_in_quito_pichincha_province_ecuador | EVAC | 山火 |
| bangladesh | the_flooding_across_eastern_bangladesh | INFL | 洪水 |

### 需要新纳入分析 (12 个):

| 简称 | slug | n_windows | 预期类型 |
|:---|:---|:---:|:---:|
| moldova | moldova_flooding_2024 | 28 | INFL |
| park_fire1 | park_fire_2024 | 17 | INFL |
| helene_pre | hurricane_helene_pre_landfall_gulf_of_mexico_24_september_2024 | 15 | INFL |
| line_fire | line_fire_southern_california_9_september_2024 | 15 | INFL |
| park_fire2 | park_fire_california_29_july_2024 | 15 | INFL |
| yagi_ph | tropical_storm_yagi_philippines_2_september_2024 | 15 | EVAC |
| boise_fire | wildfires_in_boise_county_idaho_27_august_2024 | 15 | INFL |
| guinea_fld | the_flooding_in_conakry_city_conakry_guinea | 13 | INFL |
| enteng | tropical_storm_enteng_across_luzon_and_visayas_islands_philippines | 12 | EVAC |
| kristine | tropical_storm_kristine_in_bicol_and_calabarzon_philippines | 12 | INFL |
| john_gue | hurricane_john_across_southeastern_guerrero_mexico | 7 | INFL |
| nigeria_fld | the_flooding_in_benue_and_kogi_states_nigeria | 7 | INFL |

**排除**: colombia_flood (仅 1 个时间窗口)

---

## 四、技术要点

1. **必须用 phi_rt_long.csv**，不要用 phi_rt_matrix.csv（Turkiye 等事件 matrix 全 NaN）
2. **r_max = 200km**，n_tiles_overlap ≥ 3 的质量过滤
3. **时间单位**: hours_since_quake 列（8 小时间隔）
4. **Power-law α 不是全局普适的**: EVAC 和 INFL 有显著不同的 α
5. **单调衰减段的识别至关重要**: 很多事件有双峰结构（Nepal = 洪水第二波，Bangladesh = 二次冲击），如果把反弹段也纳入拟合，α 和 R² 都会严重失真
6. **绘图风格**: 遵循 `Docs/visual_style_guide.md` 和 `plot_style.py`

---

## 五、输出目录结构

```
outputs/cross_disaster_comparison/Dt_decay/
├── tables/
│   ├── Dt_all_events.csv          # Task 1
│   ├── Dt_powerlaw_fits.csv       # Task 2
│   ├── Dt_model_bic.csv           # Task 3
│   └── Dt_collapse_quality.csv    # Task 4
└── figures/
    ├── Dt_decay_all_events_loglog.png    # Fig 1
    ├── Dt_alpha_comparison.png           # Fig 2
    ├── Dt_collapse_all.png               # Fig 3a
    ├── Dt_collapse_by_type.png           # Fig 3b
    └── Dt_timeseries_panels.png          # Fig 4
```

---

## 六、预期结论与 story

### 如果结果符合预期:
> 灾难人口响应的弛豫遵循 power-law 衰减 $D(t') \sim t'^{-\alpha}$。疏散型事件 (α ≈ 0.7) 的恢复显著快于涌入型事件 (α ≈ 0.2)，这一分叉跨越了飓风、台风、洪水、地震和山火五类灾难。事件类型（EVAC/INFL）是决定恢复速度的首要因素（η² ≈ 0.47），而非灾难种类本身。

### 需要警惕的风险:
1. **EVAC 内 α 变异大** (CV ≈ 53%): Gujarat (α=0.16) 是异常值，需要理解原因
2. **Nepal 双峰结构**: 第一波衰减后有第二波，如果不正确截断会污染拟合
3. **样本量**: EVAC 仅 5-7 个事件，统计力有限
4. **数据坍缩质量**: 初步测试 CV 在 0.2-0.5 之间，不是完美坍缩
