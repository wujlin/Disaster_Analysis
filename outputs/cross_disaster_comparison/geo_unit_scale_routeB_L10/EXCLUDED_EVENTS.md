# Route-B L10 剔除事件说明

## 本轮剔除
- `the_earthquake_across_central_mexico`

## 剔除原因（严格口径）
在 `scripts/geo_unit_analysis.py` 的严格参数下：
- `--require-all-events 1`
- `--quadkey-level 10`
- `--min-time-windows 6`
- `--fit-min-tprime-hours 24`
- `--min-mono-points 3`

该事件在 geo-unit 子区域拟合阶段没有形成可用单元（`n_units_fit=0`），会导致整批任务直接报错并中止。

## 可复核证据
- 上一次未剔除时的 strict 运行报错：`存在事件无可用 geo-unit 拟合结果`。
- 对应可用性诊断显示该事件 `n_windows=4`、`n_units_fit=0`。
- 拟合失败诊断以 `short_mono` 为主，说明单调衰减段有效点不足。

## 本轮处理
- 本次运行使用：
  - `--exclude-slugs the_earthquake_across_central_mexico`
- 结果：其余事件在 strict 模式下全部通过（`availability_ok = 12/12`）。

## 备注
这次剔除仅针对当前 `Route-B L10` 严格分析批次；后续若调整该事件的时间锚点/观测窗口定义，可单独复算并评估是否可重新纳入。
