# Pipeline 透明化协议（v1）

本协议用于消除两类黑箱：  
- 结构性黑箱：`t0/center` 自动推断路径不一致；  
- 参数黑箱：阈值分散在脚本中，难以追溯。

## 1. 结构性黑箱：`t0/center` 强约束

主分析建议使用以下命令参数：

```bash
python scripts/cross_disaster_phi_heatmap.py \
  --catalog Docs/cross_disaster_catalog_routeB16_frozen.csv \
  --output-root outputs/_runs/routeB16_main \
  --distance-mode radial \
  --hours-pt 0 8 16 \
  --on-error fail \
  --require-explicit-t0-center 1 \
  --require-explicit-sources 1 \
  --write-provenance 1
```

含义：
- `--require-explicit-t0-center 1`：catalog 缺 `t0_pt/center_lat/center_lon` 直接报错；
- `--require-explicit-sources 1`：catalog 缺 `t0_source/center_source` 直接报错；
- `--write-provenance 1`：输出 `outputs/.../_provenance_phi_heatmap.csv`。

## 2. Provenance 表（SI Table S1）

统一导出：

```bash
python scripts/export_provenance_table.py \
  --catalog Docs/cross_disaster_catalog_routeB16_frozen.csv \
  --output-root outputs/_runs/routeB16_main \
  --out-csv outputs/cross_disaster_comparison/provenance_table_s1.csv \
  --strict 1
```

输出字段包含：
- `t0_pt/center_lat/center_lon`
- `t0_source/center_source`
- `t0_method_used/center_method_used`
- `auto_inference_used`
- `t0_minus_first_window_hours`

## 3. 参数黑箱：配置文件统一

`dt_decay` 支持从 JSON 读参数：

```bash
python scripts/dt_decay.py \
  --config-json config/dt_decay_config_routeB16.json \
  --output-root outputs/_runs/routeB16_main \
  --out-dir outputs/cross_disaster_comparison/Dt_decay_routeB16_main \
  --catalog Docs/cross_disaster_catalog_routeB16_frozen.csv \
  --use-catalog-exclude-reason 1
```

说明：
- 阈值集中在 `config/dt_decay_config_routeB16.json`；
- 运行后 `metadata.json` 会写入 `config_json/config_payload`；
- `exclude_reason` 优先来自 catalog，不再依赖代码硬编码。

## 4. 事件筛选透明化

`Dt_routeB_sample_flags.csv` 中新增：
- `data_quality_ok`（数据质量层）；
- `analysis_applicability_ok`（方法适用性层）；
- `drop_reason_class`（`data_quality` / `analysis_applicability` / `manual_exclude`）；
- `drop_reason_primary`（具体原因）；
- `catalog_exclude_reason`（catalog 给出的排除理由）。

## 5. 数学定义（Methods 对齐）

核心定义：

- 扰动振幅  
  \[
  D(t)=\frac{1}{N_r}\sum_{r\le r_{max}}\left|\phi(r,t)-1\right|
  \]
- 近场符号量  
  \[
  \delta_{near}(t)=\frac{1}{N_{r\le r_{near}}}\sum_{r\le r_{near}}(\phi(r,t)-1)
  \]
- 峰后归一化  
  \[
  D_{norm}(t')=\frac{D(t)}{D_{peak}},\quad t'=t-t_{peak}
  \]
- 结构性反弹判据（首次超阈值即截断）  
  对峰后序列，若出现  
  \[
  D_{norm}(t'_{i+1}) > D_{norm}(t'_i)\times \texttt{mono\_tol\_up}
  \]
  则在该点前截断；默认 `mono_tol_up=1.05`。

## 6. 推荐 gate

跑前：
- `python scripts/routeb16_preflight.py --require-explicit-t0-center 1 --require-source-columns 1 --require-nonempty-sources 1`

跑后：
- `python scripts/routeb16_postgate.py ... --expected-selected 16`

若 gate 未通过，不进入统计解释阶段。
