# Movement 跨带净流量（cross-band net flow）

本目录实现 PI 更新任务框的 **跨带净流量** 指标（按距离带与时间窗口聚合）：

对每条 OD：
- 计算起点距离带 start_band（按起点到中心距离分箱）
- 计算终点距离带 end_band（按终点到中心距离分箱）

对每个距离带 band、时间窗口 t：
- N_out(band,t) = Σ n_crisis where start_band==band and end_band!=band
- N_in(band,t)  = Σ n_crisis where end_band==band and start_band!=band
- Net(band,t)   = N_in - N_out (= end_sum - start_sum)

## 配置

- slug: turkiye_earthquake_2023
- center: (37.1740, 37.0320)
- t0_pt: 2023-02-05 16:00:00
- only_hour_pt: 8
- time range (hours_since_quake): [-16.0, 832.0]
- distance_bins_km: [0.0, 25.0, 50.0, 100.0, 200.0, inf]

## 输出

- `tables/cross_band_net_flow.csv`：每个 (band, time) 的 N_in/N_out/Net（可选合并 φ 字段）
- `tables/net_flow_phi_corr_by_band.csv`：若提供 population_by_band_csv，则输出 corr(Net, φ-1)（按 band）
