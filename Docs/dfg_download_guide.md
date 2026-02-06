# Facebook Data for Good (DFG) 数据下载技术文档

> 最后更新：2026-02-06  
> 状态：下载管线已验证通过，可稳定运行

---

## 1. 技术路线概述

### 1.1 问题定义

Facebook Data for Good (DFG) 平台通过 `partners.facebook.com` 提供灾难数据（人口变动、人口流动、网络覆盖、商业活动等）。平台**没有公开 API 文档**，所有交互通过内部 GraphQL 接口完成。我们需要：

1. 自动获取全部可用数据集目录
2. 按条件筛选并批量下载 CSV 文件

### 1.2 最终成功的技术架构

```
浏览器登录 DFG 平台
       │
       ├── 导出 cookie → config/cookie.json
       │     （使用 Cookie-Editor 等浏览器扩展）
       │
       └── 提取 FB 内部会话参数 → config/_dfg_tokens.json
             （从 DevTools Network 面板或 JS 控制台提取）
             
                    ↓
                    
Python 脚本 (scripts/dfg_downloader.py)
       │
       ├── catalog  → 获取全部数据集目录 (GraphQL API)
       ├── list     → 浏览/筛选已获取的目录
       └── download → 批量下载 CSV 文件 (CDN 直链)
```

### 1.3 关键 GraphQL 端点

| 用途 | `doc_id` | `friendly_name` |
|---|---|---|
| 首页数据集列表 | `9656680804428472` | `DataForGoodDatasetQueryContextQuery` |
| 分页加载更多 | `9691183727639209` | `DataForGoodConsolidatedDatasetListQuery` |
| 数据集详情 | `25010506245226288` | `DataForGoodPortalDatasetQueryQuery` |
| 文件资源列表 | `29112475378400107` | `DataForGoodPortalResourceQueryQuery` |

所有请求发送到 `POST https://partners.facebook.com/api/graphql/`。

---

## 2. 踩坑记录与解决方案

### 2.1 ❌ 坑1：仅发送 fb_dtsg/lsd 导致 400 错误

**现象**：脚本发送 GraphQL 请求后返回 `400 Client Error: Bad Request`。

**根因**：Facebook 的 GraphQL API 要求请求体中包含 **~15 个内部会话参数**，而不仅仅是 `fb_dtsg` 和 `lsd`。浏览器每次请求都会自动附带这些参数，它们由页面加载时的 JS 框架生成。

**必需参数清单**：

| 参数 | 说明 | 获取方式 |
|---|---|---|
| `fb_dtsg` | CSRF token | 页面 HTML 中 `DTSGInitialData` |
| `lsd` | 额外 CSRF token | 页面 HTML 中 `LSD` |
| `__user` / `c_user` | 用户 ID | cookie `c_user` |
| `__hsi` | Haste Session ID | `SiteData.hsi` |
| `__rev` | 服务器版本号 | `SiteData.server_revision` |
| `__hs` | Haste Session 字符串 | `SiteData.haste_session` |
| `__ccg` | 连接质量 | 通常为 `"EXCELLENT"` |
| `__dyn` | 已加载动态模块的 bitmask | 仅从网络请求中获取 |
| `__hsdp` | Haste 依赖 bitmask | 仅从网络请求中获取 |
| `__hblp` | Bootloader 包 bitmask | 仅从网络请求中获取 |
| `__spin_r` | Spin 版本号 | 同 `__rev` |
| `__spin_b` | Spin 分支 | 通常为 `"trunk"` |
| `__spin_t` | Spin 时间戳 | 页面加载时间戳 |
| `jazoest` | 反 CSRF 校验 | `"2" + sum(charCodes(fb_dtsg))` |
| `__s` | 会话追踪 ID | 页面 JS 生成 |

**解决方案**：从浏览器 DevTools 的 Network 面板中，复制任一成功的 `api/graphql` 请求的完整 Form Data，保存到 `config/_dfg_tokens.json`。

### 2.2 ❌ 坑2：从页面 HTML 提取 token 失败

**现象**：用 `requests.get()` 访问 DFG 页面，尝试用正则从 HTML 中提取 `fb_dtsg` 和 `lsd`，但返回的 HTML 内容与浏览器渲染的不同（可能是登录重定向或 JS 渲染前的骨架页面）。

**根因**：DFG 页面是 React SPA，核心内容靠客户端 JS 渲染。`requests` 库拿到的只是服务器端渲染的初始 HTML，不包含完整的 JS 运行时状态。

**教训**：不要试图用 `requests` 模拟浏览器获取动态生成的 token。直接从真实浏览器会话中提取。

