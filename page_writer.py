import os
from datetime import datetime
from notion_client import Client

# 从环境变量获取配置
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DIARY_PAGE_ID = os.environ.get("DIARY_PAGE_ID")

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
        response = notion.blocks.children.list(block_id=parent_page_id)
        child_blocks = response.get("results", [])
        
        for block in child_blocks:
            if block.get("type") == "child_page":
                child_title = block.get("child_page", {}).get("title", "")
                if child_title == title:
                    # 获取完整的页面信息
                    page = notion.pages.retrieve(page_id=block.get("id"))
                    return page
        
        # 2. 如果直接查询子页面没有找到，尝试使用search方法
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

def update_page_content(page_id, summary):
    """
    更新页面内容
    
    Args:
        page_id: 页面ID
        summary: 新的页面内容
    """
    try:
        # 先清空页面内容
        blocks = notion.blocks.children.list(block_id=page_id)
        for block in blocks.get("results", []):
            notion.blocks.delete(block_id=block.get("id"))
        
        # 生成新的页面标题
        today = datetime.now().strftime("%Y-%m-%d")
        title = f"每日总结 - {today}"
        
        # 添加新内容
        notion.blocks.children.append(
            block_id=page_id,
            children=[
                {
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{
                            "type": "text",
                            "text": {
                                "content": title
                            }
                        }]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{
                            "type": "text",
                            "text": {
                                "content": summary
                            }
                        }]
                    }
                }
            ]
        )
        return True
    except Exception as e:
        print(f"更新页面内容失败: {e}")
        return False

def create_daily_summary(summary, existing_ideas_content=None):
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
    title = f"每日总结 - {today}"
    
    try:
        # 首先查找是否已存在相同标题的页面
        existing_page = find_page_by_title(DIARY_PAGE_ID, title)
        
        if existing_page:
            # 页面已存在，执行更新逻辑
            print(f"📝 已存在相同标题的页面，正在更新页面: {title}")
            page_id = existing_page.get("id")
            
            # 更新页面内容
            update_page_content(page_id, summary)
            return page_id
        else:
            # 页面不存在，创建新页面
            print(f"📝 页面不存在，正在创建新页面: {title}")
            page = notion.pages.create(
                parent={"page_id": DIARY_PAGE_ID},
                properties={
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                },
                children=[
                    {
                        "object": "block",
                        "type": "heading_1",
                        "heading_1": {
                            "rich_text": [{
                                "type": "text",
                                "text": {
                                    "content": title
                                }
                            }]
                        }
                    },
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{
                                "type": "text",
                                "text": {
                                    "content": summary
                                }
                            }]
                        }
                    }
                ]
            )
            return page.get("id")
    except Exception as e:
        raise Exception(f"创建/更新每日总结页面失败: {str(e)}")

def test_notion_connection():
    """
    测试Notion连接
    
    Returns:
        bool: 连接是否成功
    """
    try:
        # 先尝试获取页面信息，测试连接
        test_page = notion.pages.retrieve(page_id=DIARY_PAGE_ID)
        
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
