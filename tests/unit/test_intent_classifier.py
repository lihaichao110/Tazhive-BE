"""IntentClassifier 单元测试：结构化分类、超时/异常兜底、prompt 拼装。"""
import asyncio

import pytest

from app.core.langgraph.intent.classifier import (
    IntentClassifier,
    IntentResult,
    build_classification_prompt,
)
from app.core.langgraph.intent.registry import DEFAULT_INTENT_ID, INTENT_SPECS


class FakeStructuredModel:
    """with_structured_output 返回自身；ainvoke 记录入参并返回预设结果。"""

    def __init__(self, result=None, delay=0.0, exc=None):
        self.result = result or IntentResult(intent="chitchat", confidence=0.9)
        self.delay = delay
        self.exc = exc
        self.calls = []

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        return self.result


def _last_call_text(model) -> tuple[str, str]:
    """返回（分类 prompt, 用户消息文本）"""
    messages = model.calls[-1]
    return messages[0].content, messages[1].content


@pytest.mark.asyncio
async def test_classify_returns_structured_result():
    model = FakeStructuredModel(result=IntentResult(intent="insurance", confidence=0.88))
    classifier = IntentClassifier(model=model)

    result = await classifier.classify("我想买份重疾险")

    assert result.intent == "insurance"
    assert result.confidence == 0.88
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_classify_sends_registry_prompt_and_user_text():
    model = FakeStructuredModel()
    classifier = IntentClassifier(model=model)

    await classifier.classify("把销售额画成柱状图")

    prompt, text = _last_call_text(model)
    assert text == "把销售额画成柱状图"
    # 分类 prompt 由注册表拼装：包含全部意图的 id 与描述
    for spec in INTENT_SPECS.values():
        assert spec.id in prompt
        assert spec.description in prompt


def test_classification_prompt_includes_examples_and_fallback():
    prompt = build_classification_prompt()
    assert "示例：" in prompt
    assert DEFAULT_INTENT_ID in prompt


@pytest.mark.asyncio
async def test_classify_empty_text_skips_llm():
    model = FakeStructuredModel()
    classifier = IntentClassifier(model=model)

    result = await classifier.classify("   ")

    assert result.intent == DEFAULT_INTENT_ID
    assert result.confidence == 0.0
    assert model.calls == []


@pytest.mark.asyncio
async def test_classify_timeout_falls_back_to_default():
    model = FakeStructuredModel(delay=0.5)
    classifier = IntentClassifier(model=model, timeout_seconds=0.05)

    result = await classifier.classify("你好")

    assert result.intent == DEFAULT_INTENT_ID


@pytest.mark.asyncio
async def test_classify_exception_falls_back_to_default():
    model = FakeStructuredModel(exc=RuntimeError("llm down"))
    classifier = IntentClassifier(model=model)

    result = await classifier.classify("你好")

    assert result.intent == DEFAULT_INTENT_ID
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_unknown_intent_id_normalized_to_registered():
    """分类器输出了未注册意图 id 时，兜底到注册表默认意图。"""
    model = FakeStructuredModel(result=IntentResult(intent="bogus", confidence=0.7))
    classifier = IntentClassifier(model=model)

    result = await classifier.classify("随便什么")

    assert result.intent == DEFAULT_INTENT_ID
