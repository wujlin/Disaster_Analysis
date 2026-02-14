# 工作站（WSA）数据路径规范与防冲突指南

## 1) 目标
这份文档只解决一件事：**在工作站上跑全量分析时，统一数据路径口径，避免和其他设备（partner 机器）的路径配置互相污染**。

---

## 2) 工作站固定路径（本机专用）
- 项目根目录：`/home/jinlin/projects/Disaster_Analysis`
- Facebook 原始灾害数据根目录：`/home/jinlin/data/Facebook_Disaster`
- 项目内补充数据目录（5个缺失事件）：`/home/jinlin/projects/Disaster_Analysis/datasets`

建议在 shell 中固定为环境变量：

```bash
export PROJ_ROOT=/home/jinlin/projects/Disaster_Analysis
export FB_ROOT=/home/jinlin/data/Facebook_Disaster
export DS_ROOT=$PROJ_ROOT/datasets
```

---

## 3) 防冲突规则（必须遵守）
1. **不要手改** `Docs/cross_disaster_catalog_extended.csv` 的 `data_root`。  
   该文件保留跨设备通用口径。
2. 工作站只使用带 `_wsa` 后缀的 catalog：
   - `Docs/cross_disaster_catalog_extended_wsa.csv`
   - `Docs/cross_disaster_catalog_extended_wsa_existing_only.csv`
3. 运行分析时，一律优先用 `*_wsa_existing_only.csv`，避免因单个目录缺失中断全流程。
4. 若 partner 在其他设备更新了 catalog，**重新执行一次路径重映射**，不要复用旧的 `_wsa` 文件。

---

## 4) 路径重映射（核心步骤）
已内置脚本：`scripts/remap_catalog_data_roots.py`

它会自动做三件事：
- 优先从 `FB_ROOT` 匹配目录；
- 对缺失项回退到 `DS_ROOT`（已覆盖 5 个补充事件）；
- 生成“全量映射表 + 仅存在且含 population CSV 的子集 + 校验报告”。

执行命令：

```bash
cd /home/jinlin/projects/Disaster_Analysis

python scripts/remap_catalog_data_roots.py \
  --catalog-in Docs/cross_disaster_catalog_extended.csv \
  --catalog-out Docs/cross_disaster_catalog_extended_wsa.csv \
  --existing-only-out Docs/cross_disaster_catalog_extended_wsa_existing_only.csv \
  --report-out Docs/cross_disaster_catalog_extended_wsa_path_check.csv \
  --facebook-root /home/jinlin/data/Facebook_Disaster \
  --datasets-root /home/jinlin/projects/Disaster_Analysis/datasets \
  --prefer facebook
```

---

## 5) 全量分析标准入口（工作站）

### Step A: 生成/更新每个事件的 `phi_heatmap`
```bash
python scripts/cross_disaster_phi_heatmap.py \
  --catalog Docs/cross_disaster_catalog_extended_wsa_existing_only.csv \
  --output-root outputs \
  --distance-mode radial \
  --on-error fail \
  --hours-pt 0 8 16 \
  --min-hours -16 \
  --max-hours 832 \
  --distance-bin-km 10 \
  --max-distance-km 500
```

### Step B: 生成 `Dt_decay` 汇总表
```bash
python scripts/dt_decay.py \
  --output-root outputs \
  --out-dir outputs/cross_disaster_comparison/Dt_decay
```

### Step C: 跑动力学四实验（全量口径）
```bash
python scripts/dynamics_potential.py \
  --output-root outputs \
  --dt-tables-dir outputs/cross_disaster_comparison/Dt_decay/tables \
  --out-dir outputs/cross_disaster_comparison/dynamics_potential_all \
  --use-route-b-selected 0
```

### Step D: 跑动力学四实验（论文主结果口径）
```bash
python scripts/dynamics_potential.py \
  --output-root outputs \
  --dt-tables-dir outputs/cross_disaster_comparison/Dt_decay/tables \
  --out-dir outputs/cross_disaster_comparison/dynamics_potential_routeB \
  --use-route-b-selected 1
```

---

## 5.1 一键全流程（推荐）
如果你担心终端断开后看不到报错，直接用一键脚本：

```bash
python scripts/wsa_full_pipeline.py \
  --project-root /home/jinlin/projects/Disaster_Analysis \
  --facebook-root /home/jinlin/data/Facebook_Disaster \
  --datasets-root /home/jinlin/projects/Disaster_Analysis/datasets \
  --allow-missing-events 0
```

它会自动执行：
1. 路径重映射  
2. `cross_disaster_phi_heatmap`  
3. `dt_decay`  
4. `dynamics_potential` 全量口径  
5. `dynamics_potential` Route B 口径  

并把日志写到：
- `outputs/_runs/wsa_full_pipeline_YYYYmmdd_HHMMSS/pipeline.log`
- `outputs/_runs/wsa_full_pipeline_YYYYmmdd_HHMMSS/logs/*.log`
- `outputs/_runs/wsa_full_pipeline_YYYYmmdd_HHMMSS/status.json`

---

## 5.2 防“终端关闭看不到报错”的运行方式
建议用 `nohup` 后台运行（终端断开也不会丢日志）：

```bash
cd /home/jinlin/projects/Disaster_Analysis
nohup python scripts/wsa_full_pipeline.py \
  --project-root /home/jinlin/projects/Disaster_Analysis \
  --facebook-root /home/jinlin/data/Facebook_Disaster \
  --datasets-root /home/jinlin/projects/Disaster_Analysis/datasets \
  --allow-missing-events 0 \
  > /tmp/wsa_full_pipeline_stdout.log 2>&1 &

echo $!   # 记录 PID
```

实时看进度：
```bash
tail -f /tmp/wsa_full_pipeline_stdout.log
```

看结构化状态（失败步骤/退出码）：
```bash
ls -1dt outputs/_runs/wsa_full_pipeline_* | head -n 1
cat <上一步最新目录>/status.json
```

---

## 6) 工作站已知特殊映射（脚本内置）
- `spain_flood` → `Spain fllood`
- `mountain_fire_in_california` → `Mountain fire in California`
- `global_earthquake_model_research_2025_sep_18` → `datasets/Global_Earthquake_Model_Research_2025_Sep_18`
- `hurricane_melissa_10_27_2025` → `datasets/Hurricane_Melissa_10_27_2025`
- `hurricane_melissa_aftermath_2025_11_03` → `datasets/Hurricane_Melissa_Aftermath_2025_11_03`
- `the_earthquake_across_central_mexico` → `datasets/The_Earthquake_Across_Central_Mexico`
- `the_earthquake_across_dhaka_division_bangladesh` → `datasets/The_Earthquake_Across_Dhaka_Division_Bangladesh`

---

## 7) 快速自检
每次重映射后先看这两个文件：
- `Docs/cross_disaster_catalog_extended_wsa_path_check.csv`
- `Docs/cross_disaster_catalog_extended_wsa_existing_only.csv`

重点检查：
- `path_exists` 是否还有 0；
- `resolved_source` 是否符合预期（`facebook` 或 `datasets`）；
- 事件数是否满足当前实验要求（全量/子集）。
