#!/usr/bin/env python3
"""
Probe Meta (Facebook) Data for Good partner portal with an existing cookie export.

Design goals:
- Safety first: minimal page loads, no bulk crawling by default.
- Reproducible: write a small JSON report + screenshot/html to an output directory.

Typical usage (after you have internet access and Playwright installed):

  python scripts/fbd4g_probe.py --dataset-name "The Flooding Across Northwestern Colombia"

Notes:
- `config/cookie.json` is expected to be a Chrome cookie export (list of dicts) for `.facebook.com`.
- This script never prints cookie values.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_LISTING_URL = (
    "https://partners.facebook.com/data_for_good/data/"
    "?partner_id=274171648108880&section=25&lsrc=lb"
)


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _load_cookie_export(cookie_file: Path) -> List[Dict[str, Any]]:
    data = json.loads(cookie_file.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "cookies" in data:
        data = data["cookies"]
    if not isinstance(data, list):
        raise ValueError(f"Unsupported cookie export format: {type(data)}")
    cookies: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        cookies.append(item)
    return cookies


def _map_same_site(value: Any) -> Optional[str]:
    if not value:
        return None
    s = str(value).strip().lower()
    if s in {"no_restriction", "none"}:
        return "None"
    if s in {"lax"}:
        return "Lax"
    if s in {"strict"}:
        return "Strict"
    return None


def _to_playwright_cookies(cookie_export: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cookies: List[Dict[str, Any]] = []
    for c in cookie_export:
        name = c.get("name")
        value = c.get("value")
        domain = c.get("domain")
        path = c.get("path") or "/"
        if not (name and value and domain):
            continue

        same_site = _map_same_site(c.get("sameSite"))
        cookie: Dict[str, Any] = {
            "name": str(name),
            "value": str(value),
            # Leading dot is obsolete; Playwright accepts "facebook.com" for domain cookies.
            "domain": str(domain).lstrip("."),
            "path": str(path),
            "httpOnly": bool(c.get("httpOnly")),
            "secure": bool(c.get("secure", True)),
        }
        if same_site:
            cookie["sameSite"] = same_site

        # Chrome exports `expirationDate` as epoch seconds (float).
        if not bool(c.get("session")) and c.get("expirationDate") is not None:
            try:
                cookie["expires"] = int(float(c["expirationDate"]))
            except Exception:
                pass

        cookies.append(cookie)
    return cookies


def _summarize_cookie_export(cookie_export: List[Dict[str, Any]]) -> Dict[str, Any]:
    domains: Dict[str, int] = {}
    http_only_true = 0
    http_only_false = 0
    names: List[str] = []
    for c in cookie_export:
        dom = str(c.get("domain") or "")
        domains[dom] = domains.get(dom, 0) + 1
        if bool(c.get("httpOnly")):
            http_only_true += 1
        else:
            http_only_false += 1
        n = c.get("name")
        if n:
            names.append(str(n))
    return {
        "count": len(cookie_export),
        "domains_top": sorted(domains.items(), key=lambda kv: kv[1], reverse=True)[:10],
        "httpOnly": {"true": http_only_true, "false": http_only_false},
        "names_sample": names[:12],
    }


def _extract_links(page: Any) -> List[Dict[str, str]]:
    # Keep it generic: extract all links and let downstream filtering decide.
    return page.evaluate(
        """() => {
  const anchors = Array.from(document.querySelectorAll('a'));
  return anchors
    .map(a => ({ href: a.href || '', text: (a.innerText || '').trim() }))
    .filter(x => x.href && x.href.startsWith('http'));
}"""
    )


def _detect_login_page(page: Any) -> Tuple[bool, List[str]]:
    signals: List[str] = []
    url = (page.url or "").lower()
    title = (page.title() or "").lower()
    if "login" in url or "checkpoint" in url:
        signals.append("url_contains_login_or_checkpoint")
    if "log in" in title or "login" in title:
        signals.append("title_contains_login")
    # Common login inputs (best-effort)
    try:
        if page.locator("input[name='email'], input[name='pass']").count() > 0:
            signals.append("has_email_or_pass_input")
    except Exception:
        pass
    return (len(signals) > 0), signals


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_LISTING_URL)
    parser.add_argument("--cookie-file", default="config/cookie.json")
    parser.add_argument("--dataset-name", default=None)
    parser.add_argument("--out-dir", default="outputs/_tmp_fbd4g_probe")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--slowmo-ms", type=int, default=0)
    parser.add_argument("--sleep-ms", type=int, default=800)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    _safe_mkdir(out_dir)

    cookie_file = Path(args.cookie_file)
    if not cookie_file.exists():
        raise FileNotFoundError(f"Cookie file not found: {cookie_file}")

    cookie_export = _load_cookie_export(cookie_file)
    cookie_summary = _summarize_cookie_export(cookie_export)
    cookies = _to_playwright_cookies(cookie_export)

    report: Dict[str, Any] = {
        "ts_utc": _utc_now_iso(),
        "requested_url": args.url,
        "dataset_name": args.dataset_name,
        "cookie_file": str(cookie_file),
        "cookie_summary": cookie_summary,
        "env_proxy": {
            "http_proxy": os.environ.get("http_proxy"),
            "https_proxy": os.environ.get("https_proxy"),
            "all_proxy": os.environ.get("all_proxy"),
        },
        "playwright": {},
    }

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as e:
        report["playwright"]["error"] = f"Playwright not available: {type(e).__name__}: {e}"
        (out_dir / "probe.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[fbd4g_probe] Playwright not installed. Wrote report to: {out_dir / 'probe.json'}")
        print("[fbd4g_probe] Install: pip install playwright && playwright install chromium")
        return 2

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, slow_mo=args.slowmo_ms)
        context = browser.new_context()
        context.add_cookies(cookies)

        page = context.new_page()
        page.set_default_timeout(args.timeout_ms)

        page.goto(args.url, wait_until="domcontentloaded")
        page.wait_for_timeout(args.sleep_ms)

        is_login, login_signals = _detect_login_page(page)

        report["playwright"].update(
            {
                "final_url": page.url,
                "title": page.title(),
                "is_login_page": is_login,
                "login_signals": login_signals,
            }
        )

        # Save raw artifacts for local debugging.
        try:
            (out_dir / "page.html").write_text(page.content(), encoding="utf-8")
        except Exception as e:
            report["playwright"]["page_html_error"] = f"{type(e).__name__}: {e}"

        try:
            page.screenshot(path=str(out_dir / "page.png"), full_page=True)
        except Exception as e:
            report["playwright"]["screenshot_error"] = f"{type(e).__name__}: {e}"

        # Optional: try to open a specific dataset and extract links from the Files tab.
        if args.dataset_name and not is_login:
            report["dataset"] = {"name": args.dataset_name}
            try:
                # Best-effort search box interaction.
                search = page.locator("input[placeholder*='Find datasets']")
                if search.count() > 0:
                    search.first.fill(args.dataset_name)
                    page.wait_for_timeout(200)
                # Click dataset card by text.
                page.get_by_text(args.dataset_name, exact=False).first.click(timeout=args.timeout_ms)
                page.wait_for_timeout(args.sleep_ms)
                report["dataset"]["url"] = page.url
                report["dataset"]["title"] = page.title()

                # Try Files tab.
                try:
                    page.get_by_text("Files", exact=True).click(timeout=5_000)
                    page.wait_for_timeout(args.sleep_ms)
                except Exception:
                    pass

                links = _extract_links(page)
                report["dataset"]["links_count"] = len(links)
                report["dataset"]["links"] = links[:500]

                try:
                    (out_dir / "dataset.html").write_text(page.content(), encoding="utf-8")
                    page.screenshot(path=str(out_dir / "dataset.png"), full_page=True)
                except Exception:
                    pass
            except Exception as e:
                report["dataset"]["error"] = f"{type(e).__name__}: {e}"

        browser.close()

    (out_dir / "probe.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[fbd4g_probe] Wrote: {out_dir / 'probe.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

