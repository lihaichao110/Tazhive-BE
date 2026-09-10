from app.core.langgraph.intent.registry import (
    DEFAULT_INTENT_ID,
    INTENT_SPECS,
    get_intent_spec,
)
from app.core.langgraph.prompts.system_chat import (
    CHART_RESPONSE_PROTOCOL_PROMPT,
    SYSTEM_CHAT_PROMPT,
)


def test_base_prompt_is_protocol_free():
    """基础身份提示词不再内嵌响应协议，协议由意图注册表按意图引用。"""
    assert "泰智汇" in SYSTEM_CHAT_PROMPT
    assert CHART_RESPONSE_PROTOCOL_PROMPT not in SYSTEM_CHAT_PROMPT


def test_general_spec_uses_chart_protocol_with_rag():
    """兜底意图 general 保持 chart 信封协议 + RAG，前端契约不变。"""
    general = get_intent_spec("general")
    assert general.id == DEFAULT_INTENT_ID
    assert general.protocol_prompt == CHART_RESPONSE_PROTOCOL_PROMPT
    assert general.use_rag is True


def test_chitchat_spec_is_plain_text_without_rag():
    chitchat = get_intent_spec("chitchat")
    assert chitchat.protocol_prompt is None
    assert chitchat.use_rag is False


def test_chart_analysis_spec_extends_chart_protocol():
    from app.core.langgraph.prompts.system_chat import CHART_ANALYSIS_PROTOCOL_PROMPT

    spec = get_intent_spec("chart_analysis")
    assert spec.protocol_prompt.startswith(CHART_RESPONSE_PROTOCOL_PROMPT)
    assert spec.protocol_prompt == CHART_ANALYSIS_PROTOCOL_PROMPT


def test_unknown_intent_falls_back_to_general():
    assert get_intent_spec("no-such-intent").id == DEFAULT_INTENT_ID
    assert get_intent_spec(None).id == DEFAULT_INTENT_ID


def test_every_registered_intent_is_routable():
    """注册表是路由表的数据源：每条配置必须有 id 与分类描述。"""
    for spec in INTENT_SPECS.values():
        assert spec.id
        assert spec.description
        assert spec.id in INTENT_SPECS
