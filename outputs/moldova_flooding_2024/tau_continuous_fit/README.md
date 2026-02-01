# Continuous $\tau(r)$ (tile-level)

目的：回应“距离带划分是否人为导致结论”的审稿风险。
做法：对每个 tile 拟合 $\phi_i(t)=n_{crisis}/n_{baseline}$ 的指数恢复时间常数 $\tau_i$，再在连续距离上拟合 $\tau(r)$ 并给出 bootstrap 置信带与 $r^*$。

## 输入

- `Data/Moldova Flooding Sept 16 2024/population/*.csv`

## 关键口径

- 仅使用 PT 08:00 窗口（若 only_hour_pt=-1 则不过滤小时）
- tile universe：震前窗口（hours_since_quake<0）中 baseline 与 crisis 同时非空的 tiles
- $\phi_i(t)=n_{crisis}/n_{baseline}$，并裁剪到 [0.0, 3.0]
- 单 tile 指数拟合：线性化方法（尾部中位数估计 $\phi_\infty$）
- 连续拟合：$\log \tau = a + b\log r + c(\log r)^2$
- bootstrap：1000 次（seed=7）

## 产物

- `tables/tile_level_tau.csv`：每个 tile 的 $\tau_i$ 与距离
- `tables/tau_r_fit_quadratic.csv`：连续 $\tau(r)$ 拟合参数与 $r^*$
- `tables/tau_r_star_bootstrap.csv`：$r^*$ bootstrap 样本
- `tables/tau_r_curve_ci.csv`：$\tau(r)$ 曲线的 bootstrap 置信带（若 bootstrap 成功）
- `figures/tau_vs_distance_continuous.*`
- `figures/r_star_bootstrap_hist.*`
