"""通过 GraphQL API 获取全部 83 个 Data for Good 数据集信息"""
import sys, io, json, csv, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from urllib.parse import urlencode
from curl_cffi import requests as curl_requests

COOKIE_FILE = r"E:\newdesktop\Disaster\config\cookie.json"
PROXIES = {"http": "socks5h://127.0.0.1:10808", "https": "socks5h://127.0.0.1:10808"}

# 从浏览器抓包获取的关键参数
API_URL = "https://partners.facebook.com/api/graphql/"
DOC_ID = "9656680804428472"
USER_ID = "100095409033268"

# 从浏览器抓包获取的动态参数
FB_DTSG = "NAfvxQGmYEOzg5iZBKhM4h5J6nL0ivC4x0w-32s4Ib7KYDgclQxigyw:28:1743474718"
LSD = "JOtXXP3I__9Xvtu71L3M4A"
HSI = "7603581622273900281"
REV = "1033020866"
SPIN_T = "1770346803"

# 加载 cookie
with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies_raw = json.load(f)
cookie_str = "; ".join(f'{c["name"]}={c["value"]}' for c in cookies_raw)

# 也使用浏览器的实际 cookie (从抓包获取)
BROWSER_COOKIE = (
    "datr=FVmFaZ1egWsubDCQb2tMic7I; "
    "fr=054hp0KsppS8nYH67..BphVkV..AAA.0.0.BphVkV.AWe9T3S7FGlZUICz5Df6-WOC5-A; "
    "sb=FVmFaaTFGLyKNl2qDxRYLemR; "
    "ps_l=1; "
    "xs=28%3Al2uTeapL-yAyPg%3A2%3A1743474718%3A-1%3A-1%3A%3AAcwMsXrxvGmZN_iLB2GMTLBHIO4ytSEf9aZKIOm53Q; "
    "c_user=100095409033268; "
    "presence=C%7B%22t3%22%3A%5B%5D%2C%22utc3%22%3A1770337520541%2C%22v%22%3A1%7D; "
    "ps_n=1; "
    "wd=1912x914"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://partners.facebook.com",
    "Referer": "https://partners.facebook.com/data_for_good/data/?partner_id=274171648108880&section=25&lsrc=lb",
    "X-FB-Friendly-Name": "DataForGoodDatasetQueryContextQuery",
    "X-FB-LSD": LSD,
    "Cookie": BROWSER_COOKIE,
    "Accept": "*/*",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


def build_request_body(variables: dict, req_num: int = 3) -> str:
    """构造和浏览器一样的请求体"""
    params = {
        "av": USER_ID,
        "__aaid": "0",
        "__user": USER_ID,
        "__a": "1",
        "__req": str(req_num),
        "__hs": "20490.BP:DEFAULT.2.0...0",
        "dpr": "1",
        "__ccg": "EXCELLENT",
        "__rev": REV,
        "__s": "vioqeo:94utw8:3dulhg",
        "__hsi": HSI,
        "__dyn": "7xeUmxa3-Q5E5ObwKBAgc9o9E6u5U4e1Fx-ewSwMxW4E2czobo1nEhw9-0r-q1ew6ywaq1xwEwgo9o1vohwLzE885W0IU9k2C0iK2Sq1DwaOfwbK1dw8y1iwmE2ewnE2xzo4G0muazo11E2Zxi3Uwowqo3KwDwr86a3Cq1BzE4O1ZwtXw4Ww5bxq0So6a",
        "__hsdp": "gSMF7ETa8zPBnxMgAgjFCcQFQOprrguCGyh089p4E9WzU8E4B1S4F-XGQ7K2Im7e0DA0jy-0SEfE20g0T20Fbw6NBw2iE0beo0szw1tq0dMw2CE1Mo0-W0Uo04x6",
        "__hblp": "0QwaC2e3Sdw7Rw2vo7u0EE760sm0qy2y0GUbU0JS1pw1RK1Zw0zAgC8gO059U0bHE0Me1vwaS0fnwkGu2u9Dw7cw0xxw5Gw",
        "fb_dtsg": FB_DTSG,
        "jazoest": "25454",
        "lsd": LSD,
        "__spin_r": REV,
        "__spin_b": "trunk",
        "__spin_t": SPIN_T,
        "__jssesw": "1",
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "DataForGoodDatasetQueryContextQuery",
        "server_timestamps": "true",
        "variables": json.dumps(variables),
        "doc_id": DOC_ID,
    }
    return urlencode(params)


def fetch_datasets(cursor: str = None, count: int = 100) -> dict:
    """获取一页数据集"""
    variables = {
        "name": "",
        "mapTypes": [],
        "countries": [],
        "include_test_data": False,
        "include_discontinued": False,
        "first": count,
    }
    if cursor:
        variables["cursor"] = cursor

    body = build_request_body(variables)
    r = curl_requests.post(
        API_URL,
        headers=HEADERS,
        data=body,
        proxies=PROXIES,
        impersonate="chrome110",
        timeout=30,
    )

    if r.status_code != 200:
        print(f"  [ERROR] 状态码: {r.status_code}")
        print(f"  {r.text[:500]}")
        return None

    text = r.text
    if text.startswith("for (;;);"):
        text = text[len("for (;;);"):]

    return json.loads(text)


def parse_edge(edge: dict) -> dict:
    """解析单个数据集 edge"""
    node = edge["node"]
    ds = node["dfg_default_dataset"]["nodes"][0]

    countries = []
    if ds.get("crisis"):
        for cn in ds["crisis"].get("countries", {}).get("nodes", []):
            if cn["iso_name"] != "Global":
                countries.append(cn["iso_name"])

    return {
        "id": ds["id"],
        "collection_id": node["id"],
        "name": ds["display_name"],
        "type": ds["collection_title"],
        "map_type": ds.get("map_type_title", ""),
        "countries": ", ".join(countries) if countries else "Global",
        "date_start": ds.get("date_range_start", ""),
        "date_end": ds.get("date_range_end", ""),
        "download_types": ", ".join(ds.get("downloadable_resource_types", [])),
        "hours_in_window": ds.get("hours_in_window", 0),
        "max_bulk_days": ds.get("max_days_in_bulk_download", 0),
    }


# ===== 主流程 =====
print("开始获取所有数据集...")
all_datasets = []
cursor = None
page = 0

while True:
    page += 1
    print(f"\n--- 第 {page} 页 (cursor: {str(cursor)[:30] if cursor else 'None'}) ---")

    result = fetch_datasets(cursor)
    if not result:
        break

    collections = result["data"]["xfb_dfg_dataset_collections"]
    edges = collections["edges"]
    total = collections["count"]

    print(f"  总数: {total}, 本页: {len(edges)}")

    if not edges:
        break

    for edge in edges:
        try:
            ds = parse_edge(edge)
            all_datasets.append(ds)
        except Exception as e:
            print(f"  [WARN] 解析失败: {e}")

    # 获取下一页游标 (使用 page_info.end_cursor)
    page_info = collections.get("page_info", {})
    has_next = page_info.get("has_next_page", False)
    cursor = page_info.get("end_cursor")
    if not has_next or not cursor or len(all_datasets) >= total:
        break

    # 控制请求频率，避免封号
    time.sleep(2)

# 输出结果
print(f"\n{'=' * 80}")
print(f"共获取 {len(all_datasets)} 个数据集")

# 类型统计
type_counts = {}
for ds in all_datasets:
    t = ds["type"]
    type_counts[t] = type_counts.get(t, 0) + 1
print("\n数据集类型:")
for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
    print(f"  {t}: {c}")

# 国家统计
country_counts = {}
for ds in all_datasets:
    for c in ds["countries"].split(", "):
        country_counts[c] = country_counts.get(c, 0) + 1
print("\n国家分布:")
for c, cnt in sorted(country_counts.items(), key=lambda x: -x[1])[:15]:
    print(f"  {c}: {cnt}")

# 打印完整列表
print(f"\n{'=' * 80}")
print("完整数据集列表:")
for i, ds in enumerate(all_datasets, 1):
    print(f"  {i:3d}. [{ds['type'][:25]:25s}] {ds['name']}")
    print(f"       {ds['countries']} | {ds['date_start']} ~ {ds['date_end']}")

# 保存 CSV
csv_path = "datasets_catalog.csv"
if all_datasets:
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=all_datasets[0].keys())
        writer.writeheader()
        writer.writerows(all_datasets)
    print(f"\n已保存到: {csv_path}")

# 保存 JSON
json_path = "datasets_catalog.json"
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(all_datasets, f, ensure_ascii=False, indent=2)
print(f"已保存到: {json_path}")
