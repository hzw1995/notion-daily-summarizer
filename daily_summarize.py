import os
from datetime import datetime, timedelta
from notion_client import Client
from openai import OpenAI

# 初始化
notion = Client(auth=os.getenv("NOTION_TOKEN"))
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

IDEA_DB_ID = os.getenv("IDEA_DB_ID")
DIARY_PAGE_ID = os.getenv("DIARY_PAGE_ID")

# 计算昨天日期（按北京时间）
yesterday = (datetime.now() + timedelta(hours=8) - timedelta(days=1)).date()
start_time = f"{yesterday}T00:00:00+08:00"
end_time = f"{yesterday}T23:59:59+08:00"

print(f"🔍 查找 {yesterday} 的想法...")

# 查询昨天的所有想法
try:
    ideas = notion.databases.query(
        database_id=IDEA_DB_ID,
        filter={
            "and": [
                {"property": "创建时间", "date": {"after": start_time}},
                {"property": "创建时间", "date": {"before": end_time}}
            ]
        }
    )
except Exception as e:
    print(f"❌ 查询 Notion 失败: {e}")
    exit(1)

if not ideas["results"]:
    print("😴 昨天没有记录想法，跳过总结。")
    exit(0)

# 提取文本
idea_texts = []
for idea in ideas["results"]:
    content = idea["properties"]["内容"]["rich_text"]
    if content:
        idea_texts.append(content[0]["plain_text"])

full_text = "\n".join(idea_texts)
print(f"✅ 找到 {len(idea_texts)} 条想法，调用 AI 总结...")

# 调用 AI
try:
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "你是一个高效的知识整理助手，请将以下碎片想法归纳成一段结构清晰、有逻辑的每日总结，突出关键洞察和行动项。"},
            {"role": "user", "content": f"以下是用户在 {yesterday} 记录的所有想法：\n\n{full_text}\n\n请生成一段 100-200 字的总结。"}
        ],
        temperature=0.7
    )
    summary = response.choices[0].message.content.strip()
except Exception as e:
    print(f"❌ AI 调用失败: {e}")
    summary = "⚠️ AI 总结失败，请检查 API Key 或网络。"

# 创建新日记页面
try:
    new_page = notion.pages.create(
        parent={"page_id": DIARY_PAGE_ID},
        properties={
            "title": [{"text": {"content": f"{yesterday} 日记"}}]
        },
        children=[
            {
                "heading_2": {"rich_text": [{"text": {"content": "🤖 AI 每日总结"}}]}
            },
            {
                "paragraph": {"rich_text": [{"text": {"content": summary}}]}
            },
            {
                "divider": {}
            },
            {
                "heading_2": {"rich_text": [{"text": {"content": "📝 原始想法（共 {} 条）".format(len(idea_texts))}}]}
            }
        ] + [
            {
                "bulleted_list_item": {
                    "rich_text": [{"text": {"content": text[:200]}}]  # 截断长文本
                }
            } for text in idea_texts
        ]
    )
    print(f"🎉 成功生成日记！查看地址: {new_page['url']}")
except Exception as e:
    print(f"❌ 写入 Notion 失败: {e}")
    exit(1)
