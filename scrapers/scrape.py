#!/usr/bin/env python3
"""
Residency Tracker - 主爬虫脚本
每天运行一次,爬取所有配置的网站,生成 calls.json 和 HTML 网页
"""

import json
import re
import sys
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# ============== 配置 ==============
ROOT = Path(__file__).parent.parent
CONFIG_FILE = ROOT / "sites.yaml"
DATA_FILE = ROOT / "data" / "calls.json"
SEEN_FILE = ROOT / "data" / "seen.json"
HTML_OUTPUT = ROOT / "docs" / "index.html"

# 让 import generate_html 找得到
sys.path.insert(0, str(Path(__file__).parent))

REQUEST_TIMEOUT = 20

# 多组浏览器 User-Agent,随机轮换
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
]

def get_headers():
    import random
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8,ca;q=0.7,zh;q=0.6",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",
    }

# ============== 工具函数 ==============
def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_seen():
    if SEEN_FILE.exists():
        with open(SEEN_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_seen(seen):
    SEEN_FILE.parent.mkdir(exist_ok=True)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)

def hash_text(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]

def fetch(url, retries=2):
    """请求一个页面,返回 BeautifulSoup 对象。失败重试 + 优雅降级"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=get_headers(), timeout=REQUEST_TIMEOUT, allow_redirects=True)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "html.parser")
            last_err = f"HTTP {r.status_code}"
            if r.status_code == 403:
                # 403 重试通常无用,但换 UA 可能有效
                time.sleep(3)
                continue
            if r.status_code >= 500:
                time.sleep(5)
                continue
            break  # 4xx 其他直接放弃
        except requests.exceptions.Timeout:
            last_err = "timeout"
            time.sleep(3)
        except Exception as e:
            last_err = str(e)[:100]
            time.sleep(2)
    print(f"  ⚠️ {url} -> {last_err}", file=sys.stderr)
    return None

def clean_text(text):
    """清洗文本"""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text

def text_contains_any(text, keywords):
    """文本是否包含任一关键词(大小写不敏感)"""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)

def extract_deadline(text):
    """从文本里尽力抽取一个截止日期。返回 (datetime, 原始字符串) 或 (None, None)"""
    if not text:
        return None, None
    text = text.replace("\u00a0", " ")

    # 月份名映射(英文 + 西班牙文 + 加泰兰)
    month_patterns = {
        "january|jan|enero|ene|gener|gen": 1, "february|feb|febrero|febrer": 2,
        "march|mar|marzo|març": 3, "april|apr|abril": 4, "may|mayo|maig": 5,
        "june|jun|junio|juny": 6, "july|jul|julio|juliol": 7, "august|aug|agosto|agost": 8,
        "september|sep|sept|septiembre|setembre": 9, "october|oct|octubre": 10,
        "november|nov|noviembre|novembre": 11, "december|dec|diciembre|desembre": 12,
    }

    candidates = []

    # 模式 1: "deadline: 25 May 2026" / "截止 5/25/2026" / "fins al 30 maig 2026"
    deadline_keywords = r"(?:deadline|due|closes?|until|fins\s+al?|hasta|antes\s+del?|before|by|límit\s+de\s+presentació|plazo|presentación|expiration|expira|tanca\s+el)"

    # ISO 格式 2026-05-25
    for m in re.finditer(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text):
        try:
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if d.year >= 2025 and d.year <= 2030:
                candidates.append((d, m.group(0)))
        except: pass

    # 25/5/2026 或 25-05-2026 (DMY)
    for m in re.finditer(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", text):
        try:
            d = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if d.year >= 2025 and d.year <= 2030:
                candidates.append((d, m.group(0)))
        except: pass

    # "25 May 2026" / "25 de mayo de 2026" / "25 maig 2026"
    for month_re, month_num in month_patterns.items():
        pattern = rf"(\d{{1,2}})(?:\s+de)?\s+(?:{month_re})(?:\s+de)?\s+(\d{{4}})"
        for m in re.finditer(pattern, text, re.I):
            try:
                d = datetime(int(m.group(2)), month_num, int(m.group(1)))
                if d.year >= 2025 and d.year <= 2030:
                    candidates.append((d, m.group(0)))
            except: pass

    # "May 25, 2026"
    for month_re, month_num in month_patterns.items():
        pattern = rf"(?:{month_re})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})"
        for m in re.finditer(pattern, text, re.I):
            try:
                d = datetime(int(m.group(2)), month_num, int(m.group(1)))
                if d.year >= 2025 and d.year <= 2030:
                    candidates.append((d, m.group(0)))
            except: pass

    if not candidates:
        return None, None

    # 优先选 deadline / closes / 等关键词附近的日期
    for cand_date, cand_str in candidates:
        # 看这个日期前后 80 字符里有没有 deadline 关键词
        idx = text.find(cand_str)
        if idx > 0:
            window = text[max(0, idx - 80):idx + len(cand_str) + 20]
            if re.search(deadline_keywords, window, re.I):
                return cand_date, cand_str

    # 否则返回最早的、未来的那个
    today = datetime.now()
    future = [(d, s) for d, s in candidates if d >= today - timedelta(days=7)]
    if future:
        future.sort()
        return future[0]

    candidates.sort()
    return candidates[0]

def score_call(text, priority_kw):
    """为一段内容打主题契合度分"""
    text_lower = text.lower()
    score = 0
    matched = []
    for kw in priority_kw:
        if kw.lower() in text_lower:
            score += 1
            matched.append(kw)
    return score, matched

# ============== 通用爬虫 ==============
def scrape_generic(site, config):
    """通用爬虫:找页面里所有像 'open call' 的链接,跟进去抽 metadata"""
    print(f"\n[{site['name']}]")
    soup = fetch(site["url"])
    if not soup:
        return []

    found = []
    keywords = site.get("keywords", ["open call", "convocatoria", "residency"])
    priority_kw = config.get("priority_keywords", [])

    # 策略 1: 找所有链接,看链接文本或周围文本是否包含关键词
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
            continue

        full_url = urljoin(site["url"], href)
        if full_url in seen_urls:
            continue

        # 链接周围的上下文(链接文本 + 前后 200 字)
        link_text = clean_text(a.get_text())
        parent = a.find_parent(["article", "div", "li", "section", "p"]) or a.parent
        context = clean_text(parent.get_text()) if parent else link_text

        if not text_contains_any(link_text + " " + context, keywords):
            continue

        # 跳过明显不相关的(其他语言版本、社交媒体等)
        if any(skip in href.lower() for skip in ["facebook.com", "twitter.com", "instagram.com",
                                                  "linkedin.com", "youtube.com", "/tag/", "/category/",
                                                  "/author/", "mailto:", ".pdf"]):
            if not href.endswith(".pdf"):
                continue

        # 域名过滤:只跟进同域名链接(避免爬遍整个网络)
        try:
            site_domain = urlparse(site["url"]).netloc.lower().replace("www.", "")
            link_domain = urlparse(full_url).netloc.lower().replace("www.", "")
            if site_domain not in link_domain and link_domain not in site_domain:
                continue
        except:
            continue

        # 排除关键词
        exclude_kw = config.get("exclude_keywords", [])
        if text_contains_any(context, exclude_kw):
            continue

        seen_urls.add(full_url)

        deadline, deadline_str = extract_deadline(context)
        score, matched_kw = score_call(context, priority_kw)

        # 标题
        title = link_text if len(link_text) > 5 else clean_text(parent.find(["h1","h2","h3","h4"]).get_text() if parent and parent.find(["h1","h2","h3","h4"]) else link_text)

        if len(title) < 5:
            continue

        # 截断 context 留前 500 字符
        snippet = context[:500] + ("..." if len(context) > 500 else "")

        item = {
            "id": hash_text(full_url),
            "title": title[:200],
            "url": full_url,
            "source": site["name"],
            "location": site.get("location", "Unknown"),
            "tags": site.get("tags", []),
            "snippet": snippet,
            "deadline": deadline.isoformat() if deadline else None,
            "deadline_raw": deadline_str,
            "priority_score": score,
            "matched_keywords": matched_kw,
            "first_seen": datetime.now().isoformat(),
        }
        found.append(item)

    # 去重(以 URL 为准,保留分数最高的)
    by_url = {}
    for item in found:
        key = item["url"]
        if key not in by_url or item["priority_score"] > by_url[key]["priority_score"]:
            by_url[key] = item

    print(f"  Found {len(by_url)} potential calls")
    return list(by_url.values())

# ============== 主流程 ==============
def main():
    config = load_config()
    seen = load_seen()
    today = datetime.now()

    all_calls = []

    for site in config["sites"]:
        try:
            calls = scrape_generic(site, config)
            time.sleep(2)  # 礼貌停顿
            for call in calls:
                # 标记新发现 vs 已见过
                if call["id"] in seen:
                    call["first_seen"] = seen[call["id"]]
                    call["is_new"] = False
                else:
                    seen[call["id"]] = call["first_seen"]
                    call["is_new"] = True
            all_calls.extend(calls)
        except Exception as e:
            print(f"  ❌ Error scraping {site['name']}: {e}", file=sys.stderr)

    # 过滤已经过期超过 7 天的
    fresh_calls = []
    for call in all_calls:
        if call["deadline"]:
            try:
                d = datetime.fromisoformat(call["deadline"])
                if d < today - timedelta(days=7):
                    continue
            except: pass
        fresh_calls.append(call)

    # 排序:有 deadline 且 priority_score 高的在前
    def sort_key(call):
        # 主排:有截止日 vs 没有
        # 次排:截止日近的(只看未来)
        # 三排:priority_score 高的
        if call["deadline"]:
            try:
                d = datetime.fromisoformat(call["deadline"])
                days_left = (d - today).days
                return (0, days_left, -call["priority_score"])
            except: pass
        return (1, 0, -call["priority_score"])

    fresh_calls.sort(key=sort_key)

    # 保存
    DATA_FILE.parent.mkdir(exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": today.isoformat(),
            "total": len(fresh_calls),
            "calls": fresh_calls
        }, f, ensure_ascii=False, indent=2)

    save_seen(seen)

    # 生成 HTML
    from generate_html import generate
    generate(fresh_calls, today)

    print(f"\n✅ Done. {len(fresh_calls)} calls. {sum(1 for c in fresh_calls if c['is_new'])} new.")
    print(f"   Output: {HTML_OUTPUT}")

if __name__ == "__main__":
    main()
