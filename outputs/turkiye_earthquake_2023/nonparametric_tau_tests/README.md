# Non-parametric Tests (tile-level)

对应 PI 的“统计显著性/稳健性”要求：

1) τ 排序显著性：相邻距离范围的 median(τ) 差异 + bootstrap CI + permutation test
2) 假说 B vs A/C（代理）：tile 可见性恢复是否显著快于强度恢复（paired sign-flip permutation）

## 输入

- `outputs/turkiye_earthquake_2023/tau_continuous_fit/tables/tile_level_tau.csv`

## 输出

- `tables/tau_range_comparisons.csv`（若可计算）
- `tables/visibility_vs_intensity_tests.csv`（若输入包含 tile-level 恢复时间列）
