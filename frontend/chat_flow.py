# 处理对话时逻辑

import streamlit as st
from backend_client import stream_from_backend


def handle_chat_turn(prompt):
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
            content = data.get("content", "")
            event_type = data.get("type")

            if event_type == "phase":
                status_container.info(content or "处理中...")
                continue
            elif event_type == "status":
                status_container.info(content or "处理中...")
                continue
            elif event_type == "token": # 流式输出
                token_text = content if isinstance(content, str) else "" # 防止脏输出
                full_response += token_text
                response_placeholder.markdown(full_response)
                continue
            elif event_type == "message": # 整段消息返回
                if content:
                    full_response = content
                    response_placeholder.markdown(full_response)
            elif event_type == "tool_start":
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
        status_container.update(label="✅️ 生成完毕",state="complete",expanded=False)
        if not full_response or not full_response.strip():
            full_response = "未生成有效内容，请重试。"
        response_placeholder.markdown(full_response) # 显示最终文本
        # 最终回复记入历史
        st.session_state.message.append(
            {"role":"assistant","content":full_response,"steps":tool_logs}
        )