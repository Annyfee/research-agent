import operator
from typing import Annotated, List

from langgraph.graph import MessagesState



class ResearchAgent(MessagesState):
    topic:str
    plan:list[str]
    report:str
    document:list[dict]
    logs:Annotated[List[str],operator.add]


