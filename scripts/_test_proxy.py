"""测试通过 curl_cffi (浏览器 TLS 指纹) 访问 Facebook Data for Good"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import json, re
from curl_cffi import requests as curl_requests

COOKIE_FILE = r"E:\newdesktop\Disaster\config\cookie.json"
PROXIES = {
    "http": "socks5h://127.0.0.1:10808",
    "https": "socks5h://127.0.0.1:10808",
}

# ---------- 加载 cookie ----------
with open(COOKIE_FILE, "r", encoding="utf-8") as f:
    cookies_raw = json.load(f)

# 构造 cookie 字符串
cookie_str = "; ".join(f'{c["name"]}={c["value"]}' for c in cookies_raw)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cookie": cookie_str,
    "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# ---------- 测试 1: Facebook 主页 ----------
print("=" * 60)
print("[测试 1] curl_cffi + 浏览器指纹 访问 Facebook")
try:
    r = curl_requests.get(
        "https://www.facebook.com/",
        headers=HEADERS,
        proxies=PROXIES,
        impersonate="chrome110",
        timeout=30,
    )
    print(f"  状态码: {r.status_code}, 长度: {len(r.text)}")

    # 查找 fb_dtsg
    fb_dtsg = None
    for pattern in [
        r'"DTSGInitialData",\[\],\{"token":"([^"]+)"',
        r'name="fb_dtsg" value="([^"]+)"',
        r'"dtsg":\{"token":"([^"]+)"',
        r'"token":"([^"]+?)","async_get_token"',
    ]:
        m = re.search(pattern, r.text)
        if m:
            fb_dtsg = m.group(1)
            print(f"  [OK] fb_dtsg: {fb_dtsg[:30]}...")
            break

    if not fb_dtsg:
        print("  [WARN] 未找到 fb_dtsg")
        # 看看是否已登录
        if "c_user" in r.text or "userID" in r.text:
            print("  但似乎已登录")
        if "login" in r.url.lower():
            print("  [FAIL] 被重定向到登录页，cookie 已过期")
        # 保存调试
        with open("_debug_fb_curl.html", "w", encoding="utf-8") as f:
            f.write(r.text[:50000])
        print("  已保存前 50000 字符到 _debug_fb_curl.html")
except Exception as e:
    print(f"  [ERROR] {e}")
    fb_dtsg = None

# ---------- 测试 2: Data for Good 页面 ----------
print("\n" + "=" * 60)
print("[测试 2] 访问 Data for Good 页面")
try:
    url = "https://partners.facebook.com/data_for_good/data/?partner_id=274171648108880&section=25&lsrc=lb"
    r = curl_requests.get(
        url,
        headers=HEADERS,
        proxies=PROXIES,
        impersonate="chrome110",
        timeout=30,
    )
    print(f"  状态码: {r.status_code}")
    print(f"  最终 URL: {r.url}")
    print(f"  长度: {len(r.text)}")

    if r.status_code == 200 and len(r.text) > 2000:
        print("  [OK] 页面可访问!")
        # 查找数据集信息
        if "Flooding" in r.text or "Movement" in r.text:
            print("  [OK] 页面包含数据集关键词")
        # 查找 fb_dtsg
        if not fb_dtsg:
            for pattern in [
                r'"DTSGInitialData",\[\],\{"token":"([^"]+)"',
                r'"token":"([^"]+?)","async_get_token"',
            ]:
                m = re.search(pattern, r.text)
                if m:
                    fb_dtsg = m.group(1)
                    print(f"  [OK] 从 partners 页面获取 fb_dtsg: {fb_dtsg[:30]}...")
                    break
        # 保存页面
        with open("_debug_partners.html", "w", encoding="utf-8") as f:
            f.write(r.text[:100000])
        print("  已保存页面到 _debug_partners.html")
    else:
        print(f"  [WARN] 状态异常")
        print(f"  前 500 字: {r.text[:500]}")
except Exception as e:
    print(f"  [ERROR] {e}")

print("\n" + "=" * 60)
print("测试完成")
if fb_dtsg:
    print(f"\n>> fb_dtsg 已获取，可以继续进行 API 调用")
else:
    print(f"\n>> 未获取 fb_dtsg，可能需要换方案（浏览器 MCP + 系统代理）")
