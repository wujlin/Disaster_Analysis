# 新 n=18 口径 robustness 重跑摘要

## 输入口径
- dt: `outputs/cross_disaster_comparison/Dt_decay_unified_static_h8_gtfix_mtw5_mpp4`
- subregion: `outputs/cross_disaster_comparison/geo_unit_scale_unified_static_h8_gtfix_mtw5_mpp4`

## 1) Event-level（dt）
- ρ(α, δ_near) = -0.694530, p = 0.001382, n = 18
- 选中/作图: 18/16
- 未选中类型: data_quality=6, analysis_applicability=6

## 2) Subregion diagnostic
- Random Intercept: β(D_peak_unit) = 0.205433, p = 0.010370
- Random Slope: beta=0.122, p=0.2012
- Two-stage meta (equal-weight): beta = -0.346919, p = 0.303516

## 3) Data collapse（subregion）
- all_events: Q_global=0.7522, Q_within=0.3290, beta_master=0.2601, R2_master=0.8717, units=1210, events=16
- excl_earthquake: Q_global=0.7807, Q_within=0.3914, beta_master=0.3094, R2_master=0.8622, units=1069, events=15

## 4) Gao baseline 三模型
- Winner counts: Power Law=5, Exponential=6, Stretched Exp=7
- M1 vs M2 (PL-EXP) 平均ΔBIC = 2.284775

## 5) PDE 参数重估
- global fit: k0=0.032509, gamma=1.065814e-14, R2_total=-0.359574
- ΔBIC(ODE-PL)=-20.212245, ΔBIC(ODE-null)=5.389072
- LOO: gamma>0 folds = 18/18
