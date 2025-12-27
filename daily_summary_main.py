import os
import sys
import importlib.util

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入各个模块
import idea_retriever
import summary_generator
import page_writer

def load_module(module_name, filename):
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        print(f"加载模块失败 {filename}: {e}")
        return None
    return mod

def run_news_aggregator():
    os.environ["AGGREGATOR_MODE"] = "1"
    flash_news = load_module("flash_news", "快讯聚合LLM分析.py")
    mkt_news = load_module("mkt_news", "MKT新闻LLM分析.py")
    ids = {
        "flash": (os.environ.get("FLASH_DIARY_PAGE_ID") or os.environ.get("DIARY_PARENT_PAGE_ID") or "").strip(),
        "mkt": (os.environ.get("MKT_DIARY_PAGE_ID") or os.environ.get("DIARY_PARENT_PAGE_ID") or "").strip(),
    }
    try:
        if flash_news is None:
            raise RuntimeError("快讯模块不可用")
        flash_news.main()
        content = getattr(flash_news, "report", None)
        if not content:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            content = f"{today} 快讯分析暂无可写入内容"
        flash_news.write_to_notion(content, ids["flash"]) 
    except Exception as e:
        print(f"快讯分析执行失败: {e}")
        try:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            fallback = f"{today} 快讯分析暂无可写入内容"
            if flash_news is not None:
                flash_news.write_to_notion(fallback, ids["flash"]) 
        except Exception:
            pass

    try:
        if mkt_news is None:
            raise RuntimeError("MKT新闻模块不可用")
        mkt_news.main()
        content = getattr(mkt_news, "mkt_analysis", None)
        if not content:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            content = f"{today} MKT新闻分析暂无可写入内容"
        mkt_news.write_to_notion(content, ids["mkt"]) 
    except Exception as e:
        print(f"MKT新闻分析执行失败: {e}")
        try:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            fallback = f"{today} MKT新闻分析暂无可写入内容"
            if mkt_news is not None:
                mkt_news.write_to_notion(fallback, ids["mkt"]) 
        except Exception:
            pass


def run_flash_only():
    os.environ["AGGREGATOR_MODE"] = "1"
    flash_news = load_module("flash_news", "快讯聚合LLM分析.py")
    target_id = (os.environ.get("FLASH_DIARY_PAGE_ID") or os.environ.get("DIARY_PARENT_PAGE_ID") or "").strip()
    try:
        if flash_news is None:
            raise RuntimeError("快讯模块不可用")
        flash_news.main()
        content = getattr(flash_news, "report", None)
        if not content:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            content = f"{today} 快讯分析暂无可写入内容"
        flash_news.write_to_notion(content, target_id)
    except Exception as e:
        print(f"快讯分析执行失败: {e}")
        try:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            fallback = f"{today} 快讯分析暂无可写入内容"
            if flash_news is not None:
                flash_news.write_to_notion(fallback, target_id)
        except Exception:
            pass

