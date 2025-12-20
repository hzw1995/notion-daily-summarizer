import os
import json
from datetime import datetime, timedelta
from notion_client import Client
from notion_client.errors import APIResponseError
import requests

# 从环境变量获取配置
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
IDEA_DB_ID = os.environ.get("IDEA_DB_ID")

# 初始化Notion客户端
notion = Client(auth=NOTION_TOKEN)

"""
获取想法的脚本
"""
def get_database_id_from_page(page_id):
    """
    如果提供的是页面ID，检查页面中是否包含子数据库，如果有则返回子数据库ID
    """
    try:
        # 先尝试作为页面获取
        page = notion.pages.retrieve(page_id=page_id)
        if page.get("object") != "page":
            return None
        
        blocks = notion.blocks.children.list(block_id=page_id)
        db_ids = [b.get("id") for b in blocks.get("results", []) if b.get("type") == "child_database"]
        if not db_ids:
            return None
        for dbid in db_ids:
            try:
                db = notion.databases.retrieve(database_id=dbid)
                props = db.get("properties", {})
                for name, prop in props.items():
                    t = prop.get("type")
                    if t == "status" or (t == "select" and name in ("状态", "Status")):
                        return dbid
            except Exception:
                continue
        return db_ids[0]
    except Exception as e:
        return None


def get_database_properties(database_id):
    """
    获取数据库的属性结构
    """
    try:
        database = notion.databases.retrieve(database_id=database_id)
        return database.get("properties", {})
    except Exception as e:
        print(f"获取数据库属性失败: {e}")
        return {}


def query_idea_database():
    """
    查询想法数据库，获取最近30天的记录
    """
    try:
        # 检查是否需要从页面中提取数据库ID
        actual_db_id = IDEA_DB_ID
        
        # 先尝试直接作为数据库查询；失败时回退为页面并提取子数据库
        try:
            database = notion.databases.retrieve(database_id=actual_db_id)
            if database.get("object") != "database":
                actual_db_id = get_database_id_from_page(IDEA_DB_ID)
                if not actual_db_id:
                    raise ValueError(f"提供的ID {IDEA_DB_ID} 既不是有效的数据库ID，也不是包含子数据库的页面ID")
        except Exception:
            actual_db_id = get_database_id_from_page(IDEA_DB_ID)
            if not actual_db_id:
                raise
        
        # 计算30天前的日期
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        properties = get_database_properties(actual_db_id)
        if not properties:
            try:
                sample_body = {"page_size": 1}
                if hasattr(notion.databases, "query"):
                    sample = notion.databases.query(database_id=actual_db_id, **sample_body)
                else:
                    url = f"https://api.notion.com/v1/databases/{actual_db_id}/query"
                    headers = {
                        "Authorization": f"Bearer {NOTION_TOKEN}",
                        "Notion-Version": "2022-06-28",
                        "Content-Type": "application/json"
                    }
                    resp = requests.post(url, headers=headers, data=json.dumps(sample_body))
                    if resp.status_code != 200:
                        sample = {"results": []}
                    else:
                        sample = resp.json()
                items = sample.get("results", [])
                if items:
                    props_from_page = items[0].get("properties", {})
                    properties = {k: {"type": v.get("type")} for k, v in props_from_page.items()}
            except Exception:
                properties = {}

        def _find_property_by_type(props, types):
            for name, prop in props.items():
                if prop.get("type") in types:
                    return name, prop.get("type")
            return None, None

        def _resolve_status_value(prop_def):
            t = prop_def.get("type")
            cfg = prop_def.get(t, {})
            options = cfg.get("options", [])
            names = [o.get("name", "") for o in options]
            for candidate in ["未开始", "Not started", "Not Started", "To do", "Todo", "未完成"]:
                if candidate in names:
                    return candidate
            return None

        query_params = {"filter": {"and": []}}

        status_name, status_type = _find_property_by_type(properties, ["status", "select"])
        if not status_name:
            if "状态" in properties:
                status_name = "状态"
                status_type = properties[status_name].get("type")
            elif "Status" in properties:
                status_name = "Status"
                status_type = properties[status_name].get("type")
        if not status_name or not status_type:
            print("⚠️  未找到状态属性，无法筛选未开始")
            return []
        if status_type != "status" and status_type != "select":
            print("⚠️  状态属性类型非可筛选类型，无法筛选未开始")
            return []
        value = "未开始"
        query_params["filter"]["and"].append({
            "property": status_name,
            status_type: {
                "equals": value
            }
        })
        
        # 执行查询（兼容缺少 query 方法的旧版 SDK）
        if hasattr(notion.databases, "query"):
            results = notion.databases.query(
                database_id=actual_db_id,
                **query_params
            )
        else:
            url = f"https://api.notion.com/v1/databases/{actual_db_id}/query"
            headers = {
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            }
            resp = requests.post(url, headers=headers, data=json.dumps(query_params))
            if resp.status_code != 200:
                raise Exception(f"查询Notion失败: {resp.status_code} {resp.text}")
            results = resp.json()
        
        return results.get("results", [])
    except Exception as e:
        raise Exception(f"查询Notion失败: {str(e)}")


