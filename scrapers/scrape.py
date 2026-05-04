#!/usr/bin/env python3
"""
Residency Tracker v2 - 多策略爬虫
- RSS / Atom feed(最稳)
- HTML + cloudscraper(绕 Cloudflare)
- 状态诊断面板
"""

import json
import re
import sys
import time
import random
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import yaml
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# 让 import generate_html 找得到
sys.path.insert(0, str(Path(__file__).parent))

# ============== 配置 ==============
ROOT = Path(__file__).parent.parent
CONFIG_FILE = ROOT / "sites.yaml"
DATA_FILE = ROOT / "data" / "calls.json"
SEEN_FILE = ROOT / "data" / "seen.json"
STATUS_FILE = ROOT / "data" / "status.json"

REQUEST_TIMEOUT = 25

# ============== HTTP 客户端 ==============
# cloudscraper 比 requests 多一层 Cloudflare 绕过
try:
    import cloudscraper
    SCRAPER = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'darwin', 'mobile': False}
    )
    print("✓ cloudscraper available")
except ImportError:
    import requests
    SCRAPER = requests.Session()
    print("⚠️ cloudscraper not installed, using requests")

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
]


def get_headers(referer=None):
    h = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8,ca;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }
    if referer:
        h["Referer"] = referer
    return h


def fetch(url, retries=2):
    """获取网页内容,返回 (BeautifulSoup, status_string)"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = SCRAPER.get(url, headers=get_headers(), timeout=REQUEST_TIMEOUT, allow_redirects=True)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "html.parser"), "ok"
            last_err = f"HTTP {r.status_code}"
            time.sleep(2 + attempt)
        except Exception as e:
            last_err = type(e).__name__
            time.sleep(2)
    return None, last_err


def fetch_raw(url, retries=2):
    """获取原始字节,用于 RSS / XML"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = SCRAPER.get(url, headers=get_headers(), timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                return r.content, "ok"
            last_err = f"HTTP {r.status_code}"
            time.sleep(2)
        except Exception as e:
            last_err = type(e).__name__
            time.sleep(2)
    return None, last_err


# ============== 工具 ==============
def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen():
    if SEEN_FILE.exists():
        try:
            with open(SEEN_FILE, encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}


