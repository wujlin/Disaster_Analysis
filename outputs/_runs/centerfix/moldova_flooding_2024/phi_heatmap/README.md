# Phi Heatmap (Task 4)

本目录对应 `Opinion_PI.md` 的 **任务 4**：计算并可视化连续版本的 $\phi(r,t)$：

- 距离：0–500 km，每 10 km 一个 bin
- 时间：每 8 小时一个窗口（PT），t 范围 [0.0, 72.0] 小时
- 指标：$\phi_{agg}(r,t)=\sum n_{crisis}/\sum n_{baseline}$

## 配置

- center: (47.1820, 28.5516)
- center_track_csv: None
- center_track_to_tz: America/Los_Angeles
- center_track_storm_name: None
- t0_pt: 2024-09-16 16:00:00
- hours_pt: [8]

## 输出

- `tables/phi_rt_long.csv`：长表（每个窗口 × 每个 r_bin 的汇总）
- `tables/phi_rt_matrix.csv`：宽表（rows=r_bin_km, cols=hours_since_quake）
- `tables/center_by_window.csv`：每个时间窗口使用的中心点（static 或 track 插值）
- `tables/three_phase_by_time.csv`：三相分离判定（按时间）
- `tables/three_phase_windows.csv`：三相分离连续时间段
- `figures/phi_rt_heatmap.*`：热力图（含 φ=1/0.9/0.8 等值线）

## 覆盖时间（PT）

- 2024-09-17 08:00:00 → 2024-09-19 08:00:00
