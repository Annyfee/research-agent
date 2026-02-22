# 处理对话时逻辑
import re
import streamlit as st
from backend_client import stream_from_backend

# 清洗CALL_SWARM
def sanitize_text(text):
    if not text:
        return ""
    return re.sub(r"(?i)^\s*call_swarm[\s:-]*","",text)

# 优化数据来源展示
def format_sources_simple(text):
    if not text:
        return ""
    marker = "标明数据来源"
    if marker not in text:
        return text
    head,tail = text.split(marker,1)
    tail = re.sub(r"(?<!^)\[(\d+)\]",r"\n[\1]",tail)
    return head + marker + tail


def handle_chat_turn(prompt):
    # A.显示用户提问
    with st.chat_message("user",avatar="👤"):
        st.markdown(prompt)
    st.session_state.message.append({"role":"user","content":prompt})

    # B.请求后端并流式显示
    with st.chat_message("assistant",avatar="🤖"):
        # 俩容器:思考中 & 正文
        status_placeholder = st.empty()
        with status_placeholder.container():
            status_container = st.status("🤔 Agent正在思考...",expanded=True)
        response_placeholder = st.empty()
        full_response = ""
        final_response = ""
        tool_logs = []

        # 判断manager状态:闲聊/分配任务
        is_research = False
        # 等待文本
        shown_waiting_text = False

        # 调用工具函数,接收数据
        for data in stream_from_backend(prompt,st.session_state.session_id):
            content = data.get("content", "")
            event_type = data.get("type")
            if event_type == "phase":
                phase = data.get("phase","")
                phase_map = {
                "planning": "🧭 正在规划任务...",
                "researching": "🔎 正在检索资料...",
                "writing": "✍️ 正在撰写报告..."
            }
                msg = phase_map.get(phase,"")
                if msg:
                    status_container.info(msg)
                continue
            elif event_type == "status":
                # 只在后端真有内容时展示
                if content:
                    status_container.info(content)
                continue
            elif event_type == "token": # 流式输出
                token_text = content if isinstance(content, str) else "" # 防止脏输出
                full_response += token_text
                final_response = format_sources_simple(sanitize_text(full_response))
                response_placeholder.markdown(final_response)
                continue
            elif event_type == "message": # 整段消息返回
                if content:
                    full_response = content
                    final_response = format_sources_simple(sanitize_text(full_response))
                    response_placeholder.markdown(final_response)
                continue
            elif event_type == "tool_start":
                if not shown_waiting_text:
                    response_placeholder.markdown("正在并发搜索资料中，请耐心等待...")
                    shown_waiting_text = True
                is_research = True
                tool_name = data.get("tool","unknown_tool")
                tool_input = data.get("input",{})
                # 存入工具列表
                tool_logs.append({"name": tool_name, "input": tool_input})
                status_container.write(f"🔨 调用工具:**{tool_name}**")
                with status_container.expander(f"⚙️ 展开{tool_name}底层参数"):
                    st.json(tool_input) # 参数细节
                continue
            elif event_type == "tool_end":
                continue
            elif event_type == "error": # 错误信息
                st.error(f"后端错误:{data.get('content', '未知错误')}")
            elif event_type == "done":
                break

        # 单次回复结束
        if is_research:
            status_container.update(label="✅️ 生成完毕", state="complete", expanded=False)
        else:
            status_placeholder.empty()
        if not final_response or not final_response.strip():
            final_response = "未生成有效内容，请重试。"

        # response_placeholder.markdown(sanitize_text(full_response)) # 显示最终文本
        # 最终回复记入历史
        st.session_state.message.append(
            {"role":"assistant","content":final_response,"steps":tool_logs}
        )