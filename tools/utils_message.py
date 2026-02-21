# 注:LangChain会将ToolMessage调整为list类型，但部分llm(如deepseek)只能接收str。所以我们需要中间件来处理
import json
from langchain_core.messages import ToolMessage


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