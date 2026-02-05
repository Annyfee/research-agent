import logging

from langchain_core.messages import HumanMessage

import state

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

    session_id = str(uuid.uuid4())

    app = await build_graph()

    config = {
        "configurable":{"thread_id":session_id,},
        "recursion_limit": 100
    }
    print("\n💡 系统就绪！请输入你的研究课题 (输入 'q' 退出):")

    while 1:
        user_input = input("\n你:")
        if user_input == "q":
            break

        inputs = {
            "messages": [HumanMessage(content=user_input)],
            "session_id":session_id,
        }

        await run_agent_with_streaming(app,inputs,config)

if __name__ == '__main__':
    asyncio.run(main())