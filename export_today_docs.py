import os
import sys
from datetime import datetime, timedelta
from notion_client import Client
import argparse

def _rt_to_md(rich_text):
    out = []
    for item in rich_text or []:
        text = (item.get("text", {}) or {}).get("content", "") or ""
        link = (item.get("text", {}) or {}).get("link", {}) or {}
        url = link.get("url")
        ann = item.get("annotations", {}) or {}
        s = text
        if ann.get("code"):
            s = f"`{s}`"
        if ann.get("bold"):
            s = f"**{s}**"
        if ann.get("italic"):
            s = f"*{s}*"
        if url:
            s = f"[{s}]({url})"
        out.append(s)
    return "".join(out)

def _block_to_md(block):
    t = block.get("type")
    data = block.get(t, {}) or {}
    if t == "heading_1":
        return "# " + _rt_to_md(data.get("rich_text", []))
    if t == "heading_2":
        return "## " + _rt_to_md(data.get("rich_text", []))
    if t == "heading_3":
        return "### " + _rt_to_md(data.get("rich_text", []))
    if t == "quote":
        return "> " + _rt_to_md(data.get("rich_text", []))
    if t == "numbered_list_item":
        return "1. " + _rt_to_md(data.get("rich_text", []))
    if t == "bulleted_list_item":
        return "- " + _rt_to_md(data.get("rich_text", []))
    if t == "divider":
        return "---"
    if t == "to_do":
        checked = data.get("checked", False)
        box = "x" if checked else " "
        return f"- [{box}] " + _rt_to_md(data.get("rich_text", []))
    if t == "code":
        lang = (data.get("language") or "").strip()
        content = _rt_to_md(data.get("rich_text", []))
        fence = "```" + (lang if lang else "")
        return f"{fence}\n{content}\n```"
    if t == "paragraph":
        return _rt_to_md(data.get("rich_text", []))
    return ""

def _fetch_blocks(notion, page_id):
    items = []
    cursor = None
    while True:
        if cursor:
            resp = notion.blocks.children.list(block_id=page_id, start_cursor=cursor)
        else:
            resp = notion.blocks.children.list(block_id=page_id)
        items.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return items

def _find_child_page_id(notion, parent_id, title_exact, date_str, base):
    items = []
    cursor = None
    try:
        while True:
            if cursor:
                resp = notion.blocks.children.list(block_id=parent_id, start_cursor=cursor)
            else:
                resp = notion.blocks.children.list(block_id=parent_id)
            items.extend(resp.get("results", []))
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
    except Exception:
        return None
    target_id = None
    for b in items:
        if b.get("type") == "child_page":
            t = (b.get("child_page") or {}).get("title", "") or ""
            if t == title_exact:
                target_id = b.get("id")
                break
    if not target_id:
        for b in items:
            if b.get("type") == "child_page":
                t = (b.get("child_page") or {}).get("title", "") or ""
                if date_str in t and (t.startswith(base) or base in t):
                    target_id = b.get("id")
                    break
    return target_id

def _export_page(notion, parent_id, base, date_str, filename):
    title = f"{base} - {date_str}"
    page_id = _find_child_page_id(notion, parent_id, title, date_str, base)
    if not page_id:
        # 回退：全局搜索页面，按父页面与内容首个标题匹配
        try:
            results = notion.search(
                query=base,
                filter={"property": "object", "value": "page"},
                sort={"direction": "descending", "timestamp": "last_edited_time"},
                page_size=100
            ).get("results", [])
        except Exception:
            results = []
        for p in results:
            parent = p.get("parent", {}) or {}
            pid = (parent.get("page_id") or parent.get("workspace") or "")
            if parent.get("type") == "page_id" and pid == parent_id:
                # 读取首个标题块判断
                try:
                    blocks = _fetch_blocks(notion, p.get("id"))
                    if not blocks:
                        continue
                    # 找到第一个 heading_1 或 heading_2
                    top = ""
                    for b in blocks:
                        bt = b.get("type")
                        if bt in ("heading_1", "heading_2", "heading_3"):
                            top = _block_to_md(b)
                            break
                    if not top:
                        continue
                    if (base in top) and (date_str in top):
                        page_id = p.get("id")
                        break
                except Exception:
                    continue
        if not page_id:
            # 最后回退：不限定父页面，按标题与首块判断
            try:
                results2 = notion.search(
                    query=title,
                    filter={"property": "object", "value": "page"},
                    sort={"direction": "descending", "timestamp": "last_edited_time"},
                    page_size=100
                ).get("results", [])
            except Exception:
                results2 = []
            for p in results2:
                try:
                    blocks = _fetch_blocks(notion, p.get("id"))
                    top = ""
                    for b in blocks:
                        bt = b.get("type")
                        if bt in ("heading_1", "heading_2", "heading_3"):
                            top = _block_to_md(b)
                            break
                    if (base in top) and (date_str in top):
                        page_id = p.get("id")
                        break
                except Exception:
                    continue
            if not page_id:
                return False, f"未找到页面: {title}"
    blocks = _fetch_blocks(notion, page_id)
    lines = []
    for b in blocks:
        line = _block_to_md(b).strip()
        if line:
            lines.append(line)
    content = "\n".join(lines)
    out_dir = os.environ.get("OUT_DIR") or "."
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        pass
    safe_name = filename.replace("/", "_").replace("\\", "_")
    out_path = os.path.join(out_dir, safe_name)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    # 如果指定了输出目录，复制过去
    if out_path != filename:
        try:
            with open(out_path, "w", encoding="utf-8") as f2:
                f2.write(content)
            return True, out_path
        except Exception:
            return True, filename
    return True, filename

