# 空间扩散-弛豫实验输出（Direction C）

输入：
- `outputs/<slug>/phi_heatmap/tables/phi_rt_long.csv`
- `outputs/cross_disaster_comparison/Dt_decay/tables/Dt_routeB_sample_flags.csv`

实验分层：
- Exp0：数据准备（峰值剖面 + 后峰轨迹）
- Exp1：profile 形状指标 + 贝塞尔模态分解 + 相关/偏相关
- Exp2：解析工具（合成 profile 的 D(t) 与 α）
- Exp3：真实 profile 的 PDE 预测与参数搜索
- Exp4：bootstrap 与反事实验证
