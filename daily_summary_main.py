import os
import sys

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入各个模块
import idea_retriever
import summary_generator
import page_writer


class DailySummaryRunner:
    """
    每日总结执行器，整合所有功能
    """
    
    def __init__(self):
        # 检查环境变量
        self.check_environment_variables()
    
    def check_environment_variables(self):
        """
        检查所有必要的环境变量
        """
        print("🔍 正在检查环境变量...")
        
        required_vars = [
            "NOTION_TOKEN",
            "IDEA_DB_ID",
            "DIARY_PAGE_ID",
            "OPENAI_API_KEY"
        ]
        
        missing_vars = []
        for var in required_vars:
            if not os.environ.get(var):
                missing_vars.append(var)
            else:
                print(f"   {var}: 已设置")
        
        if missing_vars:
            raise ValueError(f"缺少必要的环境变量: {', '.join(missing_vars)}")
    
    def run(self):
        """
        执行每日总结流程
        """
        try:
            # 1. 测试Notion连接
            print("\n📊 正在测试Notion连接...")
            page_writer.test_notion_connection()
            
            # 2. 查询想法数据库
            print("\n📊 正在查询Notion数据库...")
            ideas = idea_retriever.query_idea_database()
            
            if not ideas:
                print("😴 过去30天没有想法记录，跳过总结。")
                return
            
            print(f"✅ 成功获取 {len(ideas)} 个想法记录")
            
            # 3. 检查是否已存在今日总结页面
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            title = f"每日总结 - {today}"
            
            existing_page = page_writer.find_page_by_title(page_writer.DIARY_PAGE_ID, title)
            existing_content = ""
            
            if existing_page:
                # 如果存在，获取现有页面内容
                print("\n📄 发现已存在今日总结页面，正在获取现有内容...")
                existing_content = page_writer.get_page_content(existing_page.get("id"))
                
                if existing_content:
                    print("✅ 成功获取现有页面内容")
            
            # 4. 生成总结（如果有现有内容，会整合新旧数据）
            print("\n🤖 正在调用千问API生成总结...")
            
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
            
            # 如果有现有内容，整合新旧数据
            if existing_content:
                print("🔄 正在整合新旧数据...")
                full_text = f"# 现有总结\n{existing_content}\n\n# 新获取的想法\n{full_text}"
            
            # 调用AI生成新总结
            summary = summary_generator.call_qwen_api(full_text)
            
            # 5. 创建或更新每日总结页面
            print("\n📝 正在创建或更新每日总结页面...")
            page_id = page_writer.create_daily_summary(summary, existing_content)
            
            print(f"\n🎉 每日总结生成完成！页面ID: {page_id}")
            
        except Exception as e:
            print(f"\n❌ 执行失败: {str(e)}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    # 创建执行器并运行
    runner = DailySummaryRunner()
    runner.run()
