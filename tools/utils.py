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
    返回 None:无需处理
    """
    kind = event["event"]
    meta = event.get("metadata",{}) or {} # 防止键不存在或为空
    node = meta.get("langgraph_node") # 标记事件来源节点


    # LLM吐字:仅允许manager与writer输出到前端:token碎
    if kind == "on_chat_model_stream":
        if node not in ("writer", "manager"):
            return None
        chunk = event.get("data", {}).get("chunk")
        content = getattr(chunk, "content", "")
        if content is None:
            return None
        if isinstance(content, list):
            # 兼容富文本/分片结构
            content = "".join(
                c if isinstance(c, str) else str(c.get("text", "")) if isinstance(c, dict) else str(c)
                for c in content
            )
        elif not isinstance(content, str):
            content = str(content)
        if not content.strip():
            return None
        return {"type": "token", "content": content, "source": node}
    # 工具调用
    elif kind == "on_tool_start":
        tool_name = event.get("name", "")
        raw_input = event.get("data", {}).get("input", {})
        if isinstance(raw_input, dict):
            safe_input = {}
            for k, v in raw_input.items():
                if k not in ("runtime", "callbacks", "config"):
                    safe_input[k] = v
        else:
            # 非 dict 输入兜底
            safe_input = {"value": raw_input}
        return {
            "type": "tool_start",
            "tool": tool_name,
            "input": safe_input,
            "source": node,
        }
    # 调用结束
    elif kind == "on_tool_end":
        tool_name = event["name"]
        if not tool_name.startswith("_"):
            output = str(event["data"]["output"])
            return {
                "type":"tool_end",
                "tool":tool_name,
                "output":output[:200] + "..." if len(output) > 200 else output,
                "source":node
            }
    # 节点执行完成后触发(return结束)
    elif kind == "on_chain_end":
        output = event["data"]["output"]
        # DEBUG: 打印 writer 相关的 on_chain_end 事件
        if node == "writer":
            print(f"[DEBUG] on_chain_end for writer, output type: {type(output)}, keys: {output.keys() if isinstance(output, dict) else 'N/A'}")
            if isinstance(output, dict):
                print(f"[DEBUG] final_answer exists: {'final_answer' in output}, value preview: {str(output.get('final_answer', ''))[:100]}")
        # writer：优先读 final_answer，避免 messages 合并污染
        if node == "writer":
            if isinstance(output, dict):
                final_answer = output.get("final_answer")
                if final_answer:
                    if not isinstance(final_answer, str):
                        final_answer = str(final_answer)
                    return {
                        "type": "message",
                        "content": final_answer,
                        "source": "writer"
                    }
                # 兜底：若没有 final_answer，再从 messages 找最后 AI
                messages = output.get("messages", []) or []
                for msg in reversed(messages):
                    if getattr(msg, "type", "") == "ai" and getattr(msg, "content", ""):
                        return {
                            "type": "message",
                            "content": msg.content,
                            "source": "writer"
                        }
            return None
        # manager：仅 end_chat 才允许输出 message
        if node == "manager":
            if not isinstance(output, dict):
                return None
            if output.get("main_route") != "end_chat":
                return None
            messages = output.get("messages", []) or []
            for msg in reversed(messages):
                if getattr(msg, "type", "") == "ai" and getattr(msg, "content", ""):
                    return {
                        "type": "message",
                        "content": msg.content,
                        "source": "manager"
                    }
    return None