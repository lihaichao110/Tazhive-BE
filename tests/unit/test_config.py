"""全局配置新增字段的最小契约测试。"""

from app.core.config import Settings


def _settings(**overrides) -> Settings:
    """提供必填数据库字段，避免测试依赖开发者本地 .env 的具体值。"""
    values = {
        "PG_USER": "test-user",
        "PG_PASSWORD": "test-password",
        "PG_DB": "test-db",
        **overrides,
    }
    return Settings(**values)


def test_tavily_api_key_accepts_empty_and_configured_values():
    assert _settings(tavily_api_key="").tavily_api_key == ""
    assert _settings(tavily_api_key="test-key").tavily_api_key == "test-key"
