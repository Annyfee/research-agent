from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from loguru import logger


from tools.rag_store import RAGStore

global_rag_store = RAGStore()

# [新增 3] 定义 RAG 检索工具 (给 Agent 查库用)
@tool
def search_knowledge_base(query: str):
    """
    当系统提示'资料已存入知识库'时，或者需要回答基于事实的问题时，
    必须调用此工具从本地知识库(RAG)中检索。
    """
    logger.info(f"📚 Agent 正在查询知识库: {query}")
    return global_rag_store.query_formatted(query)

# 加载所有工具
async def load_all_tools():
    """
    初始化并返回所有可用工具列表(MCP+RAG)
    """
    mcp_config = {
        "搜索服务": {
            "transport": "http",
            "url": "http://127.0.0.1:8003/mcp"
        }
    }
    logger.info("🔌 正在连接 MCP 服务器...")
    try:
        client = MultiServerMCPClient(mcp_config)
        mcp_tools = await client.get_tools()
        logger.success(f"✅ MCP 工具加载成功: {[t.name for t in mcp_tools]}")
    except Exception as e:
        logger.error(f"❌ MCP 连接失败: {e}")
        mcp_tools = []

    return mcp_tools + [search_knowledge_base]