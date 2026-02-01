# Physical Model: $\phi(r,t)$ (Task B)

本目录对应 `Opinion_PI.md` 的 **Task B**：
把 `outputs/population_redistribution/tables/redistribution_by_distance_band.csv` 里的 $\phi_{agg}(r,t)$ 转成可视化 + 指数恢复拟合，提取 $\tau(r)$。

## 输入

- `outputs/park_fire_2024/population_redistribution/tables/redistribution_by_distance_band.csv`

## 主要输出

- `tables/phi_rt_matrix.csv`：$\phi(r,t)$ 矩阵（rows=hours_since_quake, cols=distance bands）
- `figures/phi_vs_r_multitime.*`：$\phi(r)$ 多时间点曲线
- `figures/phi_vs_t_multiband.*`：$\phi(t)$ 多距离带曲线
- `figures/phi_rt_heatmap.*`：$\phi(r,t)$ 热力图
- `tables/relaxation_fit_by_band.csv`：指数恢复拟合参数（$\phi_0,\phi_\infty,\tau$）
- `tables/tau_vs_distance.csv`：$\tau(r)$
- `figures/tau_vs_distance.*`：$\tau(r)$ 图（log-log）

## 拟合窗口

- t >= 0.0h