def get_idea_title(idea):
    """
    获取想法的标题
    """
    title_property = idea.get("properties", {})
    for prop_name in ["名称", "Name", "标题", "Title"]:
        if prop_name in title_property:
            title_parts = title_property[prop_name].get("title", [])
            return "".join(part.get("text", {}).get("content", "") for part in title_parts)
    for name, prop in title_property.items():
        if prop.get("type") == "title":
            title_parts = prop.get("title", [])
            return "".join(part.get("text", {}).get("content", "") for part in title_parts)
    return "无标题"


def get_idea_description(idea):
    """
    获取想法的描述
    """
    description_property = idea.get("properties", {})
    for prop_name in ["描述", "Description", "内容", "Content"]:
        if prop_name in description_property:
            if description_property[prop_name].get("type") == "rich_text":
                description_parts = description_property[prop_name].get("rich_text", [])
                return "".join(part.get("text", {}).get("content", "") for part in description_parts)
            elif description_property[prop_name].get("type") == "plain_text":
                return description_property[prop_name].get("plain_text", "")
    for prop in description_property.values():
        if prop.get("type") == "rich_text":
            description_parts = prop.get("rich_text", [])
            return "".join(part.get("text", {}).get("content", "") for part in description_parts)
    return ""


def get_idea_content(idea):
    """
    获取想法页面的内容
    """
    try:
        blocks = notion.blocks.children.list(block_id=idea.get("id"))
        content = []
        for block in blocks.get("results", []):
            block_type = block.get("type")
            if block_type == "paragraph":
                text_parts = block.get("paragraph", {}).get("rich_text", [])
                content.append("".join(part.get("text", {}).get("content", "") for part in text_parts))
        return "\n".join(content)
    except Exception as e:
        print(f"获取想法内容失败: {e}")
        return ""


if __name__ == "__main__":
    # 测试获取想法功能
    try:
        ideas = query_idea_database()
        print(f"成功获取 {len(ideas)} 个想法")
        for idea in ideas:
            print(f"- {get_idea_title(idea)}")
    except Exception as e:
        print(f"错误: {e}")
def update_ideas_status_to_done(ideas, database_id):
    try:
        properties = get_database_properties(database_id)
        status_name = None
        status_type = None
        prop_def = None
        if properties:
            for name, prop in properties.items():
                t = prop.get("type")
                if t in ("status", "select"):
                    status_name = name
                    status_type = t
                    prop_def = prop
                    break
        if not status_name and ideas:
            p = ideas[0].get("properties", {})
            for name, prop in p.items():
                t = prop.get("type")
                if t in ("status", "select"):
                    status_name = name
                    status_type = t
                    break
        if not status_name or not status_type:
            return 0
        options = []
        if prop_def:
            cfg = prop_def.get(status_type, {})
            options = cfg.get("options", [])
        target = None
        names = [o.get("name", "") for o in options]
        for cand in ["完成", "已完成", "Done", "Completed"]:
            if cand in names:
                target = cand
                break
        if not target and names:
            target = names[-1]
        updated = 0
        for idea in ideas:
            try:
                notion.pages.update(
                    page_id=idea.get("id"),
                    properties={
                        status_name: {
                            status_type: {
                                "name": target or "完成"
                            }
                        }
                    }
                )
                updated += 1
            except Exception:
                continue
        return updated
    except Exception:
        return 0
