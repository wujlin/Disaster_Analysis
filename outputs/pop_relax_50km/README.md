# Population Relaxation（50km bins, Turkey 2023）

这个目录是基于 **全量 Turkey 2023 原始数据**跑出的结果快照，用于“机制分区（regime differentiation）”主线。

## 关键产出

- `figures/regime_map_z_score.*`：距离带 → 最优模型类型（BIC）分区图
- `tables/regime_boundaries_z_score.csv`：模型切换的边界表
- `figures/regime_bootstrap_winrates_z_score.*`：bootstrap 模型胜率热力图（稳健性）
- `fits/regime_fit_z_score_best_bic.csv`：每个距离 bin 的最优模型（含参数与 at_bounds）
- `fits/regime_fit_z_score_all_models.csv`：全模型竞争明细（便于诊断）

## 复现命令（全量数据）

```bash
# 1) 先用新代码重跑聚合表（会生成包含 n_baseline_sum / n_crisis_sum 等列的新 CSV）
python scripts/population_relaxation.py \
  --data-root <FULL_DATA_ROOT> \
  --output-dir outputs/pop_relax_50km \
  --bin-width-km 50 --max-bin-km 1000

# 2) P0：z_score vs φ 对比图
python scripts/zscore_phi_compare.py \
  --ts-csv outputs/pop_relax_50km/tables/population_relaxation_by_distance.csv \
  --output-root outputs/pop_relax_50km

# 3) P0：0-150km、前 200h 疏散-回流
python scripts/evacuation_return.py \
  --ts-csv outputs/pop_relax_50km/tables/population_relaxation_by_distance.csv \
  --output-root outputs/pop_relax_50km \
  --metric z_score --max-distance-km 150 --max-hours 200

# 4) P1：baseline / crisis 绝对量时间序列
python scripts/baseline_crisis_timeseries.py \
  --ts-csv outputs/pop_relax_50km/tables/population_relaxation_by_distance.csv \
  --output-root outputs/pop_relax_50km

# 5) 机制分区（regime map + 边界 + bootstrap 胜率）
python scripts/regime_differentiation.py \
  --ts-csv outputs/pop_relax_50km/tables/population_relaxation_by_distance.csv \
  --output-root outputs/pop_relax_50km \
  --metric z_score \
  --n-bootstrap 300 \
  --open-ended-right-km 1300
```
