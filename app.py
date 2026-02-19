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
                return

            if response.status_code != 200:
                yield {"type": "error", "content": f"服务器报错: {response.status_code}"}
                return

            # 逐行监听
            for line in response.iter_lines(): # iter_lines:切片模式，(发现换行)立刻切走
                if line:
                    decoded_line = line.decode("utf-8")
                    if decoded_line.startswith("data:"):
                        json_str = decoded_line[5:].strip()
                        if not json_str:
                            continue
                        if "[DONE]" in json_str:
                            break # 结束
                        try:
                            yield json.loads(json_str)
                        except Exception:
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
        # 状态锁：标记是否已进入最终报告输出阶段
        has_final_answer = False

        planning_shown = False
        searching_shown = False
        writer_shown = False

        tool_logs = []



        # 调用工具函数,接收数据
        for data in stream_from_backend(prompt,st.session_state.session_id):
            node = data.get("source")
            event_type = data.get("type")
            # 获取文本
            if event_type == "token":
                token_text = data.get("content", "")
                if not isinstance(token_text, str):
                    token_text = str(token_text)

                # manager 流式：在 writer 出现前可展示（用于“思考/规划中”可视化）
                if node == "manager":
                    if has_final_answer:
                        continue
                    # 过滤明显的结构化控制串，避免把调度JSON刷到正文
                    if any(x in token_text for x in ["CALL_SWARM", '"tasks"', '"task"', '"main_route"']):
                        if not planning_shown:
                            response_placeholder.markdown("🔍 *正在识别需求并准备研究计划...*")
                            planning_shown = True
                        continue
                    full_response += token_text
                    response_placeholder.markdown(full_response)
                    continue

                # writer 流式：一旦开始，清空前面 manager 的临时文本，进入最终成稿阶段
                if node == "writer":
                    if not writer_shown:
                        status_container.info("✍️ Writer 正在撰写最终报告...")
                        writer_shown = True
                        # writer 首次出现时，强制接管并清空 manager 临时内容
                        full_response = ""
                        has_final_answer = True
                    full_response += token_text
                    response_placeholder.markdown(full_response)
                    continue

                # 其他节点token直接忽略
                continue


                # # 去掉思考文本
                # if not has_final_answer and source == "manager" and any(x in full_response for x in ["CALL_SWARM", '"tasks"', '"task"']):
                #     # 不要用 .empty()，而是显示一个友好的提示，占住位置
                #     response_placeholder.markdown("🔍 *正在识别需求并准备研究计划...*")
                #     # 翻译planner
                #     if "tasks" in full_response and "}" in full_response:
                #         status_container.info("🧠 规划员已完成任务拆解，正在分发搜索指令...")
                #         full_response = ""
                #         response_placeholder.markdown("正在为您搜寻资料,请耐心等待...")
                # # writer阶段(最终报告)
                # else:
                #     if source == "writer":
                #         has_final_answer = True
                #     response_placeholder.markdown(full_response + "▌")




            # 工具调用
            elif event_type == "tool_start":
                tool_name = data["tool"]
                tool_input = data["input"]

                if not planning_shown:
                    # 不要用 .empty()，而是显示一个友好的提示，占住位置
                    response_placeholder.markdown("🔍 *正在识别需求并准备研究计划...*")
                    planning_shown = True
                if tool_name == "web_search":
                    if not searching_shown:
                        status_container.info("🧠 规划员已完成任务拆解，正在分发搜索指令...")
                        response_placeholder.markdown("正在为您搜寻资料,请耐心等待...")
                        searching_shown = True
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
            elif event_type == "message":
                text = data.get("content", "")
                if node == "writer":
                    # 关键：writer到达时直接覆盖，清理任何残留
                    if not writer_shown:
                        status_container.info("✍️ 正在整理最终成稿...")
                        writer_shown = True
                    if text:
                        full_response = text
                        response_placeholder.markdown(full_response)
                        has_final_answer = True
                elif node == "manager":
                    # 仅闲聊兜底，避免覆盖 writer
                    if text and (not has_final_answer) and (not full_response.strip()):
                        status_container.info("💬 正在整理回复...")
                        full_response = text
                        response_placeholder.markdown(full_response)
                        has_final_answer = True
            # 错误信息
            elif event_type == "error":
                st.error(f"后端错误:{data.get('content', '未知错误')}")
            elif event_type == "done":
                break
        # 单次回复结束
        status_container.update(label="✅️ 生成完毕",state="complete",expanded=False)
        if not full_response or not full_response.strip():
            full_response = "未生成有效内容，请重试。"
        response_placeholder.markdown(full_response) # 显示最终文本

        # 最终回复记入历史
        st.session_state.message.append(
            {"role":"assistant","content":full_response,"steps":tool_logs}
        )