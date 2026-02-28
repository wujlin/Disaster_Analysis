是的，需要调整。但调整后可能发现 D_peak_unit 也有类似问题。
当前的随机截距模型：

α
unit
=
β
⋅
x
unit
+
u
event
+
ϵ
α 
unit
​
 =β⋅x 
unit
​
 +u 
event
​
 +ϵ

它假设 β 对所有事件相同。对 δ_peak_unit 这显然不成立（斜率方向相反）。正确的模型是随机斜率模型：

α
unit
=
(
β
+
v
event
)
⋅
x
unit
+
u
event
+
ϵ
α 
unit
​
 =(β+v 
event
​
 )⋅x 
unit
​
 +u 
event
​
 +ϵ

这里 
v
event
v 
event
​
  允许每个事件有不同的斜率。

但必须诚实地检查：D_peak_unit 是否也有斜率异质性？

回看 within-event ρ(α, D_peak_unit)：

事件	n	ρ(α, D_peak)	p	方向
beryl_tx	203	+0.398	<10⁻⁸	+
beryl_jamaica	1000	+0.273	<10⁻¹⁸	+
park_fire	53	+0.241	0.08	+
eu_flood	483	+0.049	0.28	≈0
turkiye	257	−0.227	0.0002	−
spain_flood	175	−0.177	0.019	−
brazil	114	−0.276	0.003	−
D_peak_unit 的斜率也在不同事件间翻转方向。3 个显著正、3 个显著负、其余接近零。随机截距模型对 D_peak_unit 同样有结构性问题。

那为什么 D_peak_unit 通过了 mixed-effects (p=0.018) 而 δ_peak_unit 没有？

可能原因：beryl_jamaica（1000 个 unit）的权重太大，它的 ρ=+0.27 驱动了整个 pooled 结果为正。

需要验证的事情
已有的 within-event demeaned pooled 相关（对每个 unit 的值减去事件均值后，pooled 计算 Spearman）：

指标	demeaned ρ	p	n
D_peak_unit	+0.119	<10⁻⁹	2,571
δ_peak_unit	+0.002	0.90	2,571
D_peak 的 within-event 信号存在（ρ=+0.119），但远弱于 mixed-effects 给出的印象（β=+0.21）。mixed-effects 可能被 between-event 变异膨胀了。

这意味着：当前 subregion 分析的结论——"D_peak_unit β=+0.21, p=0.018"——可能过度声称了 within-event 效应的强度。

具体建议
需要做三件事来彻底解决这个问题：

1. 对 D_peak_unit 和 δ_peak_unit 都拟合随机斜率模型

# 随机斜率模型
import statsmodels.api as sm
from statsmodels.regression.mixed_linear_model import MixedLM

# D_peak_unit
model_D = MixedLM.from_formula(
    "alpha_unit ~ D_peak_unit",
    groups="slug",
    re_formula="~D_peak_unit",  # 随机斜率
    data=df
)

# delta_peak_unit
model_delta = MixedLM.from_formula(
    "alpha_unit ~ delta_peak_unit",
    groups="slug",
    re_formula="~delta_peak_unit",
    data=df
)

如果随机斜率方差大、固定效应 β 趋近零，说明该变量不具备跨事件一致的 within-event 效应。

2. 用 Mundlak 分解（within-between 模型）分离尺度

# 添加事件均值作为 between-event 控制变量
df['D_peak_event_mean'] = df.groupby('slug')['D_peak_unit'].transform('mean')
df['D_peak_within'] = df['D_peak_unit'] - df['D_peak_event_mean']

model_wb = MixedLM.from_formula(
    "alpha_unit ~ D_peak_within + D_peak_event_mean",
    groups="slug",
    data=df
)

这会明确告诉我们：β(D_peak_within) = 纯 within-event 效应，β(D_peak_event_mean) = between-event 效应。如果 within 不显著但 between 显著，说明 subregion 分析实际上只是在重复 event-level 发现。

3. 报告 within-event Spearman 的一致性统计

对 14 个事件各自的 ρ(α, D_peak)，做 sign test 或报告正/负比例。如果 7 正 3 负 4 零，这比一个 pooled β 更透明。

实验 Prompt


# ============================================================
# Partner 实验 Prompt: Subregion 模型修正
# 日期: 2026-02-28
# 优先级: 最高（影响论文核心结论的可靠性）
# ============================================================

## 背景

