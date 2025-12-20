# -*- coding: utf-8 -*-
import os
import re
import json
import hashlib
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

API_URL = "https://news.crabpi.com/api/flash-news"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
FLASH_DIARY_PAGE_ID = os.environ.get("FLASH_DIARY_PAGE_ID")
report = None



def to_shanghai_dt(date_str: str) -> datetime:
    if not date_str:
        dt = datetime.utcnow()
    else:
        s = date_str.replace('Z', '')
        dt = None
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except Exception:
                continue
        if dt is None:
            dt = datetime.utcnow()
    if ZoneInfo is not None:
        try:
            dt = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Asia/Shanghai"))
        except Exception:
            dt = dt + timedelta(hours=8)
    else:
        dt = dt + timedelta(hours=8)
    return dt


def extract_text(item: dict) -> tuple[str, str]:
    title = (item.get("title") or "").strip()
    text = (item.get("content_text") or "").strip()
    if not text:
        html = item.get("content_html") or ""
        if html:
            text = re.sub(r"<[^>]+>", "\n", html)
            text = re.sub(r"\n{2,}", "\n", text).strip()
    if not text:
        text = title
    return title, text

def normalize_text(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"\s+", " ", t)
    return t

def text_hash(text: str) -> str:
    t = normalize_text(text)
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _tokens(text: str) -> List[str]:
    t = normalize_text(text).lower()
    tokens = re.findall(r"[\w]+", t)
    chars = re.sub(r"\s+", "", t)
    shingles = [chars[i:i+3] for i in range(max(0, len(chars) - 2))]
    return tokens + shingles

def simhash(text: str, bits: int = 64) -> int:
    v = [0] * bits
    for tok in _tokens(text):
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        for i in range(bits):
            if (h >> i) & 1:
                v[i] += 1
            else:
                v[i] -= 1
    fp = 0
    for i in range(bits):
        if v[i] > 0:
            fp |= (1 << i)
    return fp

def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")



def fetch_flash_news(limit: int = 200) -> List[Dict]:
    params = {"limit": limit}
    try:
        r = requests.get(API_URL, params=params, timeout=15)
        r.raise_for_status()
        js = r.json()
        if isinstance(js, dict):
            if "items" in js and isinstance(js["items"], list):
                return js["items"]
            if "data" in js and isinstance(js["data"], list):
                return js["data"]
        if isinstance(js, list):
            return js
    except Exception:
        return []
    return []


def main():
    import sys
    limit = 300
    print_n = 20
    only_today = False
    dedup_mode = "content"
    simhash_thresh = 5
    hours_window = 36
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            try:
                limit = int(sys.argv[i + 1])
            except Exception:
                pass
        if arg == "--print" and i + 1 < len(sys.argv):
            try:
                print_n = int(sys.argv[i + 1])
            except Exception:
                pass
        if arg == "--today":
            only_today = True
        if arg == "--dedup" and i + 1 < len(sys.argv):
            dedup_mode = sys.argv[i + 1].strip()
        if arg == "--simhash-thresh" and i + 1 < len(sys.argv):
            try:
                simhash_thresh = int(sys.argv[i + 1])
            except Exception:
                pass
        if arg == "--hours" and i + 1 < len(sys.argv):
            try:
                hours_window = int(sys.argv[i + 1])
            except Exception:
                pass

    print("正在抓取快讯...")
    items = fetch_flash_news(limit=limit)
    print(f"抓取到 {len(items)} 条原始数据")
    
    saved = 0
    paths: List[str] = []
    sh_now = datetime.now() if ZoneInfo is None else datetime.now(ZoneInfo("Asia/Shanghai"))
    cutoff = sh_now - timedelta(hours=hours_window)

    enriched: List[Tuple[Dict, datetime, str]] = []
    for it in items:
        dt_sh = to_shanghai_dt(it.get("date_published"))
        ts_str = dt_sh.strftime("%Y%m%d_%H%M%S")
        if only_today:
            if dt_sh.date() != sh_now.date():
                continue
        else:
            if dt_sh < cutoff:
                continue
        enriched.append((it, dt_sh, ts_str))
    enriched.sort(key=lambda x: x[1], reverse=True)

    print(f"筛选后剩余 {len(enriched)} 条有效快讯")

    seen_hashes = set()
    seen_simhash: List[int] = []
    
    collected_texts = []

    for it, dt_sh, ts in enriched:
        title, text = extract_text(it)
        
        # 收集用于分析的文本（包含标题和正文，保留时间戳）
        collected_texts.append(f"【{dt_sh.strftime('%Y-%m-%d %H:%M')}】 {title}\n{text}\n{'-'*40}")

        if dedup_mode == "content":
            h = text_hash(text)
            if h in seen_hashes:
                continue
        elif dedup_mode == "simhash":
            sh = simhash(text)
            dup = False
            for prev in seen_simhash:
                if hamming_distance(sh, prev) <= simhash_thresh:
                    dup = True
                    break
            if dup:
                continue
        if dedup_mode == "content":
            seen_hashes.add(h)
        elif dedup_mode == "simhash":
            seen_simhash.append(sh)
        saved += 1

    print(f"收集用于分析条数: {saved}")
    
    api_key = (OPENAI_API_KEY or "").strip()
    if api_key and collected_texts:
        print(f"正在使用千问生成快讯分析，共 {len(collected_texts)} 条...")
        full_context = "\n".join(collected_texts)
        if len(full_context) > 100000:
            full_context = full_context[:100000] + "\n...(截断)..."
        try:
            import summary_generator
            out = summary_generator.call_qwen_api(full_context, type="KX")
            global report
            report = (out or "").strip()
        except Exception as e:
            print(f"千问生成失败: {e}")
            report = ""
        if report:
            target_id = (FLASH_DIARY_PAGE_ID or os.environ.get("DIARY_PARENT_PAGE_ID") or "").strip()
            if target_id and not os.environ.get("AGGREGATOR_MODE"):
                # 自定义标题
                title = f"快讯分析 - {datetime.now().strftime('%Y-%m-%d')}"
                write_to_notion_with_title(report, target_id, title)
                print(f"✅ 已写入Notion页面: {target_id}")
            else:
                print("⚠️ 未配置Notion页面ID，已生成分析内容")
        else:
            print("❌ 分析失败或无返回")
    elif not api_key:
        print("❌ 未找到 API Key: 需设置环境变量 OPENAI_API_KEY")
    else:
        print("⚠️ 没有符合条件的快讯可供分析")

def write_to_notion(content, diary_page_id):
    from page_writer import create_daily_summary
    if content and diary_page_id:
        title = f"快讯分析 - {datetime.now().strftime('%Y-%m-%d')}"
        create_daily_summary(content, parent_page_id=diary_page_id, title_override=title)

def write_to_notion_with_title(content, diary_page_id, title):
    from page_writer import create_daily_summary
    if content and diary_page_id:
        create_daily_summary(content, parent_page_id=diary_page_id, title_override=title)


if __name__ == "__main__":
    main()
