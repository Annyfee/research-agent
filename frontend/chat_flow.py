# 处理对话时逻辑

import streamlit as st
from frontend.backend_client import stream_from_backend


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