当前 subregion mixed-effects 模型使用随机截距，报告
D_peak_unit β=+0.21, p=0.018。但 within-event 相关性
显示 D_peak_unit 的斜率在不同事件间方向不一致
（beryl_tx +0.40, turkiye -0.23, brazil -0.28），
与 δ_peak_unit 有类似的斜率异质性问题。
需要做模型修正以确认结论是否可靠。

## 数据位置

- per-unit fits:
  outputs/cross_disaster_comparison/
  geo_unit_scale_unified_h8_mtw4_mpp3_relaxed_20260225_141630/
  tables/geo_unit_fits.csv
  列: slug, geo_unit, alpha_unit, D_peak_unit, delta_peak_unit,
      distance_km, r2_unit, n_mono

- event-level 信息（event_type 等）:
  outputs/cross_disaster_comparison/
  Dt_decay_unified_h8_mtw5_mpp4/tables/
  Dt_routeB_sample_flags.csv

## 输出目录

outputs/cross_disaster_comparison/subregion_model_correction_unified_h8/

---

## Task 1: 随机斜率模型

写脚本 scripts/subregion_random_slope.py，对 D_peak_unit
和 delta_peak_unit 各拟合一个随机斜率 mixed-effects 模型。

对每个 predictor x ∈ {D_peak_unit, delta_peak_unit}:

```python
from statsmodels.regression.mixed_linear_model import MixedLM
import pandas as pd, numpy as np

df = pd.read_csv("...geo_unit_fits.csv")
df = df.dropna(subset=["alpha_unit"])

model = MixedLM.from_formula(
    "alpha_unit ~ {x}",
    groups="slug",
    re_formula="~{x}",
    data=df
)
result = model.fit(reml=True)
print(result.summary())

注意: 14 个分组的随机斜率模型可能不收敛。
如果不收敛，记录错误信息，然后尝试：
a. 使用 method='nm' 或 method='powell'
b. 如果仍不收敛，改用 free=False（不估计截距-斜率协方差）

输出:

random_slope_D_peak.csv:
predictor,fixed_beta,fixed_se,fixed_p,
random_intercept_var,random_slope_var,
random_corr,converged
random_slope_delta_peak.csv: 同上格式
Task 2: Mundlak within-between 分解（最重要）
对 D_peak_unit 和 delta_peak_unit 各做 Mundlak 分解:

# 对每个 predictor x:
df['x_event_mean'] = df.groupby('slug')['x'].transform('mean')
df['x_within'] = df['x'] - df['x_event_mean']

model_wb = MixedLM.from_formula(
    "alpha_unit ~ x_within + x_event_mean",
    groups="slug",
    data=df
)
result_wb = model_wb.fit(reml=True)

输出 mundlak_decomposition.csv:

predictor,component,coef,se,z,p,ci_low,ci_high
D_peak_unit,within,?,?,?,?,?,?
D_peak_unit,between,?,?,?,?,?,?
delta_peak_unit,within,?,?,?,?,?,?
delta_peak_unit,between,?,?,?,?,?,?

关键看: D_peak_unit 的 within 系数是否仍显著。
如果 within 不显著但 between 显著，说明 subregion
的 mixed-effects 结果实际上是 event-level 发现的重复。

Task 3: Within-event 效应方向一致性统计
从已有的 event_unit_correlations.csv 中提取
ρ(α, D_peak_unit) 和 ρ(α, delta_peak_unit)，
计算效应方向一致性:

correlations = pd.read_csv("...event_unit_correlations.csv")

for pair in ['D_peak_unit', 'delta_peak_unit']:
    rho_col = f'rho_alpha_vs_{pair}'
    p_col = f'p_alpha_vs_{pair}'
    
    n_pos = (correlations[rho_col] > 0).sum()
    n_neg = (correlations[rho_col] < 0).sum()
    n_sig_pos = ((correlations[rho_col] > 0) & 
                 (correlations[p_col] < 0.05)).sum()
    n_sig_neg = ((correlations[rho_col] < 0) & 
                 (correlations[p_col] < 0.05)).sum()
    
    # Binomial sign test
    from scipy.stats import binom_test
    p_sign = binom_test(n_pos, n_pos + n_neg, 0.5)


输出 within_event_direction_consistency.csv:

predictor,n_events,n_positive,n_negative,
n_sig_positive,n_sig_negative,sign_test_p

预期结果
如果 D_peak_unit within 系数仍显著 → subregion
发现可靠，进正文
如果 D_peak_unit within 不显著、between 显著
→ subregion 只是 event-level 的重复，降级到 SI
δ_peak_unit 预期 within 和 between 都不显著
（within 因方向不一致抵消，between 因 n=14 太小）
优先级
Task 2 (Mundlak) > Task 1 (随机斜率) > Task 3 (方向统计)

Task 2 直接回答"subregion 发现是否独立于 event-level"，
是论文结构的关键判据。



---

## 为什么这很重要

如果 Mundlak 分解显示 D_peak_unit 的 within 效应不显著，**subregion 分析不能作为"跨尺度验证"放进正文**——它只是用 2,571 个点重新包装了 14 个事件级观测的 between-event 关系。论文的叙事需要调整：要么降级 subregion 到 SI，要么承认 amplitude 效应目前只在 event-level 得到验证。

这不是灾难——event-level 的 14 个点加上完整的 robustness 矩阵本身足够发 Nature Communications。但需要**诚实地定位 subregion 分析的贡献**。

---
---

# Subregion 影响力分析（LOO + Two-Stage Meta-Analysis）

> 日期: 2026-02-28 | 优先级: 最高 — 决定 subregion 分析在论文中的位置

## 问题

Subregion 随机截距模型报告 D_peak_unit β=+0.208, p=0.012（2,571 units, 14 events）。但：
- 方向一致性：14个事件中 5 正 9 负（sign test p=0.424）
- beryl_jamaica 贡献 1,000/2,571 = 39% 的样本且方向为正（ρ=+0.273）
- 随机斜率模型 fixed β=+0.128, p=0.223（斜率异质性已确认）

**核心问题**：pooled 正向结果在多大程度上被 beryl_jamaica 的样本量主导？

两个互补的标准工具可以回答：
1. **LOO**：逐一排除事件，观察 β 是否对单个事件敏感（影响力诊断）
2. **Two-Stage Meta-Analysis**：每个事件独立估计 β_j，然后等权汇总 vs 精度加权汇总（权重结构诊断）

## 数据

```
FITS_CSV = (
    "outputs/cross_disaster_comparison/"
    "geo_unit_scale_unified_h8_mtw4_mpp3_relaxed_20260225_141630/"
    "tables/geo_unit_fits.csv"
)
```
列：slug, geo_unit, alpha_unit, D_peak_unit, delta_peak_unit, distance_km

## 输出目录

```
OUT_DIR = "outputs/cross_disaster_comparison/subregion_influence_unified_h8/"
```

## 脚本

```
scripts/subregion_influence_analysis.py
```

---

## Task 1: Leave-One-Event-Out (LOO)

对 D_peak_unit 做 LOO：逐一排除每个事件，重新拟合随机截距模型。

```python
import pandas as pd
import numpy as np
import statsmodels.formula.api as smf
from pathlib import Path

