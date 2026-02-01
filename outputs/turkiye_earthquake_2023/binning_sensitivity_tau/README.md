# Binning Sensitivity (tile-level $\tau_i$)

目的：验证“50–100km 恢复最快”是否只是人为分箱产物。
方法：在 `base=[25.0, 50.0, 100.0, 200.0]` 的基础上对边界做 log-normal jitter，重复 200 次。
每个 scheme 用各 bin 内 **median $\tau_i$** 找 winner bin，并统计 winner 的距离分布。

## 输入

- `outputs/turkiye_earthquake_2023/tau_continuous_fit/tables/tile_level_tau.csv`（来自 `scripts/tau_continuous_fit.py` 的 `tile_level_tau.csv`）

## 输出

- `tables/binning_sensitivity_winner_bins.csv`
- `figures/winner_mid_distance_hist.*`