def _list_child_titles(notion, parent_id, limit=50):
    titles = []
    cursor = None
    try:
        while True:
            if cursor:
                resp = notion.blocks.children.list(block_id=parent_id, start_cursor=cursor)
            else:
                resp = notion.blocks.children.list(block_id=parent_id)
            for b in resp.get("results", []):
                if b.get("type") == "child_page":
                    t = (b.get("child_page") or {}).get("title", "") or ""
                    if t:
                        titles.append(t)
                        if len(titles) >= limit:
                            return titles
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
    except Exception:
        pass
    return titles

def _describe_parent(notion, parent_id):
    try:
        p = notion.pages.retrieve(page_id=parent_id)
        return "page", (p.get("id") or parent_id)
    except Exception:
        pass
    try:
        d = notion.databases.retrieve(database_id=parent_id)
        return "database", (d.get("id") or parent_id)
    except Exception:
        pass
    return "unknown", parent_id

def main():
    parser = argparse.ArgumentParser(description="导出当天的 Notion 子页面为 Markdown（快讯分析/MKT分析/股市总结）")
    parser.add_argument("-d", "--date", help="指定日期 YYYY-MM-DD（默认今天，找不到则自动尝试昨天）")
    parser.add_argument("-o", "--out", help="输出目录（默认当前目录）")
    parser.add_argument("-p", "--prefix", help="文件名前缀（可选）")
    args = parser.parse_args()

    if args.out:
        os.environ["OUT_DIR"] = args.out
    if args.prefix:
        os.environ["FILE_PREFIX"] = args.prefix

    token = (os.environ.get("NOTION_TOKEN") or "").strip()
    if not token:
        print("NOTION_TOKEN 未设置")
        return
    notion = Client(auth=token)

    if args.date:
        date_candidates = [args.date.strip()]
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        date_candidates = [today, yesterday]

    parents = [
        ("快讯分析", (os.environ.get("FLASH_DIARY_PAGE_ID") or os.environ.get("DIARY_PARENT_PAGE_ID") or "").strip()),
        ("MKT分析", (os.environ.get("MKT_DIARY_PAGE_ID") or os.environ.get("DIARY_PARENT_PAGE_ID") or "").strip()),
        ("股市总结", (os.environ.get("DIARY_PARENT_PAGE_ID") or "").strip()),
    ]
    results = []
    prefix = os.environ.get("FILE_PREFIX") or ""
    for base, parent_id in parents:
        ok = False
        final_title = ""
        final_msg = ""
        for d in date_candidates:
            filename = f"{prefix}{base}-{d}.md"
            ok, final_msg = _export_page(notion, parent_id, base, d, filename)
            final_title = f"{base} - {d}"
            if ok:
                break
        results.append((final_title, ok, final_msg))
    for t, ok, m in results:
        if ok:
            print(f"已导出: {t} -> {m}")
        else:
            print(f"导出失败: {t} -> {m}")
            # Debug: list child page titles under the parent
            base_name = t.split(" - ")[0]
            parent_id = None
            for b, pid in parents:
                if b == base_name:
                    parent_id = pid
                    break
            if parent_id:
                p_type, p_id = _describe_parent(notion, parent_id)
                print(f"父ID类型: {p_type}, ID: {p_id}")
                titles = _list_child_titles(notion, parent_id, limit=20)
                if titles:
                    print(f"{base_name} 父页面下现有子页面标题（前20）：")
                    for tt in titles:
                        print(f"- {tt}")
                else:
                    print(f"{base_name} 父页面下未能列出子页面（可能无权限或无子页面）")

if __name__ == "__main__":
    main()
