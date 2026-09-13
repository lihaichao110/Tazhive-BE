"""RagMiddleware 单元测试：检索注入 system message 的行为。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import FakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.langgraph.middleware.rag import RagMiddleware
from app.core.langgraph.prompts.system_chat import SYSTEM_CHAT_PROMPT


def _make_request(messages, state=None):
    return ModelRequest(
        model=FakeChatModel(),
        messages=messages,
        state=state if state is not None else {},
    )


def _make_handler(captured):
    async def handler(req):
        captured["request"] = req
        return ModelResponse(result=[AIMessage(content="ok")])

    return handler


def _patch_rag(finding_contents):
    """mock embedder / retriever / reranker，检索固定返回 finding_contents"""
    embedder = AsyncMock()
    embedder.aembed_query.return_value = [0.1, 0.2]
    chunks = [MagicMock(content=c) for c in finding_contents]
    patches = [
        patch("app.core.langgraph.middleware.rag.get_embedder", return_value=embedder),
        patch(
            "app.core.langgraph.middleware.rag.retrieve_similar_chunks",
            return_value=chunks,
        ),
        patch(
            "app.core.langgraph.middleware.rag.rerank_chunks",
            side_effect=lambda query, cs: cs,
        ),
    ]
    return embedder, patches


@pytest.mark.asyncio
async def test_rag_injects_findings_into_system_message():
    embedder, patches = _patch_rag(["chunk-1", "chunk-2"])
    captured = {}
    mw = RagMiddleware()

    for p in patches:
        p.start()
    try:
        await mw.awrap_model_call(
            _make_request([HumanMessage(content="什么是 TaiWisHub？")]),
            _make_handler(captured),
        )
    finally:
        for p in patches:
            p.stop()

    embedder.aembed_query.assert_awaited_once_with("什么是 TaiWisHub？")
    system_message = captured["request"].system_message
    assert isinstance(system_message, SystemMessage)
    assert system_message.content.startswith(SYSTEM_CHAT_PROMPT)
    assert "参考资料：" in system_message.content
    assert "chunk-1" in system_message.content and "chunk-2" in system_message.content


@pytest.mark.asyncio
async def test_rag_uses_custom_system_prompt_from_state():
    embedder, patches = _patch_rag(["chunk-1"])
    captured = {}
    mw = RagMiddleware()

    for p in patches:
        p.start()
    try:
        await mw.awrap_model_call(
            _make_request(
                [HumanMessage(content="hi")],
                state={"system_prompt": "你是客服小智"},
            ),
            _make_handler(captured),
        )
    finally:
        for p in patches:
            p.stop()

    assert captured["request"].system_message.content.startswith("你是客服小智")
    assert "chunk-1" in captured["request"].system_message.content


@pytest.mark.asyncio
async def test_rag_skips_retrieval_without_user_message():
    embedder, patches = _patch_rag(["chunk-1"])
    captured = {}
    mw = RagMiddleware()

    for p in patches:
        p.start()
    try:
        await mw.awrap_model_call(
            _make_request([AIMessage(content="只有助手消息")]),
            _make_handler(captured),
        )
    finally:
        for p in patches:
            p.stop()

    embedder.aembed_query.assert_not_awaited()
    assert captured["request"].system_message.content == SYSTEM_CHAT_PROMPT
