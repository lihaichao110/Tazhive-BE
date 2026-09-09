import json
import time
import uuid
from typing import AsyncGenerator

from logging import getLogger
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from sqlmodel import Session
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.thread import Thread
from app.models.message import Message
from app.schemas.chat import ChatRequest
from app.core.langgraph.agents import get_chat_agent
from app.services.database import engine
from app.models.agent import Agent
from app.core.langgraph.prompts.system_chat import SYSTEM_CHAT_PROMPT
from langfuse.langchain import CallbackHandler

logger = getLogger(__name__)

langfuse_handler = CallbackHandler()

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
    """生成 SSE 流式响应，并在结束时保存完整消息到数据库。

    token 级增量通过 custom 流接收（StreamingMiddleware 用 stream_writer 转发
    模型 chunk，规避 create_agent 不透传 config 导致的回调断链）；
    完整消息（含 tool_calls / usage_metadata，用于落库）通过 messages 流接收。
    """
    full_content = ""
    final_message = None  # 在循环外初始化，确保 finally 中可访问
    try:
        logger.info(f"流式响应开始：{config}")
        async for mode, payload in agent.astream(
            input_state, config=config, stream_mode=["custom", "messages"]
        ):
            if mode == "custom":
                # StreamingMiddleware 转发的 AIMessageChunk 增量
                chunk = payload
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
            else:
                # messages 流：取模型节点产出的完整消息（工具循环的中间消息
                # 会被后续消息覆盖），工具结果 ToolMessage 不需要
                chunk, meta = payload
                if isinstance(chunk, AIMessage) and meta.get("langgraph_node") == "model":
                    final_message = chunk
    except Exception as e:
        # 模型彻底调用失败等异常直接向上抛出，这里统一转成 SSE error 帧，
        # 前端才能看到错误而不是只收到 [DONE]
        logger.error(f"Agent 流式调用出错：{e}")
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

    # 获取对话 Agent（create_agent 构建的编译图）
    chat_agent = await get_chat_agent()

    # 默认值
    system_prompt = SYSTEM_CHAT_PROMPT
    model_name = payload.model

    # 如果指定了 agent_id，则加载 Agent 配置（注意与上面的 chat_agent 区分）
    if payload.agent_id:
        agent_config = db.get(Agent, payload.agent_id)
        if not agent_config or agent_config.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="找不到对应的 Agent")
        if agent_config.system_prompt:
            system_prompt = agent_config.system_prompt
        if not payload.model and agent_config.model:
            model_name = agent_config.model
        # 也可使用 agent_config.temperature 等，但当前未传递

    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [langfuse_handler]
    }

    # 增量发送：agent 的 messages 为 add_messages 累积语义，会话记忆由
    # checkpointer 按 thread_id 维护。该 thread 已有记忆时只发本轮新的
    # 用户消息；空 thread（首次对话/前端带历史导入）才发送全量消息。
    checkpoint_state = await chat_agent.aget_state(config)
    if checkpoint_state.values.get("messages"):
        input_messages = [m for m in lc_messages if isinstance(m, HumanMessage)][-1:]
        input_messages = input_messages or lc_messages
    else:
        input_messages = lc_messages

    # 输入状态
    input_state = {
        "messages": input_messages,
        "model": model_name,
        "thinking": payload.thinking,
        "system_prompt": system_prompt,
    }

    # 统一走 SSE 流式输出
    return StreamingResponse(
        stream_chat_response(
            thread_id=thread_id,
            model=model_name or "deepseek-v4-flash",
            agent=chat_agent,
            input_state=input_state,
            config=config,
            last_user_content=last_user_content,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )