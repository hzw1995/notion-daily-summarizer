# -*- coding: utf-8 -*-
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
import pandas as pd
import os
import re
import html
try:
    from googletrans import Translator
    HAS_GT = True
except Exception:
    HAS_GT = False
    class Translator:
        def translate(self, text, dest='zh-CN'):
            class R:
                def __init__(self, t):
                    self.text = t
            return R(text)
import requests
import concurrent.futures
import threading
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
mkt_analysis = None
QWEN_MKT_TRANSLATION_MODEL = os.environ.get("QWEN_MKT_TRANSLATION_MODEL") or "qwen-plus"

API_BASE = "https://api.mktnews.net"

# 简易进度条类
class ProgressBar:
    def __init__(self, total, prefix='', suffix='', decimals=1, length=50, fill='█', printEnd="\r"):
        self.total = total
        self.prefix = prefix
        self.suffix = suffix
        self.decimals = decimals
        self.length = length
        self.fill = fill
        self.printEnd = printEnd
        self.iteration = 0
        self.lock = threading.Lock()

    def update(self, n=1):
        with self.lock:
            self.iteration += n
            self.print_progress()

    def print_progress(self):
        percent = ("{0:." + str(self.decimals) + "f}").format(100 * (self.iteration / float(self.total)))
        filledLength = int(self.length * self.iteration // self.total)
        bar = self.fill * filledLength + '-' * (self.length - filledLength)
        print(f'\r{self.prefix} |{bar}| {percent}% {self.suffix}', end=self.printEnd)
        if self.iteration == self.total:
            print()



def http_get(path, params=None, timeout=20):
    qs = ""
    if params:
        qs = "?" + urllib.parse.urlencode(params)
    url = API_BASE + path + qs
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        return json.loads(data.decode("utf-8"))

def fetch_categories():
    return http_get("/api/category")

def fetch_news(offset=0, category_id=None):
    params = {"offset": int(offset)}
    if category_id is not None:
        params["category_id"] = int(category_id)
    return http_get("/api/news", params=params)

def fetch_detail(news_id):
    return http_get("/api/news/detail", params={"id": int(news_id)})

def normalize_items(items):
    rows = []
    for it in items or []:
        rows.append({
            "id": it.get("id"),
            "title": it.get("title"),
            "introduction": it.get("introduction", ""),
            "publish_time": it.get("publish_time"),
            "categories": ",".join([c.get("name") for c in it.get("categories", [])]),
            "thumb": (it.get("thumbs") or [None])[0],
            "source_name": ((it.get("data") or {}).get("source") or {}).get("name", ""),
            "source_url": ((it.get("data") or {}).get("source") or {}).get("url", ""),
        })
    return rows

def strip_html_to_text(html_content):
    if not html_content:
        return ""
    text = re.sub(r"<script[\s\S]*?</script>", "", html_content, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html.unescape(text)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    # 噪声过滤
    noise_patterns = [
        r"免责声明", r"市场有风险", r"仅供参考", r"广告", r"赞助", r"未经授权", r"版权所有",
        r"Twitter", r"Facebook", r"分享", r"复制链接"
    ]
    for pat in noise_patterns:
        text = re.sub(pat, "", text)
    return text.strip()

def translate_to_zh(text, translator):
    if not text:
        return ""
    try:
        # 分段翻译，避免过长
        parts = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
        translated_parts = []
        for p in parts:
            # googletrans可能存在偶发错误，做重试
            for _ in range(2):
                try:
                    res = translator.translate(p, dest='zh-CN')
                    translated_parts.append(res.text)
                    break
                except Exception:
                    time.sleep(0.5)
                    continue
        return "\n".join(translated_parts)
    except Exception:
        return text

def dt_from_publish(publish_time):
    try:
        # 输入形如 2025-11-28T06:29:54.000Z
        dt = datetime.strptime(publish_time, "%Y-%m-%dT%H:%M:%S.%fZ")
    except Exception:
        try:
            dt = datetime.strptime(publish_time, "%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            dt = datetime.now()
    return dt

    

def main():
    global mkt_analysis
    category_name = None
    offset = 0
    crawl_all = False
    per_category = False
    flash_mode = False
    only_important = False
    max_pages = 2000
    for i, arg in enumerate(sys.argv):
        if arg == "--category" and i + 1 < len(sys.argv):
            category_name = sys.argv[i + 1]
        if arg == "--offset" and i + 1 < len(sys.argv):
            try:
                offset = int(sys.argv[i + 1])
            except Exception:
                offset = 0
        if arg == "--all":
            crawl_all = True
        if arg == "--per-category":
            per_category = True
        if arg == "--flash":
            flash_mode = True
        if arg == "--only-important":
            only_important = True
        if arg == "--max-pages" and i + 1 < len(sys.argv):
            try:
                max_pages = int(sys.argv[i + 1])
            except Exception:
                max_pages = 2000

    cat_map = {}
    try:
        cats = fetch_categories()
        for c in cats.get("data", []):
            cat_map[c.get("name")] = c.get("id")
    except Exception:
        pass

    cat_id = None
    if category_name and category_name in cat_map:
        cat_id = cat_map[category_name]
    
    def crawl_chain(start_offset=0, cat_id=None, max_pages=max_pages):
        all_rows = []
        current = start_offset
        pages = 0
        print(f"正在抓取列表... (Category: {cat_id})")
        while pages < max_pages:
            data = fetch_news(offset=current, category_id=cat_id)
            items = data.get("data", [])
            if not items:
                break
            rows = normalize_items(items)
            all_rows.extend(rows)
            # 使用最后一条的 offset 继续翻页
            current = items[-1].get("offset", current)
            pages += 1
            # 简单节流
            time.sleep(0.1)
            print(f"\r已获取 {len(all_rows)} 条列表数据...", end="")
        print()
        return pd.DataFrame(all_rows)

    translator = Translator()
    
    collected_news = [] # List of dict: {time, title, body}

    # News Feed 快讯模式
    if flash_mode:
        print("开始采集 News Feed 快讯...")
        last_id = None
        pages = 0
        today = datetime.now().date()
        
        while pages < max_pages:
            params = {"limit": 50}
            if last_id:
                params["last_id"] = last_id
            try:
                resp = http_get("/api/flash", params=params)
                items = resp.get("data", [])
                if not items:
                    break
                
                batch_processed = False
                for it in items:
                    # 过滤重要
                    if only_important and int(it.get("important", 0)) < 1:
                        continue
                    # 时间过滤：仅当天
                    dt_item = dt_from_publish(it.get("time") or datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
                    if dt_item.date() != today:
                        # 一旦遇到非当天，认为后续更旧，直接停止
                        pages = max_pages
                        break
                    
                    t_en = (it.get("data", {}).get("title") or "")
                    c_en = (it.get("data", {}).get("content") or "")
                    body_en = "\n".join([s for s in [t_en, c_en] if s])
                    body_en = strip_html_to_text(body_en)
                    
                    collected_news.append({
                        "time": dt_item,
                        "title": t_en,
                        "body": body_en
                    })
                    batch_processed = True
                
                if not batch_processed and pages < max_pages: 
                    # specifically if we broke out of the inner loop due to date
                    break
                    
                last_id = items[-1].get("id")
                pages += 1
                print(f"\r已采集快讯 {len(collected_news)} 条...", end="")
                time.sleep(0.2)
            except Exception:
                break
        print(f"\n快讯采集完成，共 {len(collected_news)} 条。")

    elif crawl_all:
        print("开始全量抓取（按分类遍历 + offset 链式分页）...")
        all_dfs = []
        cats_iter = list(cat_map.items()) if per_category else [(None, None)]
        for name, cid in cats_iter:
            df_cat = crawl_chain(start_offset=offset, cat_id=cid, max_pages=300)
            if not df_cat.empty:
                df_cat["category_filter"] = name or "ALL"
                all_dfs.append(df_cat)
        df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame(columns=["id","title"]) 
    else:
        data = fetch_news(offset=offset, category_id=cat_id)
        items = data.get("data", [])
        rows = normalize_items(items)
        df = pd.DataFrame(rows)
        print(f"列表条数: {len(df)}")

    # 如果不是快讯模式，需要并行抓取详情
    if not flash_mode and not df.empty:
        print(f"准备抓取 {len(df)} 条新闻详情...")
        rows_list = [row for _, row in df.iterrows()]
        
        def fetch_task(row):
            nid = row.get("id")
            try:
                detail = fetch_detail(nid)
                d = detail.get("data", {})
                title_en = d.get("title") or row.get("title") or ""
                content_html = d.get("content") or ""
                body_en = strip_html_to_text(content_html)
                dt = dt_from_publish(d.get("publish_time") or row.get("publish_time") or datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
                return {
                    "time": dt,
                    "title": title_en,
                    "body": body_en
                }
            except Exception:
                return None

        pb = ProgressBar(len(rows_list), prefix='详情抓取进度:', length=40)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_task, row) for row in rows_list]
            for f in concurrent.futures.as_completed(futures):
                res = f.result()
                if res:
                    collected_news.append(res)
                pb.update()

    # 统一处理：分析与保存
    if not collected_news:
        print("未获取到任何新闻内容。")
        return

    # 按时间倒序排列
    collected_news.sort(key=lambda x: x['time'], reverse=True)
    
    mkt_diary_id = (os.environ.get("MKT_DIARY_PAGE_ID") or os.environ.get("DIARY_PARENT_PAGE_ID") or "").strip()
    
    print(f"\n正在使用千问生成统一分析报告 (共 {len(collected_news)} 条新闻)...")
    full_context = "【今日A股相关重要新闻汇总】\n\n"
    for i, item in enumerate(collected_news):
        t_str = item['time'].strftime("%Y-%m-%d %H:%M")
        full_context += f"No.{i+1} [{t_str}] {item['title']}\n{item['body']}\n{'-'*40}\n"
    try:
        import summary_generator
        report = summary_generator.call_qwen_api(full_context, type="MKT")
    except Exception:
        report = None
    if report:
        mkt_analysis = (report or "").strip()
        if mkt_diary_id and not os.environ.get("AGGREGATOR_MODE"):
            from datetime import datetime
            title = f"MKT分析 - {datetime.now().strftime('%Y-%m-%d')}"
            write_to_notion_with_title(report, mkt_diary_id, title)
            print(f"已写入Notion页面: {mkt_diary_id}")
        else:
            print("未配置Notion页面ID，已生成分析内容")
    else:
        print("千问API未返回结果，准备写入翻译汇总内容")
        try:
            import summary_generator
            ctx = []
            for item in collected_news:
                ctx.append(f"【{item['title']}】\n{item['body']}\n{'-'*30}")
            translate_input = "\n".join(ctx)
            trans_out = summary_generator.call_qwen_api(translate_input, type="MKT_TRANS", model=QWEN_MKT_TRANSLATION_MODEL)
            fallback = (trans_out or "").strip()
            if not fallback:
                raise Exception("empty translation")
        except Exception:
            parts = []
            for item in collected_news:
                trans = translate_to_zh(item['body'], translator)
                parts.append(f"【{item['title']}】\n{trans}\n{'-'*30}")
            fallback = "\n\n".join(parts)
        mkt_analysis = (fallback or "").strip()
        if mkt_diary_id and not os.environ.get("AGGREGATOR_MODE"):
            from datetime import datetime
            title = f"MKT分析 - {datetime.now().strftime('%Y-%m-%d')}"
            write_to_notion_with_title(fallback, mkt_diary_id, title)
            print(f"已写入Notion页面: {mkt_diary_id}")
    


def write_to_notion(content, diary_page_id):
    from page_writer import create_daily_summary
    if content and diary_page_id:
        from datetime import datetime
        title = f"MKT分析 - {datetime.now().strftime('%Y-%m-%d')}"
        create_daily_summary(content, parent_page_id=diary_page_id, title_override=title)

def write_to_notion_with_title(content, diary_page_id, title):
    from page_writer import create_daily_summary
    if content and diary_page_id:
        create_daily_summary(content, parent_page_id=diary_page_id, title_override=title)

if __name__ == "__main__":
    main()
