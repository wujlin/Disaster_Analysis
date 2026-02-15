# 动力学模型四实验输出

对应 `Opinion_PI.md` 的四个实验：
- 实验1：逐 bin 弛豫时间（`bin_relaxation_times.csv`, `asymmetry_summary.csv`）
- 实验2：非线性检验（`nonlinearity_test.csv`）
- 实验3：非对称非线性势拟合（`langevin_fit_params.csv`）
- 实验4：Langevin simulation（`simulation_phase_grid.csv`, `simulation_validation.csv`）

输入：
- `outputs/<slug>/phi_heatmap/tables/phi_rt_long.csv`
- `outputs/cross_disaster_comparison/Dt_decay/tables/Dt_event_summary.csv`
- `outputs/cross_disaster_comparison/Dt_decay/tables/Dt_powerlaw_fits.csv`
- `outputs/cross_disaster_comparison/Dt_decay/tables/Dt_routeB_sample_flags.csv`（若启用 Route B 样本筛选）

运行参数见 `metadata.json`。
