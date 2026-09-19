"""全局配置新增字段的最小契约测试。"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _settings(**overrides) -> Settings:
    """提供必填数据库字段，避免测试依赖开发者本地 .env 的具体值。"""
    values = {
        "PG_USER": "test-user",
        "PG_PASSWORD": "test-password",
        "PG_DB": "test-db",
        "llm_provider": "deepseek",
        "llm_api_key": "test-key",
        "llm_models": "deepseek-flash,deepseek-v4-pro",
        "llm_default_model": "deepseek-flash",
        "llm_fast_model": "deepseek-flash",
        "llm_text2sql_model": "deepseek-flash",
        "llm_default_temperature": 0.7,
        "llm_model_aliases": '{"deepseek-v4-flash":"deepseek-flash"}',
        **overrides,
    }
    return Settings(**values)


def test_tavily_api_key_accepts_empty_and_configured_values():
    assert _settings(tavily_api_key="").tavily_api_key == ""
    assert _settings(tavily_api_key="test-key").tavily_api_key == "test-key"


def test_cors_origins_supports_comma_separated_values():
    settings = _settings(
        cors_allowed_origins="https://ai.lihaichao.cn, http://localhost:5173,https://ai.lihaichao.cn"
    )

    assert settings.cors_origins == [
        "https://ai.lihaichao.cn",
        "http://localhost:5173",
    ]


def test_empty_cors_config_disallows_cross_origin_requests_by_default():
    assert _settings(cors_allowed_origins="").cors_origins == []


def test_llm_registry_configuration_is_parsed_and_validated():
    configured = _settings()

    assert configured.llm_model_names == ["deepseek-flash", "deepseek-v4-pro"]
    assert configured.llm_alias_map == {"deepseek-v4-flash": "deepseek-flash"}
    assert configured.llm_base_url is None


def test_llm_registry_rejects_duplicate_models():
    with pytest.raises(ValidationError, match="LLM_MODELS 不能包含重复模型"):
        _settings(llm_models="deepseek-flash,deepseek-flash")


def test_llm_registry_rejects_role_outside_registered_models():
    with pytest.raises(ValidationError, match="LLM_FAST_MODEL 必须存在于 LLM_MODELS"):
        _settings(llm_fast_model="unknown-model")


def test_llm_registry_rejects_invalid_alias_target():
    with pytest.raises(ValidationError, match="目标必须存在于 LLM_MODELS"):
        _settings(llm_model_aliases='{"legacy-model":"unknown-model"}')


@pytest.mark.parametrize("field", ["llm_provider", "llm_api_key", "llm_models"])
def test_llm_required_configuration_rejects_blank_values(field):
    with pytest.raises(ValidationError):
        _settings(**{field: " "})
