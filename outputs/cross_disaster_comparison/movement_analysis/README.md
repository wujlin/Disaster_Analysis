# Movement 分析输出（D_peak → α 机制检验）

## 口径
- 事件集合：Route B (`Dt_routeB_sample_flags.csv` 中 `route_b_selected=True`)
- 时间窗口：以每事件 `t_peak` 为中心，默认 ±24h（Exp-M1）
- 近场/远场：近场 `<50km`，远场 `50-200km`
- 序列拟合：`alpha_return` 在 `t'∈[24h,120h]` 做 log-log 斜率

## 关键指标定义
- `F_total`：峰值窗口内 `Σ|n_difference|`
- `F_out_near`：峰值窗口内 `Σ n_difference`（start_near & end_far）
- `F_in_far`：峰值窗口内 `Σ n_difference`（start_far & end_near）
- `F_long`：峰值窗口内 `Σ n_difference`（length_km > long_distance_km）
- `R_bar`：近场起点流向角的加权圆统计 resultant length（方向性）
- `cos_alignment`：流向与“远离灾害中心”方向一致性（加权均值）
- `HHI_dest`：近场疏散（start_near & end_far & n_diff>0）目的地集中度
- `alpha_return`：回流率 `R_return(t)` 的 log-log 衰减斜率

## 限制
- DFG 对小流量 OD 做隐私截断（baseline/crisis <10 移除），可能抬高 `HHI_dest`
- 对飓风类事件，若可用则使用 `t_peak` 时刻的 track 中心；否则使用 catalog/auto 中心
