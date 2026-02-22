# 初始化配置
import uuid
import streamlit as st
from chat_flow import handle_chat_turn
from backend_client import check_services_status
from ui import setup_page, render_sidebar, render_header, render_history

setup_page()

# 状态初始化
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
# 用message列表用来存结果
if "message" not in st.session_state:
    st.session_state.message = []

status = check_services_status()

new_chat_clicked = render_sidebar(status)
if new_chat_clicked:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.message = []
    st.rerun()

render_header()
render_history()


# 处理用户输入(核心)
prompt = st.chat_input("请输入你的研究课题...")
if prompt:
    handle_chat_turn(prompt)