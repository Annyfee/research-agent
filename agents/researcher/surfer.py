# 【搜索员】 负责调用工具并搜索。
import json
from datetime import datetime

import openai
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState
from loguru import logger

from agents.researcher.state import Researcher
from config import OPENAI_API_KEY
from state import ResearchAgent
from tools.utils import clean_msg_for_deepseek

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=OPENAI_API_KEY,
    base_url="https://api.deepseek.com",
    temperature=0.6
)


async def surfer_node(state:Researcher,tools=None):
    """
    【搜索员】
    职责: 针对单任务 state["task"] 进行搜索
    """
    task = state["task"]
    retry_count = state["retry_count"]
    task_idx = state["task_idx"]

    prefix = f"🏄 [Surfer #{task_idx}]"

    advice = ""
    if retry_count > 0:
        advice = f"⚠️ 警告: 上一次搜索未获得有效信息。这是第 {retry_count} 次重试。请务必更换更精准的关键词，或者尝试不同的搜索方向。"

    # 快速判断是否有工具返回
    has_search_result = any(isinstance(msg,ToolMessage) for msg in state["messages"])

    stage = "深度抓取" if has_search_result else "广度搜索"

    logger.info(f"{prefix} 启动执行 | 阶段: {stage} | 任务: {task} (重试: {retry_count})")


    # logger.info(f"🏄 [Surfer] 开始执行任务: {task} (重试: {retry_count})")

    sys_prompt = f"""你是一名专业的全网信息采集专家。
        当前任务: "{task}"
        当前时间: {datetime.now().strftime("%Y-%m-%d")}

        {advice}

        ### 🛠️ 你的标准作业程序 (SOP):
        你处于“Map-Reduce”架构的【采集端】。你的唯一目标是**获取高质量的全文数据**。

        请根据当前的【执行状态】灵活选择下一步行动：

        **状态 A: 起步阶段 (无历史搜索结果)**
        - **动作**: 调用 `web_search` 进行广撒网。
        - **策略**: 构造精准的关键词组合，寻找该领域的权威信源。

        **状态 B: 推进阶段 (已有搜索列表)**
        - **动作**: 分析上一步 `web_search` 返回的列表。
        - **决策**: 挑选 1-3 个最匹配、最有深度的 URL（优先选长文、研报、深度解析）。
        - **执行**: 立即调用 `batch_fetch` 或 `get_page_content` 抓取正文。
        - **禁忌**: 不要重复搜索！除非上一步的搜索结果全是垃圾。

        ### ⚠️ 执行严律:
        1. **拒绝废话**: 这是一个自动化接口，严禁输出“好的我来搜”、“根据结果我决定”等思考过程。
        2. **工具优先**: 直接输出 Tool Call。
        3. **目标导向**: 优先获取长文、研报、深度解析。
        """

    # # 格式化消息：确保所有 ToolMessage.content 都是字符串
    # formatted_msg = []
    # # 是否有工具返回
    # has_search_result = False
    # for msg in state["messages"]:
    #     if isinstance(msg, ToolMessage) and not isinstance(msg.content, str):
    #         has_search_result = True
    #         # 如果 content 是列表，转换为 JSON 字符串 --》 这个问题非常深:ToolMessage的所有内容一定要做一次修复:你无法确保MCP返回的信息百分百是str而非list
    #         formatted_msg.append(
    #             ToolMessage(
    #                 content=json.dumps(msg.content, ensure_ascii=False),
    #                 tool_call_id=msg.tool_call_id,
    #                 name=msg.name,
    #                 id=msg.id
    #             )
    #         )
    #     else:
    #         formatted_msg.append(msg)

    messages = [SystemMessage(content=sys_prompt)] + state["messages"]

    safe_messages = clean_msg_for_deepseek(messages)

    # if not formatted_msg:
    #     messages.append(HumanMessage(content=f"请开始执行采集任务: {task}")) # 只在冷启动，无历史时让它开始

    if not tools:
        logger.error("❌ Surfer 没拿到工具列表")
        return {"messages": [HumanMessage(content="系统错误：工具未加载")]}



    try:
        response = await llm.bind_tools(tools).ainvoke(safe_messages)

        # 【新增改动点】: 打印它决定干什么，让你心里有数
        if response.tool_calls:
            tools_name = ",".join([t['name'] for t in response.tool_calls])
            logger.success(f"🤖 {prefix} 决策: 调用 {tools_name}")
        else:
            logger.warning(f"🤔 {prefix} 思考中(无工具调用)")


        return {"messages":[response]}
    # AI的api可能会拒绝生成内容，需要做防护
    except openai.BadRequestError as e:
        # 捕获 llm 的内容风控错误
        err_dict = e.body or {}
        if "Content Exists Risk" in str(err_dict):
            logger.error(f"🚫 {prefix} 触发 DeepSeek 内容风控，强制跳过当前轮次。")
            # 返回一个由 Human 构造的 System 提示，假装这一步失败了，让 Leader 决定是否重试
            return {"messages": [HumanMessage(content="系统警告：上一轮请求触发了内容安全过滤，请尝试更换搜索关键词。")]}
        else:
            logger.error(f"❌ {prefix} API 请求错误: {e}")
            return {"messages": []}

    except Exception as e:
        logger.error(f"❌ {prefix} 未知错误: {e}")
        return {"messages": []}
























