from functools import partial

from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Send
from loguru import logger

from agents.researcher.core import core_node
from agents.researcher.graph import build_researcher_graph
from agents.researcher.leader import leader_node
from agents.manager import manager_node
from agents.planner import planner_node
from agents.researcher.surfer import surfer_node
from agents.writer import writer_node
from state import ResearchAgent

from tools.registry import load_all_tools




def route(state:ResearchAgent):
    return state.get("main_route","end_chat")


# 并发分发逻辑
def distribute_tasks(state:ResearchAgent):
    """
    Map 过程：
    将 Planner 生成的 tasks 列表，拆分成一个个独立的 Send 指令。
    每个 Send 会启动一个 Researcher 子图实例。
    """
    tasks = state.get("tasks",[])
    logger.info(f"\n🚀 [Main] 正在并发分发 {len(tasks)} 个任务给 Researcher 子图...")

    return [
        Send(
            "researcher",
            {
                "task":task,
                "task_idx":i+1,
                "retry_count":0,
                "messages":[] # 防止上下文污染
            }
        )
        for i,task in enumerate(tasks)
    ]





async def build_graph():
    """
    组装Swarm智能体网络
    """
    # tools = await load_all_tools()

    researcher_app = await build_researcher_graph()

    workflow = StateGraph(ResearchAgent)

    workflow.add_node("manager",manager_node)
    workflow.add_node("planner",planner_node)
    workflow.add_node("researcher",researcher_app)
    workflow.add_node("writer",writer_node)


    workflow.add_edge(START,"manager")
    workflow.add_conditional_edges(
        "manager",
        route,
        {
            "planner":"planner",
            "end_chat":END
        }
    )
    workflow.add_conditional_edges(
        "planner",
        distribute_tasks,
        ["researcher"] # 明确指明它可能去的节点
    )
    workflow.add_edge("researcher","writer")
    workflow.add_edge("writer",END)
    return workflow.compile(checkpointer=MemorySaver())