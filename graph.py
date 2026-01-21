from langgraph.constants import START, END
from langgraph.graph import StateGraph

from state import ResearchAgent



def plan_node(state:ResearchAgent):
    print('Planner is working')
    return {"plan":["关键词1","关键词2"],"logs":[f'Planner 已根据主题{state.get("topic")}生成计划']}

def research_node(state:ResearchAgent):
    print("Researcher is working")
    return {"document":[{"url":"mock_url"}],"logs":["Researcher 已完成信息搜集，获取1条数据"]}

def write_node(state:ResearchAgent):
    print("Writer is working")
    return {"report":"# Mock Report","logs":["Writer已生成报告"]}

def publish_node(state:ResearchAgent):
    print("Publisher is working")
    return {"logs":["已归档"]}


workflow = StateGraph(ResearchAgent)

workflow.add_node("plan",plan_node)
workflow.add_node("research",research_node)
workflow.add_node("write",write_node)
workflow.add_node("publish",publish_node)


workflow.add_edge(START,"plan")
workflow.add_edge("plan","research")
workflow.add_edge("research","write")
workflow.add_edge("write","publish")
workflow.add_edge("publish",END)


app = workflow.compile()






