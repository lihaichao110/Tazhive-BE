import json
import time
import uuid
from collections.abc import AsyncGenerator
from logging import getLogger
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    message_chunk_to_message,
)
from langchain_core.runnables import RunnableConfig
from langfuse.langchain import CallbackHandler
from sqlmodel import Session

from app.api.deps import get_current_user, get_db
from app.core.langgraph.graph import get_supervisor_graph
from app.core.langgraph.prompts.system_chat import SYSTEM_CHAT_PROMPT
from app.core.limiter import limiter
from app.models.agent import Agent
from app.models.message import Message, ensure_created_after
from app.models.thread import Thread
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.database import engine
from app.services.dataquery.table_markdown import merge_table_into_envelope
from app.services.plans import format_a2ui_fence

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
def dict_to_langchain_messages(messages: list[dict]) -> list[BaseMessage]:
    lc_messages: list[BaseMessage] = []
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


def _is_model_node(meta: dict) -> bool:
    """判断 messages 流事件是否来自子 Agent 的模型节点。

    supervisor 化后模型节点位于子图内，langgraph_node 可能是子图内部
    节点名（"model"）或带命名空间前缀（如 "general_node:xxx:model"）。
    """
    node = str(meta.get("langgraph_node") or "")
    return node == "model" or node.endswith(":model")


def _accumulate_model_message(
    current: AIMessage | AIMessageChunk | None,
    incoming: AIMessage | AIMessageChunk,
) -> AIMessage | AIMessageChunk:
    """按消息 ID 聚合同一轮模型输出，保留工具调用后的最后一轮回复。"""
    if isinstance(incoming, AIMessageChunk):
        if isinstance(current, AIMessageChunk) and current.id == incoming.id:
            return current + incoming
        # 消息 ID 变化代表新一轮模型调用，上一轮工具调用消息不再作为最终回复。
        return incoming
    return incoming


def _content_chunk_frame(model: str, content: str) -> str:
    """构造一帧 OpenAI 风格的正文增量 SSE 数据，供卡片围栏、合并表格等收尾载荷复用。"""
    chunk_data = {
        "id": str(uuid.uuid4()),
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": content, "reasoning_content": None},
                "finish_reason": None,
                "logprobs": None,
            }
        ],
    }
    return f"data: {json.dumps(chunk_data)}\n\n"


async def _read_stream_attachments(agent, config: RunnableConfig) -> tuple[str, str]:
    """流结束后一次读取本轮图状态里的正文附件，返回 (A2UI 围栏, 表格 Markdown)。

    两者都只走「状态 → API 出口」：不写进 checkpoint 消息（否则几十 KB 内容
    会在后续轮次被反复塞进模型上下文），但会随 assistant 消息一起下发并落库，
    使历史消息重放拿到与本次流式输出完全同形的内容。
    """
    try:
        state = await agent.aget_state(config)
    except Exception as e:
        logger.warning(f"读取卡片状态失败，本轮不下发卡片：{e}")
        return "", ""
    values = state.values or {}
    x_card = values.get("x_card")
    fence = format_a2ui_fence(x_card) if isinstance(x_card, dict) and x_card.get("commands") else ""
    table_markdown = values.get("table_markdown")
    table = table_markdown if isinstance(table_markdown, str) and table_markdown else ""
    return fence, table


