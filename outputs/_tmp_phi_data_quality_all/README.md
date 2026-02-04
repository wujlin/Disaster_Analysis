# Cross-disaster Phi Data Quality Diagnosis

本目录用于在下结论前，先做 **φ 数据质量诊断**（基于 `outputs/<slug>/phi_heatmap/tables/phi_rt_long.csv`）。

## 运行配置

- catalog: `outputs/_tmp_universality_scaling_all/catalog_all.csv`
- output_root: `outputs`
- 时间过滤：hours_since_quake ∈ [0.0, None]
- 径向剖面窗口：[24.0, 72.0] 小时

## 输出

- `tables/data_quality_by_disaster.csv`：每个灾害的 φ 分布诊断（φ=0/NaN/φ>2/min_nonzero，含加权版本；并记录 t0/center 元数据）
- `tables/spatial_coverage_by_disaster.csv`：每个灾害的空间覆盖摘要（r_max_with_ge_10_tiles 等）
- `tables/spatial_coverage_by_band.csv`：按 50.0km 距离带汇总 n_tiles（检查 coverage drop / 边界效应）
- `tables/phi_zero_nan_summary.csv`：兼容旧输出名（同 data_quality_by_disaster）
- `tables/phi_zero_nan_by_rbin.csv`：φ=0/NaN 在距离 r_bin 上的分布（按时间汇总）
- `figures/phi_radial_profiles_examples.*`：若干“典型灾害”的 φ(r) 径向剖面（不是 |φ-1|）
- `figures/phi_zero_fraction_by_distance_examples.*`：典型灾害 φ=0 的距离分布（按行比例）

## Turkey φ=0 tile 诊断（若可访问 raw population 数据）

- `tables/turkey_phi_zero_tiles.csv`
- `tables/turkey_phi_zero_distance_hist.csv`
- `figures/turkey_phi_zero_map.*`
- `figures/turkey_phi_zero_distance_hist.*`
