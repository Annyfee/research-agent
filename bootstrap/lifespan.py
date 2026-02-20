# 生命周期管理
from contextlib import asynccontextmanager
from fastapi import FastAPI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from loguru import logger
from graph import build_graph


@asynccontextmanager
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
        """
        只做启动/关闭时的资源初始化
        
        """
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