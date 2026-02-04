from langgraph.graph import MessagesState


# 定义类属性是 class xx(yy) 定义def才是 def xx(state:yy)
# class后面跟括号:我是谁的子类(继承
# def后面跟括号:我需要什么数据来干活(参数与类型提示

class ResearchAgent(MessagesState):
    # 全局上下文
    session_id:str

    # --- 主图业务状态 ---
    # planner 拆解出来的任务清单:
    tasks:list[str]
    # 清洗完的数据摘要:让writer先看摘要,再决定是直接回答还是根据摘要去数据库查资料
    research_notes:str
    # 路由指针:下一步指向什么节点(与子图命名分开)
    main_route:str
