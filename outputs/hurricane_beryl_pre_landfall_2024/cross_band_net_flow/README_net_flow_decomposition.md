# Net 流分解（用于验证 H3）

目标：对指定距离带（默认 50-100km）的 Net_total 进行分解：

- Net_internal：与 0-50km 的带间净流（默认 internal_bands=['0-25km', '25-50km']）
- Net_external：与 100km+ 的带间净流（默认 external_bands=['100-200km', '200km+']）
- F_within：带内流量（start=end=target_band）

定义（每个时间窗口 t）：

- F_start_total = Σ n_crisis where start_band==target
- F_end_total   = Σ n_crisis where end_band==target
- Net_total     = F_end_total - F_start_total
- Net_internal  = (Σ end=target,start∈internal) - (Σ start=target,end∈internal)
- Net_external  = (Σ end=target,start∈external) - (Σ start=target,end∈external)
- F_within      = Σ start=target,end=target

## 配置

- slug: hurricane_beryl_pre_landfall_2024
- center: (11.3154, -61.1969)
- t0_pt: 2024-06-30 16:00:00
- only_hour_pt: 8
- time range (hours_since_quake): [-16.0, 832.0]
- target_band: 50-100km
- internal_bands: ['0-25km', '25-50km']
- external_bands: ['100-200km', '200km+']

## 输出

- `tables/net_flow_decomposed.csv`：每窗口的分解结果（可选包含 φ 字段）
- `tables/net_flow_decomposed_corr.csv`：corr(Net_internal, φ) 与 corr(Net_external, φ)
