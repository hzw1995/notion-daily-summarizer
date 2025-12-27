import os
from datetime import datetime
from notion_client import Client

# 从环境变量获取配置
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DIARY_PARENT_PAGE_ID = os.environ.get("DIARY_PARENT_PAGE_ID")

# 初始化Notion客户端
notion = Client(auth=NOTION_TOKEN)

"""
写入页面的脚本
"""
def find_page_by_title(parent_page_id, title):
    """
    在指定父页面下查找具有相同标题的页面
    
    Args:
        parent_page_id: 父页面ID
        title: 要查找的页面标题
    
    Returns:
        dict or None: 如果找到页面则返回页面信息，否则返回None
    """
    try:
        # 1. 直接查询父页面下的所有子页面（最可靠的方法）
        has_more = True
        next_cursor = None
        
        while has_more:
            list_params = {"block_id": parent_page_id}
            if next_cursor:
                list_params["start_cursor"] = next_cursor
                
            response = notion.blocks.children.list(**list_params)
            child_blocks = response.get("results", [])
            has_more = response.get("has_more")
            next_cursor = response.get("next_cursor")
            
            for block in child_blocks:
                if block.get("type") == "child_page":
                    child_title = block.get("child_page", {}).get("title", "")
                    if child_title == title:
                        # 获取完整的页面信息
                        page = notion.pages.retrieve(page_id=block.get("id"))
                        return page
        
        # 2. 如果直接查询子页面没有找到，尝试使用search方法
        # 注意：search会返回所有匹配的页面，需要验证父页面ID
        pages = notion.search(
            query=title,
            filter={
                "property": "object",
                "value": "page"
            },
            sort={
                "direction": "descending",
                "timestamp": "last_edited_time"
            },
            page_size=100
        )
        
        for page in pages.get("results", []):
            # 验证父页面ID
            parent = page.get("parent", {})
            p_id = parent.get("page_id") or parent.get("database_id")
            # 只有当父页面ID匹配时才返回（忽略破折号带来的格式差异）
            if p_id and p_id.replace("-", "") == parent_page_id.replace("-", ""):
                properties = page.get("properties", {})
                page_title = ""
                
                for prop_name in ["标题", "Title", "名称", "Name"]:
                    if prop_name in properties:
                        prop = properties[prop_name]
                        if prop.get("type") == "title" and prop.get("title"):
                            page_title = "".join([t.get("text", {}).get("content", "") for t in prop.get("title", [])])
                            break
                
                if page_title == title:
                    return page
        
        return None
    except Exception as e:
        print(f"查找页面失败: {e}")
        return None

def get_page_content(page_id):
    """
    获取页面的内容
    
    Args:
        page_id: 页面ID
    
    Returns:
        str: 页面内容
    """
    try:
        blocks = notion.blocks.children.list(block_id=page_id)
        content = []
        for block in blocks.get("results", []):
            block_type = block.get("type")
            if block_type == "paragraph":
                text_parts = block.get("paragraph", {}).get("rich_text", [])
                content.append(" ".join(part.get("text", {}).get("content", "") for part in text_parts))
        return "\n".join(content)
    except Exception as e:
        print(f"获取页面内容失败: {e}")
        return ""

