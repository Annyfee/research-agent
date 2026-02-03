import asyncio
import json

import logging  # <--- 记得导入 logging
import os
import re
import shutil

from datetime import datetime

# --- 消音代码 --- 等级低于Warning的提示全部屏蔽
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)
# -----------------------


from langchain_core.messages import SystemMessage, ToolMessage, HumanMessage
# [新增 1] 引入 tool 装饰器和 RAG 仓库
from langchain_core.tools import tool
from tools.rag_store import RAGStore

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from loguru import logger

from config import OPENAI_API_KEY, LANGCHAIN_API_KEY
from tools.stream import run_agent_with_streaming

os.environ["LANGCHAIN_TRACING_V2"] = "true"  # 总开关，决定启用追踪功能
os.environ["LANGCHAIN_PROJECT"] = "research-agent"  # 自定义项目名
os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY

# [新增 2] 初始化 RAG (单例模式)
# 这一步会加载 rag_store.py 里的配置 (本地/云端)
rag = RAGStore()

MCP_SERVERS = {
    "搜索服务": {
        "transport": "http",
        "url": "http://127.0.0.1:8003/mcp"
    }
    # "搜索服务":{
    #         "transport": "stdio",
    #         "command": "python",
    #         "args": ["-m", "tools.mcp_server_search"],
    #         "env": None
    # }
}


# [新增 3] 定义 RAG 检索工具 (给 Agent 查库用)
@tool
def search_knowledge_base(query: str):
    """
    当系统提示'资料已存入知识库'时，或者需要回答基于事实的问题时，
    必须调用此工具从本地知识库(RAG)中检索。
    """
    logger.info(f"📚 Agent 正在查询知识库: {query}")
    results = rag.query(query)

    if not results:
        return "知识库中未找到相关内容。"

    # 格式化返回结果
    formatted_res = []
    for doc in results:
        source = doc.metadata.get('source', 'unknown')
        score = doc.metadata.get('rerank_score', 0)
        formatted_res.append(f"[来源: {source} | 置信度: {score:.2f}]\n{doc.page_content}")
    print('formatted_res:::', formatted_res)

    return "\n\n---\n\n".join(formatted_res)


# [新增 4] 定义处理器节点 (核心拦截逻辑)
async def processor_node(state: MessagesState):
    messages = state["messages"]
    last_msg = messages[-1]

    print("messages:::",messages)
    # 1. 判断是否是我们要拦截的长文本工具
    if isinstance(last_msg, ToolMessage) and last_msg.name in ["get_page_content", "batch_fetch"]:
        target_id = last_msg.tool_call_id

        # 2. 往回找 AI 的原始指令 (寻找匹配该 ID 的 tool_calls) - 具体数据无序且混乱，输出流程并非线性的结构，如果不用id显式指定，根本无法保证url获取的准确性
        source_url = "未知来源"
        for msg in reversed(messages):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    print('tc:::', tc)
                    if tc["id"] == target_id:
                        # 找到了！取出 AI 当初传给工具的 url 参数
                        args = tc.get("args", {})
                        print('args:::', args)
                        # 如果是 batch_fetch 是 urls 列表，如果是 get_page_content 是 url 字符串
                        source_url = str(args.get("urls") or args.get("url") or "tool_call_id")
                        break

        # 3. 数据清洗
        raw_content = str(last_msg.content)

        # A. 物理剔除所有图片标签 ![描述](url)
        # 这些标签会导致 Agent 误以为图片链接是参考资料来源
        cleaned = re.sub(r'!\[.*?\]\(.*?\)', '', raw_content)

        # B. 剔除常见的网页“噪声”行 (页脚、备案、报警等)
        # 解决第一个 formatted_res 里的“110报警/营业执照”污染问题
        noise_keywords = ["版权所有", "©", "备案", "110报警", "营业执照", "免责声明", "出版物许可证"]
        filtered_lines = []
        for line in cleaned.split('\n'):
            keep = True
            for noise in noise_keywords:
                if noise in line:
                    keep = False
                    break
            if keep:
                filtered_lines.append(line)
        final_text = '\n'.join(filtered_lines)

        # 4. 物理入库 (离线模块)
        rag.add_documents(final_text, source_url=source_url)

        # 5. 构造极其简单的通知
        new_msg = ToolMessage(
            content="✅ [系统] 内容已存入 RAG。由于原文过长，已在当前上下文中物理删除，请调用检索工具。",
            tool_call_id=target_id,
            name=last_msg.name,
            id=last_msg.id  # 保持 ID 一致
        )

        # 6. 【断根操作】用“列表切片”直接剔除掉原本的那条长消息，替换为短消息
        # 这样返回后，MessagesState 里的最后一条消息会被物理替换为我们的短消息
        return {"messages": [new_msg]}

    return {}


