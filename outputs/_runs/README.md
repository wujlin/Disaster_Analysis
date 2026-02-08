# outputs/_runs

本目录用于集中存放项目中“可复现 / 可同步”的实验输出，避免在仓库一级目录堆放多个 `outputs_*` 目录。

## 迁移映射（旧 → 新）

- `outputs_trackpath/` → `outputs/_runs/trackpath/v1/`
- `outputs_trackpath_v2/` → `outputs/_runs/trackpath/v2/`
- `outputs_trackpath_v3/` → `outputs/_runs/trackpath/v3/`
- `outputs_trackpath_v4_yagi_fix/` → `outputs/_runs/trackpath/v4_yagi_fix/`
- `outputs_centerfix/` → `outputs/_runs/centerfix/`
- `outputs_dfg_batch1/` → `outputs/_runs/dfg/batch1/`
- `outputs_dfg_batch1_anchor/` → `outputs/_runs/dfg/batch1_anchor/`

## 说明

- `H3a` 相关脚本的默认 `--output-root` 已更新为 `outputs/_runs/trackpath/v3`；如需分析其它版本，请显式传参覆盖。
