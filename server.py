import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from loguru import logger
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from config import LANGCHAIN_API_KEY
from graph import build_graph
from tools.utils import parse_langgraph_event



# 追踪
os.environ["LANGCHAIN_TRACING_V2"] = "true"  # 总开关，决定启用追踪功能
os.environ["LANGCHAIN_PROJECT"] = "research-agent"  # 自定义项目名
os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY



# --- 消音代码 --- 等级低于Warning的提示全部屏蔽
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)
# -----------------------

# 文件夹不存在，则创建
for path in ["logs","db"]:
    os.makedirs(path,exist_ok=True)


# 创建日志
logger.add("logs/server.log",rotation="10 MB")


from collections import defaultdict
from fastapi.responses import JSONResponse
import time

# 限流存储（内存级别，重启清零，够用） - 不存在key 自动创建空list
request_counts = defaultdict(list)


# 全局限流器 - 只有5个会话会运行
MAX_CONCURRENT_USERS = asyncio.Semaphore(5)



class ChatRequest(BaseModel):
    message:str
    session_id:str = None


# 生命周期管理
@asynccontextmanager #
async def lifespan(app:FastAPI):
    """
    服务器总开关
    FastAPI启动时执行yield前面的代码(建立连接)
    FastAPI关闭时执行yield后面的代码(断开连接)
    """
    logger.info("🚀 Server 正在启动...")

    # 建立SQLite数据库连接
    conn = AsyncSqliteSaver.from_conn_string("db/checkpointer.sqlite")

    # 激活连接上下文
    async with conn as checkpointer: # 针对conn这个对象，进行异步上下文管理，并在正式进入上下文管理后，将其称作为checkpointer
        logger.info("💾 SQLite 数据库已连接")

        # 编译Graph:连接数据库，让数据库在运行时自动把状态保存到sqlite文件中
        compiled_graph = await build_graph(checkpointer=checkpointer)

        # 存入app的state变量内，之后再用
        app.state.graph = compiled_graph
        logger.info("✅ Graph 已编译 (带持久化记忆)")

        # 服务器运行，直至被关闭
        yield

        # async with已自动清理
        logger.info("👋 Server 已关闭，数据库连接已断开") # 注:async with代表自动上下文管理的语法/@asynccontextmanager代表实现自动上下文管理的具体工具


# 初始化FastAPI
app = FastAPI(title="Deep Research Agent API",lifespan=lifespan) # lifespan:生命周期处理函数