async def stream_chat_response(
    thread_id: str,
    model: str,
    agent,
    input_state: dict,
    config: RunnableConfig,
    last_user_content: str | None,
) -> AsyncGenerator[str, None]:
    """生成 SSE 流式响应，并在结束时保存完整消息到数据库。

    token 级增量通过 custom 流接收（StreamingMiddleware 用 stream_writer 转发
    模型 chunk，规避 create_agent 不透传 config 导致的回调断链）；
    完整消息（含 tool_calls / usage_metadata，用于落库）通过 messages 流接收。
    收尾附件按意图二选一：insurance 轮的 A2UI 围栏直接追加在正文后；
    data_query 轮的表格 Markdown 则并入图表信封 content 字段后整帧下发
    （该意图回答不做 token 透传），两种附件都保证流式与落库同形。
    """
    full_content = ""
    final_message: AIMessage | AIMessageChunk | None = None
    card_fence = ""
    table_markdown = ""
    try:
        logger.info(f"流式响应开始：{config}")
        async for _namespace, mode, payload in agent.astream(
            input_state,
            config=config,
            stream_mode=["custom", "messages"],
            subgraphs=True,
        ):
            if mode == "custom":
                chunk = payload
                # 只处理 StreamingMiddleware 转发的模型 chunk；其他结构化载荷
                # （如未来的事件广播）不参与 token 流，跳过而不是抛 AttributeError。
                if not isinstance(chunk, (AIMessage, AIMessageChunk)):
                    logger.debug(f"忽略 custom 通道的非模型载荷：type={type(chunk).__name__}")
                    continue
                # StreamingMiddleware 转发的 AIMessageChunk 增量
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
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "role": "assistant",
                                    "content": delta_content,
                                    "reasoning_content": delta_reasoning,
                                },
                                "finish_reason": None,
                                "logprobs": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"
            else:
                # messages 流：取子 Agent 模型节点产出的完整消息（工具循环的
                # 中间消息会被后续消息覆盖），工具结果 ToolMessage 不需要
                chunk, meta = payload
                if _is_model_node(meta) and isinstance(chunk, (AIMessage, AIMessageChunk)):
                    # messages 模式逐块发送；结束时的空 chunk 也必须合并，不能覆盖正文。
                    final_message = _accumulate_model_message(final_message, chunk)
        # 正文附件在流正常结束后读取（放在 try 内而非 finally，避免客户端断开、
        # 生成器收尾阶段还要发起异步 IO）
        card_fence, table_markdown = await _read_stream_attachments(agent, config)
    except Exception as e:
        # 模型彻底调用失败等异常直接向上抛出，这里统一转成 SSE error 帧，
        # 前端才能看到错误而不是只收到 [DONE]
        logger.error(f"Agent 流式调用出错：{e}")
        error_data = {"error": str(e)}
        yield f"data: {json.dumps(error_data)}\n\n"
    finally:
        composed_content = ""
        if card_fence:
            # A2UI 卡片作为最后一段正文增量下发，前端与历史消息拿到同形内容
            full_content += card_fence
            yield _content_chunk_frame(model, card_fence)
        if table_markdown and final_message is not None and not full_content:
            # data_query 回答不做 token 透传，这里把表格并入信封 content 后整帧
            # 下发。not full_content 是防误配守卫：SSE 只能追加，若 token 已被
            # 透传，前端累积内容无法回退，再下发合并帧只会重复正文。
            raw_content = final_message.content
            composed_content = merge_table_into_envelope(
                raw_content if isinstance(raw_content, str) else str(raw_content),
                table_markdown,
            )
            full_content += composed_content
            yield _content_chunk_frame(model, composed_content)
        elif not full_content and final_message is not None:
            # 兜底：data_query 轮没产出表格（count 类单标量、不可回答、SQL 连续
            # 失败）时 token 透传又是关闭的，回答文本只能在这里整帧补发，
            # 否则客户端只收到一个空 stop 帧。
            fallback_content = _extract_text_from_content(final_message.content)
            if fallback_content:
                full_content += fallback_content
                yield _content_chunk_frame(model, fallback_content)

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
            user_message = None
            if last_user_content:
                user_message = Message(thread_id=thread_id, role="user", content=last_user_content)
                session.add(user_message)
            if isinstance(final_message, AIMessageChunk):
                final_message = cast(AIMessage, message_chunk_to_message(final_message))
            assistant_message = None
            if isinstance(final_message, AIMessage):
                # 完整保存 assistant 消息（卡片围栏/合并表格一并落库，供历史重放）
                assistant_fields = extract_assistant_message_fields(final_message)
                if composed_content:
                    assistant_fields["content"] = composed_content
                elif card_fence:
                    assistant_fields["content"] = f"{assistant_fields['content']}{card_fence}"
                assistant_message = Message(
                    thread_id=thread_id, role="assistant", **assistant_fields
                )
            elif full_content:
                # 降级：只保存文本（但这种情况应避免）
                assistant_message = Message(
                    thread_id=thread_id, role="assistant", content=full_content
                )
            if assistant_message is not None:
                if user_message is not None:
                    # 成对落库时保证 assistant 时间戳严格晚于 user，避免列表排序并列乱序
                    ensure_created_after(assistant_message, user_message)
                session.add(assistant_message)
            session.commit()


@router.post("/chat/{thread_id}", response_model=None)
@limiter.limit("20/minute")
async def chat(
    request: Request,
    thread_id: str,
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # slowapi 通过 request 获取客户端信息并执行限流。
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

    # 获取 supervisor 图（意图识别 + 按注册表路由子 Agent）
    supervisor = await get_supervisor_graph()

    # 默认值：基础身份提示词（协议片段由目标意图 Agent 按需拼接）
    system_prompt = SYSTEM_CHAT_PROMPT
    model_name = payload.model

    # 如果指定了 agent_id，则加载 Agent 配置（注意与上面的 supervisor 区分）
    if payload.agent_id:
        agent_config = db.get(Agent, payload.agent_id)
        if not agent_config or agent_config.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="找不到对应的 Agent")
        # 自定义 Agent 的提示词作为基础提示词，意图协议由目标 Agent 拼接
        if agent_config.system_prompt:
            system_prompt = agent_config.system_prompt
        if not payload.model and agent_config.model:
            model_name = agent_config.model
        # 也可使用 agent_config.temperature 等，但当前未传递

    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [langfuse_handler],
    }

    # 增量发送：图的 messages 为 add_messages 累积语义，会话记忆由
    # checkpointer 按 thread_id 维护。该 thread 已有记忆时只发本轮新的
    # 用户消息；空 thread（首次对话/前端带历史导入）才发送全量消息。
    checkpoint_state = await supervisor.aget_state(config)
    if checkpoint_state.values.get("messages"):
        input_messages = [m for m in lc_messages if isinstance(m, HumanMessage)][-1:] or lc_messages
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
            agent=supervisor,
            input_state=input_state,
            config=config,
            last_user_content=last_user_content,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
