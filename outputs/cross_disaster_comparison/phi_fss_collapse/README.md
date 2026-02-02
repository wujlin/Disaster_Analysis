# φ 分布数据坍缩验证（FSS-style, single-window）

目的：在选定的 t_crisis 单窗口截面上，比较不同灾害在相同距离带的 tile-level φ=n_crisis/n_baseline 分布是否可通过幂指数缩放坍缩。

## 输入

- `--catalog`：Docs/cross_disaster_catalog.csv
- 每个灾害读取 1 个 population 窗口文件（t_crisis）

## t_crisis 选择

- mode=peak_0_25
- fixed：取 t=t0+88h 的最近窗口
- peak_0_25：优先复用 `outputs/<slug>/population_redistribution/tables/redistribution_by_distance_band.csv`，在 0–832h 内取最靠近中心距离带（优先 0-25km，否则取最小 band）的 `phi_aggregate` 峰值窗口

## 坍缩定义

- tile-level：φ_i = n_crisis / n_baseline（只保留 n_baseline>0 且二者非空）
- 距离带：[0.0, 25.0, 50.0, 100.0, 200.0, inf]
- 缩放变量：x = φ_i / s^α，其中 s 为每灾害/距离带的尺度
    - `--phi-scale=mean`：s = mean(φ_i)（默认）
    - `--phi-scale=aggregate`：s = phi_aggregate = sum(n_crisis)/sum(n_baseline)
- p(x)：统一 bins 的直方图密度
- 残差：E(α) = ∫ Var_i[p_i(x)] dx（用 bin 宽加权近似）

## 主要输出

- `tables/phi_samples_summary.csv`：每灾害/距离带的样本量与尺度统计（含 t_crisis 选择详情）
- `tables/alpha_scan_<band>.csv`：每距离带的 E(α) 扫描
- `tables/best_alpha_by_band.csv`：每距离带最优 α*
- `figures/residual_E_alpha_<band>.*`：E(α) 曲线
- `figures/collapse_pdf_<band>.*`：坍缩后的 p(x)
