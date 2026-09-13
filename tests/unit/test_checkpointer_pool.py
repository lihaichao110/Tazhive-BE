"""LangGraph checkpoint PostgreSQL 连接池配置测试。"""

import logging

import pytest

from app.core.langgraph import checkpointer


def test_create_async_pool_enables_stale_connection_protection(monkeypatch):
    """公网连接池应在借出前检查连接，并配置主动回收和 TCP 保活。"""
    captured = {}

    class FakeAsyncConnectionPool:
        @staticmethod
        async def check_connection(_connection):
            return None

        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(checkpointer, "AsyncConnectionPool", FakeAsyncConnectionPool)
    monkeypatch.setattr(checkpointer.settings, "checkpoint_pool_min_size", 0)
    monkeypatch.setattr(checkpointer.settings, "checkpoint_pool_max_size", 10)
    monkeypatch.setattr(checkpointer.settings, "checkpoint_pool_timeout_seconds", 10.0)
    monkeypatch.setattr(checkpointer.settings, "checkpoint_pool_max_idle_seconds", 300.0)
    monkeypatch.setattr(checkpointer.settings, "checkpoint_pool_max_lifetime_seconds", 1800.0)
    monkeypatch.setattr(checkpointer.settings, "db_connect_timeout_seconds", 5)
    monkeypatch.setattr(checkpointer.settings, "db_keepalives_idle_seconds", 60)
    monkeypatch.setattr(checkpointer.settings, "db_keepalives_interval_seconds", 20)
    monkeypatch.setattr(checkpointer.settings, "db_keepalives_count", 3)

    checkpointer._create_async_pool()

    assert captured["open"] is False
    assert captured["min_size"] == 0
    assert captured["max_size"] == 10
    assert captured["timeout"] == 10.0
    assert captured["max_idle"] == 300.0
    assert captured["max_lifetime"] == 1800.0
    assert captured["check"] is FakeAsyncConnectionPool.check_connection
    assert captured["reconnect_failed"] is checkpointer._log_checkpoint_reconnect_failed
    assert captured["name"] == "langgraph-checkpoint"
    assert captured["kwargs"] == {
        "connect_timeout": 5,
        "keepalives": 1,
        "keepalives_idle": 60,
        "keepalives_interval": 20,
        "keepalives_count": 3,
    }


@pytest.mark.asyncio
async def test_reconnect_failure_log_contains_no_connection_info(caplog):
    """重连失败日志只包含诊断字段，不应泄露数据库连接串。"""

    class FakePool:
        name = "langgraph-checkpoint"
        reconnect_timeout = 300.0

    with caplog.at_level(logging.ERROR, logger=checkpointer.logger.name):
        await checkpointer._log_checkpoint_reconnect_failed(FakePool())

    record = caplog.records[-1]
    assert record.pool_name == "langgraph-checkpoint"
    assert record.error_type == "ReconnectTimeout"
    assert record.elapsed_seconds == 300.0
    assert "postgresql" not in record.getMessage()
