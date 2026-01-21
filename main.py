import asyncio
import json

import logging  # <--- 记得导入 logging

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

from config import OPENAI_API_KEY
from tools.stream import run_agent_with_streaming

# [新增 2] 初始化 RAG (单例模式)
# 这一步会加载 rag_store.py 里的配置 (本地/云端)
rag = RAGStore()

MCP_SERVERS = {
    "搜索服务": {
        "transport": "streamable_http",
        "url": "http://0.0.0.0:8002/mcp"
    }
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

    return "\n\n---\n\n".join(formatted_res)


# [新增 4] 定义处理器节点 (核心拦截逻辑)
async def processor_node(state: MessagesState):
    """
    拦截器：监听 MCP 抓取工具，自动存入 RAG 并缩减上下文
    """
    messages = state["messages"]
    last_msg = messages[-1]

    # 只处理 ToolMessage
    if isinstance(last_msg, ToolMessage):
        # 拦截目标：MCP 的抓取工具名 (需与 mcp_server_search.py 一致)
        if last_msg.name in ["get_page_content", "batch_fetch"]:

            content = last_msg.content
            # 简单校验
            if content and len(str(content)) > 50:
                logger.info(f"🕵️ [Processor] 捕获到抓取数据 (长度: {len(str(content))})")

                # A. 存入 RAG
                rag.add_documents(str(content), source_url=f"tool_call_{last_msg.tool_call_id}")

                # B. 替换记忆
                new_content = (f"✅ [系统通知] ...")  # 内容不变

                return {
                    "messages": [
                        ToolMessage(
                            content=new_content,
                            tool_call_id=last_msg.tool_call_id,
                            name=last_msg.name,
                            # 🔥🔥🔥【新增这行】核心修复！！！🔥🔥🔥
                            # 只有继承了上一条消息的 ID，LangGraph 才会执行“覆盖”操作，而不是“追加”
                            id=last_msg.id
                        )
                    ]
                }
    return {}


def build_graph(available_tools):
    if not available_tools:
        print('⚠️ 未加载任何工具')

    # [修改 A] 合并工具：MCP工具 + RAG查询工具
    all_tools = available_tools + [search_knowledge_base]

    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=OPENAI_API_KEY,
        base_url="https://api.deepseek.com",
        streaming=True
    )

    # [修改 B] 更新 Prompt，教会 Agent 工作流
    sys_prompt = (
        "你是一个智能研究助手。工作流程：\n"
        "1. 搜索(web_search) -> 2. 抓取(batch_fetch) -> "
        "3. [系统会自动存入RAG] -> 4. 你必须调用 'search_knowledge_base' 阅读内容 -> 5. 回答。"
    )

    # 绑定合并后的工具列表
    llm_with_tools = llm.bind_tools(all_tools)
    tool_node = ToolNode(all_tools)

    # 你的原版 agent_node (完全保持不变)
    async def agent_node(state: MessagesState):
        formatted_msg = []
        for msg in state["messages"]:
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

    # [修改 C] 改变流向：Tools -> Processor -> Agent
    workflow.add_edge("tools", "processor")
    workflow.add_edge("processor", "agent")  # 以前是 tools -> agent

    return workflow.compile(MemorySaver())


async def chat_loop(app):
    thread_id = "user_123"
    config = {"configurable": {"thread_id": thread_id}}
    while 1:
        user_input = input('\n\n👤 你:').strip()
        # 增加一个退出判断，方便调试
        if not user_input or user_input in ["exit", "quit"]:
            break
        await run_agent_with_streaming(app, user_input, config)


async def main():
    print("🔌 正在初始化MCP客户端...")

    client = MultiServerMCPClient(MCP_SERVERS)
    tools = await client.get_tools()
    print(f"✅️ 成功加载工具{[t.name for t in tools]}")

    app = build_graph(tools)
    await chat_loop(app)


if __name__ == '__main__':
    asyncio.run(main())