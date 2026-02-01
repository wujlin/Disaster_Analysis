# Business Activity Recovery by Distance

用途：作为独立经济 proxy，检验 population 侧的空间恢复模式是否可复现。

## 输入

- `Data/Turkiye Turkey Earthquake Full Country Version Feb 8 2023/business activity/**/*.csv`

## 口径

- business_vertical = `all`
- activity 指标：`activity_quantile`（文档定义为相对 baseline 的 quantile；0.5≈正常）
- 距离：polygon centroid (lat/lon) → 震中

## 输出

- `tables/business_activity_by_band.csv`
- `tables/business_activity_tau_by_band.csv`（对 band-level mean(activity) 做线性化指数拟合）
- `figures/business_activity_timeseries.*`
