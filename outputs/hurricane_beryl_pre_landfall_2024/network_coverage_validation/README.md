# Network Coverage Validation

目的：排除“Population 下降只是因为手机没信号/网络中断”的混淆。
本脚本把 network coverage 数据按距离带聚合，给出 outage proxy 的时序；并可选与 population 距离带表按日期对齐输出。

## 输入

- `Data/Hurricane Beryl Pre Landfall Disaster Maps June 30 2024/network coverage/**/*.csv`
- （可选）`outputs/hurricane_beryl_pre_landfall_2024/population_redistribution/tables/redistribution_by_distance_band.csv`

## 输出

- `tables/network_coverage_outage_by_band.csv`
- `figures/network_outage_timeseries.*`
- （可选）`tables/network_coverage_vs_population_by_band.csv`