def save_json(path, data):
    path.parent.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def hash_text(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def text_contains_any(text, keywords):
    if not keywords:
        return False
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def extract_deadline(text):
    """从文本里抽取截止日期。返回 (datetime, 原始字符串) 或 (None, None)"""
    if not text:
        return None, None
    text = text.replace("\u00a0", " ")

    month_patterns = {
        "january|jan|enero|ene|gener|gen": 1, "february|feb|febrero|febrer": 2,
        "march|mar|marzo|març": 3, "april|apr|abril": 4, "may|mayo|maig": 5,
        "june|jun|junio|juny": 6, "july|jul|julio|juliol": 7, "august|aug|agosto|agost": 8,
        "september|sep|sept|septiembre|setembre": 9, "october|oct|octubre": 10,
        "november|nov|noviembre|novembre": 11, "december|dec|diciembre|desembre": 12,
    }

    candidates = []
    deadline_keywords = r"(?:deadline|due|closes?|until|fins\s+al?|hasta|antes\s+del?|before|by|límit\s+de\s+presentació|plazo|expira|tanca\s+el)"

    # ISO 2026-05-25
    for m in re.finditer(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text):
        try:
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if 2025 <= d.year <= 2030:
                candidates.append((d, m.group(0)))
        except: pass

    # 25/5/2026
    for m in re.finditer(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", text):
        try:
            d = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if 2025 <= d.year <= 2030:
                candidates.append((d, m.group(0)))
        except: pass

    # "25 May 2026" / "25 de mayo de 2026"
    for month_re, month_num in month_patterns.items():
        for m in re.finditer(rf"(\d{{1,2}})(?:\s+de)?\s+(?:{month_re})(?:\s+de)?\s+(\d{{4}})", text, re.I):
            try:
                d = datetime(int(m.group(2)), month_num, int(m.group(1)))
                if 2025 <= d.year <= 2030:
                    candidates.append((d, m.group(0)))
            except: pass

    # "May 25, 2026"
    for month_re, month_num in month_patterns.items():
        for m in re.finditer(rf"(?:{month_re})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", text, re.I):
            try:
                d = datetime(int(m.group(2)), month_num, int(m.group(1)))
                if 2025 <= d.year <= 2030:
                    candidates.append((d, m.group(0)))
            except: pass

    if not candidates:
        return None, None

    # 优先选 deadline 关键词附近的
    for cand_date, cand_str in candidates:
        idx = text.find(cand_str)
        if idx > 0:
            window = text[max(0, idx - 80):idx + len(cand_str) + 20]
            if re.search(deadline_keywords, window, re.I):
                return cand_date, cand_str

    today = datetime.now()
    future = [(d, s) for d, s in candidates if d >= today - timedelta(days=7)]
    if future:
        future.sort()
        return future[0]

    candidates.sort()
    return candidates[0]


def score_call(text, priority_kw):
    text_lower = text.lower()
    matched = []
    for kw in priority_kw:
        if kw.lower() in text_lower:
            matched.append(kw)
    return len(matched), matched


# ============== RSS / Atom 解析 ==============
def scrape_rss(source, config):
    """解析 RSS / Atom feed"""
    print(f"\n[RSS] {source['name']}")
    raw, err = fetch_raw(source["url"])
    if raw is None:
        return [], f"❌ {err}"

    try:
        soup = BeautifulSoup(raw, "xml")
    except Exception:
        soup = BeautifulSoup(raw, "html.parser")

    items = soup.find_all(["item", "entry"])
    if not items:
        return [], "⚠️ no items in feed"

    priority_kw = config.get("priority_keywords", [])
    exclude_kw = config.get("exclude_keywords", [])
    source_keywords = source.get("keywords", [])
    found = []

    for item in items:
        title_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description") or item.find("summary") or item.find("content")
        pubdate_el = item.find("pubDate") or item.find("published") or item.find("updated")

        title = clean_text(title_el.get_text() if title_el else "")
        if link_el:
            href = link_el.get("href") or link_el.get_text()
            link = href.strip() if href else ""
        else:
            link = ""
        description = clean_text(BeautifulSoup(desc_el.get_text() if desc_el else "", "html.parser").get_text())

        if not title or not link:
            continue

        full_text = f"{title} {description}"

        # 如果配置里指定了 keywords,必须命中其中之一
        if source_keywords and not text_contains_any(full_text, source_keywords):
            continue

        # 排除关键词
        if text_contains_any(full_text, exclude_kw):
            continue

        deadline, deadline_str = extract_deadline(full_text)
        score, matched = score_call(full_text, priority_kw)

        snippet = description[:500] + ("..." if len(description) > 500 else "")

        item_data = {
            "id": hash_text(link),
            "title": title[:200],
            "url": link,
            "source": source["name"],
            "location": source.get("location", ""),
            "tags": source.get("tags", []),
            "snippet": snippet,
            "deadline": deadline.isoformat() if deadline else None,
            "deadline_raw": deadline_str,
            "priority_score": score,
            "matched_keywords": matched,
            "first_seen": datetime.now().isoformat(),
        }
        found.append(item_data)

    return found, f"✅ {len(found)} items"


# ============== 通用 HTML 爬虫 ==============
def scrape_html(source, config):
    """通用 HTML 爬虫 - 找页面里所有像 'open call' 的链接"""
    print(f"\n[HTML] {source['name']}")
    soup, err = fetch(source["url"])
    if soup is None:
        return [], f"❌ {err}"

    keywords = source.get("keywords", ["open call", "convocatoria", "residency"])
    priority_kw = config.get("priority_keywords", [])
    exclude_kw = config.get("exclude_keywords", [])

    seen_urls = set()
    found = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
            continue

        full_url = urljoin(source["url"], href)
        if full_url in seen_urls:
            continue

        link_text = clean_text(a.get_text())
        parent = a.find_parent(["article", "div", "li", "section", "p"]) or a.parent
        context = clean_text(parent.get_text()) if parent else link_text

        if not text_contains_any(link_text + " " + context, keywords):
            continue

        if any(skip in href.lower() for skip in [
            "facebook.com", "twitter.com", "instagram.com", "linkedin.com",
            "youtube.com", "/tag/", "/category/", "/author/", "x.com/"
        ]):
            continue

        # 同域名过滤
        try:
            site_domain = urlparse(source["url"]).netloc.lower().replace("www.", "")
            link_domain = urlparse(full_url).netloc.lower().replace("www.", "")
            if site_domain not in link_domain and link_domain not in site_domain:
                continue
        except:
            continue

        if text_contains_any(context, exclude_kw):
            continue

        seen_urls.add(full_url)

        deadline, deadline_str = extract_deadline(context)
        score, matched = score_call(context, priority_kw)

        title = link_text if len(link_text) > 5 else ""
        if not title and parent:
            heading = parent.find(["h1", "h2", "h3", "h4"])
            if heading:
                title = clean_text(heading.get_text())
        if len(title) < 5:
            continue

        snippet = context[:500] + ("..." if len(context) > 500 else "")

        found.append({
            "id": hash_text(full_url),
            "title": title[:200],
            "url": full_url,
            "source": source["name"],
            "location": source.get("location", ""),
            "tags": source.get("tags", []),
            "snippet": snippet,
            "deadline": deadline.isoformat() if deadline else None,
            "deadline_raw": deadline_str,
            "priority_score": score,
            "matched_keywords": matched,
            "first_seen": datetime.now().isoformat(),
        })

    by_url = {}
    for it in found:
        if it["url"] not in by_url or it["priority_score"] > by_url[it["url"]]["priority_score"]:
            by_url[it["url"]] = it

    return list(by_url.values()), f"✅ {len(by_url)} items"


# ============== 主流程 ==============
def main():
    config = load_config()
    seen = load_seen()
    today = datetime.now()

    all_calls = []
    statuses = []  # 每个 source 的状态

    for source in config["sources"]:
        try:
            stype = source.get("type", "html")
            if stype == "rss":
                calls, status = scrape_rss(source, config)
            else:
                calls, status = scrape_html(source, config)

            statuses.append({
                "name": source["name"],
                "type": stype,
                "url": source["url"],
                "status": status,
                "count": len(calls),
            })
            print(f"  → {status}")

            for c in calls:
                if c["id"] in seen:
                    c["first_seen"] = seen[c["id"]]
                    c["is_new"] = False
                else:
                    seen[c["id"]] = c["first_seen"]
                    c["is_new"] = True

            all_calls.extend(calls)
            time.sleep(1.5)
        except Exception as e:
            statuses.append({
                "name": source["name"],
                "type": source.get("type", "html"),
                "url": source["url"],
                "status": f"❌ exception: {type(e).__name__}: {str(e)[:80]}",
                "count": 0,
            })
            print(f"  ❌ Error: {e}", file=sys.stderr)

    # 过滤过期(超过 7 天)
    fresh = []
    for c in all_calls:
        if c["deadline"]:
            try:
                d = datetime.fromisoformat(c["deadline"])
                if d < today - timedelta(days=7):
                    continue
            except: pass
        fresh.append(c)

    # 按 URL 去重(整个数据集)
    by_url = {}
    for c in fresh:
        u = c["url"]
        if u not in by_url or c["priority_score"] > by_url[u]["priority_score"]:
            by_url[u] = c
    fresh = list(by_url.values())

    # 排序:有 deadline 的按截止日近→远;然后按契合度
    def sort_key(c):
        if c["deadline"]:
            try:
                d = datetime.fromisoformat(c["deadline"])
                days_left = (d - today).days
                return (0, days_left, -c["priority_score"])
            except: pass
        return (1, 0, -c["priority_score"])

    fresh.sort(key=sort_key)

    save_json(DATA_FILE, {
        "generated_at": today.isoformat(),
        "total": len(fresh),
        "calls": fresh,
    })
    save_json(SEEN_FILE, seen)
    save_json(STATUS_FILE, {
        "generated_at": today.isoformat(),
        "sources": statuses,
        "summary": {
            "total_sources": len(statuses),
            "ok": sum(1 for s in statuses if s["status"].startswith("✅")),
            "failed": sum(1 for s in statuses if s["status"].startswith("❌")),
            "warned": sum(1 for s in statuses if s["status"].startswith("⚠️")),
        }
    })

    # 生成 HTML
    from generate_html import generate
    generate(fresh, today, statuses)

    new_count = sum(1 for c in fresh if c["is_new"])
    print(f"\n✅ Done. {len(fresh)} calls ({new_count} new) from {len(statuses)} sources.")


if __name__ == "__main__":
    main()
