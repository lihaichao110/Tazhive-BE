"""ModelRoutingMiddleware 与 MetricsMiddleware 单元测试。"""

from unittest.mock import MagicMock

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import FakeChatModel
from langchain_core.messages import AIMessage
from prometheus_client import REGISTRY

from app.core.langgraph.middleware.metrics import MetricsMiddleware
from app.core.langgraph.middleware.model_routing import ModelRoutingMiddleware


def _make_request(state=None):
    return ModelRequest(
        model=FakeChatModel(),
        messages=[],
        state=state if state is not None else {},
    )


@pytest.mark.asyncio
async def test_routing_overrides_model_from_state():
    sentinel = FakeChatModel()
    registry = MagicMock()
    registry.get_model.return_value = sentinel
    mw = ModelRoutingMiddleware(registry=registry)
    captured = {}

    async def handler(req):
        captured["model"] = req.model
        return ModelResponse(result=[AIMessage(content="ok")])

    await mw.awrap_model_call(
        _make_request({"model": "deepseek-v4-flash", "thinking": {"type": "enabled"}}),
        handler,
    )

    assert captured["model"] is sentinel
    registry.get_model.assert_called_once_with("deepseek-v4-flash", {"type": "enabled"})


@pytest.mark.asyncio
async def test_routing_falls_back_to_registry_default():
    sentinel = FakeChatModel()
    registry = MagicMock()
    registry.get_model.return_value = sentinel
    mw = ModelRoutingMiddleware(registry=registry)

    async def handler(req):
        return ModelResponse(result=[AIMessage(content="ok")])

    await mw.awrap_model_call(_make_request(), handler)

    registry.get_model.assert_called_once_with(None, None)


def _sample_value(name, labels):
    return REGISTRY.get_sample_value(name, labels) or 0


@pytest.mark.asyncio
async def test_metrics_counts_call_and_tokens():
    mw = MetricsMiddleware()
    model_label = "metrics-test-model"

    async def handler(req):
        return ModelResponse(
            result=[
                AIMessage(
                    content="ok",
                    usage_metadata={
                        "input_tokens": 3,
                        "output_tokens": 5,
                        "total_tokens": 8,
                    },
                )
            ]
        )

    before_calls = _sample_value("app_llm_calls_total", {"model": model_label})
    before_in = _sample_value("app_llm_tokens_total", {"model": model_label, "type": "input"})
    before_out = _sample_value("app_llm_tokens_total", {"model": model_label, "type": "output"})

    await mw.awrap_model_call(_make_request({"model": model_label}), handler)

    assert _sample_value("app_llm_calls_total", {"model": model_label}) - before_calls == 1
    assert (
        _sample_value("app_llm_tokens_total", {"model": model_label, "type": "input"}) - before_in
        == 3
    )
    assert (
        _sample_value("app_llm_tokens_total", {"model": model_label, "type": "output"}) - before_out
        == 5
    )


@pytest.mark.asyncio
async def test_metrics_does_not_count_on_failure():
    mw = MetricsMiddleware()
    model_label = "metrics-fail-model"

    async def handler(req):
        raise RuntimeError("boom")

    before_calls = _sample_value("app_llm_calls_total", {"model": model_label})
    with pytest.raises(RuntimeError):
        await mw.awrap_model_call(_make_request({"model": model_label}), handler)

    assert _sample_value("app_llm_calls_total", {"model": model_label}) == before_calls
