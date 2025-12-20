# notion-daily-summarizer

一个自动化生成 Notion 每日总结与新闻分析的脚本集合，支持快讯聚合与 MKT 新闻两类分析，并通过 GitHub Actions 定时运行或手动触发。项目提供三种执行模式，可灵活控制仅跑每日总结、仅跑新闻聚合，或两者同时执行。

## 架构概览
- 入口脚本：`daily_summary_main.py`
  - 加载并运行新闻聚合模块，统一写入 Notion 子页面（快讯与 MKT），并在失败时写入占位内容（`daily_summary_main.py:25–74`）。
  - 执行每日总结流程（检索想法数据库、生成总结、创建/更新子页面），并触发看板状态更新（`daily_summary_main.py:108–189`）。
- 每日总结：
  - 想法检索：`idea_retriever.py`，自动识别数据库或页面子数据库，筛选“未开始/Status/Select”类字段（`idea_retriever.py:63–105`、`:123–161`）。
  - 总结生成：`summary_generator.py`，调用千问模型或走回退逻辑（`summary_generator.py:409–470`）。
  - 页面写入：`page_writer.py`，查找或创建当日标题子页面，并按块追加（`page_writer.py:170–267`）。
- 新闻聚合：
  - 快讯：`快讯聚合LLM分析.py`，抓取与去重、汇总上下文、调用千问生成或占位（`快讯聚合LLM分析.py:146–231`）。
  - MKT：`MKT新闻LLM分析.py`，抓取列表与详情、构造上下文、调用千问生成；失败时写入翻译汇总（`MKT新闻LLM分析.py:290–362`）。
- 模型与提示词：
  - `summary_generator.call_qwen_api(content, type=None)` 根据 `type` 选择系统提示词：`KX`（快讯），`MKT`（MKT 新闻），否则为默认分析提示词（`summary_generator.py:409–429`、HTTP 回退 `:448–466`）。

## 执行模式
- 通过环境变量 `SIGN` 控制：
  - `SIGN=1`：仅每日总结（`daily_summary_main.py:197–213`）
  - `SIGN=2`：仅新闻聚合（快讯 + MKT）（`daily_summary_main.py:197–213`）
  - `SIGN=0` 或未设置：同时执行（`daily_summary_main.py:197–213`）

## 配置变量
- 必需（Secrets 或本地环境）：
  - `NOTION_TOKEN`：Notion 集成令牌
  - `IDEA_DB_ID`：想法数据库 ID（可为页面 ID，代码会尝试发现子数据库）
  - `DIARY_PARENT_PAGE_ID`：每日总结父页面 ID
  - `OPENAI_API_KEY`：千问密钥（兼容 `DASHSCOPE_API_KEY`）
- 新闻聚合写入目标：
  - `FLASH_DIARY_PAGE_ID`：快讯分析父页面 ID
  - `MKT_DIARY_PAGE_ID`：MKT 分析父页面 ID
- 模型选择：
  - `QWEN_MODEL`：默认 `qwen-turbo`；可通过 Secrets 动态切换为 `qwen-plus` 等（`summary_generator.py:8`）
- 模块内部行为开关：
  - `AGGREGATOR_MODE`：由入口脚本设置为 `"1"`，用于防止模块在入口运行时重复写入，统一由入口写入（`daily_summary_main.py:25–32`）。

## GitHub Actions
- 工作流文件：`.github/workflows/daily.yml`
- 依赖安装：`notion-client openai requests pandas`（`daily.yml:27–29`）
- 环境变量映射（Secrets）：
  - `NOTION_TOKEN`、`IDEA_DB_ID`、`DIARY_PARENT_PAGE_ID`、`OPENAI_API_KEY`
  - `FLASH_DIARY_PAGE_ID`、`MKT_DIARY_PAGE_ID`、`QWEN_MODEL`、`SIGN`（`daily.yml:31–40`）
- 触发方式：
  - 定时 `cron`：每天 UTC 17:00（北京时间次日 1:00）（`daily.yml:5`）
  - 手动触发：`workflow_dispatch` 支持选择分支（`daily.yml:6–11`）

## 本地运行示例（Windows）
- 仅每日总结：
  - `set SIGN=1 && python daily_summary_main.py`
- 仅新闻聚合：
  - `set SIGN=2 && python daily_summary_main.py`
- 全部执行：
  - `set SIGN=0 && python daily_summary_main.py`
- 必需环境变量：
  - `NOTION_TOKEN`、`IDEA_DB_ID`、`DIARY_PARENT_PAGE_ID`、`OPENAI_API_KEY`
  - 新闻聚合写入需：`FLASH_DIARY_PAGE_ID`、`MKT_DIARY_PAGE_ID`

## Notion 页面与权限
- 请将 Notion 集成共享到目标父页面与数据库，否则会报 404 或无法写入。
- 每日总结与新闻页面标题：
  - 每日总结：`每日总结 - YYYY-MM-DD`
  - 快讯分析：`快讯分析 - YYYY-MM-DD`
  - MKT 分析：`MKT分析 - YYYY-MM-DD`

## 常见问题
- 千问返回 401/403：
  - 401：密钥无效；请检查 `OPENAI_API_KEY` 或 `DASHSCOPE_API_KEY`。
  - 403（`AllocationQuota.FreeTierOnly`）：账号处于“仅免费额度”模式或额度已用尽；请在控制台关闭该模式或配置付费额度。
- 模块未写入但主入口写入成功：
  - 入口设置了 `AGGREGATOR_MODE`，模块在入口运行时不会重复写入；统一由入口写入并打印“正在更新页面...”日志。
- `IDEA_DB_ID` 为页面 ID：
  - 代码会尝试在该页面下发现子数据库并自动选择（`idea_retriever.py:1–60`、`:63–105`）。

## 目录结构（关键文件）
- `daily_summary_main.py`：主入口与模式切换、统一写入
- `idea_retriever.py`：Notion 数据库/页面查询与状态更新
- `summary_generator.py`：千问调用与提示词选择、回退逻辑
- `page_writer.py`：查找/创建页面与写入块内容
- `快讯聚合LLM分析.py`：快讯抓取与分析
- `MKT新闻LLM分析.py`：MKT 列表与详情抓取、分析
