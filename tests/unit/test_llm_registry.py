"""统一 LLM 注册表的模型解析与构造参数测试。"""

from unittest.mock import patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeChatModel
from pydantic import SecretStr

from app.core.config import settings
from app.services.llm.registry import LLMRegistry


def _registry() -> LLMRegistry:
    return LLMRegistry(
        model_names=["deepseek-flash", "deepseek-v4-pro"],
        default_model="deepseek-v4-pro",
        aliases={"deepseek-v4-flash": "deepseek-flash"},
    )


def test_registry_starts_rotation_from_configured_default():
    registry = _registry()

    assert registry.normalize_model_name(None) == "deepseek-v4-pro"
    registry.rotate()
    assert registry.normalize_model_name(None) == "deepseek-flash"


def test_registry_normalizes_legacy_alias_and_rejects_unknown(caplog):
    registry = _registry()

    assert registry.normalize_model_name("deepseek-v4-flash") == "deepseek-flash"
    assert "已弃用" in caplog.text
    with pytest.raises(ValueError, match="不支持的模型"):
        registry.normalize_model_name("unknown-model")


def test_registry_passes_unified_connection_configuration(monkeypatch):
    registry = _registry()
    fake_model = FakeChatModel()
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "llm_api_key", SecretStr("test-key"))
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.example.com/v1")
    monkeypatch.setattr(settings, "llm_default_temperature", 0.7)

    with patch("app.services.llm.registry.init_chat_model", return_value=fake_model) as factory:
        assert registry.get_model("deepseek-flash") is fake_model

    factory.assert_called_once_with(
        model="deepseek-flash",
        model_provider="deepseek",
        api_key="test-key",
        temperature=0.7,
        streaming=True,
        base_url="https://llm.example.com/v1",
    )
