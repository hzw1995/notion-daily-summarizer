import os
import json
import requests

# 从环境变量获取配置
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

"""
调用千问API生成总结
"""
def call_qwen_api(content):
    """
    调用千问API生成总结
    """
    url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    api_key = OPENAI_API_KEY  # 使用相同的环境变量
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": "qwen-plus",  # 可以根据需要选择模型
        "input": {
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个高效的知识整理助手，请将以下碎片想法归纳成一段结构清晰、有逻辑的总结，突出关键洞察和行动项。同时，根据这些想法，搜集相关信息并提供更深入的分析。"
                },
                {
                    "role": "user",
                    "content": content
                }
            ]
        },
        "parameters": {
            "temperature": 0.7,
            "max_tokens": 2000
        }
    }
    
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    
    if response.status_code == 200:
        result = response.json()
        return result.get("output", {}).get("text", "")
    else:
        raise Exception(f"API调用失败: {response.status_code}, {response.text}")


def generate_summary(ideas, idea_retriever):
    """
    使用千问API生成总结
    
    Args:
        ideas: 从Notion获取的想法列表
        idea_retriever: idea_retriever模块，用于获取想法的标题、描述和内容
    
    Returns:
        str: 生成的总结
    """
    if not ideas:
        return "过去30天没有想法记录"
    
    # 收集所有想法的内容
    idea_texts = []
    for idea in ideas:
        title = idea_retriever.get_idea_title(idea)
        description = idea_retriever.get_idea_description(idea)
        content = idea_retriever.get_idea_content(idea)
        
        idea_text = f"标题：{title}"
        if description:
            idea_text += f"\n描述：{description}"
        if content:
            idea_text += f"\n内容：{content}"
        
        idea_texts.append(idea_text)
    
    # 合并所有想法内容
    full_text = "\n---\n".join(idea_texts)
    
    try:
        # 调用千问API
        summary = call_qwen_api(full_text)
        return summary
    except Exception as e:
        print(f"❌ 调用千问API失败: {e}")
        # 如果API调用失败，返回简单的总结
        return f"过去30天共有{len(ideas)}个想法：\n\n" + "\n".join([f"- {idea_retriever.get_idea_title(idea)}" for idea in ideas])


if __name__ == "__main__":
    # 测试生成总结功能
    try:
        # 导入idea_retriever模块
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        import idea_retriever
        
        # 假设我们有一些测试想法
        test_ideas = [
            {
                "id": "test-id-1",
                "properties": {
                    "名称": {
                        "title": [
                            {
                                "text": {
                                    "content": "测试想法1"
                                }
                            }
                        ]
                    },
                    "描述": {
                        "rich_text": [
                            {
                                "text": {
                                    "content": "这是一个测试想法的描述"
                                }
                            }
                        ]
                    }
                }
            }
        ]
        
        summary = generate_summary(test_ideas, idea_retriever)
        print("生成的总结：")
        print(summary)
    except Exception as e:
        print(f"错误: {e}")
