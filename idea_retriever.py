import os
from datetime import datetime, timedelta
from notion_client import Client
from notion_client.errors import APIResponseError

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
        
        # 获取页面中的块
        blocks = notion.blocks.children.list(block_id=page_id)
        
        # 查找子数据库块
        for block in blocks.get("results", []):
            if block.get("type") == "child_database":
                return block.get("id")
        
        return None
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
        
        # 先尝试直接作为数据库查询
        try:
            database = notion.databases.retrieve(database_id=actual_db_id)
            if database.get("object") != "database":
                # 如果不是数据库，尝试从页面中获取
                actual_db_id = get_database_id_from_page(IDEA_DB_ID)
                if not actual_db_id:
                    raise ValueError(f"提供的ID {IDEA_DB_ID} 既不是有效的数据库ID，也不是包含子数据库的页面ID")
        except APIResponseError as e:
            if "is a page, not a database" in str(e):
                # 如果是页面ID，尝试从中提取数据库ID
                actual_db_id = get_database_id_from_page(IDEA_DB_ID)
                if not actual_db_id:
                    raise ValueError(f"提供的页面ID {IDEA_DB_ID} 中未找到子数据库")
            else:
                raise
        
        # 计算30天前的日期
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        # 获取数据库属性
        properties = get_database_properties(actual_db_id)
        
        # 构建查询条件（只根据创建时间）
        query_params = {
            "filter": {
                "and": [
                    {
                        "property": "创建时间" if "创建时间" in properties else "Created time",
                        "date": {
                            "on_or_after": thirty_days_ago
                        }
                    }
                ]
            }
        }
        
        # 添加状态过滤（如果存在状态属性）
        if "状态" in properties:
            query_params["filter"]["and"].append({
                "property": "状态",
                "select": {
                    "equals": "未完成"
                }
            })
        elif "Status" in properties:
            query_params["filter"]["and"].append({
                "property": "Status",
                "select": {
                    "equals": "未完成"
                }
            })
        else:
            print("⚠️  数据库中未找到'状态'或'Status'属性，将返回所有最近30天的记录")
        
        # 执行查询
        results = notion.databases.query(
            database_id=actual_db_id,
            **query_params
        )
        
        return results.get("results", [])
    except Exception as e:
        raise Exception(f"查询Notion失败: {str(e)}")


def get_idea_title(idea):
    """
    获取想法的标题
    """
    title_property = idea.get("properties", {})
    # 尝试不同的标题属性名
    for prop_name in ["名称", "Name", "标题", "Title"]:
        if prop_name in title_property:
            title_parts = title_property[prop_name].get("title", [])
            return "".join(part.get("text", {}).get("content", "") for part in title_parts)
    return "无标题"


def get_idea_description(idea):
    """
    获取想法的描述
    """
    description_property = idea.get("properties", {})
    # 尝试不同的描述属性名
    for prop_name in ["描述", "Description", "内容", "Content"]:
        if prop_name in description_property:
            if description_property[prop_name].get("type") == "rich_text":
                description_parts = description_property[prop_name].get("rich_text", [])
                return "".join(part.get("text", {}).get("content", "") for part in description_parts)
            elif description_property[prop_name].get("type") == "plain_text":
                return description_property[prop_name].get("plain_text", "")
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
