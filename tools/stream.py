import json

from tools.utils import parse_langgraph_event


async def run_agent_with_streaming(app,inputs:dict,config:dict = None):
    """
    通用流式运行器，负责将LangGraph的运行过程可视化输出
    """
    print('🤖 AI:',end='',flush=True)

    async for event in app.astream_events(inputs,config,version="v2"):

        data = parse_langgraph_event(event)

        if not data:
            continue
        # 吐字
        if data['type'] == "on_chat_model_stream":
            print(data['content'],end="",flush=True)
        # 工具开始调用
        elif data['type'] == "on_tool_start":
            tool_name = data["tool"]
            input_str = json.dumps(data['input'],ensure_ascii=False)
            print(f"\n\n{"—" * 30}")
            print(f"🔨 正在调用: {tool_name}")
            print(f"📦 参数内容: {input_str}")
            print(f"{"—" * 30}\n")
        # 工具调用完成
        elif data['type'] == "on_tool_end":
            tool_name = data["tool"]
            if not tool_name.startswith("_"):
                print(f"✅ 调用完成，继续思考...")
                print("🤖 AI: ", end="", flush=True)