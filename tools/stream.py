from langchain_core.messages import HumanMessage
import json

async def run_agent_with_streaming(app,inputs:dict,config:dict = None):
    """
    通用流式运行器，负责将LangGraph的运行过程可视化输出
    """
    print('🤖 AI:',end='',flush=True)

    async for event in app.astream_events(inputs,config,version="v2"):
        kind = event["event"]

        # 吐字
        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            # 过滤空chunk
            if chunk.content:
                print(chunk.content,end="",flush=True)
        # 工具开始调用
        elif kind == "on_tool_start":
            tool_name = event["name"]
            # 提取工具参数
            if not tool_name.startswith("_"):
                raw_input = event["data"].get("input", {})
                clean_input = {}
                for k,v in raw_input.items():
                    if k != 'runtime':
                        clean_input[k] = v

                input_str = json.dumps(clean_input,ensure_ascii=False)
                print(f"\n\n{"—" * 30}")
                print(f"🔨 正在调用: {tool_name}")
                print(f"📦 参数内容: {input_str}")
                print(f"{"—" * 30}\n")
        # 工具调用完成
        elif kind == "on_tool_end":
            tool_name = event["name"]
            if not tool_name.startswith("_"):
                print(f"✅ 调用完成，继续思考...")
                print("🤖 AI: ", end="", flush=True)