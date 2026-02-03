# 【输出员】 高质量输出:只阅读RAG来产出报告
# 总流程: manager() -  planner(确认搜索方向) - surfer(开始搜寻) - core(数据入库) - leader(对数据做检查，是否进行第二轮检索) - writer(生成报告)
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from loguru import logger

from config import OPENAI_API_KEY
from state import ResearchAgent
from tools.registry import global_rag_store

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=OPENAI_API_KEY,
    base_url="https://api.deepseek.com",
    temperature=0.5
)


async def writer_node(state:ResearchAgent):
    """
    [最终整合]
    职责:根据planner拆解的课题，从RAG中提取精准知识，撰写深度报告
    """
    logger.info("✍️ [Writer] 正在构建上下文并撰写报告...")

    # 暴力检索
    content_blocks = []
    tasks = state.get("tasks",[])





    for i,task in enumerate(tasks):
        retrieved_text = global_rag_store.query_formatted(task)
        block = f"""
        ### 课题:{i+1}:{task}
        【检索到的事实与数据】:
        {retrieved_text}
        """
        content_blocks.append(block)

    full_context_str= "\n".join(content_blocks)



    sys_prompt = f"""你是一名世界顶级的行业研究分析师（类似于麦肯锡或高盛的首席分析师）。
        当前日期: {datetime.now().strftime("%Y-%m-%d")}

        你的任务是根据提供的【调研资料】，撰写一份逻辑严密、数据详实、极具洞察力的**深度研究报告**。

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

        --------------------------------------------------
        以下是必须基于的【调研资料】:
        {full_context_str}
        """
    message = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content="请开始撰写报告")
    ]
    try:
        response = await llm.ainvoke(message)
        logger.success("✅ [Writer] 报告撰写完成")
        return {
            # "research_notes": response.content,
            "messages":[response]
        }
    except Exception as e:
            logger.error(f"❌ Writer 生成失败: {e}")
            # return {"research_notes": "报告生成失败，请检查日志。"}
            return {}
