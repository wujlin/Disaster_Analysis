Partner Prompt: 参数整理 + 三 Batch 全量重跑
一、背景与目标
我们的核心发现（event-level α vs δ_near）在新数据上崩溃了（ρ 从 −0.53 变成 +0.04），根因是 pipeline 中存在大量隐式决策（auto-inferred t₀/center、15 个硬编码阈值、单调截断策略）。这次重跑的目标不是"让结果变好"，而是建立一条可解释、可复现、对阈值选择不敏感的分析管线。

二、任务 A：参数整理
A1. 创建统一配置文件
新建 Docs/analysis_config.yaml（或 .json），集中管理所有分析参数。结构建议：

# ── 空间范围 ──
r_max_km: 200          # D(t) 汇总的最大距离
near_r_km: 50          # δ_near 近场定义半径
min_tiles_per_bin: 3   # 每个环带最少 tile 数
min_r_bins_per_step: 5 # 每个时间步最少环带数

# ── 时间范围 ──
t_fit_start_hours: 24  # post-peak 拟合起点

# ── 拟合策略 ──
fit_method: "full_post_peak"  # "full_post_peak" | "monotone_truncated"
# 如果 fit_method == "monotone_truncated"，以下才生效：
mono_tol_up: 1.05
min_n_mono: 3

# ── 事件筛选（仅数据质量） ──
min_post_peak_steps: 4   # post-peak 至少 N 个时间步才拟合
# 注意：不再使用 D_peak_min 硬阈值，改为信噪比标准（见下）
snr_threshold: null       # 如需启用：D_peak / std(D_baseline) >= k

# ── 以下参数已废弃，不再使用 ──
# near_thresh: 0.02      → 删除（EVAC/INFL 分类改为描述性语言，不参与统计）
# peak_frac: 0.5         → 删除（δ_near 只在 peak 时刻计算）
# r2_plot_threshold: 0.6 → 删除（移到绑图脚本内）
# route_b_exclude_slugs  → 删除（排除理由写入 catalog 的 exclude_reason 列）
# high_freq_thresh: 16   → 删除（统一用 only_hour=8）

A2. 修改 dt_decay.py 的入口
入口函数从函数签名读取参数 → 改为从 config 文件读取
运行时自动将完整 config dump 到 outputs/.../metadata.json
关键：禁用所有 auto-fallback。 如果某事件的 t₀ 或 center 在 catalog 中为空，直接报错 raise ValueError(f"{slug}: t0/center missing in catalog")，不再静默推断
A3. 事件 catalog 整理
在 cross_disaster_catalog_routeB16_frozen.csv（或新建一份干净的 catalog）中：

为每个事件补全 t0_pt 和 center_lat/center_lon，附上外部来源
新增以下列：
t0_source: 如 "USGS event page", "NHC advisory #12", "首个 FBDM 窗口"
center_source: 如 "USGS epicenter", "NHC best track landfall", "FBDM |n_diff| weighted centroid"
exclude_reason: 空 = 不排除；非空 = 排除理由（如 "aftermath event, non-independent from melissa_10_27"）
目标：catalog 中零个缺失字段。 每个值都有明确来源
三、任务 B：全段拟合 vs 截断拟合对比实验
这是最关键的方法学决策。在做全量重跑之前，先用当前 13 个 Route B 事件做一个轻量对比：

B1. 实验设计
对每个事件，用相同的 post-peak 数据（
t
′
≥
24
h
t 
′
 ≥24h 到观测结束）分别计算：

方法	数据段	拟合方式
α_mono	单调截断段（当前逻辑，tol=1.05）	log-log OLS
α_full	全部 post-peak（不截断）	log-log OLS
α_full_wls	全部 post-peak（不截断）	加权 log-log（权重 
1
/
t
′
1/t 
′
 ，给早期数据更多权重）
B2. 输出
生成一张对比表 outputs/.../alpha_truncation_comparison.csv：

slug, alpha_mono, n_mono, alpha_full, n_full, alpha_full_wls, r2_mono, r2_full, r2_full_wls

加上汇总统计：

Pearson(α_mono, α_full), Pearson(α_mono, α_full_wls)
符号翻转的事件数
最大绝对差异
B3. 决策规则
如果 Pearson(α_mono, α_full) > 0.90 且零符号翻转 → 采用 α_full，删除截断逻辑
如果差异大 → 检查哪些事件差异最大，分析原因（是否有明显的 rebound？rebound 是真实物理还是噪声？）
四、任务 C：三 Batch 全量重跑
在 A 和 B 完成后，用整理好的 config + 干净 catalog + 确定的拟合策略，重跑完整分析。

C1. 运行顺序1. 主分析（event-level）
   scripts/dt_decay.py --config Docs/analysis_config.yaml --catalog <干净catalog>
   → 输出：Dt_all_events.csv, sample_flags.csv, alpha_delta_spearman.csv

2. 子区域分析（geo-unit L10）
   scripts/geo_unit_analysis.py --config ... --catalog ...
   → 输出：pooled_correlations.csv, mixed_effects.csv

3. 子区域分析（geo-unit L8，作为 sensitivity）
   同上，quadkey_level=8

4. PDE 实验（如果子区域结果成立）
   后续再定
C2. 核心输出检查清单
重跑完成后，提供以下诊断表：

检查项	文件	关注什么
事件入选流水	sample_flags.csv	多少事件通过每一步筛选？与旧结果差异？
Event-level α vs δ_near	alpha_delta_spearman.csv	ρ, p, n
Event-level α vs D_peak	同上或新表	ρ, p, n
Event-level α vs D_inf	alpha_dinf_spearman.csv	ρ, p, n
Geo-unit mixed-effects	mixed_effects_alpha_unit.csv	β(δ_peak_unit), z, p
Geo-unit pooled + demeaned	pooled_unit_correlations.csv	ρ, p（raw + within-event）
Config 快照	metadata.json	确认所有参数与 config 一致

C3. Sensitivity analysis（如果核心结果成立）
对 5 个保留参数做 
3
2
3 
2
 （先做最重要的两个）的 sensitivity：

参数	扫描值
near_r_km	30, 50, 80
r_max_km	150, 200, 300
共 9 种组合，对每种重跑 geo-unit mixed-effects，输出 β 和 p 的 9 格表。如果时间允许再加 t_fit_start ∈ {16, 24, 48} 和 min_tiles ∈ {3, 5} 扩展到更多组合。

五、注意事项
不要追求"让 event-level ρ 变显著"。 如果 n=13 的事件级信号不稳健，那就是不稳健——我们转向子区域分析不是因为它"更好看"，而是因为它有 ~1800 个数据点和 mixed-effects 控制，统计上更可靠
每步都保留完整中间输出。 不要只存最终表，把 D(t) 时间序列、逐事件的拟合曲线都存下来，方便事后诊断
如果发现新的 auto-fallback 或 magic number，直接在 config 里加参数并标注，不要在代码里硬编码新的默认值
Catalog 中的 exclude_reason 只能基于数据质量或物理理由（如"非独立事件"、"多阶段洪水"），不能基于"排除后 p 值变小"