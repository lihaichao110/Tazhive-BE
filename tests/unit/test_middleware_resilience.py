"""ResilienceMiddleware 单元测试：重试 + registry 故障转移。"""

from unittest.mock import MagicMock

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import FakeChatModel
from langchain_core.messages import AIMessage

from app.core.langgraph.middleware.resilience import ResilienceMiddleware


def _make_request():
    return ModelRequest(model=FakeChatModel(), messages=[], state={})


def _make_mw(**kwargs):
    registry = MagicMock()
    mw = ResilienceMiddleware(registry=registry, max_attempts=3, wait_min=0, wait_max=0, **kwargs)
    return mw, registry


@pytest.mark.asyncio
async def test_retry_rotates_and_succeeds_on_third_attempt():
    mw, registry = _make_mw()
    calls = {"n": 0}

    async def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return ModelResponse(result=[AIMessage(content="ok")])

    response = await mw.awrap_model_call(_make_request(), handler)

    assert response.result[0].content == "ok"
    assert calls["n"] == 3
    # 3 次尝试 = 2 次重试，每次重试前 rotate 切换模型
    assert registry.rotate.call_count == 2


@pytest.mark.asyncio
async def test_all_attempts_fail_raises_last_error():
    mw, registry = _make_mw()

    async def handler(req):
        raise RuntimeError("permanent failure")

    with pytest.raises(RuntimeError, match="permanent failure"):
        await mw.awrap_model_call(_make_request(), handler)

    assert registry.rotate.call_count == 2


@pytest.mark.asyncio
async def test_no_retry_on_success():
    mw, registry = _make_mw()

    async def handler(req):
        return ModelResponse(result=[AIMessage(content="ok")])

    response = await mw.awrap_model_call(_make_request(), handler)

    assert response.result[0].content == "ok"
    registry.rotate.assert_not_called()