def update_page_content(page_id, summary, heading_title=None):
    """
    更新页面内容
    
    Args:
        page_id: 页面ID
        summary: 新的页面内容
    """
    try:
        blocks = notion.blocks.children.list(block_id=page_id)
        for block in blocks.get("results", []):
            notion.blocks.delete(block_id=block.get("id"))
        today = datetime.now().strftime("%Y-%m-%d")
        title = heading_title or f"每日总结 - {today}"
        def _chunks(text, limit=1800):
            res = []
            i = 0
            n = len(text)
            while i < n:
                res.append(text[i:i+limit])
                i += limit
            return res
        def _append_text_block(children, t, content):
            for c in _chunks(content):
                if t == "divider":
                    children.append({"object":"block","type":"divider","divider":{}})
                else:
                    import re
                    def _inline_rich_text(s):
                        parts = []
                        pattern = re.compile(r"(\[([^\]]+)\]\(([^)]+)\))|(\*\*([^\*]+)\*\*)|(`([^`]+)`)|(\*([^*]+)\*)|(_([^_]+)_)")
                        pos = 0
                        for m in pattern.finditer(s):
                            start, end = m.span()
                            if start > pos:
                                parts.append({
                                    "type": "text",
                                    "text": {"content": s[pos:start]}
                                })
                            if m.group(2) and m.group(3):
                                parts.append({
                                    "type": "text",
                                    "text": {"content": m.group(2), "link": {"url": m.group(3)}}
                                })
                            elif m.group(5):
                                parts.append({
                                    "type": "text",
                                    "text": {"content": m.group(5)},
                                    "annotations": {"bold": True}
                                })
                            elif m.group(7):
                                parts.append({
                                    "type": "text",
                                    "text": {"content": m.group(7)},
                                    "annotations": {"code": True}
                                })
                            elif m.group(9):
                                parts.append({
                                    "type": "text",
                                    "text": {"content": m.group(9)},
                                    "annotations": {"italic": True}
                                })
                            elif m.group(11):
                                parts.append({
                                    "type": "text",
                                    "text": {"content": m.group(11)},
                                    "annotations": {"italic": True}
                                })
                            pos = end
                        if pos < len(s):
                            parts.append({
                                "type": "text",
                                "text": {"content": s[pos:]}
                            })
                        return parts
                    children.append({
                        "object": "block",
                        "type": t,
                        t: {
                            "rich_text": _inline_rich_text(c)
                        }
                    })
        def _line_block_type(p):
            if p.startswith("### "):
                return "heading_3", p[4:]
            if p.startswith("## "):
                return "heading_2", p[3:]
            if p.startswith("# "):
                return "heading_1", p[2:]
            if p in ("---", "———", "___"):
                return "divider", ""
            if p.startswith(">"):
                return "quote", p[1:].strip()
            import re
            if re.match(r"^\d+\.\s+", p):
                return "numbered_list_item", re.sub(r"^\d+\.\s+", "", p)
            if p.startswith("- ") or p.startswith("* ") or p.startswith("• "):
                return "bulleted_list_item", p[2:].strip()
            return "paragraph", p
        children_all = [{
            "object": "block",
            "type": "heading_1",
            "heading_1": {"rich_text": [{"type": "text", "text": {"content": title}}]}
        }]
        for line in summary.split("\n"):
            p = line.strip()
            if not p:
                continue
            t, content = _line_block_type(p)
            _append_text_block(children_all, t, content)
        i = 0
        while i < len(children_all):
            batch = children_all[i:i+90]
            notion.blocks.children.append(block_id=page_id, children=batch)
            i += 90
        return True
    except Exception as e:
        print(f"更新页面内容失败: {e}")
        return False