### 2.3 ❌ 坑3：Windows PowerShell 的 `UnicodeEncodeError`

**现象**：脚本中使用了 emoji 字符（如 🔑、📋），在 Windows PowerShell 中运行时报错 `UnicodeEncodeError: 'gbk' codec can't encode character`。

**解决方案**：在脚本开头添加 UTF-8 输出包装：

```python
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
```

### 2.4 ❌ 坑4：PowerShell 不支持 `&&` 连接符

**现象**：`cd dir && python script.py` 在 PowerShell 中报语法错误。

**解决方案**：使用 `;` 代替 `&&`：`cd dir; python script.py`。

### 2.5 ❌ 坑5：浏览器自动化导航超时

**现象**：尝试用 MCP 浏览器工具 `navigate_page` 访问 DFG 页面时超时（页面加载复杂的 React 应用需要较长时间）。

**解决方案**：需要开启浏览器工具的全局模式（Global Mode），允许访问 `partners.facebook.com` 域名。

### 2.6 ❌ 坑6：同一时间窗口多种资源类型导致文件覆盖

**现象**：DFG 平台对同一个 `date_time` 会提供多种资源类型（`DOWNLOADABLE_CSV`、`DOWNLOADABLE_GEOTIFF`、`DOWNLOADABLE_GEOJSON`）。旧版脚本将所有资源都保存为 `.csv` 后缀，导致：
- 后下载的 TIFF/JSON 覆盖了先下载的 CSV
- 磁盘上出现"后缀 `.csv`、内容实际是 TIFF 或 JSON"的污染文件

**影响范围**（2026-02-06 发现并修复）：
- 共 **37 个文件**被污染（32 个 TIFF + 5 个 JSON）
- 涉及所有 5 个灾害目录的 Population、Network Coverage、Business Activity 数据
- Movement Between Places 数据未受影响（该类型无 TIFF/GeoJSON 资源）

**修复方案**：
1. 下载时按 `resource_type` 过滤，默认只下载 `DOWNLOADABLE_CSV`（`--format csv`）
2. 文件后缀按 `resource_type` 映射：CSV → `.csv`，GeoTIFF → `.tiff`，GeoJSON → `.geojson`
3. 新增 `purge-bad` 命令自动扫描并删除被污染的文件
4. `download_file()` 增加内容校验：下载前检查已存在文件的 magic bytes，如不匹配则重新下载

```bash
# 扫描并删除污染文件
python scripts/dfg_downloader.py purge-bad --yes

# 重新下载（默认只下 CSV，自动跳过已存在的正常文件）
python scripts/dfg_downloader.py download --name "Earthquake" --yes

# 如需下载 GeoTIFF
python scripts/dfg_downloader.py download --name "Earthquake" --format geotiff --yes
```

### 2.7 ✅ jazoest 计算公式

`jazoest` 并非随机值，而是由 `fb_dtsg` 派生：

```python
jazoest = "2" + str(sum(ord(c) for c in fb_dtsg))
```

当 `fb_dtsg` 更新时，`jazoest` 也必须重新计算。

---

## 3. 使用指南

### 3.1 首次配置

#### 步骤 1：导出 Cookie

