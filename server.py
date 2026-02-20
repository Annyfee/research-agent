import logging
import os
from fastapi import FastAPI
from loguru import logger
from starlette.middleware.cors import CORSMiddleware
from api.routes import router
from bootstrap.lifespan import lifespan
from config import LANGCHAIN_API_KEY


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


# 初始化FastAPI
app = FastAPI(title="Deep Research Agent API",lifespan=lifespan) # lifespan:生命周期处理函数

# 插入中间件，对请求域名做检测 / 不加浏览器默认阻止跨域请求(前端与后端API不在同一个域名/端口时)，非浏览器客户端不受影响
app.add_middleware( # @app.post确定路由(门牌号)/CORSMiddleware是门卫(决定能不能进门)/allow_origins是白名单(只认这些人)
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# 挂载路由
app.include_router(router)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port=8011)