def create_daily_summary(summary, existing_ideas_content=None, parent_page_id=None, title_override=None):
    """
    创建或更新每日总结页面
    
    Args:
        summary: 要写入页面的总结内容
        existing_ideas_content: 现有页面中的想法内容（用于更新时整合）
    
    Returns:
        str: 创建或更新的页面ID
    """
    # 生成页面标题
    today = datetime.now().strftime("%Y-%m-%d")
    title = title_override or f"股市总结 - {today}"
    
    try:
        # 首先查找是否已存在相同标题的页面
        existing_page = find_page_by_title(parent_page_id or DIARY_PARENT_PAGE_ID, title)
        
        if existing_page:
            # 页面已存在，执行更新逻辑
            print(f"📝 已存在相同标题的页面，正在更新页面: {title}")
            page_id = existing_page.get("id")
            
            # 更新页面内容
            update_page_content(page_id, summary, heading_title=title)
            return page_id
        else:
            # 页面不存在，创建新页面
            print(f"📝 页面不存在，正在创建新页面: {title}")
            def _chunks(text, limit=1800):
                res = []
                i = 0
                n = len(text)
                while i < n:
                    res.append(text[i:i+limit])
                    i += limit
                return res
            def _append_text_block(children, t, content):
                for c in _chunks(content):
                    if t == "divider":
                        children.append({"object":"block","type":"divider","divider":{}})
                    else:
                        import re
                        def _inline_rich_text(s):
                            parts = []
                            pattern = re.compile(r"(\[([^\]]+)\]\(([^)]+)\))|(\*\*([^\*]+)\*\*)|(`([^`]+)`)|(\*([^*]+)\*)|(_([^_]+)_)")
                            pos = 0
                            for m in pattern.finditer(s):
                                start, end = m.span()
                                if start > pos:
                                    parts.append({
                                        "type": "text",
                                        "text": {"content": s[pos:start]}
                                    })
                                if m.group(2) and m.group(3):
                                    parts.append({
                                        "type": "text",
                                        "text": {"content": m.group(2), "link": {"url": m.group(3)}}
                                    })
                                elif m.group(5):
                                    parts.append({
                                        "type": "text",
                                        "text": {"content": m.group(5)},
                                        "annotations": {"bold": True}
                                    })
                                elif m.group(7):
                                    parts.append({
                                        "type": "text",
                                        "text": {"content": m.group(7)},
                                        "annotations": {"code": True}
                                    })
                                elif m.group(9):
                                    parts.append({
                                        "type": "text",
                                        "text": {"content": m.group(9)},
                                        "annotations": {"italic": True}
                                    })
                                elif m.group(11):
                                    parts.append({
                                        "type": "text",
                                        "text": {"content": m.group(11)},
                                        "annotations": {"italic": True}
                                    })
                                pos = end
                            if pos < len(s):
                                parts.append({
                                    "type": "text",
                                    "text": {"content": s[pos:]}
                                })
                            return parts
                        children.append({
                            "object": "block",
                            "type": t,
                            t: {
                                "rich_text": _inline_rich_text(c)
                            }
                        })
            def _line_block_type(p):
                if p.startswith("### "):
                    return "heading_3", p[4:]
                if p.startswith("## "):
                    return "heading_2", p[3:]
                if p.startswith("# "):
                    return "heading_1", p[2:]
                if p in ("---", "———", "___"):
                    return "divider", ""
                if p.startswith(">"):
                    return "quote", p[1:].strip()
                import re
                if re.match(r"^\d+\.\s+", p):
                    return "numbered_list_item", re.sub(r"^\d+\.\s+", "", p)
                if p.startswith("- ") or p.startswith("* ") or p.startswith("• "):
                    return "bulleted_list_item", p[2:].strip()
                return "paragraph", p
            children_all = [{
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": [{"type": "text", "text": {"content": title}}]}
            }]
            for line in summary.split("\n"):
                p = line.strip()
                if not p:
                    continue
                t, content = _line_block_type(p)
                _append_text_block(children_all, t, content)
            initial = children_all[:90]
            created = notion.pages.create(
                parent={"page_id": parent_page_id or DIARY_PARENT_PAGE_ID},
                properties={
                    "title": [
                        {
                            "type": "text",
                            "text": {"content": title}
                        }
                    ]
                },
                children=initial
            )
            page_id = created.get("id")
            i = 90
            while i < len(children_all):
                batch = children_all[i:i+90]
                notion.blocks.children.append(block_id=page_id, children=batch)
                i += 90
            return page_id
    except Exception as e:
        raise Exception(f"创建/更新每日总结页面失败: {str(e)}")

def create_market_analysis(summary, parent_page_id=None):
    """
    创建或更新市场分析页面
    
    Args:
        summary: 市场分析内容
        parent_page_id: 父页面ID，默认使用配置的DIARY_PARENT_PAGE_ID
        
    Returns:
        str: 页面ID
    """
    today = datetime.now().strftime("%Y-%m-%d")
    title = f"市场分析 - {today}"
    return create_daily_summary(summary, parent_page_id=parent_page_id, title_override=title)


def test_notion_connection():
    """
    测试Notion连接
    
    Returns:
        bool: 连接是否成功
    """
    try:
        # 先尝试获取页面信息，测试连接
        test_page = notion.pages.retrieve(page_id=DIARY_PARENT_PAGE_ID)
        
        # 安全获取页面标题
        page_title = "无标题"
        properties = test_page.get("properties", {})
        
        # 尝试不同的标题属性名
        for prop_name in ["标题", "Title", "名称", "Name"]:
            if prop_name in properties:
                prop = properties[prop_name]
                if prop.get("type") == "title" and prop.get("title"):
                    page_title = "".join([t.get("text", {}).get("content", "") for t in prop.get("title", [])])
                    break
        
        print(f"✅ Notion连接成功！页面标题: {page_title}")
        return True
    except Exception as e:
        print(f"⚠️  Notion连接测试失败: {e}")
        return False


if __name__ == "__main__":
    # 测试创建页面功能
    try:
        # 测试连接
        if test_notion_connection():
            # 创建测试总结页面
            test_summary = "这是一个测试总结，用于验证页面写入功能是否正常工作。"
            page_id = create_daily_summary(test_summary)
            print(f"✅ 成功创建测试总结页面，页面ID: {page_id}")
    except Exception as e:
        print(f"错误: {e}")
