# 【规划员】 任务拆解:将用户问题分成3-5个具体的指令 planner -> surfer
import json
from datetime import datetime

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState, message
from loguru import logger

from config import OPENAI_API_KEY
from state import ResearchAgent

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=OPENAI_API_KEY,
    base_url="https://api.deepseek.com",
    temperature=0.3
)


async def planner_node(state:ResearchAgent):
    """
    【规划员】
    职责: 将模糊的用户需求拆解为 2-4 个具体的、可执行的搜索指令。
    """

    user_query = state["messages"][-1].content

    logger.info(f"🎯 [Planner] 正在拆解课题: {user_query}")


    sys_prompt = f"""你是一名首席研究规划师。当前时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}。
    你的任务是将用户模糊、庞大的需求，拆解为 **3-5 个具体的、可执行的搜索引擎关键词**。

    【拆解原则】
    1. **多维视角**: 不要只换一种说法搜。要从“定义/背景”、“技术原理”、“市场数据”、“竞品对比”、“最新评价”等不同维度拆解。
    2. **关键词化**: 输出必须是适合 Google/Bing 搜索的关键词组合，而不是长难句。
    3. **逻辑递进**: 子任务应当有先后逻辑，帮助后续的 Writer 建立完整的知识链条。

    【输出格式】
    {{
        "tasks":[
            "搜索 DeepSeek 公司的融资历程",
            "查找 DeepSeek-V3 模型的评测数据",
            "分析当前开源大模型市场的竞争格局"
        ]
    }}

    不要输出任何多余的解释或废话，只输出列表。
    """

    # 只发System与User Query，保证上下文干净  这种写法用于单轮对话，x+x用于多轮对话
    messages = [
        SystemMessage(content=sys_prompt),
        state["messages"][-1]
    ] # 只将用户的单次提问加入消息列表

    # 保底确定返回数据格式正确
    try:
        response = await llm.ainvoke(messages)
        # 防止可能存在的markdown语法
        content = response.content.replace("```json","").replace("```","").strip()
        tasks = json.loads(content)["tasks"]
        # 二次兜底，防止任务为空或值不是列表
        if not tasks or not isinstance(tasks,list):
            raise ValueError("任务为空或不是列表")
        return {
            "tasks": tasks,
            # "main_route": "surfer"
        }
    except Exception as e:
        logger.warning(f"⚠️ [Planner] 解析失败，回滚到单任务模式: {e}")
        # 保底:把用户原话当做任务
        return {
            "tasks":[user_query],
            # "main_route":"surfer"
        }