import json
import time
import uuid
from typing import AsyncGenerator

from logging import getLogger
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.thread import Thread
from app.models.message import Message
from app.schemas.chat import ChatRequest, ChatResponse
from app.core.langgraph.graphs import get_chat_agent
from app.services.database import engine

logger = getLogger(__name__)

router = APIRouter(tags=["chat"])

def extract_assistant_message_fields(msg: AIMessage) -> dict:
    """从 AIMessage 提取需要存入数据库的字段"""
    usage_meta = msg.usage_metadata if hasattr(msg, "usage_metadata") else None
    additional = msg.additional_kwargs if msg.additional_kwargs else None
    response_meta = msg.response_metadata if msg.response_metadata else None

    return {
        "content": msg.content if isinstance(msg.content, str) else str(msg.content),
        "usage_metadata": usage_meta,
        "response_metadata": response_meta,
        "additional_kwargs": additional,
        "tool_calls": msg.tool_calls if msg.tool_calls else None,
        "invalid_tool_calls": msg.invalid_tool_calls if msg.invalid_tool_calls else None,
        "message_id": msg.id,
    }

# 辅助函数：将前端消息字典转换为 LangChain 消息对象
def dict_to_langchain_messages(messages: list[dict]):
    lc_messages = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls is not None:
                lc_messages.append(AIMessage(content=content, tool_calls=tool_calls))
            else:
                lc_messages.append(AIMessage(content=content))
        elif role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id", "")
            lc_messages.append(ToolMessage(content=content, tool_call_id=tool_call_id))
        else:
            # 未知角色跳过，避免污染上下文
            continue
    return lc_messages

def _extract_text_from_content(content) -> str:
    """从 AIMessageChunk.content 中提取纯文本，兼容 str 或 list 格式"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        return "".join(text_parts)
    return ""

async def stream_chat_response(
    thread_id: str,
    model: str,
    agent,
    input_state: dict,
    config: dict,
    last_user_content: str | None,
) -> AsyncGenerator[str, None]:
    """生成 SSE 流式响应，并在结束时保存完整消息到数据库"""
    full_content = ""
    final_message = None  # 在循环外初始化，确保 finally 中可访问
    try:
        logger.info(f"流式响应开始：{config}")
        async for event in agent.astream_events(input_state, config=config, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                # logger.info(f'response_chunk: {chunk}')
                delta_content = _extract_text_from_content(chunk.content)
                # 2. 提取思考推理delta（DeepSeek‑R1等推理模型）
                delta_reasoning: str | None = chunk.additional_kwargs.get("reasoning_content")
                if delta_content or delta_reasoning:
                    full_content += delta_content
                    chunk_data = {
                        "id": str(uuid.uuid4()),
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "content": delta_content,
                                "reasoning_content": delta_reasoning
                            },
                            "finish_reason": None,
                            "logprobs": None
                        }],
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"
            elif kind == "on_chat_model_end":
                final_message = event["data"]["output"]
            elif kind == "on_chain_error":
                # 节点内异常（例如模型彻底调用失败）会以 on_chain_error 事件上报，
                # 若不加处理会静默吞掉，前端只会收到 [DONE] 而看不到任何错误。
                err = event["data"].get("error")
                logger.error(f"Agent 流式调用出错：{err}")
                error_data = {"error": str(err)}
                yield f"data: {json.dumps(error_data)}\n\n"
    except Exception as e:
        error_data = {"error": str(e)}
        yield f"data: {json.dumps(error_data)}\n\n"
    finally:
        # 发送结束标记
        end_data = {
            "id": str(uuid.uuid4()),
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(end_data)}\n\n"
        yield "data: [DONE]\n\n"

        # 保存数据库（独立会话）
        with Session(engine) as session:
            if last_user_content:
                session.add(Message(thread_id=thread_id, role="user", content=last_user_content))
            if final_message and isinstance(final_message, AIMessage):
                # 完整保存 assistant 消息
                assistant_fields = extract_assistant_message_fields(final_message)
                session.add(Message(thread_id=thread_id, role="assistant", **assistant_fields))
            elif full_content:
                # 降级：只保存文本（但这种情况应避免）
                session.add(Message(thread_id=thread_id, role="assistant", content=full_content))
            session.commit()

@router.post("/chat/{thread_id}", response_model=None)
async def chat(
    thread_id: str,
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 验证线程归属
    thread = db.get(Thread, thread_id)
    if not thread or thread.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 转换消息
    lc_messages = dict_to_langchain_messages(payload.messages)
    if not lc_messages:
        raise HTTPException(status_code=400, detail="内容格式不支持")

    # 获取最后一条用户消息内容（用于落库）
    last_user_content: str | None = None
    for msg in reversed(payload.messages):
        if msg.get("role") == "user":
            last_user_content = msg.get("content")
            break

    # 获取 Agent
    agent = await get_chat_agent()

    # 输入状态
    input_state = {
        "messages": lc_messages,
        "model": payload.model,
        "thinking": payload.thinking,
    }
    config = {"configurable": {"thread_id": thread_id}}

    # 是否使用 流式输出
    if payload.stream:
        return StreamingResponse(
            stream_chat_response(
                thread_id=thread_id,
                model=payload.model or "deepseek-v4-flash",
                agent=agent,
                input_state=input_state,
                config=config,
                last_user_content=last_user_content,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
    else:
        try:
            result = await agent.ainvoke(input_state, config=config)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

        messages = result.get("messages", [])
        if not messages:
            raise HTTPException(status_code=500, detail="No response from agent")
        assistant_message = messages[-1]
        if not isinstance(assistant_message, AIMessage):
            assistant_message = AIMessage(content=str(assistant_message))

        logger.info(f"非流式大模型响应：{assistant_message}")

        # 保存消息
        if last_user_content:
            db.add(Message(thread_id=thread_id, role="user", content=last_user_content))

        # 非流式保存 assistant 消息
        assistant_fields = extract_assistant_message_fields(assistant_message)
        db.add(Message(thread_id=thread_id, role="assistant", **assistant_fields))
        db.commit()

        response_data = {
            "id": str(uuid.uuid4()),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": payload.model or "deepseek-v4-flash",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": assistant_message.content,
                },
                "finish_reason": "stop",
            }],
            "usage": None,
        }
        return response_data