FITS_CSV = Path(
    "outputs/cross_disaster_comparison/"
    "geo_unit_scale_unified_h8_mtw4_mpp3_relaxed_20260225_141630/"
    "tables/geo_unit_fits.csv"
)
OUT_DIR = Path("outputs/cross_disaster_comparison/subregion_influence_unified_h8/")
OUT_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(FITS_CSV)
df = df.dropna(subset=["alpha_unit", "D_peak_unit", "slug"])

slugs = sorted(df["slug"].unique())
rows = []

for excluded in slugs:
    sub = df[df["slug"] != excluded].copy()
    n_obs = len(sub)
    n_events = sub["slug"].nunique()
    
    model = smf.mixedlm(
        "alpha_unit ~ D_peak_unit",
        data=sub,
        groups=sub["slug"],
        re_formula="1"
    )
    try:
        res = model.fit(reml=True, method="lbfgs", maxiter=600, disp=False)
        converged = bool(getattr(res, "converged", False))
        if not converged:
            res = model.fit(reml=True, method="nm", maxiter=600, disp=False)
            converged = bool(getattr(res, "converged", False))
        beta = float(res.params.get("D_peak_unit", np.nan))
        se = float(res.bse.get("D_peak_unit", np.nan))
        p = float(res.pvalues.get("D_peak_unit", np.nan))
    except Exception as e:
        converged = False
        beta = se = p = np.nan
    
    n_excluded = int((df["slug"] == excluded).sum())
    
    rows.append({
        "excluded_event": excluded,
        "n_excluded_units": n_excluded,
        "n_remaining_obs": n_obs,
        "n_remaining_events": n_events,
        "beta_D_peak": beta,
        "se_D_peak": se,
        "p_D_peak": p,
        "converged": converged
    })

