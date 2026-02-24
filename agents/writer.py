# 【输出员】 高质量输出:只阅读RAG来产出报告
# 总流程: manager() -  planner(确认搜索方向) - surfer(开始搜寻) - core(数据入库) - leader(对数据做检查，是否进行第二轮检索) - writer(生成报告)
from datetime import datetime
from loguru import logger

import openai
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI

from config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
from state import ResearchAgent
from tools.registry import global_rag_store

llm = ChatOpenAI(
    model=OPENAI_MODEL,
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL,
    temperature=0.5
)


async def writer_node(state:ResearchAgent):
    """
    [最终整合]
    职责:根据planner拆解的课题，从RAG中提取精准知识，撰写深度报告
    """
    logger.info("✍️ [Writer] 正在构建上下文并撰写报告...")

    # 检索rag数据
    content_blocks = []
    tasks = state.get("tasks",[])

    session_id = state.get("session_id","default_session")

    for i,task in enumerate(tasks):
        retrieved_text = global_rag_store.query_formatted(task,session_id=session_id)
        block = f"""
        ### 课题:{i+1}:{task}
        【检索到的事实与数据】:
        {retrieved_text}
        """
        content_blocks.append(block)

    full_context_str= "\n".join(content_blocks)

    # 提取最近的历史上下文(这里不直接使用state["messages"][-10:] 还特地转换格式，是为了将其给llm读，而不是直接用invoke的语法)
    chat_history = []
    for message in state["messages"][-5:]:
        role = "用户" if message.type == "human" else "AI"
        chat_history.append(f'{role}:{message.content}')
    history_str = "\n".join(chat_history)



    sys_prompt = f"""你是一名世界顶级的行业研究分析师（类似于麦肯锡或高盛的首席分析师）。
        当前日期: {datetime.now().strftime("%Y-%m-%d")}

        ### 🎯 【你的核心目标】
        请结合用户的【历史对话上下文】，针对用户的最新需求，基于【调研资料】撰写深度报告。
        
        ### 📜 用户的历史对话上下文:
        {history_str}

        ### 🚫 严格约束:
        1. **基于事实**: 所有的分析必须基于下文提供的【调研资料】。严禁编造数据或引用不存在的来源。
        2. **如果资料缺失**: 如果某个课题在资料中未找到答案，请诚实地在报告中注明“缺乏相关数据”，而不是瞎编。
        3. **引用来源**: 在引用关键数据或观点时，请尽量标注来源（例如：*根据路透社报道...*）。

        ### 📝 报告输出格式 (必须严格遵守):

        # [报告标题] (请自拟一个专业标题)

        ## 1. 执行摘要 (Executive Summary)
        > (用简练的语言总结核心结论，让读者在30秒内看懂全貌。包含最重要的发现、趋势或风险。)

        ## 2. 关键发现 (Key Findings)
        * **发现点 1**: ...
        * **发现点 2**: ...
        * (使用无序列表，提炼出最有价值的信息点)

        ## 3. 深度分析 (Deep Dive)
        (在此处，请将之前的 {len(tasks)} 个课题有机地串联起来，进行分章节的详细论述。不要机械地罗列问题，要融合成一篇通顺的文章。)

        * **[子标题1]**: ...
        * **[子标题2]**: ...

        ## 4. 数据来源与可信度评估 (Source Evaluation)
        * (简要评价本次调研获取信息的质量。例如：信息源主要来自官方报道，具有较高可信度；或者：关于XX的数据较少，建议进一步人工核实。)
        
        ## 5.标明数据来源
        * (输出对应参考的信息链接来源,这里的信息来源必须真实源自你检索到的来源，严禁脑补编造)
        ### 📚 参考资料格式示例:
        [1] https: // example.com / paper_details - xx年x应用行情主线深度分析报告
        [2] https: // news.tech / report-2026

        --------------------------------------------------
        以下是必须基于的【调研资料】:
        {full_context_str}
        """
    message = [SystemMessage(content=sys_prompt)]
    try:
        response = await llm.ainvoke(message)
        logger.success("✅ [Writer] 报告撰写完成")

        global_rag_store.clear_session(session_id)
        logger.info(f"🧹 [Writer] 任务完成，清理 Session: {session_id}")

        return {
            "final_answer":response.content,
            "messages":[response]
        }
    # AI的api可能会拒绝生成内容，需要做防护
    except openai.BadRequestError as e:
        # 捕获 llm 的内容风控错误
        err_dict = e.body or {}
        if "Content Exists Risk" in str(err_dict):
            logger.error(f"🚫 [Writer] 触发内容风控，内容无法生成")
            # 告知风控
            msg = "⚠️ 抱歉，由于内容安全策略，我无法生成关于该主题的详细报告。请尝试更换关键词。"
            return {
                "final_answer":msg,
                "messages":[AIMessage(content=msg)]
            }
        else:
            logger.error(f"❌ API 请求错误: {e}")
            msg = f"❌ API 请求错误: {e}"
            return {
                "final_answer":msg,
                "messages": [AIMessage(content=msg)]
            }
    except Exception as e:
        logger.error(f"❌ 未知错误: {e}")
        msg = f"⚠️ 系统运行异常，请检查日志。错误详情: {str(e)}"
        return {
            "final_answer":msg,
            "messages": [AIMessage(content=msg)]
        }
