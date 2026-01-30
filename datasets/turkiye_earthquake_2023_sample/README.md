# Turkey Earthquake 2023（Sample Raw Dataset）

这个目录提供一个**可放进 GitHub 的小体量 sample**，用于：
- 让 PI 快速接触“原始 CSV 的真实格式/字段”
- 让代码在 CI/本地快速跑通（无需下载全量 ~6.9G）

## 合规提醒

请确保你对该数据的分发方式（例如 GitHub）有授权，并优先使用 **private** 仓库。

## 内容

- `raw/population/*.csv`：从全量 Turkey 数据集中**原样复制**的 Population During Crisis 原始窗口文件  
- `manifest.csv`：每个文件的 `size_bytes` 与 `sha256` 校验和（便于验证传输/复制无误）

## 时间范围（PT）

为保证包含 `t=0=2023-02-05 16:00 PT` 窗口，且拟合模块需要的 `t>0` 数据点数 `>=10`，sample 覆盖：

- `2023-02-05` ~ `2023-02-09`（窗口：`0000/0800/1600`）

## 如何跑通 pipeline（建议输出到单独目录）

```bash
python scripts/population_relaxation.py \
  --data-root datasets/turkiye_earthquake_2023_sample/raw \
  --output-dir outputs/population_relaxation_sample
```

## 生成方式

```bash
python scripts/build_turkiye_sample_dataset.py
```
