#!/usr/bin/env python3
"""
Facebook Data for Good (DFG) — 自动数据采集脚本

功能:
  1. catalog  — 获取全部数据集目录，保存到 datasets/dfg_catalog.json
  2. download — 按条件筛选后，批量下载 CSV 文件

用法:
  python scripts/dfg_downloader.py catalog
  python scripts/dfg_downloader.py download --name "Earthquake" --type Population
  python scripts/dfg_downloader.py download --dataset-id 1603570647757603

需要: config/cookie.json (从浏览器导出的 cookie)
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

# Windows 控制台 UTF-8 兼容
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests

# ─────────────────────────── 常量 ──────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[1]
COOKIE_FILE = REPO_ROOT / "config" / "cookie.json"
CATALOG_FILE = REPO_ROOT / "datasets" / "dfg_catalog.json"
DOWNLOAD_DIR = REPO_ROOT / "datasets"

GRAPHQL_URL = "https://partners.facebook.com/api/graphql/"

# GraphQL doc_id（从浏览器网络请求中抓取）
DOC_ID_DATASET_LIST = "9656680804428472"       # DataForGoodDatasetQueryContextQuery (首页，含全部)
DOC_ID_PAGINATED_LIST = "9691183727639209"     # DataForGoodConsolidatedDatasetListQuery (分页)
DOC_ID_DATASET_DETAIL = "25010506245226288"    # DataForGoodPortalDatasetQueryQuery (详情)
DOC_ID_RESOURCES = "29112475378400107"         # DataForGoodPortalResourceQueryQuery (文件列表)


# ─────────────────────────── Cookie / 认证 ──────────────────────────


def _load_cookies() -> dict[str, str]:
    """从 cookie.json 解析出 name->value 字典"""
    if not COOKIE_FILE.exists():
        print(f"❌ Cookie 文件不存在: {COOKIE_FILE}")
        sys.exit(1)
    raw = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
    # 只保留 facebook.com / partners.facebook.com 域名的 cookie
    cookies = {}
    for c in raw:
        domain = c.get("domain", "")
        if "facebook.com" in domain:
            cookies[c["name"]] = c["value"]
    return cookies


def _cookie_string(cookies: dict[str, str]) -> str:
    """拼接成 HTTP Cookie header 字符串"""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def _extract_auth_tokens(cookies: dict[str, str]) -> dict[str, str]:
    """从 cookie 中提取认证所需的关键字段"""
    return {
        "c_user": cookies.get("c_user", ""),
        "xs": cookies.get("xs", ""),
        "fr": cookies.get("fr", ""),
    }


# ─────────────────────────── 会话参数管理 ──────────────────────────

TOKEN_CACHE_FILE = REPO_ROOT / "config" / "_dfg_tokens.json"


def _load_session_params() -> dict[str, str]:
    """从缓存文件加载完整会话参数"""
    if not TOKEN_CACHE_FILE.exists():
        return {}
    try:
        return json.loads(TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_session_params(params: dict[str, str]) -> None:
    """保存会话参数到缓存文件"""
    TOKEN_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE_FILE.write_text(
        json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ─────────────────────────── GraphQL 请求 ──────────────────────────


_REQ_COUNTER = 0  # 递增请求计数器


def _graphql_request(
    session: requests.Session,
    doc_id: str,
    variables: dict,
    sp: dict[str, str],
    friendly_name: str = "",
) -> dict:
    """发送 GraphQL 请求到 Facebook API（包含完整内部参数）

    sp: 从 _load_session_params() 加载的完整会话参数
    """
    global _REQ_COUNTER
    _REQ_COUNTER += 1

    user_id = sp.get("user_id", "")
    fb_dtsg = sp.get("fb_dtsg", "")
    lsd = sp.get("lsd", "")

    # 构建完整的请求体 —— 严格复刻浏览器发送的全部字段
    data = {
        "av": user_id,
        "__aaid": "0",
        "__user": user_id,
        "__a": "1",
        "__req": str(_REQ_COUNTER),
        "__hs": sp.get("__hs", ""),
        "dpr": "1",
        "__ccg": sp.get("__ccg", "EXCELLENT"),
        "__rev": sp.get("__rev", ""),
        "__s": sp.get("__s", ""),
        "__hsi": sp.get("__hsi", ""),
        "__dyn": sp.get("__dyn", ""),
        "__hsdp": sp.get("__hsdp", ""),
        "__hblp": sp.get("__hblp", ""),
        "fb_dtsg": fb_dtsg,
        "jazoest": sp.get("jazoest", ""),
        "lsd": lsd,
        "__spin_r": sp.get("__spin_r", ""),
        "__spin_b": sp.get("__spin_b", ""),
        "__spin_t": sp.get("__spin_t", ""),
        "__jssesw": "1",
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": friendly_name,
        "server_timestamps": "true",
        "variables": json.dumps(variables),
        "doc_id": doc_id,
    }

    headers = {
        "x-fb-friendly-name": friendly_name,
        "x-fb-lsd": lsd,
        "x-asbd-id": "359341",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://partners.facebook.com",
        "referer": "https://partners.facebook.com/data_for_good/data/"
                   "?partner_id=274171648108880&section=25&lsrc=lb",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }
    resp = session.post(GRAPHQL_URL, data=data, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────── 目录获取 ──────────────────────────


def fetch_catalog(session: requests.Session, sp: dict[str, str]) -> list[dict]:
    """获取全部数据集目录（分页获取）"""
    all_datasets = []
    cursor = None
    page = 0

    while True:
        page += 1
        variables: dict[str, Any] = {
            "count": 20,
            "countries": [],
            "include_discontinued": False,
            "include_test_data": False,
            "mapTypes": [],
            "name": "",
        }
        if cursor:
            variables["cursor"] = cursor

        if cursor is None:
            # 首次请求用初始查询
            result = _graphql_request(
                session, DOC_ID_DATASET_LIST, {
                    "name": "",
                    "mapTypes": [],
                    "countries": [],
                    "include_test_data": False,
                    "include_discontinued": False,
                },
                sp,
                "DataForGoodDatasetQueryContextQuery",
            )
        else:
            result = _graphql_request(
                session, DOC_ID_PAGINATED_LIST, variables,
                sp,
                "DataForGoodConsolidatedDatasetListQuery",
            )

        collections = result.get("data", {}).get("xfb_dfg_dataset_collections", {})
        total = collections.get("count", 0)
        edges = collections.get("edges", [])

        if not edges:
            break

        for edge in edges:
            node = edge.get("node", {})
            ds_info = node.get("dfg_default_dataset", {}).get("nodes", [{}])[0]
            if not ds_info:
                continue

            # 提取国家列表
            crisis = ds_info.get("crisis", {})
            countries = []
            for cn in crisis.get("countries", {}).get("nodes", []):
                name = cn.get("iso_name", "")
                if name and name != "Global":
                    countries.append(name)

            dataset = {
                "dataset_id": ds_info.get("id", ""),
                "display_name": ds_info.get("display_name", ""),
                "collection_title": ds_info.get("collection_title", ""),
                "map_type_title": ds_info.get("map_type_title", ""),
                "countries": countries,
                "date_range_start": ds_info.get("date_range_start", ""),
                "date_range_end": ds_info.get("date_range_end", ""),
                "hours_in_window": ds_info.get("hours_in_window", 0),
                "max_days_in_bulk_download": ds_info.get("max_days_in_bulk_download", 0),
                "downloadable_formats": ds_info.get("downloadable_resource_types", []),
                "crisis_id": crisis.get("id", ""),
                "bounding_box": crisis.get("bounding_box", {}),
                "collection_id": node.get("id", ""),
            }
            all_datasets.append(dataset)

        # 分页
        page_info = collections.get("page_info", {})
        if page_info.get("has_next_page"):
            cursor = page_info.get("end_cursor")
            print(f"  📄 第 {page} 页完成，已获取 {len(all_datasets)}/{total} 个数据集...")
            time.sleep(1)  # 避免请求过快
        else:
            break

    print(f"✅ 共获取 {len(all_datasets)} 个数据集")
    return all_datasets


def fetch_file_urls(
    session: requests.Session,
    dataset_id: str,
    sp: dict[str, str],
    end_date: str = "",
    num_dates: int = 100,
) -> list[dict]:
    """获取指定数据集的所有文件下载 URL"""
    variables: dict[str, Any] = {
        "dataset_id": dataset_id,
        "num_dates_to_fetch": num_dates,
    }
    if end_date:
        variables["end_date"] = end_date

    result = _graphql_request(
        session, DOC_ID_RESOURCES, variables,
        sp,
        "DataForGoodPortalResourceQueryQuery",
    )

    ds = result.get("data", {}).get("fetch__DFGBaseGeospatialDataset", {})
    resources = ds.get("resources", {}).get("edges", [])

    files = []
    for edge in resources:
        node = edge.get("node", {})
        if node.get("is_downloadable"):
            files.append({
                "id": node.get("id", ""),
                "cdn_url": node.get("cdn_url", ""),
                "date_time": node.get("date_time", ""),
                "content_type": node.get("content_type", ""),
                "resource_type": node.get("resource_type", ""),
                "size": node.get("size", 0),
            })
    return files


# ─────────────────────────── 下载 ──────────────────────────


def download_file(session: requests.Session, url: str, save_path: Path) -> bool:
    """下载单个文件，下载后校验内容类型是否与后缀一致"""
    save_path.parent.mkdir(parents=True, exist_ok=True)
    if save_path.exists():
        # 校验已存在文件的内容类型
        if _is_content_mismatched(save_path):
            print(f"  [!] 已存在但内容类型与后缀不符，将重新下载: {save_path.name}")
            save_path.unlink()
        else:
            print(f"  -- 已存在: {save_path.name}")
            return True

    try:
        resp = session.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        downloaded = 0

        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)

        size_mb = downloaded / (1024 * 1024)
        print(f"  [ok] 下载完成: {save_path.name} ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"  [ERR] 下载失败: {save_path.name} -- {e}")
        return False


# ─── 内容类型校验 ───

# 文件 magic bytes 判断
_TIFF_LE = b"\x49\x49\x2a\x00"  # TIFF little-endian
_TIFF_BE = b"\x4d\x4d\x00\x2a"  # TIFF big-endian


def _is_content_mismatched(path: Path) -> bool:
    """检查文件内容是否与后缀不符（如 .csv 文件实际是 TIFF/JSON）"""
    ext = path.suffix.lower()
    if ext != ".csv":
        return False  # 只检查 CSV 后缀的文件
    try:
        with open(path, "rb") as f:
            head = f.read(4)
        if len(head) < 4:
            return False
        # TIFF magic bytes
        if head[:4] in (_TIFF_LE, _TIFF_BE):
            return True
        # JSON (starts with '{' or '[')
        if head[0:1] in (b"{", b"["):
            return True
    except Exception:
        pass
    return False


# ─── resource_type → 文件后缀 映射 ───

RESOURCE_TYPE_EXT = {
    "DOWNLOADABLE_CSV": ".csv",
    "DOWNLOADABLE_GEOTIFF": ".tiff",
    "DOWNLOADABLE_GEOJSON": ".geojson",
}


def _ext_for_resource(resource_type: str, content_type: str = "") -> str:
    """根据 resource_type 和 content_type 确定文件后缀"""
    ext = RESOURCE_TYPE_EXT.get(resource_type, "")
    if ext:
        return ext
    # fallback: 根据 content_type
    ct = content_type.lower()
    if "tiff" in ct:
        return ".tiff"
    if "json" in ct or "geojson" in ct:
        return ".geojson"
    if "csv" in ct:
        return ".csv"
    return ".bin"  # 未知类型


def _sanitize_name(name: str) -> str:
    """将数据集名称转为安全目录名"""
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:80]


# ─────────────────────────── CLI ──────────────────────────


def _build_session() -> tuple[requests.Session, dict[str, str]]:
    """构建认证 Session 和会话参数"""
    cookies = _load_cookies()
    sp = _load_session_params()

    if not sp.get("fb_dtsg"):
        print("  [!] 缺少会话参数。请先运行: python scripts/dfg_downloader.py refresh-session")
        sys.exit(1)

    # 如果 user_id 缺失，从 cookie 补充
    if not sp.get("user_id"):
        sp["user_id"] = cookies.get("c_user", "")

    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    return session, sp


def cmd_catalog(args: argparse.Namespace) -> None:
    """获取并保存数据集目录"""
    session, sp = _build_session()

    fb_dtsg = sp["fb_dtsg"]
    lsd = sp.get("lsd", "")
    user_id = sp.get("user_id", "")

    print("[auth] 会话参数已加载")
    print(f"  fb_dtsg: {fb_dtsg[:20]}...")
    print(f"  lsd: {lsd[:20]}..." if lsd else "  lsd: (empty)")
    print(f"  user_id: {user_id}")
    print(f"  __rev: {sp.get('__rev', '?')}")

    print("\n[catalog] 正在获取数据集目录...")
    catalog = fetch_catalog(session, sp)

    CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_FILE.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n💾 目录已保存到: {CATALOG_FILE}")

    # 按类型统计
    type_counts: dict[str, int] = {}
    for ds in catalog:
        t = ds.get("collection_title", "Unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    print("\n📊 数据类型分布:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")

    # 按灾难事件统计
    event_counts: dict[str, int] = {}
    for ds in catalog:
        name = ds.get("display_name", "Unknown")
        event_counts[name] = event_counts.get(name, 0) + 1
    print(f"\n🌍 独立灾难事件: {len(event_counts)}")
    for name, c in sorted(event_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {name}: {c} 种数据")


def cmd_download(args: argparse.Namespace) -> None:
    """筛选并下载数据集"""
    # 加载目录
    if not CATALOG_FILE.exists():
        print("❌ 请先运行 catalog 命令获取目录")
        sys.exit(1)
    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))

    # 筛选
    selected = catalog
    if args.dataset_id:
        selected = [d for d in selected if d["dataset_id"] == args.dataset_id]
    if args.name:
        keyword = args.name.lower()
        selected = [d for d in selected if keyword in d["display_name"].lower()]
    if args.type:
        type_kw = args.type.lower()
        selected = [d for d in selected if type_kw in d["collection_title"].lower()]
    if args.country:
        country_kw = args.country.lower()
        selected = [d for d in selected if any(country_kw in c.lower() for c in d["countries"])]

    if not selected:
        print("❌ 没有匹配的数据集")
        sys.exit(1)

    print(f"📥 找到 {len(selected)} 个匹配数据集:")
    for ds in selected:
        print(f"  • {ds['display_name']} ({ds['collection_title']}) [{', '.join(ds['countries'])}]")

    if not args.yes:
        answer = input(f"\n确认下载 {len(selected)} 个数据集? (y/N): ")
        if answer.lower() != "y":
            print("取消下载")
            return

    # 认证
    session, sp = _build_session()
    print("\n[auth] 会话参数已加载")

    # 逐个下载
    for i, ds in enumerate(selected, 1):
        dsid = ds["dataset_id"]
        name = ds["display_name"]
        dtype = ds["collection_title"]
        print(f"\n{'='*60}")
        print(f"[{i}/{len(selected)}] {name}")
        print(f"  类型: {dtype}")
        print(f"  ID: {dsid}")

        # 获取文件列表
        # 默认下载到该数据集的 date_range_end；如提供 --end-date 则覆盖（便于抓取早期窗口）。
        end_date = str(args.end_date).strip() if getattr(args, "end_date", None) else ""
        end_date = end_date or ds.get("date_range_end", "")
        files = fetch_file_urls(
            session, dsid, sp,
            end_date=end_date,
            num_dates=args.max_dates,
        )

        if not files:
            print("  ⚠️ 没有可下载的文件")
            continue

        # 按 resource_type 过滤
        fmt = getattr(args, "format", "csv").lower()
        if fmt != "all":
            fmt_key = f"DOWNLOADABLE_{fmt.upper()}"
            files = [f for f in files if f.get("resource_type", "") == fmt_key]

        print(f"  找到 {len(files)} 个文件 (format={fmt})")

        if not files:
            print("  [!] 过滤后没有文件可下载")
            continue

        # 创建保存目录
        safe_name = _sanitize_name(name)
        safe_type = _sanitize_name(dtype)
        save_dir = DOWNLOAD_DIR / safe_name / safe_type / "raw"
        save_dir.mkdir(parents=True, exist_ok=True)

        # 下载每个文件 —— 按 resource_type 给正确后缀
        for f in files:
            dt = f["date_time"].replace(" ", "_").replace(":", "")
            ext = _ext_for_resource(
                f.get("resource_type", ""),
                f.get("content_type", ""),
            )
            filename = f"{safe_name}_{safe_type}_{dt}{ext}"
            save_path = save_dir / filename
            download_file(session, f["cdn_url"], save_path)
            time.sleep(0.5)  # 避免过快

        # 保存文件清单
        manifest = {
            "dataset_id": dsid,
            "display_name": name,
            "collection_title": dtype,
            "countries": ds["countries"],
            "date_range": f"{ds['date_range_start']} — {ds['date_range_end']}",
            "files": files,
        }
        manifest_path = save_dir.parent / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n🎉 下载完成!")


def cmd_list(args: argparse.Namespace) -> None:
    """列出目录中的数据集"""
    if not CATALOG_FILE.exists():
        print("❌ 请先运行 catalog 命令获取目录")
        sys.exit(1)
    catalog = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))

    # 可选筛选
    if args.type:
        type_kw = args.type.lower()
        catalog = [d for d in catalog if type_kw in d["collection_title"].lower()]
    if args.country:
        country_kw = args.country.lower()
        catalog = [d for d in catalog if any(country_kw in c.lower() for c in d["countries"])]

    print(f"📋 共 {len(catalog)} 个数据集:\n")
    for i, ds in enumerate(catalog, 1):
        countries = ", ".join(ds.get("countries", [])) or "Global"
        date_range = f"{ds.get('date_range_start', '?')} ~ {ds.get('date_range_end', '?')}"
        print(f"  {i:3d}. [{ds['dataset_id']}] {ds['display_name']}")
        print(f"       类型: {ds['collection_title']} | 国家: {countries}")
        print(f"       日期: {date_range}")
        print()


def cmd_set_token(args: argparse.Namespace) -> None:
    """手动设置 fb_dtsg 和 lsd token（向后兼容）"""
    sp = _load_session_params()
    sp["fb_dtsg"] = args.fb_dtsg
    sp["lsd"] = args.lsd
    sp["timestamp"] = int(time.time())
    _save_session_params(sp)
    print(f"  Token 已保存到 {TOKEN_CACHE_FILE}")
    print("[ok] Token 设置成功")


def cmd_purge_bad(args: argparse.Namespace) -> None:
    """扫描 datasets/ 下所有 .csv 文件，删除内容实际为 TIFF/JSON 的污染文件"""
    scan_root = DOWNLOAD_DIR
    bad_files: list[tuple[str, Path]] = []

    for csv_path in scan_root.rglob("*.csv"):
        if csv_path.name == "dfg_catalog.json":
            continue
        if _is_content_mismatched(csv_path):
            # 判断实际类型
            with open(csv_path, "rb") as f:
                head = f.read(4)
            if head[:4] in (_TIFF_LE, _TIFF_BE):
                actual = "TIFF"
            elif head[0:1] in (b"{", b"["):
                actual = "JSON"
            else:
                actual = "UNKNOWN"
            bad_files.append((actual, csv_path))

    if not bad_files:
        print("[ok] 没有发现被污染的 .csv 文件")
        return

    print(f"[!] 发现 {len(bad_files)} 个被污染的 .csv 文件:\n")
    for actual, p in bad_files:
        rel = p.relative_to(REPO_ROOT)
        size_kb = p.stat().st_size / 1024
        print(f"  [{actual}] {rel}  ({size_kb:.0f} KB)")

    if not args.yes:
        answer = input(f"\n确认删除这 {len(bad_files)} 个污染文件? (y/N): ")
        if answer.lower() != "y":
            print("取消")
            return

    for _, p in bad_files:
        p.unlink()
    print(f"\n[ok] 已删除 {len(bad_files)} 个污染文件。请重新运行 download 命令补回 CSV。")


def cmd_refresh_session(args: argparse.Namespace) -> None:
    """从浏览器提取完整会话参数（需要先在浏览器打开 DFG 页面）

    使用方法:
      1. 在浏览器中打开 partners.facebook.com/data_for_good/data/
      2. 打开 DevTools → Network → 找到任一 api/graphql 请求
      3. 复制请求体（Form Data）
      4. 运行: python scripts/dfg_downloader.py refresh-session --body "av=123&..."
    """
    body = args.body
    params: dict[str, str] = {}
    for part in body.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            params[urllib.parse.unquote(k)] = urllib.parse.unquote(v)

    # 映射关键字段
    sp: dict[str, str] = {}
    key_map = {
        "fb_dtsg": "fb_dtsg",
        "lsd": "lsd",
        "__user": "user_id",
        "__hsi": "__hsi",
        "__rev": "__rev",
        "__hs": "__hs",
        "__spin_r": "__spin_r",
        "__spin_b": "__spin_b",
        "__spin_t": "__spin_t",
        "__ccg": "__ccg",
        "jazoest": "jazoest",
        "__dyn": "__dyn",
        "__hsdp": "__hsdp",
        "__hblp": "__hblp",
        "__s": "__s",
    }
    for form_key, store_key in key_map.items():
        if form_key in params:
            sp[store_key] = params[form_key]

    sp["timestamp"] = str(int(time.time()))
    _save_session_params(sp)
    print(f"[ok] 已提取 {len(sp)} 个参数并保存到 {TOKEN_CACHE_FILE}")
    for k, v in sp.items():
        display = v[:40] + "..." if len(v) > 40 else v
        print(f"  {k}: {display}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Facebook Data for Good 自动数据采集工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # catalog 命令
    sub.add_parser("catalog", help="获取全部数据集目录")

    # list 命令
    p_list = sub.add_parser("list", help="列出目录中的数据集")
    p_list.add_argument("--type", help="按数据类型筛选 (Population/Movement/Network/Business)")
    p_list.add_argument("--country", help="按国家筛选")

    # download 命令
    p_dl = sub.add_parser("download", help="下载数据集")
    p_dl.add_argument("--dataset-id", help="指定数据集 ID")
    p_dl.add_argument("--name", help="按名称关键词筛选")
    p_dl.add_argument("--type", help="按数据类型筛选 (Population/Movement/Network/Business)")
    p_dl.add_argument("--country", help="按国家筛选")
    p_dl.add_argument("--max-dates", type=int, default=100, help="最大下载天数 (默认 100)")
    p_dl.add_argument("--end-date", default="", help="覆盖 catalog 的 date_range_end（格式：YYYY-MM-DD HH:MM）")
    p_dl.add_argument("--format", default="csv",
                       help="下载格式: csv (默认) / geotiff / geojson / all")
    p_dl.add_argument("--yes", "-y", action="store_true", help="跳过确认直接下载")

    # set-token 命令
    p_token = sub.add_parser("set-token", help="手动设置认证 token")
    p_token.add_argument("fb_dtsg", help="fb_dtsg token")
    p_token.add_argument("lsd", help="lsd token")

    # purge-bad 命令
    p_purge = sub.add_parser("purge-bad", help="扫描并删除被 TIFF/JSON 污染的 .csv 文件")
    p_purge.add_argument("--yes", "-y", action="store_true", help="跳过确认直接删除")

    # refresh-session 命令
    p_refresh = sub.add_parser("refresh-session", help="从浏览器请求体提取完整会话参数")
    p_refresh.add_argument("--body", required=True,
                           help="从 DevTools 复制的 GraphQL 请求体 (Form Data)")

    args = parser.parse_args()

    if args.command == "catalog":
        cmd_catalog(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "download":
        cmd_download(args)
    elif args.command == "set-token":
        cmd_set_token(args)
    elif args.command == "purge-bad":
        cmd_purge_bad(args)
    elif args.command == "refresh-session":
        cmd_refresh_session(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
