"""意图分类器：轻量 LLM 调用，把用户消息映射为注册表中的意图 id。

设计约束：
- 分类失败（异常/超时）绝不阻塞主对话，一律兜底 DEFAULT_INTENT_ID；
- 分类 prompt 由意图注册表动态拼装，注册表新增意图后无需改这里；
- 使用 flash 档模型做单次非流式调用，控制延迟与成本。
"""

import asyncio

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.core.langgraph.intent.registry import (
    DEFAULT_INTENT_ID,
    INTENT_SPECS,
    get_intent_spec,
)
from app.core.logging import logger

INTENT_MODEL_NAME = "deepseek-v4-flash"
"""分类用的轻量模型（LLMRegistry 注册列表内的低档位模型）。"""

INTENT_MODEL_THINKING = {"type": "disabled"}
"""意图分类无需深度推理；关闭 thinking，避免与结构化输出能力冲突。"""

CLASSIFY_TIMEOUT_SECONDS = 8.0
"""单次分类调用的超时时间；超时直接兜底，不重试。"""


class IntentResult(BaseModel):
    """结构化输出的意图分类结果。"""

    intent: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


def build_classification_prompt() -> str:
    """由注册表拼装分类 prompt：意图清单 + 示例，注册表变更后自动生效。"""
    lines = [
        "你是意图分类器。将用户消息分类为以下意图之一，只输出最匹配的一个：",
    ]
    for spec in INTENT_SPECS.values():
        lines.append(f"- {spec.id}：{spec.description}")
        for example in spec.examples:
            lines.append(f"  示例：{example}")
    lines.append(
        f"不确定或都不匹配时输出 {DEFAULT_INTENT_ID}。"
        "返回 JSON：{\"intent\": \"意图id\", \"confidence\": 0到1之间的置信度}。"
    )
    return "\n".join(lines)


class IntentClassifier:
    """调用 LLM 结构化输出做意图分类，内置超时与兜底。"""

    def __init__(
        self,
        model: BaseChatModel,
        timeout_seconds: float = CLASSIFY_TIMEOUT_SECONDS,
    ):
        # DeepSeek 的 thinking 模式不支持 function_calling 默认附带的 tool_choice。
        # 使用 JSON Mode 获取结构化结果，避免把分类任务伪装成工具调用。
        self._structured = model.with_structured_output(IntentResult, method="json_mode")
        self._timeout_seconds = timeout_seconds

    async def classify(self, text: str) -> IntentResult:
        """对一段用户消息分类；空文本直接兜底，异常/超时兜底且不重试。"""
        if not text or not text.strip():
            return IntentResult(intent=DEFAULT_INTENT_ID, confidence=0.0)

        try:
            result = await asyncio.wait_for(
                self._structured.ainvoke(
                    [
                        SystemMessage(content=build_classification_prompt()),
                        HumanMessage(content=text),
                    ]
                ),
                timeout=self._timeout_seconds,
            )
            # 分类器可能返回未注册的意图 id，统一在注册表侧兜底。
            spec = get_intent_spec(result.intent)
            return IntentResult(intent=spec.id, confidence=result.confidence)
        except Exception as exc:
            logger.warning(f"意图分类失败，兜底到 {DEFAULT_INTENT_ID}：{exc}")
            return IntentResult(intent=DEFAULT_INTENT_ID, confidence=0.0)


_classifier: IntentClassifier | None = None


def get_intent_classifier() -> IntentClassifier:
    """模块级单例：分类模型与结构化包装只构建一次。"""
    global _classifier
    if _classifier is None:
        from app.services.llm.registry import default_registry

        # 分类模型固定关闭 thinking；用户为主对话选择的 thinking 模式不受影响。
        model = default_registry.get_model(
            INTENT_MODEL_NAME,
            thinking=INTENT_MODEL_THINKING,
        )
        _classifier = IntentClassifier(model=model)
    return _classifier