# 插入中间件，对请求域名做检测 / 不加浏览器默认阻止跨域请求(前端与后端API不在同一个域名/端口时)，非浏览器客户端不受影响
app.add_middleware( # @app.post确定路由(门牌号)/CORSMiddleware是门卫(决定能不能进门)/allow_origins是白名单(只认这些人)
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

def _to_phase_from_source(source:str):
    if source in ("manager","planner"):
        return "planning"
    if source in ("researcher","leader","surfer"):
        return "researching"
    if source == "writer":
        return "writing"
    return None

# 统一事件封装函数
def make_event(event_type:str,run_id:str,sid:str,**payload):
    return{
        "type":event_type,
        "protocol_version":"v1",
        "ts":int(time.time()*1000),
        "run_id":run_id, # 运行实例id
        "session_id":sid,
        **payload
    }


def adapt_event_for_ui(data:dict,fsm_state:dict,run_id:str,sid:str):
    """
    输入 parse_langgraph_event的结果，输出 0-n 个统一UI事件
    只允许输出协议事件，禁止透传原始data
    """
    if not data:
        return [] # 无UI事件
    out = [] # 收集UI
    source = data.get("source","unknown")
    t = data.get("type", "unknown")
    text = data.get("content","")
    phase = _to_phase_from_source(source)
    # 根据来源事件，自动判断并切换到对应的阶段 - phase自动推进并变化
    if phase and phase != fsm_state["phase"]:
        fsm_state["phase"] = phase
        out.append(make_event("phase", run_id, sid, phase=phase, source=source)) # 更新状态
    # token
    if t == "token":
        # 命中脏数据隐藏 / 没命中正常传
        if source == "manager" and any(x in text for x in ["CALL_SWARM",'"tasks"','"task"','"main_route"']):
            out.append(make_event(
                "status",run_id,sid,
                source="system",
                content="🔍 正在识别需求并规划任务..."
            ))
            return out
        out.append(make_event("token",run_id,sid,source=source,content=text))
        return out
    # message 降级成 token，共用一套渲染逻辑
    if t == "message":
        out.append(make_event("token",run_id,sid,source=source,content=text))
        return out
    if t == "tool_start":
        out.append(make_event(
            "tool_start",run_id,sid,
            source=source,
            tool=data.get("tool",""),
            input=data.get("input",{})
        ))
        return out
    if t == "tool_end":
        out.append(make_event(
            "tool_end",run_id,sid,
            source=source,
            tool=data.get("tool",""),
            output=data.get("output",{}) # 注意区分:input & output
        ))
        return out
    if t == "error":
        out.append(make_event(
            "error",run_id,sid,
            source=source,
            content=text or "未知错误"
        ))
        return out
    # 未知事件统一转status，不透传
    out.append(make_event(
        "status",run_id,sid,
        source=source,
        content=text or f'{t}'
    ))
    return out



# 流式输出
async def event_generator(inputs:dict,config:dict,sid:str):
    """
    负责将LangGraph事件转换为SSE数据流
    """
    # 限制最大并发数
    async with MAX_CONCURRENT_USERS:
        graph = app.state.graph
        run_id = str(uuid.uuid4())
        try:
            fsm_state = {"phase": None}
            # 启动Graph流式执行 - 这里只负责丢数据，展示什么数据(如on_tool_start)由前端来管
            async for event in graph.astream_events(inputs,config,version="v2"):
                data = parse_langgraph_event(event)
                ui_events = adapt_event_for_ui(data,fsm_state,run_id,sid)
                for data in ui_events:
                    # 返回SSE协议格式数据
                    yield f"data: {json.dumps(data,ensure_ascii=False)}\n\n"
        except Exception as e:
            err_str = str(e)
            # 如果是风控导致的后续崩溃，直接给用户看人话
            if "Content Exists Risk" in err_str or "No AIMessage found" in err_str:
                err_str = "⚠️ 系统安全策略拦截：该话题无法继续研究。"
            logger.exception("❌ 运行出错")
            error_data = make_event("error",run_id,sid,source="system",content=err_str)
            yield f"data: {json.dumps(error_data,ensure_ascii=False)}\n\n"
        finally:
            done = make_event("done",run_id,sid)
            yield f"data: {json.dumps(done,ensure_ascii=False)}\n\n"



# 聊天接口
@app.post("/chat")
async def chat_endpoint(request:ChatRequest): # 其中sid与message都是从前端的请求体接收的，这里无需做显式接收，但可使用
    # 获取session_id
    sid = request.session_id or str(uuid.uuid4())
    logger.info(f"收到请求 | Session: {sid}")

    # 限流检查
    now = time.time()
    request_counts[sid] = [t for t in request_counts[sid] if now - t < 3600]  # 清理一小时前的记录
    if len(request_counts[sid]) >= 6: # 超过六次拒绝
        logger.warning(f"🚫 限流触发 | Session: {sid}")
        return JSONResponse(
            status_code=429,
            content={"detail":"每小时最多访问6次，请稍后再试!"}
        )
    request_counts[sid].append(now)


    # 构造config(为数据库指明会话)
    config = {
        "configurable":{"thread_id":sid},
        "recursion_limit":100
    }
    # 构造Input(为RAG指明用户)
    inputs = {
        "messages":[HumanMessage(content=request.message)],
        "session_id":sid
    }
    # 返回流式响应
    return StreamingResponse(
        event_generator(inputs, config,sid),
        media_type="text/event-stream",
        # 减少中间件缓冲
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port=8011)