def run_mkt_only():
    os.environ["AGGREGATOR_MODE"] = "1"
    mkt_news = load_module("mkt_news", "MKT新闻LLM分析.py")
    target_id = (os.environ.get("MKT_DIARY_PAGE_ID") or os.environ.get("DIARY_PARENT_PAGE_ID") or "").strip()
    print(f"MKT目标页面ID: {target_id or '未配置'}")
    try:
        if mkt_news is None:
            raise RuntimeError("MKT新闻模块不可用")
        mkt_news.main()
        content = getattr(mkt_news, "mkt_analysis", None)
        if not content:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            content = f"{today} MKT新闻分析暂无可写入内容"
        mkt_news.write_to_notion(content, target_id)
    except Exception as e:
        print(f"MKT新闻分析执行失败: {e}")
        try:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            fallback = f"{today} MKT新闻分析暂无可写入内容"
            if mkt_news is not None:
                mkt_news.write_to_notion(fallback, target_id)
        except Exception:
            pass

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
            "DIARY_PARENT_PAGE_ID",
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
            
            # 2. 查询想法来源
            print("\n📊 正在扫描Notion来源...")
            source_structure = idea_retriever.scan_idea_source(idea_retriever.IDEA_DB_ID)
            db_id = source_structure.get("database_id")
            pages = source_structure.get("pages", [])
            
            # 处理独立页面（市场分析）
            if pages:
                print(f"✅ 发现 {len(pages)} 个市场分析页面，开始处理...")
                for page in pages:
                    try:
                        title = idea_retriever.get_idea_title(page)
                        print(f"   正在分析页面: {title}")
                        content = idea_retriever.get_idea_content(page)
                        if not content:
                            print("   ⚠️ 页面内容为空，跳过")
                            continue
                            
                        # AI分析
                        analysis = summary_generator.call_qwen_api(content)
                        if analysis:
                            pid = page_writer.create_market_analysis(analysis)
                            print(f"   ✅ 市场分析已写入，页面ID: {pid}")
                        else:
                            print("   ⚠️ AI分析结果为空")
                    except Exception as e:
                        print(f"   ❌ 处理页面失败: {e}")
            
            # 处理数据库想法
            ideas = []
            if db_id:
                print(f"✅ 正在查询想法数据库: {db_id}")
                ideas = idea_retriever.query_idea_database(specific_db_id=db_id)
            else:
                # 尝试使用默认逻辑（兼容旧行为）
                try:
                    ideas = idea_retriever.query_idea_database()
                except Exception:
                    print("⚠️ 未发现想法数据库")
            
            if not ideas:
                print("😴 过去30天没有想法记录，今日不更新每日总结。")
                return
            
            print(f"✅ 成功获取 {len(ideas)} 个想法记录")
            
            # 3. 检查是否已存在今日总结页面
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            title = f"股市总结 - {today}"
            
            existing_page = page_writer.find_page_by_title(page_writer.DIARY_PARENT_PAGE_ID, title)
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
            
            summary = ""
            try:
                summary = summary_generator.call_qwen_api(full_text).strip()
            except Exception:
                summary = ""
            if not summary:
                summary = summary_generator.generate_summary(ideas, idea_retriever)
            
            # 5. 创建或更新每日总结页面
            print("\n📝 正在创建或更新每日总结页面...")
            page_id = page_writer.create_daily_summary(summary, existing_content)
            
            print(f"\n🎉 每日总结生成完成！页面ID: {page_id}")
            print("\n✅ 正在更新看板状态为完成...")
            # 使用正确的数据库ID（如果找到了子数据库）或回退到环境变量ID
            target_db_id = db_id or idea_retriever.IDEA_DB_ID
            updated = idea_retriever.update_ideas_status_to_done(ideas, target_db_id)
            print(f"已更新 {updated} 条")
            
        except Exception as e:
            print(f"\n❌ 执行失败: {str(e)}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    sign = (os.environ.get("SIGN") or "0").strip()
    if sign == "1":
        runner = DailySummaryRunner()
        runner.run()
    elif sign == "2":
        try:
            run_flash_only()
        except Exception as e:
            print(f"快讯聚合执行失败: {e}")
    elif sign == "3":
        try:
            run_mkt_only()
        except Exception as e:
            print(f"MKT聚合执行失败: {e}")
    else:
        print("🚀 开始执行每日总结全流程...")
        
        # 1. 执行新闻聚合 (快讯 + MKT)
        try:
            print("\n=== 正在执行新闻聚合 ===")
            run_news_aggregator()
        except Exception as e:
            print(f"❌ 新闻聚合执行失败: {e}")
            
        # 2. 执行每日总结 (想法分析 + 总结生成)
        try:
            print("\n=== 正在执行每日总结 ===")
            runner = DailySummaryRunner()
            runner.run()
        except Exception as e:
            print(f"❌ 每日总结执行失败: {e}")
