# H3a Track/Path Report

本目录用于对 `output_root` 下已有的 `phi_heatmap` 结果做 **track/path 组**汇总。

本次运行参数：

- output_root: `outputs_trackpath_v2`
- phi_col: `phi_aggregate`
- time: [0.0, 72.0] hours
- min_tiles: 50

主要产物（按 min_tiles 后缀区分，避免同目录多次运行覆盖）：

- `tables/track_report_minTiles50.csv`
- `tables/overlap_metric_minTiles50.csv`
- `tables/collapse_curves_minTiles50.csv`
- `figures/collapse_plot_minTiles50.*`