# async def surfer_node(state:ResearchAgent,tools=None):
#     """
#     【搜索员】
#     职责: 针对任务，进行专门的搜索
#     """
    # # 安全检查
    # if not tools:
    #     logger.error("❌ Surfer 未接收到工具！")
    #     return {"next_node": "writer"}
    #
    # # 提取当前task
    # cur_task_idx = state["cur_task_idx"]
    # tasks = state["tasks"]
    # task = tasks[cur_task_idx]
    #
    # # 边界检查
    # if cur_task_idx >= len(tasks):
    #     logger.warning(f"⚠️ 任务索引越界 ({cur_task_idx}/{len(task)})，强制结束搜索")
    #     return {"next_node":"writer"}
    #
    # # 开始执行任务
    # logger.info(f"🏄 [Surfer] 执行任务 {cur_task_idx + 1}/{len(tasks)}: {task}")
    #
    # sys_prompt = f"""你是一名全网搜索与数据抓取专家。当前时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}。
    # 你的唯一任务是调用工具来获取信息。
    #     当前任务: "{task}"
    #
    #     规则：
    #     1. 直接调用 `web_search` 工具。
    #     2. 不要输出任何寒暄、解释或“我将为您搜索”之类的废话。
    #     3. 这是一个自动化流程，只接收工具调用请求。
    # """
    # logger.info("正在搜寻相关文章...")
    #
    # # messages = [SystemMessage(content=sys_prompt)] + state["messages"] +  [HumanMessage(content=f"当前任务:{task},请开始执行搜索和抓取")]
    #
    #
    # # 格式化消息：确保所有 ToolMessage.content 都是字符串
    # formatted_msg = []
    # for msg in state["messages"]:
    #     if isinstance(msg, ToolMessage) and not isinstance(msg.content, str):
    #         # 如果 content 是列表，转换为 JSON 字符串
    #         formatted_msg.append(
    #             ToolMessage(
    #                 content=json.dumps(msg.content, ensure_ascii=False),
    #                 tool_call_id=msg.tool_call_id,
    #                 name=msg.name,
    #                 id=msg.id
    #             )
    #         )
    #     else:
    #         formatted_msg.append(msg)
    #
    # messages = [SystemMessage(content=sys_prompt)] + formatted_msg + [HumanMessage(content=f"当前任务:{task},请开始执行搜索和抓取")]
    #
    #
    #
    # response = await llm.bind_tools(tools).ainvoke(messages)
    #
    # # 将返回的内容记录到当前上下文
    # return {
    #     "messages":[response],
    #     "next_node":"tools"
    # }