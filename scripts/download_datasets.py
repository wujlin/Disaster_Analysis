#!/usr/bin/env python3
"""
Facebook Data for Good — 自动化数据下载脚本

功能：
  1. 从 config/cookie.json 读取 Cookie 进行身份认证
  2. 自动从页面提取 fb_dtsg (CSRF token)
  3. 通过 GraphQL 搜索获取完整数据集目录
  4. 批量下载指定数据集的 CSV ZIP 文件

用法：
  # 列出所有可用数据集
  python scripts/download_datasets.py --list

  # 按关键词筛选并列出
  python scripts/download_datasets.py --list --filter "earthquake"

  # 下载指定 dataset_id
  python scripts/download_datasets.py --download --ids 1603570647757603

  # 下载所有匹配关键词的数据集
  python scripts/download_datasets.py --download --filter "flooding"

  # 刷新数据集目录缓存
  python scripts/download_datasets.py --refresh-catalog

依赖：pip install curl_cffi
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

try:
    from curl_cffi import requests as cffi_requests  # type: ignore
except ImportError:
    print("需要安装 curl_cffi: pip install curl_cffi")
    sys.exit(1)

# ── 常量 ──────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
COOKIE_FILE = REPO_ROOT / "config" / "cookie.json"
CATALOG_FILE = REPO_ROOT / "datasets_catalog.json"
DOWNLOAD_DIR = REPO_ROOT / "datasets_downloads"

PARTNER_ID = "274171648108880"
BASE_URL = "https://partners.facebook.com"
DATA_PAGE_URL = f"{BASE_URL}/data_for_good/data/?partner_id={PARTNER_ID}&section=25&lsrc=lb"
GRAPHQL_URL = f"{BASE_URL}/api/graphql/"
BULK_DOWNLOAD_URL = f"{BASE_URL}/data_for_good/bulk_download/"

SEARCH_KEYWORDS = [
    "earthquake", "hurricane", "flood", "storm", "typhoon",
    "cyclone", "tornado", "wildfire", "volcano", "tsunami",
    "drought", "landslide", "winter", "heat",
]

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}


# ── Cookie 处理 ──────────────────────────────────────────────────────
def load_cookies(path: Path = COOKIE_FILE) -> dict[str, str]:
    """从 cookie.json 加载 Cookie（Netscape / EditThisCookie 格式均支持）。"""
    raw = json.loads(path.read_text(encoding="utf-8"))
    cookies: dict[str, str] = {}
    for c in raw:
        name = c.get("name", "")
        value = c.get("value", "")
        domain = c.get("domain", "")
        if name and value and ("facebook.com" in domain or "partners" in domain):
            cookies[name] = value
    return cookies


def cookies_to_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


# ── Session 封装 ─────────────────────────────────────────────────────
class FBSession:
    """封装 Facebook 认证 Session。"""

    def __init__(self, cookies: dict[str, str]):
        self.cookies = cookies
        self.fb_dtsg: str | None = None
        self.lsd: str | None = None
        self.user_id: str | None = cookies.get("c_user")

    def _make_session(self) -> cffi_requests.Session:
        # chrome110 兼容 Windows，若失败则不使用 impersonate
        try:
            s = cffi_requests.Session(impersonate="chrome110")
        except Exception:
            s = cffi_requests.Session()
        for k, v in self.cookies.items():
            s.cookies.set(k, v, domain=".facebook.com")
        return s

    def extract_fb_dtsg(self) -> str:
        """访问 Data for Good 页面，提取 fb_dtsg CSRF token。"""
        print("[*] 正在获取 fb_dtsg token ...")
        s = self._make_session()
        resp = s.get(DATA_PAGE_URL, headers=BROWSER_HEADERS, timeout=30)
        resp.raise_for_status()

        html = resp.text
        # 尝试多种正则匹配
        patterns = [
            r'"DTSGInitialData".*?"token"\s*:\s*"([^"]+)"',
            r'name="fb_dtsg"\s+value="([^"]+)"',
            r'"dtsg"\s*:\s*\{"token"\s*:\s*"([^"]+)"',
            r'"fb_dtsg"\s*:\s*"([^"]+)"',
        ]
        for pat in patterns:
            m = re.search(pat, html)
            if m:
                self.fb_dtsg = m.group(1)
                print(f"[+] 成功提取 fb_dtsg: {self.fb_dtsg[:30]}...")
                return self.fb_dtsg

        # 备选：从 LSD token 提取
        m_lsd = re.search(r'"LSD".*?"token"\s*:\s*"([^"]+)"', html)
        if m_lsd:
            self.lsd = m_lsd.group(1)

        raise RuntimeError(
            "无法从页面提取 fb_dtsg token。Cookie 可能已过期，请刷新 cookie.json。"
        )

    def graphql_search(self, keyword: str) -> list[dict]:
        """通过 GraphQL 搜索数据集。"""
        if not self.fb_dtsg:
            self.extract_fb_dtsg()

        s = self._make_session()
        # doc_id from intercepted requests
        doc_id = "9893204754036604"
        variables = {
            "partnerId": PARTNER_ID,
            "searchQuery": keyword,
            "includeDiscontinued": True,
        }
        data = {
            "fb_dtsg": self.fb_dtsg,
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": "DataForGoodDatasetQueryContextQuery",
            "variables": json.dumps(variables),
            "doc_id": doc_id,
        }
        headers = {**BROWSER_HEADERS, "Content-Type": "application/x-www-form-urlencoded"}
        resp = s.post(GRAPHQL_URL, data=data, headers=headers, timeout=30)
        resp.raise_for_status()

        result = resp.json()
        edges = (
            result.get("data", {})
            .get("xfb_dfg_dataset_collections", {})
            .get("edges", [])
        )

        datasets = []
        for edge in edges:
            node = edge.get("node", {})
            coll_name = node.get("name", "")
            coll_id = node.get("id", "")
            for ds_edge in node.get("datasets", {}).get("edges", []):
                ds = ds_edge.get("node", {})
                ds_info = ds.get("dataset_info", {})
                dl_info = ds.get("download_info", {})
                date_range = ds_info.get("date_range", {})
                datasets.append({
                    "id": ds.get("id", ""),
                    "collection_id": coll_id,
                    "name": coll_name,
                    "type": ds_info.get("type_display_name", ""),
                    "map_type": ds_info.get("map_type_display_name", ""),
                    "countries": ", ".join(
                        c.get("name", "") for c in ds_info.get("countries", [])
                    ),
                    "date_start": date_range.get("start", ""),
                    "date_end": date_range.get("end", ""),
                    "download_types": ", ".join(
                        t.get("type", "") for t in dl_info.get("download_types", [])
                    ),
                    "hours_in_window": dl_info.get("hours_in_window", 8),
                    "max_bulk_days": dl_info.get("max_date_range_length_in_days", 0),
                    "crisis_end_date": ds.get("crisis_end_date", 0),
                })
        return datasets

    def refresh_catalog(self) -> list[dict]:
        """通过多关键词搜索构建完整数据集目录。"""
        print(f"[*] 正在刷新数据集目录（搜索 {len(SEARCH_KEYWORDS)} 个关键词）...")
        seen_ids: set[str] = set()
        all_datasets: list[dict] = []

        for kw in SEARCH_KEYWORDS:
            print(f"  搜索: {kw} ...", end=" ", flush=True)
            try:
                results = self.graphql_search(kw)
                new_count = 0
                for ds in results:
                    if ds["id"] not in seen_ids:
                        seen_ids.add(ds["id"])
                        ds["idx"] = len(all_datasets) + 1
                        all_datasets.append(ds)
                        new_count += 1
                print(f"找到 {len(results)} 个, 新增 {new_count}")
            except Exception as e:
                print(f"失败: {e}")
            time.sleep(1)  # 限速

        # 保存
        CATALOG_FILE.write_text(
            json.dumps(all_datasets, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[+] 目录已保存: {CATALOG_FILE} ({len(all_datasets)} 个数据集)")
        return all_datasets

    def download_dataset(
        self,
        dataset_id: str,
        start_date: str,
        end_date: str,
        resource_type: str = "downloadable_csv",
        output_dir: Path | None = None,
    ) -> Path | None:
        """下载单个数据集的 ZIP 文件。"""
        if not self.fb_dtsg:
            self.extract_fb_dtsg()

        out_dir = output_dir or DOWNLOAD_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        s = self._make_session()
        data = {
            "resource_type": resource_type,
            "partner_id": PARTNER_ID,
            "start_date": start_date,
            "end_date": end_date,
            "dataset_id": dataset_id,
            "fb_dtsg": self.fb_dtsg,
        }
        headers = {
            **BROWSER_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": BASE_URL,
            "Referer": DATA_PAGE_URL,
        }

        print(f"  下载中: dataset_id={dataset_id}, {start_date} → {end_date} ...")
        resp = s.post(BULK_DOWNLOAD_URL, data=data, headers=headers, timeout=120)

        if resp.status_code != 200:
            print(f"  ✗ HTTP {resp.status_code}")
            return None

        # 提取文件名
        cd = resp.headers.get("content-disposition", "")
        m = re.search(r'filename=(.+?)(?:;|$)', cd)
        if m:
            filename = m.group(1).strip('"').strip()
        else:
            filename = f"{dataset_id}_{start_date}_{end_date}.zip"

        out_path = out_dir / filename
        out_path.write_bytes(resp.content)
        size_mb = len(resp.content) / 1024 / 1024
        print(f"  ✓ 已保存: {out_path.name} ({size_mb:.2f} MB)")
        return out_path

    def download_dataset_full(
        self,
        ds: dict,
        output_dir: Path | None = None,
    ) -> list[Path]:
        """根据数据集元数据，自动分批下载全部日期范围的数据。"""
        dataset_id = ds["id"]
        name = ds.get("name", "unknown")
        ds_type = ds.get("type", "unknown")
        date_start_str = ds.get("date_start", "")
        date_end_str = ds.get("date_end", "")
        max_bulk_days = ds.get("max_bulk_days", 7)

        # 解析日期
        try:
            date_start = datetime.strptime(date_start_str[:10], "%Y-%m-%d")
            date_end = datetime.strptime(date_end_str[:10], "%Y-%m-%d")
        except (ValueError, IndexError):
            print(f"  ⚠ 日期无效: {date_start_str} ~ {date_end_str}, 跳过")
            return []

        # 异常日期过滤
        if date_start.year > 2900 or date_end.year < 1900:
            print(f"  ⚠ 日期异常 ({date_start_str} ~ {date_end_str}), 跳过")
            return []

        # 确定资源类型
        dl_types = ds.get("download_types", "")
        if "DOWNLOADABLE_CSV" in dl_types:
            resource_type = "downloadable_csv"
        elif "DOWNLOADABLE_GEOTIFF" in dl_types:
            resource_type = "downloadable_geotiff"
        else:
            print(f"  ⚠ 无可下载类型: {dl_types}, 跳过")
            return []

        # 构建输出目录: datasets_downloads/<event_name>/<type>/
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)[:80]
        safe_type = re.sub(r'[<>:"/\\|?*]', '_', ds_type)[:60]
        ds_dir = (output_dir or DOWNLOAD_DIR) / safe_name / safe_type
        ds_dir.mkdir(parents=True, exist_ok=True)

        # 分批下载
        total_days = (date_end - date_start).days
        if total_days <= 0:
            total_days = 1

        batch_size = min(max_bulk_days, total_days) if max_bulk_days > 0 else total_days
        if batch_size <= 0:
            batch_size = total_days

        downloaded: list[Path] = []
        current = date_start
        while current < date_end:
            batch_end = min(current + timedelta(days=batch_size), date_end)
            s_str = current.strftime("%Y-%m-%d")
            e_str = batch_end.strftime("%Y-%m-%d")

            path = self.download_dataset(
                dataset_id=dataset_id,
                start_date=s_str,
                end_date=e_str,
                resource_type=resource_type,
                output_dir=ds_dir,
            )
            if path:
                downloaded.append(path)

            current = batch_end
            if current < date_end:
                time.sleep(2)  # 批次间限速

        return downloaded


# ── CLI ──────────────────────────────────────────────────────────────
def load_catalog() -> list[dict]:
    if CATALOG_FILE.exists():
        return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    return []


def filter_datasets(datasets: list[dict], keyword: str) -> list[dict]:
    kw = keyword.lower()
    return [
        ds for ds in datasets
        if kw in ds.get("name", "").lower()
        or kw in ds.get("type", "").lower()
        or kw in ds.get("countries", "").lower()
    ]


def print_dataset_table(datasets: list[dict]) -> None:
    if not datasets:
        print("(无匹配数据集)")
        return
    print(f"\n{'#':>3}  {'ID':>20}  {'类型':<40}  {'国家':<15}  {'日期范围':<25}  {'名称'}")
    print("─" * 140)
    for i, ds in enumerate(datasets, 1):
        ds_id = ds.get("id", "?")
        ds_type = ds.get("type", "?")[:38]
        countries = ds.get("countries", "?")[:13]
        date_s = ds.get("date_start", "?")[:10]
        date_e = ds.get("date_end", "?")[:10]
        name = ds.get("name", "?")[:60]
        print(f"{i:>3}  {ds_id:>20}  {ds_type:<40}  {countries:<15}  {date_s} ~ {date_e}  {name}")
    print(f"\n共 {len(datasets)} 个数据集")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Facebook Data for Good 数据下载工具"
    )
    parser.add_argument("--list", action="store_true", help="列出可用数据集")
    parser.add_argument("--download", action="store_true", help="下载数据集")
    parser.add_argument("--refresh-catalog", action="store_true", help="刷新数据集目录")
    parser.add_argument("--filter", type=str, default="", help="按关键词筛选")
    parser.add_argument("--ids", nargs="+", default=[], help="指定 dataset_id 下载")
    parser.add_argument("--output-dir", type=str, default="", help="输出目录")
    parser.add_argument("--cookie", type=str, default="", help="Cookie 文件路径")
    parser.add_argument("--dry-run", action="store_true", help="仅显示计划，不实际下载")
    args = parser.parse_args()

    cookie_path = Path(args.cookie) if args.cookie else COOKIE_FILE
    if not cookie_path.exists():
        print(f"✗ Cookie 文件不存在: {cookie_path}")
        sys.exit(1)

    cookies = load_cookies(cookie_path)
    session = FBSession(cookies)

    # 刷新目录
    if args.refresh_catalog:
        session.refresh_catalog()
        if not args.list and not args.download:
            return

    # 加载目录
    catalog = load_catalog()
    if not catalog and not args.refresh_catalog:
        print("[*] 目录为空，正在刷新...")
        catalog = session.refresh_catalog()

    # 筛选
    if args.filter:
        catalog = filter_datasets(catalog, args.filter)

    # 列出
    if args.list:
        print_dataset_table(catalog)
        return

    # 下载
    if args.download:
        out_dir = Path(args.output_dir) if args.output_dir else DOWNLOAD_DIR

        # 按 ID 筛选
        if args.ids:
            to_download = [ds for ds in catalog if ds.get("id") in args.ids]
        else:
            to_download = catalog

        if not to_download:
            print("✗ 没有匹配的数据集")
            sys.exit(1)

        print(f"\n[*] 计划下载 {len(to_download)} 个数据集到 {out_dir}")
        print_dataset_table(to_download)

        if args.dry_run:
            print("\n(dry-run 模式，不实际下载)")
            return

        print("\n" + "=" * 60)
        total_files = 0
        for i, ds in enumerate(to_download, 1):
            print(f"\n[{i}/{len(to_download)}] {ds.get('name', '?')} — {ds.get('type', '?')}")
            files = session.download_dataset_full(ds, output_dir=out_dir)
            total_files += len(files)
            time.sleep(2)  # 数据集间限速

        print(f"\n[+] 下载完成！共 {total_files} 个文件")

    if not args.list and not args.download and not args.refresh_catalog:
        parser.print_help()


if __name__ == "__main__":
    main()
