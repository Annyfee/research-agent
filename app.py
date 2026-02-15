# Streamlit前端UI配置
import json
import uuid

import streamlit as st
import requests



# 页面基础配置
st.set_page_config(
    page_title="深度搜索智能体",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded" # 初始侧边栏展开
)

# CSS美化
st.markdown("""
<style>
    /* 聊天气泡样式 */
    .stChatMessage {
        padding: 1.5rem;
        border-radius: 12px;
        margin-bottom: 1rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    /* 状态容器样式 (显示工具调用) */
    [data-testid="stStatusWidget"] {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        background-color: #f9f9f9;
    }
</style>
""",unsafe_allow_html=True) # 允许渲染



# 不使用next_asyncio.run() -- 因为我们复杂的异步逻辑已经丢给了Docker里的FastAPI后端



# 处理SSE协议的工具函数
def stream_from_backend(user_input,session_id):
    """
    连接docker后端，并把复杂的数据流按SSE协议解析成简单的Py对象
    """
    # docker后端地址
    api_url = "http://localhost:8011/chat"
    try:
        with requests.post(
            api_url,
            json={"message":user_input,"session_id":session_id},
            stream=True
        ) as response:
            # 检测限流
            if response.status_code == 429:
                yield {"type": "error", "content": "⚠️ 每小时最多使用6次，请稍后再试"}

            if response.status_code != 200:
                yield {"type": "error", "content": f"服务器报错: {response.status_code}"}
                return

            # 逐行监听
            for line in response.iter_lines(): # iter_lines:切片模式，(发现换行)立刻切走
                if line:
                    decoded_line = line.decode("utf-8")
                    if decoded_line.startswith("data:"):
                        json_str = decoded_line[5:]
                        if "[DONE]" in json_str:
                            break # 结束
                        try:
                            yield json.loads(json_str)
                        except:
                            pass
    except Exception as e:
        yield {"type":"error","content":f"连接失败:{str(e)}"}

# 状态初始化
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# 用message列表用来存结果
if "message" not in st.session_state:
    st.session_state.message = []

# 侧边栏
with st.sidebar:
    st.header("🔬 研究控制台")
    st.caption(f"Session ID:{st.session_state.session_id}")

    # 检测后端联通
    try:
        if requests.get("http://localhost:8011/docs").status_code == 200:
            st.success("🟢 后端服务在线")
            try:
                requests.get("http://localhost:8003",timeout=1)
                st.success("🟢 MCP服务在线")
            except:
                st.warning("⚪ MCP服务未启动 (端口8003不通)")
    except:
        st.error("🔴 后端服务离线(请启动docker)")

    st.divider()

    # 历史记录管理
    col1,col2 = st.columns(2) # 侧边栏分两列
    with col1:
        if st.button("🧹 新对话",use_container_width=True):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.message = []
            st.rerun()
    st.info("""
    **架构说明**：
    - **Frontend**: Streamlit (UI/交互)
    - **Backend**: FastAPI + LangGraph (Docker容器)
    - **Protocol**: HTTP + SSE 流式传输
    """)

# 主界面:渲染历史消息
st.title("🔎 Deep Research Agent")
st.caption("基于 LangGraph 多智能体架构 | Docker 容器化部署")

# 遍历历史记录并将其渲染
for msg in st.session_state.message:
    role = "user" if msg["role"] == "user" else "assistant"
    avatar = "👤" if role == "user" else "🤖"

    with st.chat_message(role,avatar=avatar):
        # 有工具日志，则渲染
        if "steps" in msg and msg["steps"]:
            with st.status("✅ 历史思考过程", state="complete", expanded=False) as status:
                for step in msg["steps"]:
                    st.write(f"🔨 调用工具: **{step['name']}**")
                    with status.expander("查看参数详情:"):
                        st.json(step['input'])

        # 再渲染正文
        st.markdown(msg["content"])


# 处理用户输入(核心)
prompt = st.chat_input("请输入你的研究课题...")
if prompt:
    # A.显示用户提问
    with st.chat_message("user",avatar="👤"):
        st.markdown(prompt)
    st.session_state.message.append({"role":"user","content":prompt})

    # B.请求后端并流式显示
    with st.chat_message("assistant",avatar="🤖"):
        # 俩容器:思考中、正文
        status_container = st.status("🤔 Agent正在思考...",expanded=True)
        response_placeholder = st.empty()
        full_response = ""

        tool_logs = []

        # 调用工具函数,接收数据
        for data in stream_from_backend(prompt,st.session_state.session_id):
            # 获取文本
            if data["type"] == "token":
                full_response += data["content"]
                # 去掉思考文本
                if any(x in full_response for x in ["CALL_SWARM", '"tasks"', '"task"', "{", "}","<｜DSML"]):
                    response_placeholder.empty() # 隐藏占位符
                    # 翻译planner
                    if "tasks" in full_response and "}" in full_response:
                        status_container.info("🧠 规划员已完成任务拆解，正在分发搜索指令...")
                        full_response = ""
                else:
                    # 正常报告
                    response_placeholder.markdown(full_response + "▌")
            # 工具调用
            elif data["type"] == "tool_start":
                tool_name = data["tool"]
                tool_input = data["input"]

                # 翻译行为
                if tool_name == "web_search":
                    query = tool_input.get("query")
                    status_container.markdown(f"**🔍 决定搜索**：`{query}`")
                elif tool_name == "get_page_content" or tool_name == "batch_fetch":
                    status_container.markdown("⏳ **阅读网页**：发现潜力信源，正在深入提取正文内容...")
                elif tool_name == "search_knowledge_base":
                    status_container.success("📚 **资料整合**：信源收集完毕，正在从记忆库中提取关键线索...")
                else:
                    status_container.write(f"🔨 调用工具:**{tool_name}**")
                with status_container.expander(f"⚙️ 展开{tool_name}底层参数"):
                    st.json(tool_input) # 参数细节

                # 存入工具列表
                tool_logs.append({"name":tool_name,"input":tool_input})
            # 防止无信息(报错)返回
            elif data["type"] == "message":
                if not full_response:
                    full_response = data["content"]
                    response_placeholder.markdown(full_response)
            # 错误信息
            elif data["type"] == "error":
                st.error(f"后端错误:{data['content']}")
        # 单次回复结束
        status_container.update(label="✅️ 生成完毕",state="complete",expanded=False)
        response_placeholder.markdown(full_response) # 显示最终文本

        # 最终回复记入历史
        st.session_state.message.append(
            {"role":"assistant","content":full_response,"steps":tool_logs}
        )