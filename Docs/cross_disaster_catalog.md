# Cross-Disaster Catalog（多灾难批量分析配置）

该配置用于批量生成每个灾难的：

- `population_redistribution/`（距离分带的 `phi_aggregate(r,t)`）
- `physical_model/`（`phi(r,t)` 矩阵与 `tau(r)` 拟合）
- `cross_disaster_comparison/`（跨灾难对比表与“三相分离”摘要）

## 配置文件

使用 `Docs/cross_disaster_catalog.csv`。

字段说明：

- `slug`：输出目录名（会写到 `outputs/<slug>/`）
- `name`：人类可读的灾难名称（用于表格/摘要）
- `data_root`：数据根目录（需要包含 `population/`，最好也包含 `movement/`）
- `event_type`：灾难类型（earthquake/hurricane/flood/wildfire/...）
- `t0_pt`：时间零点（PT 时间戳字符串，例如 `2023-02-05 16:00`）
- `center_lat/center_lon`：灾难中心/震中经纬度（用于距离分带）
- `only_hour_pt`：只取每日该小时的窗口（默认 08:00，用于去除日周期）
- `outflow_phi_threshold / inflow_phi_threshold`：Task 2 的 outflow/inflow 判定阈值

## 自动估计规则（当 t0/center 为空）

若 `t0_pt` 为空：取**首个 `only_hour_pt`（默认 08:00）窗口所在日期的 16:00 PT 窗口**作为 `t=0`（若该 16:00 窗口不存在，则回退到首个 `only_hour_pt` 窗口）。

若 `center_lat/center_lon` 为空：在该 `t=0` 窗口内，按 `|n_difference|` 作为权重计算加权质心（lat/lon）。若权重全为 0/缺失，则回退到 `n_crisis` 加权质心。

说明：这是为了让 pipeline **可自动跑通**。若你掌握更可信的灾难中心与发生时间，建议手动填入以提升跨灾难对比的物理可解释性。
