import logging

# --- 消音代码 --- 等级低于Warning的提示全部屏蔽
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)
# -----------------------

from loguru import logger
import asyncio
import uuid

from graph import build_graph
from tools.stream import run_agent_with_streaming




async def main():
    logger.info("🚀 正在启动 Research Swarm 系统...")

    app = await build_graph()

    thread_id = str(uuid.uuid4())
    config = {
        "configurable":{"thread_id":thread_id,},
        "recursion_limit": 100
    }

    print("\n💡 系统就绪！请输入你的研究课题 (输入 'q' 退出):")

    while 1:
        user_input = input("\n你:")
        if user_input == "q":
            break
        await run_agent_with_streaming(app,user_input,config)

if __name__ == '__main__':
    asyncio.run(main())