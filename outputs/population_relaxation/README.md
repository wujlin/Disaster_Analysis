# Population Relaxation（Latest Outputs）

这个目录包含当前仓库 **Population relaxation（Turkey 2023）** 的最新可视化与拟合结果快照，便于 PI 在 GitHub 上直接 review。

> 注意：`outputs/` 默认不进 git；本仓库仅例外跟踪 `outputs/population_relaxation/`，其余生成物仍会被忽略。

## 如何复现

```bash
# 生成（全量数据）
python scripts/population_relaxation.py

# 拟合后分析：τ(r)、C(r)
python scripts/population_postfit_analysis.py

# β 稳健性（0-50km, stretched exp）
python scripts/beta_robustness.py
```

## 目录说明

- `figures/`：论文风格图（png + pdf）
- `tables/`：按距离分箱聚合的时序与汇总表
- `fits/`：BIC 模型选择的拟合参数表 + β 稳健性输出

