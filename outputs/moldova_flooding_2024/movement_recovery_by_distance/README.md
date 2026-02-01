# Movement Recovery by Distance (08:00 windows)

用途：验证“通达性/交通受阻（假说 B）”的外部证据。

## 输入

- `Data/Moldova Flooding Sept 16 2024/movement/*.csv`

## 口径

- 仅使用 PT 08:00 窗口
- outflow：按 start tile 到震中距离分带
- inflow：按 end tile 到震中距离分带
- 仅保留 baseline 与 crisis 同时非空的 OD（overlap edges）
    - 统计：$\phi_{agg}=\sum n_{crisis}/\sum n_{baseline}$

## 输出

- `tables/movement_outflow_by_band.csv`
- `tables/movement_inflow_by_band.csv`
    - `tables/movement_tau_by_band.csv`（对 band-level $\phi_{agg}(t)$ 做线性化指数拟合）
- `figures/movement_outflow_phi_timeseries.*`
- `figures/movement_inflow_phi_timeseries.*`