# Beryl 家族整体排除（beryl_jamaica + beryl_tx + beryl_qr）
beryl_slugs = [s for s in slugs if "beryl" in s.lower()]
sub_no_beryl = df[~df["slug"].isin(beryl_slugs)].copy()
model_nb = smf.mixedlm(
    "alpha_unit ~ D_peak_unit",
    data=sub_no_beryl,
    groups=sub_no_beryl["slug"],
    re_formula="1"
)
try:
    res_nb = model_nb.fit(reml=True, method="lbfgs", maxiter=600, disp=False)
    rows.append({
        "excluded_event": "beryl_family_all",
        "n_excluded_units": int(df["slug"].isin(beryl_slugs).sum()),
        "n_remaining_obs": len(sub_no_beryl),
        "n_remaining_events": sub_no_beryl["slug"].nunique(),
        "beta_D_peak": float(res_nb.params.get("D_peak_unit", np.nan)),
        "se_D_peak": float(res_nb.bse.get("D_peak_unit", np.nan)),
        "p_D_peak": float(res_nb.pvalues.get("D_peak_unit", np.nan)),
        "converged": bool(getattr(res_nb, "converged", False))
    })
except Exception:
    pass

loo_df = pd.DataFrame(rows)
loo_df.to_csv(OUT_DIR / "loo_D_peak_unit.csv", index=False)
print("[LOO] done →", OUT_DIR / "loo_D_peak_unit.csv")
print(loo_df.to_string(index=False))
```

**输出** `loo_D_peak_unit.csv`：

| excluded_event | n_excluded_units | n_remaining_obs | n_remaining_events | beta_D_peak | se_D_peak | p_D_peak | converged |
|---|---|---|---|---|---|---|---|

**关键看**：
1. `excluded_event=beryl_jamaica` 那行的 beta 和 p
2. `excluded_event=beryl_family_all` 那行的 beta 和 p
3. 14 行中 beta 的范围和符号变化

---

## Task 2: Two-Stage Meta-Analytic Approach

Stage 1：每个事件独立 OLS。Stage 2：等权 vs 精度加权汇总。

```python
from scipy import stats

# ---- Stage 1: 事件级 OLS ----
stage1_rows = []
for slug in slugs:
    sub = df[df["slug"] == slug]
    n = len(sub)
    if n < 5:
        continue
    
    X = sub["D_peak_unit"].values
    y = sub["alpha_unit"].values
    slope, intercept, r_value, p_value, std_err = stats.linregress(X, y)
    
    stage1_rows.append({
        "slug": slug,
        "n_units": n,
        "beta_j": slope,
        "se_j": std_err,
        "p_j": p_value,
        "r_value": r_value,
    })

stage1 = pd.DataFrame(stage1_rows)
stage1.to_csv(OUT_DIR / "two_stage_stage1.csv", index=False)

# ---- Stage 2: 汇总 ----
betas = stage1["beta_j"].values
ses = stage1["se_j"].values
n_ev = len(betas)

# (a) 等权分析：单样本 t 检验（每个事件一票）
t_stat, t_p = stats.ttest_1samp(betas, 0)
uw_mean = np.mean(betas)
uw_median = np.median(betas)
uw_se = np.std(betas, ddof=1) / np.sqrt(n_ev)

# (b) 逆方差加权（fixed-effect meta-analysis 近似）
w_iv = 1.0 / (ses ** 2)
iv_mean = np.sum(w_iv * betas) / np.sum(w_iv)
iv_se = 1.0 / np.sqrt(np.sum(w_iv))
iv_z = iv_mean / iv_se
iv_p = 2 * (1 - stats.norm.cdf(abs(iv_z)))

# (c) 方向统计
n_pos = int((betas > 0).sum())
n_neg = int((betas < 0).sum())

