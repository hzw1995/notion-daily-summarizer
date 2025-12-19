# daily_summarize.py
import os
from datetime import datetime, timedelta, timezone
from notion_client import Client
from openai import OpenAI

# 初始化客户端
notion = Client(auth=os.getenv("NOTION_TOKEN"))
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 获取环境变量（自动去除连字符）
IDEA_DB_ID = os.getenv("IDEA_DB_ID", "").replace("-", "")
DIARY_PARENT_PAGE_ID = os.getenv("DIARY_PARENT_PAGE_ID", "").replace("-", "")

# 计算“昨天”（按北京时间 UTC+8）
beijing_tz = timezone(timedelta(hours=8))
today_beijing = datetime.now(beijing_tz).date()
yesterday = today_beijing - timedelta(days=1)

print(f"🔍 正在汇总 {yesterday} 的想法...")

# 查询昨天的所有想法（基于 Created time）
try:
    response = notion.databases.query(
        database_id=IDEA_DB_ID,
        filter={
            "timestamp": "created_time",
            "created_time": {
                "on_or_after": yesterday.isoformat(),
                "before": today_beijing.isoformat()
            }
        }
    )
except Exception as e:
    print(f"❌ 查询 Notion 失败: {e}")
    exit(1)

ideas = response.get("results", [])
if not ideas:
    print("😴 昨天没有新想法，跳过总结。")
    exit(0)

# 提取“内容”字段文本
idea_texts = []
for idea in ideas:
    content_prop = idea["properties"].get("内容")  # ← 字段名必须匹配！
    if content_prop and content_prop["type"] == "rich_text":
        texts = [t["plain_text"] for t in content_prop["rich_text"] if t.get("plain_text")]
        if texts:
            idea_texts.append("\n".join(texts))

if not idea_texts:
    print("⚠️ 找到记录但无有效内容，跳过。")
    exit(0)

full_text = "\n---\n".join(idea_texts)
print(f"✅ 找到 {len(idea_texts)} 条想法，调用 AI 总结...")

# 调用 OpenAI 总结
try:
    ai_response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "你是一个高效的知识整理助手，请将以下碎片想法归纳成一段结构清晰、有逻辑的每日总结，突出关键洞察和行动项。"},
            {"role": "user", "content": f"以下是用户在 {yesterday} 记录的所有想法：\n\n{full_text}\n\n请生成一段 100-200 字的总结。"}
        ],
        temperature=0.7,
        timeout=30
    )
    summary = ai_response.choices[0].message.content.strip()
except Exception as e:
    print(f"❌ AI 调用失败: {e}")
    summary = "⚠️ AI 总结失败，请检查网络或 API Key。"

# 创建日记页面
try:
    new_page = notion.pages.create(
        parent={"page_id": DIARY_PARENT_PAGE_ID},
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
                "heading_2": {"rich_text": [{"text": {"content": f"📝 原始想法（共 {len(idea_texts)} 条）"}}]}
            }
        ] + [
            {
                "bulleted_list_item": {
                    "rich_text": [{"text": {"content": text[:300]}}]  # 截断防超长
                }
            } for text in idea_texts
        ]
    )
    print(f"🎉 成功生成日记！查看地址: {new_page['url']}")
except Exception as e:
    print(f"❌ 写入 Notion 失败: {e}")
    exit(1)
