# 数据入库台账（3批次）

更新日期：2026-02-22

## 1. 目的

本文件用于统一记录项目数据来源、批次、目录位置和纳入分析状态，避免“数据已下载但未入分析口径”或“不同终端口径不一致”。

## 2. 数据根路径与统计口径

- 历史原始库（批次1主来源）：`/mnt/e/newdesktop/archive/facebook/disaster data`
- 项目内数据目录（批次2/3与样例）：`datasets/`
- 分析输出目录：`outputs/`
- 本地快照统计口径：
  - 统计范围：`datasets/` 下所有子目录，排除 `datasets/staged`
  - 统计对象：递归 `*.csv`
  - 2026-02-22 本地快照：`26` 个目录、`932` 个 CSV、约 `6.58 GB`

## 3. 三批数据总览

| 批次 | 时间 | 来源 | 主要位置 | 规模（口径） | 当前状态 |
|---|---|---|---|---|---|
| Batch-1 | 2024（历史下载） | Archive 原始灾害库 | `/mnt/e/newdesktop/archive/facebook/disaster data` | 历史主库（多灾害） | 已作为主分析来源（见 `Docs/cross_disaster_catalog_centerfix6.csv`） |
| Batch-2 | 2026-02 上旬 | DFG 补采（5灾害） | `datasets/Global_Earthquake_Model_Research_2025_Sep_18` 等 5 个目录 | 本地快照：`273` CSV，约 `924 MB` | 已纳入（见 `Docs/cross_disaster_catalog_dfg_batch1.csv`） |
| Batch-3 | 2026-02-22（本次增量） | partner 最新抓取 | `datasets/` 新增目录 + 对已存在目录增量 | partner 汇总：`67/67` 数据集、`26` 灾害目录、`932` CSV、`6.13 GB` | 待与 PI 确认后纳入分析口径 |

## 4. Batch-2（5灾害）目录明细

| 目录 | CSV 数（本地） | 大小（本地） |
|---|---:|---:|
| `Global_Earthquake_Model_Research_2025_Sep_18` | 92 | 40M |
| `Hurricane_Melissa_10_27_2025` | 41 | 52M |
| `Hurricane_Melissa_Aftermath_2025_11_03` | 40 | 52M |
| `The_Earthquake_Across_Central_Mexico` | 53 | 623M |
| `The_Earthquake_Across_Dhaka_Division_Bangladesh` | 47 | 157M |

## 5. Batch-3 新增灾害目录明细（按本次提供清单）

说明：你给的标题写“新增 11 个”，但清单实际列出了 `16` 个灾害目录。这里按清单逐项登记。

| 目录 | 对应事件（简写） | CSV 数（本地） | 大小（本地） |
|---|---|---:|---:|
| `Tropical_Cyclone_Gezani-26_2026_02_11` | Tropical Cyclone Gezani-26 | 36 | 5.0M |
| `Tropical_Storm_Basyang_Across_Mindanao_Philippines` | Tropical Storm Basyang | 47 | 218M |
| `The_Flooding_Across_Northwestern_Colombia` | Flooding NW Colombia | 53 | 117M |
| `Tropical_Cyclone_Fytia_Across_Analamanga_and_Boeny_Regions_Madagascar` | Tropical Cyclone Fytia | 50 | 12M |
| `Winter_Storm_Fern_Across_Tennessee_and_Kentucky_US` | Winter Storm Fern (TN/KY) | 54 | 1.1G |
| `Winter_Storm_Fern_2026_01_27` | Winter Storm Fern 2026-01-27 | 29 | 2.1G |
| `Storm_Chandra_2026_01_27` | Storm Chandra | 29 | 370M |
| `Drc_Ebola_Outbreak` | DRC Ebola Outbreak | 33 | 328K |
| `Flooding_And_Rain_In_Southern_California_12_23_2025` | Flooding Southern California | 34 | 117M |
| `The_Flooding_Across_Peninsular_Malaysia` | Flooding Peninsular Malaysia | 28 | 107M |
| `The_Flooding_In_Southern_Thailand_And_Malaysia` | Flooding Southern Thailand/Malaysia | 34 | 129M |
| `The_Flooding_in_Hat_Yai_Songkhla_Province_Thailand` | Flooding Hat Yai | 32 | 283M |
| `The_Flooding_in_South_Central_Region_Vietnam` | Flooding South-Central Vietnam | 32 | 250M |
| `The_Flooding_in_Sri_Lanka` | Flooding Sri Lanka | 34 | 42M |
| `The_Flooding_in_Sumatra_Indonesia` | Flooding Sumatra | 34 | 145M |
| `Tropical_Cyclone_Senyar_In_Sumatra_Indonesia_11282025` | Tropical Cyclone Senyar | 42 | 131M |

## 6. Batch-3 同步补充的非灾害通用数据

| 目录 | CSV 数（本地） | 大小（本地） |
|---|---:|---:|
| `Climate_Change_Survey` | 1 | 492K |
| `Commuting_Zones` | 1 | 11M |
| `Movement_Distribution` | 20 | 242M |
| `Travel_Patterns_Edges` | 20 | 1.8M |

## 7. 当前“数据存在”与“已纳入分析”对应关系

- 已纳入分析主 catalog：
  - `Docs/cross_disaster_catalog_centerfix6.csv`（27 条）
  - `Docs/cross_disaster_catalog_dfg_batch1.csv`（5 条）
  - `Docs/cross_disaster_catalog_extended.csv`（42 条，当前综合口径）
- 尚未纳入主分析口径：
  - 本次 Batch-3 新增灾害目录（上表 16 项）
  - 需在与 PI 确认后，再补充到新的 catalog（建议单独维护 `cross_disaster_catalog_batch3.csv`，再合并到 extended）

## 8. 提交策略（避免噪声提交）

- `manifest.json` 主要是下载索引（尤其 `cdn_url` 常变化），不是分析结果本体。
- 常规建议：
  - 分析提交优先包含 `Docs/*catalog*.csv`、`outputs/` 下可复现实验产物和代码；
  - 下载索引变化默认不提交，除非要记录“下载批次快照”。