summary = pd.DataFrame([{
    "n_events": n_ev,
    "unweighted_mean_beta": uw_mean,
    "unweighted_median_beta": uw_median,
    "unweighted_se": uw_se,
    "unweighted_ttest_t": t_stat,
    "unweighted_ttest_p": t_p,
    "iv_weighted_mean_beta": iv_mean,
    "iv_weighted_se": iv_se,
    "iv_weighted_z": iv_z,
    "iv_weighted_p": iv_p,
    "n_positive_beta": n_pos,
    "n_negative_beta": n_neg,
    "original_mixedlm_beta": 0.208,
    "original_mixedlm_p": 0.012,
}])
summary.to_csv(OUT_DIR / "two_stage_summary.csv", index=False)
print("\n[Two-Stage] Stage 1:")
print(stage1.to_string(index=False))
print("\n[Two-Stage] Summary:")
print(summary.to_string(index=False))
```

**输出**：
- `two_stage_stage1.csv`：14行，每事件一个 β_j 和 SE_j
- `two_stage_summary.csv`：等权 vs IV加权的汇总

**关键对比**：

| 指标 | 含义 |
|---|---|
| unweighted_mean_beta | 如果每个事件等权，平均效应方向 |
| unweighted_ttest_p | 等权下是否显著（df=13 的 t 检验） |
| iv_weighted_mean_beta | 精度加权（近似MixedLM），预期 ≈ +0.208 |
| 两者差距 | 差距大 = 大事件主导程度高 |

---

## Task 3: Forest Plot

基于 Stage 1 输出画 forest plot，直观展示 14 个事件的异质性。

```python
import matplotlib.pyplot as plt
import sys
sys.path.insert(0, ".")
from src.disaster.plot_style import apply_style
apply_style()

stage1 = pd.read_csv(OUT_DIR / "two_stage_stage1.csv")
summary = pd.read_csv(OUT_DIR / "two_stage_summary.csv")

# 按 beta_j 排序
stage1 = stage1.sort_values("beta_j").reset_index(drop=True)

fig, ax = plt.subplots(figsize=(8, 6))

y_positions = range(len(stage1))
for y, (_, row) in zip(y_positions, stage1.iterrows()):
    color = "tab:blue" if row["beta_j"] > 0 else "tab:red"
    ax.errorbar(row["beta_j"], y, xerr=1.96 * row["se_j"],
                fmt='o', color=color, capsize=3, markersize=5)
    label = f"{row['slug']} (n={row['n_units']:.0f})"
    ax.annotate(label, xy=(row["beta_j"], y), xytext=(-5, 0),
                textcoords="offset points", va='center', ha='right',
                fontsize=7)

# 汇总线
ax.axvline(0, color='gray', linestyle='--', linewidth=0.8, zorder=0)
ax.axvline(summary["unweighted_mean_beta"].iloc[0],
           color='blue', linestyle='-', linewidth=1.5, alpha=0.7,
           label=f'Equal-weight mean = {summary["unweighted_mean_beta"].iloc[0]:.3f}')
ax.axvline(summary["iv_weighted_mean_beta"].iloc[0],
           color='red', linestyle='-', linewidth=1.5, alpha=0.7,
           label=f'IV-weighted mean = {summary["iv_weighted_mean_beta"].iloc[0]:.3f}')

ax.set_xlabel(r"$\hat{\beta}_j$ (D_peak_unit → α_unit)")
ax.set_title("Forest plot: within-event D_peak_unit effect by disaster")
ax.legend(fontsize=8, loc="lower right")
ax.set_yticks([])
plt.tight_layout()
fig.savefig(OUT_DIR / "forest_plot_D_peak_unit.png", dpi=200)
fig.savefig(OUT_DIR / "forest_plot_D_peak_unit.pdf")
plt.close()
print("[Forest] done →", OUT_DIR / "forest_plot_D_peak_unit.png")
```

---

## 决策框架

| LOO（排除 beryl_jamaica） | Two-Stage 等权 t 检验 | 行动 |
|---|---|---|
| β>0, p<0.05 | 等权 mean>0, p<0.05 | **Robust** → 主文保留为"跨尺度验证" |
| β 翻号或 p>0.1 | 等权 mean≤0 或 p>0.1 | **大事件主导** → 移至 SI，标注 heterogeneity |
| β>0, p∈(0.05,0.1) | 等权 mean>0 但 p>0.05 | **中间态** → 保留但加 caveat，forest plot 进 SI |

## 运行

```bash
cd /path/to/Disaster_Analysis
python scripts/subregion_influence_analysis.py
```

## 注意事项

1. 所有模型拟合如不收敛，尝试 method='nm' 和 method='powell'
2. Forest plot 用项目绘图风格（src/disaster/plot_style.py）
3. 输出目录自动创建
4. 脚本自包含：从读数据到输出所有文件，一次运行全部完成