def build_graph(available_tools):
    if not available_tools:
        print('⚠️ 未加载任何工具')

    # [修改 A] 合并工具：MCP工具 + RAG查询工具(自创)
    all_tools = available_tools + [search_knowledge_base]

    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=OPENAI_API_KEY,
        base_url="https://api.deepseek.com",
        streaming=True
    )

    # [修改 B] 更新 Prompt，教会 Agent 工作流
    sys_prompt = (f"""
        你是一个专业、严谨的 AI 智能研究助手。
        当前系统时间（时空锚点）是：{datetime.now().strftime("%Y年%m月%d日 %H:%M")}。所有检索到的信息都必须以此时间为基准进行审计。

        ### 🛠️ 标准作业程序 (SOP):
        1. ** 全网搜索 **: 调用 `web_search` 获取最新的信息摘要。
        2. ** 深度抓取 **: 挑选最有价值的链接，调用 `batch_fetch` 获取正文。
        3. ** 记忆切换 **: 注意！抓取后的正文已自动存入 RAG 知识库。你当前上下文中【没有】正文内容。
        4. ** 精准检索 **: 你【必须】立即调用 `search_knowledge_base`。只有阅读了检索回来的片段，你才有权回答。
        5. ** 整合输出 **: 根据检索到的事实，组织逻辑严密的回答。
        6. ** 多轮查询 **: 如果当前返回数据或质量不足，重新搜索或检索数据库。

        ### 📑 引用规范:
        - ** 必须溯源 **: 你的每一个核心观点都必须对应参考资料。
        - ** 格式要求 **: 在回复末尾列出【参考资料】，必须使用检索工具返回的真实 URL 链接，返回URL链接不能重复。
        - ** 严禁脑补 **: 如果 RAG 中没有相关信息，请诚实回答“知识库中未找到细节”，不要编造 URL。

        ### ⚠️ 检索与引用严律:
        1. **真实溯源**: 你在检索结果中可能会看到大量 URL（如图片链接、页脚链接）。
        2. **防伪校验**: 你【只能】将你通过 `batch_fetch` 真正抓取并阅读过的原文 URL 列为参考资料。
        3. **剔除杂质**: 严禁将网页侧边栏、推荐阅读或版权声明中的无关链接列入参考资料。
        4. ** 强文本分析输出 (Insight-Driven): **
               - **拒绝罗列**: 严禁将检索到的片段进行简单的堆砌或无脑的列表罗列。
               - **结论先行**: 每个章节必须以一个核心行业洞察或趋势判断作为开头，随后引用 RAG 事实进行严密论证。
               - **跨源交叉对比**: 如果多个来源提到了同一事件（如美联储换届），你必须分析其共同点与分歧点，并指出当前时间点下最权威的消息。
               - **时序审计逻辑**: 必须区分“历史背景”、“当前动态”与“前瞻预测”。严禁将 2025 年的预测性描述误写为 2026 年的既成事实。
               - **文本张力**: 使用专业、干练的行业术语（如“存量博弈”、“边际效应”、“路径依赖”），使报告具备深度行业调研的质感，字里行间要体现出“分析”而非“复读”。

        ### 📚 参考资料格式示例:
        [1] https: // example.com / paper_details - xx年x应用行情主线深度分析报告
        [2] https: // news.tech / report-2026
        """
                  )

    # 绑定合并后的工具列表
    llm_with_tools = llm.bind_tools(all_tools)
    tool_node = ToolNode(all_tools)

    # 你的原版 agent_node (完全保持不变)
    async def agent_node(state: MessagesState):
        formatted_msg = []
        for msg in state["messages"]:
            # 当发现ToolMessage非字符串返回时，将其修正为str形式
            if isinstance(msg, ToolMessage) and not isinstance(msg.content, str):
                formatted_msg.append(
                    ToolMessage(
                        content=json.dumps(msg.content, ensure_ascii=False),
                        tool_call_id=msg.tool_call_id
                    )
                )
            else:
                formatted_msg.append(msg)
        message_for_llm = [SystemMessage(content=sys_prompt)] + formatted_msg
        response = await llm_with_tools.ainvoke(message_for_llm)
        return {"messages": [response]}

    def should_continue(state: MessagesState):
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            return "tools"
        else:
            return END

    workflow = StateGraph(MessagesState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)

    # [新增 5] 注册 processor 节点
    workflow.add_node("processor", processor_node)

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END
        }
    )

    # [修改 C] 改变流向：Tools -> Processor -> Agent (让工具返回内容先经过processor审查，rag内容存入，非rag内容才返还给agent)
    workflow.add_edge("tools", "processor")
    workflow.add_edge("processor", "agent")  # 以前是 tools -> agent

    return workflow.compile(MemorySaver())


async def chat_loop(app):
    thread_id = "user_123"
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 100  # 默认步数上限为25，但这对我们来说不够用
    }
    while 1:
        user_input = input('\n\n👤 你:').strip()
        # 增加一个退出判断，方便调试
        if not user_input or user_input in ["exit", "quit"]:
            break
        await run_agent_with_streaming(app, user_input, config)


async def main():
    # db_path = "./chroma_db"
    # if os.path.exists(db_path):
    #     shutil.rmtree(db_path)
    #     print(f"🧹 已清空旧数据库目录: {db_path}")

    print("🔌 正在初始化MCP客户端...")

    client = MultiServerMCPClient(MCP_SERVERS)
    tools = await client.get_tools()
    print(f"✅️ 成功加载工具{[t.name for t in tools]}")

    app = build_graph(tools)
    await chat_loop(app)


if __name__ == '__main__':
    asyncio.run(main())