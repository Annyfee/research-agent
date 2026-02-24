# 【前台】 分析话术，选择是否传递当前任务，还是判定用户在闲聊，不往后启动。
from datetime import datetime
from loguru import logger

from langchain_core.messages import SystemMessage, AIMessage
from langchain_openai import ChatOpenAI

from state import ResearchAgent
from config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
from tools.utils_message import clean_msg_for_deepseek


# llm每次初始化放在外面，避免每次连接都重新调用
llm = ChatOpenAI(
    model=OPENAI_MODEL,
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL,
    temperature=0
)


async def manager_node(state:ResearchAgent):
    """
    【前台经理】
    职责：分诊。
    - 闲聊 -> 回复用户 -> 结束
    - 任务 -> 不回复(静默) -> 移交 Planner
    """

    # 用暗号，比常规JSON回复更稳定
    sys_prompt = f"""你是一名专业的 AI 助手项目经理。当前时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}。

        你的核心职责是【意图识别】。请根据用户的输入，严格遵守以下判断逻辑：
        
        ### ⚠️ 身份警告：
        - 你**没有**搜索工具，你**不能**自己执行搜索。
        - 严禁输出 `<｜DSML｜` 或任何 XML 格式代码。
        - 严禁尝试模拟工具调用。

        ### 🛑 判定为【闲聊/回复】的情况 (直接回答，不要启动搜索):
        1. **闲聊/问候**: "你好", "你是谁", "天气不错"。
        2. **追问/纠正**: "不对", "我问的是这个", "停下", "在这个基础上再详细点"。
        3. **针对上一轮报告的提问**: "你觉得刚才的报告质量好吗", "为什么结果这么短"。
        4. **简单的知识问答**: "1+1等于几", "Python是什么" (不需要联网深挖的)。
        5. **无意义/模糊的短语**: "呃", "啊?", "测试", "123"。

        👉 **动作**: 直接以助手的身份回复用户，语气亲切自然。**不输出 CALL_SWARM**。

        ### 🚀 判定为【研究任务】的情况 (启动搜索集群):
        只有当用户**明确要求进行深度调查、搜索最新信息、或分析复杂话题**时。
        例如: "帮我查一下DeepSeek的最新融资", "分析2026年美国对委内瑞拉政策", "调研AI Agent的技术栈"。

        👉 **动作**: **严禁**回答问题。**必须严格且仅输出暗号字符串**: "CALL_SWARM"
        """


    messages = [SystemMessage(content=sys_prompt)] + state['messages']

    # 中间件清洗
    safe_messages = clean_msg_for_deepseek(messages)

    try:
        response = await llm.ainvoke(safe_messages)
        content = response.content.strip()

        # manager想调用工具
        is_tool_hallucination = "<｜DSML｜" in content or "function_calls" in content or "web_search" in content

        is_task_mode =  "CALL_SWARM" in content or is_tool_hallucination
        if is_task_mode:
            if is_tool_hallucination:
                logger.warning(f"⚠️ Manager 试图通过 XML 调用工具，强制修正为任务路由。")
            logger.info("🛎️ 识别到任务，静默移交 Planner")
            # 任务模式：不返回 messages，只返回路由
            return {
                "main_route":"planner"
            }
        else:
            logger.info("☕ 识别为闲聊，直接回复")
            # 闲聊模式：必须返回 messages (让用户看到回复)，并指向结束
            return {
                "main_route":"end_chat",
                "messages":[response]
            }
    except Exception as e:
        # 针对 400 风控错误的特殊处理
        if "Content Exists Risk" in str(e):
            logger.error(f"🛡️ Manager 触发内容风控，拦截敏感话题。")
            return {
                "main_route": "end_chat",  # 👈 强制走结束路由，不再移交 Planner
                "messages": [AIMessage(content="⚠️ 抱歉，该话题涉及敏感内容，为了系统安全，研究程序已自动拦截。")]
            }
        logger.error(f"Manager 决策异常: {e}")
        # 遇到错误保守起见，当做闲聊处理，避免死循环
        return {"next_node": "end_chat","messages":[AIMessage(content="⚠️ 系统暂时异常，请稍后重试。")]}