1. 浏览器登录 `partners.facebook.com/data_for_good/data/`
2. 安装浏览器扩展 [Cookie-Editor](https://cookie-editor.cgagnier.ca/)
3. 点击扩展 → Export → JSON → 保存到 `config/cookie.json`

#### 步骤 2：提取会话参数

**方法 A（推荐）：从 DevTools 复制请求体**

1. 在 DFG 页面按 F12 打开 DevTools
2. 切换到 Network 面板，筛选 `graphql`
3. 点击任一请求 → Payload → 点击 "view source"（查看原始请求体）
4. 复制整个请求体字符串
5. 运行：

```bash
python scripts/dfg_downloader.py refresh-session --body "av=12345&__aaid=0&..."
```

**方法 B：从浏览器控制台提取关键参数**

在 DFG 页面的浏览器控制台中运行：

```javascript
(() => {
  const html = document.documentElement.innerHTML;
  const sd = require('SiteData');
  const dtsg = html.match(/"DTSGInitialData"[^}]*"token"\s*:\s*"([^"]+)"/)?.[1];
  const lsd = html.match(/"LSD"\s*,\s*\[\]\s*,\s*\{"token"\s*:\s*"([^"]+)"/)?.[1];
  const cuser = document.cookie.match(/c_user=(\d+)/)?.[1];
  console.log(JSON.stringify({
    fb_dtsg: dtsg,
    lsd: lsd,
    user_id: cuser,
    __hsi: sd.hsi,
    __rev: String(sd.server_revision),
    __hs: sd.haste_session,
    __spin_r: String(sd.server_revision),
    __spin_b: "trunk",
    __spin_t: String(Math.floor(Date.now() / 1000)),
    __ccg: "EXCELLENT",
    jazoest: "2" + [...dtsg].reduce((s, c) => s + c.charCodeAt(0), 0),
  }, null, 2));
})();
```

将输出保存到 `config/_dfg_tokens.json`。

> ⚠️ 注意：此方法缺少 `__dyn`、`__hsdp`、`__hblp` 参数。如果 API 返回 400，改用方法 A。

### 3.2 日常使用

```bash
# 获取/更新数据集目录
python scripts/dfg_downloader.py catalog

# 浏览数据集
python scripts/dfg_downloader.py list
python scripts/dfg_downloader.py list --type Population
python scripts/dfg_downloader.py list --country Mexico

# 按关键词下载（默认只下载 CSV 格式）
python scripts/dfg_downloader.py download --name "Earthquake" --yes
python scripts/dfg_downloader.py download --name "Hurricane" --yes

# 按数据类型 + 国家筛选
python scripts/dfg_downloader.py download --type Population --country Bangladesh --yes

# 按 dataset_id 精确下载
python scripts/dfg_downloader.py download --dataset-id 1603570647757603 --yes

# 下载特定格式（geotiff / geojson / all）
python scripts/dfg_downloader.py download --name "Earthquake" --format geotiff --yes

# 扫描并清理被污染的文件
python scripts/dfg_downloader.py purge-bad --yes
```

### 3.3 Token 过期处理

Cookie 和会话参数会过期（通常数小时至数天）。症状：

- `400 Client Error` → 会话参数过期，重新执行步骤 2
- `401/403` 或重定向到登录页 → Cookie 过期，重新执行步骤 1 + 步骤 2

---

## 4. 已下载数据清单

> 截至 2026-02-06，共下载 **~0.9 GB**（纯 CSV），涵盖 6 个灾难事件  
> 注：修复资源类型覆盖问题后，孟加拉 Business Activity 从 1.2GB（GeoJSON 污染）降至 0.5MB（纯 CSV）

### 4.1 地震 (Earthquake)

#### The Earthquake Across Central Mexico（2026 年 1 月墨西哥地震）

| 数据类型 | dataset_id | 文件数 | 大小 | 日期范围 |
|---|---|---|---|---|
| Movement Between Places | `1304029558432254` | 20 | 478.7 MB | 2026-01-02 ~ 2026-01-16 |
| Facebook Population | `887176223902432` | 6 | 57.0 MB | 2026-01-02 ~ 2026-01-07 |
| Business Activity | `1553039769281990` | 14 | 10.5 MB | 2026-01-02 ~ 2026-01-15 |
| Network Coverage | `1384932873142250` | 6 | 9.2 MB | 2026-01-02 ~ 2026-01-07 |

#### The Earthquake Across Dhaka Division, Bangladesh（2025 年 11 月孟加拉国地震）

| 数据类型 | dataset_id | 文件数 | 大小 | 日期范围 |
|---|---|---|---|---|
| Movement Between Places | `1785492615463575` | 20 | 99.6 MB | 2025-11-21 ~ 2025-12-04 |
| Facebook Population | `1471653427259830` | 7 | 25.8 MB | 2025-11-21 ~ 2025-12-04 |
| Business Activity | `1206560174663575` | 7 | 0.5 MB | 2025-11-21 ~ 2025-12-04 |
| Network Coverage | `856951877277079` | 7 | 7.9 MB | 2025-11-21 ~ 2025-12-04 |

#### Global Earthquake Model Research 2025 Sep 18（葡萄牙地震研究）

| 数据类型 | dataset_id | 文件数 | 大小 | 日期范围 |
|---|---|---|---|---|
| Movement Between Places | `1096637342645947` | 20 | 15.0 MB | 2025-09-18 ~ 2026-02-04 |
| Facebook Population | `1126772169393938` | 7 | 2.1 MB | 2025-09-18 ~ 2026-01-07 |
| Network Coverage | `1968440140663647` | 20 | 2.4 MB | 2025-09-18 ~ 2026-02-01 |

### 4.2 飓风 (Hurricane)

#### Hurricane Melissa 10 27 2025（飓风主体阶段，加勒比海地区）

| 数据类型 | dataset_id | 文件数 | 大小 | 日期范围 |
|---|---|---|---|---|
| Movement Between Places | `1229745325844390` | 20 | 30.5 MB | 2025-10-27 ~ 2025-11-10 |
| Facebook Population | `2317035405407646` | 7 | 8.8 MB | 2025-10-27 ~ 2025-11-10 |
| Network Coverage | `2327920630957580` | 7 | 3.8 MB | 2025-10-27 ~ 2025-11-10 |

涉及国家：Dominican Republic, Jamaica, Haiti, The Bahamas, Bermuda

#### Hurricane Melissa Aftermath 2025 11 03（飓风灾后阶段）

| 数据类型 | dataset_id | 文件数 | 大小 | 日期范围 |
|---|---|---|---|---|
| Movement Between Places | `1289565269594516` | 20 | 30.8 MB | 2025-11-03 ~ 2025-11-23 |
| Facebook Population | `747262731704282` | 7 | 8.7 MB | 2025-11-03 ~ 2025-11-23 |
| Network Coverage | `1693451371571961` | 7 | 4.6 MB | 2025-11-03 ~ 2025-11-23 |

### 4.3 既有数据

#### Turkey Earthquake 2023（土耳其地震，本项目核心数据集）

| 数据类型 | 位置 | 文件数 | 大小 |
|---|---|---|---|
| Facebook Population | `datasets/turkiye_earthquake_2023_sample/raw/population/` | 15 | 90.4 MB |

> 注：此数据集为项目初始数据，通过手动方式获取，非 `dfg_downloader.py` 下载。

### 4.4 数据存储结构

```
datasets/
├── dfg_catalog.json                          # 全部 83 个数据集的目录索引
├── turkiye_earthquake_2023_sample/           # 既有数据（手动获取）
│   └── raw/population/*.csv
├── The_Earthquake_Across_Central_Mexico/     # 自动下载
│   ├── Movement_Between_Places_During_Crisis/
│   │   ├── manifest.json                     # 文件清单 + 元数据
│   │   └── raw/*.csv
│   ├── Facebook_Population_During_Crisis/
│   │   ├── manifest.json
│   │   └── raw/*.csv
│   ├── Business_Activity_Trends_During_Crisis/
│   │   ├── manifest.json
│   │   └── raw/*.csv
│   └── Network_Coverage_Maps/
│       ├── manifest.json
│       └── raw/*.csv
├── The_Earthquake_Across_Dhaka_Division_Bangladesh/
│   └── (同上结构)
├── Global_Earthquake_Model_Research_2025_Sep_18/
│   └── (同上结构，无 Business Activity)
├── Hurricane_Melissa_10_27_2025/
│   └── (同上结构，无 Business Activity)
└── Hurricane_Melissa_Aftermath_2025_11_03/
    └── (同上结构，无 Business Activity)
```

### 4.5 防重复下载机制

脚本内置了两层防重复：

1. **文件级去重**：`download_file()` 检查目标路径是否已存在，存在则跳过（显示 `⏭️ 已存在`）
2. **manifest 记录**：每个数据类型目录下的 `manifest.json` 记录了已下载的文件列表和 CDN URL

---

## 5. 文件清单

| 文件 | 用途 |
|---|---|
| `scripts/dfg_downloader.py` | 主脚本（catalog / list / download / purge-bad / set-token / refresh-session） |
| `config/cookie.json` | 浏览器导出的 Facebook cookie（**不要提交到 Git**） |
| `config/_dfg_tokens.json` | FB 内部会话参数缓存（**不要提交到 Git**） |
| `datasets/dfg_catalog.json` | 全部可用数据集目录（83 个） |
| `datasets/*/manifest.json` | 各数据集的下载元数据 |

---

## 6. 注意事项

1. **数据使用限制**：DFG 数据受 Facebook/Meta 的数据使用协议约束，不得公开分发原始数据。`datasets/*/raw/` 目录应在 `.gitignore` 中排除。
2. **Cookie 安全**：`config/cookie.json` 和 `config/_dfg_tokens.json` 包含登录凭证，务必加入 `.gitignore`，不要提交到代码仓库。
3. **API 限流**：脚本在分页请求间插入 1 秒延迟、文件下载间插入 0.5 秒延迟。如遇到限流（429 或连接重置），可适当增大延迟。
4. **数据集会停止生成**：DFG 平台上的灾难数据集有生命周期，标记为 "Data generation stopping" 的数据集将很快停止更新。尽早下载。
5. **`doc_id` 可能变化**：Facebook 可能在前端版本更新时更改 GraphQL 的 `doc_id`。如果所有请求突然都返回错误，可能需要从浏览器 Network 面板重新抓取最新的 `doc_id`。
