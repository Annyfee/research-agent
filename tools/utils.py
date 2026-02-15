import json

from langchain_core.messages import ToolMessage


# 注:LangChain会将ToolMessage调整为list类型，但部分llm(如deepseek)只能接收str。所以我们需要中间件来处理
def clean_msg_for_deepseek(messages):
    """
    专门为DeepSeek清洗消息格式的中间件
    将所有List类型的ToolMessage content 转化为 JSON String
    """
    cleaned = []
    for msg in messages:
        if isinstance(msg,ToolMessage) and isinstance(msg.content,list):
            # 直接序列化为JSON类型
            msg_copy = ToolMessage(
                content=json.dumps(msg.content,ensure_ascii=False),
                tool_call_id=msg.tool_call_id,
                name=msg.name,
                id=msg.id
            )
            cleaned.append(msg_copy)
        else:
            cleaned.append(msg)
    return cleaned

def parse_langgraph_event(event):
    """
    输入:langgraph的原始event
    输出:清洗好的标准数据
    返回None:无需处理
    """
    kind = event["event"]

    # LLM吐字
    if kind == "on_chat_model_stream":
        chunk = event["data"]["chunk"]
        if chunk.content:
            return {
                "type":"token",
                "content":chunk.content
            }
    # 工具调用
    elif kind == "on_tool_start":
        tool_name = event["name"]
        # 防止内部方法
        if not tool_name.startswith("_"):
            raw_input = event["data"]["input"]
            # 去掉runtime的参数
            clean_input = {}
            for k,v in raw_input.items():
                if k != "runtime":
                    clean_input[k] = v
            return {
                "type":"tool_start",
                "tool":tool_name,
                "input":clean_input
            }
    # 调用结束
    elif kind == "on_tool_end":
        tool_name = event["name"]
        if not tool_name.startswith("_"):
            output = str(event["data"]["output"])
            return {
                "type":"tool_end",
                "tool":tool_name,
                "output":output[:200] + "..." if len(output) > 200 else output
            }
    # 节点执行完成后触发(return结束)
    elif kind == "on_chain_end":
        node_name = event["name"]
        # 只有writer节点需要返回完整message，manager节点通过流式token输出
        if node_name in ["writer","manager"]:
            output = event["data"]["output"]
            messages = output.get("messages", [])
            if messages:  # 防止列表为空
                content = messages[-1].content
                if content:  # 防止空消息
                    return {
                        "type": "message",
                        "content": content
                    }
    return None