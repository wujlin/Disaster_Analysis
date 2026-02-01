# Tile Validation (Task A)

目标：对 0–25km 范围内 “post 存在但 pre 不存在” 的 tiles 进行地图标注，用于验证“救援营地/救援设施”假说。

## 输入窗口（PT）

- pre: 2023-02-05 08:00  (`2023-02-05_0800`)
- post: 2023-02-06 08:00 (`2023-02-06_0800`)

## 结果文件

- `tables/new_tiles_coordinates.csv`：新激活 tiles 坐标与 n_crisis 等字段
- `tables/new_tiles_evolution.csv`：新激活 tiles 在后续窗口的 n_crisis（窗口缺失则不会出现）
- `figures/new_tiles_static.*`：静态图（含 25km 圈、震中、Gaziantep Airport 标注）
- `new_tiles_map.html`：交互式地图（需要 folium；若环境无 folium 则不会生成）

## 摘要

- new tiles 数量：29
- 过滤：distance_km < 25.0

## 备注

- 交互式地图依赖 `folium`：可用 `pip install folium` 或 conda 安装。
