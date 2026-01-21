🚀 项目代号：M14 DeepResearch (research-agent)1. 项目定义 (What is it?)这是一个基于 LangGraph 与 MCP 架构的自主式 AI 深度研究员。它不仅仅是一个会联网的聊天机器人，而是一个能模仿人类研究员工作流程（规划 -> 搜集 -> 阅读 -> 清洗 -> 撰写）的智能体系统。它旨在解决通用 LLM **“知识幻觉”与“时效性滞后”**的痛点，提供有理有据、信源可溯的深度研究报告。2. 核心目标 (Goals)业务目标：实现“输入一个模糊话题，输出一份万字深度报告”。系统需具备自主纠错能力（搜不到换关键词重搜）和高信噪比（自动过滤 SEO 垃圾文）。工程目标：打造一个**生产级（Production-Ready）**的 Agent 架构。验证 LangGraph（状态机编排）、MCP（标准化工具协议）与 双层 RAG（高精度检索）的融合落地。求职目标：作为一个高技术密度、可一键部署的开源项目，展示候选人在 AI Agent 全栈开发、架构设计及 DevOps 方面的综合能力，对标中高级 AI 应用工程师岗位。3. 预期功能 (Expected Features)模块功能描述状态🧠 智能规划 (Planner)将用户模糊需求（如“分析 DeepSeek 的优势”）拆解为具体的搜索关键词列表（Task Queue）。⏳ 待开发🕷️ 自主搜索 (Searcher)基于 MCP 协议 调用搜索引擎（DuckDuckGo），支持多轮搜索、去重、并发抓取。✅ 已完成📚 深度阅读 (Reader)能够抓取网页全文，利用 RAG 技术（向量化+切片）进行语义理解，而非仅看摘要。✅/⏳ 整合中🔍 动态过滤 (Filter)采用 Embedding 粗排 + Rerank 精排 的双层漏斗，自动剔除广告和无关信息，只保留高分证据。⏳ 待开发📝 报告生成 (Writer)基于过滤后的精准上下文，生成结构化 Markdown 报告，并自动标注引用来源（[1], [2]）。⏳ 待开发🖥️ 交互终端 (UI)提供 Streamlit Web 界面，实时展示 Agent 的思考过程（Log）和最终报告，支持人工干预。⏳ 待开发4. 技术栈图谱 (Tech Stack)这是你简历上最“值钱”的部分：核心编排 (Orchestration):LangGraph: 摒弃传统的 Chain，使用状态机 (StateGraph) 管理 Agent 的循环、分支与记忆。LangChain: 用于底层的 Prompt 模板管理和模型接口封装。工具与协议 (Tools & Protocol):MCP (Model Context Protocol): 使用 fastmcp 构建独立的搜索微服务，实现 Agent 与工具的解耦（这是 2025 年的前沿热点）。Tools: ddgs (DuckDuckGo Search), requests (网页抓取)。RAG 知识库 (The Brain):Database: Chroma (持久化向量数据库)。Embedding: OpenAI text-embedding-3-small (高性价比) / 预留 BGE-M3 (本地化) 接口。Reranker: Jina Reranker / BGE-Reranker (核心亮点，用于提升准确率)。模型层 (LLM):DeepSeek-V3 (通过 OpenAI 兼容接口调用)：作为主力推理模型，兼顾智商与成本。工程与交付 (DevOps):Docker & Docker Compose: 实现包括 MCP Server、Agent Backend、Streamlit UI 的一键容器化部署。Streamlit: 快速构建 Python 原生的高颜值前端。🗺️ 架构逻辑图 (Mental Model)你可以把这个项目想象成一个**“编辑部”**：用户：主编，下达选题。LangGraph (主脑)：编辑部主任，负责分派任务。MCP Server (外勤)：实习记者，负责跑腿去互联网上把几万字的文章（网页）扛回来。Processor (RAG)：资料管理员，负责把实习记者扛回来的几万字“废话”进行清洗、切碎、打分，只留下最有用的 500 字精华存入档案柜。Agent (执笔)：资深作家，只看档案柜里的那 500 字精华，写出最终报道。




参考资料:


ddgs: https://pypi.org/project/duckduckgo-search/ —— duckduckgo-search pypi库 用以获取标题、网页链接、简介

jina: https://jina.ai/reader/ —— jina 爬虫，用以爬取所有网页，用法只需 https://r.jina.ai/ 附上对应网页名即可。用该方法可以快速获取对应返回的内容。

从架构上理解：
虽然jina支持MCP，但我们仍选择自己封装MCP：
这里我们将ddgs与jina封装在一个MCP里，可以一块使用。同时这样解耦性相比写多个api调用也更为友好，拓展性更适合：
以后再加入任意如网页搜索api，直接封装进这个MCP即可。