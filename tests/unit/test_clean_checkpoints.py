from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from scripts import clean_checkpoints


class _FakeConnection:
    """记录清理脚本执行的 SQL，避免单元测试连接真实 PostgreSQL。"""

    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        return SimpleNamespace(rowcount=3)


class _FakeEngine:
    def __init__(self, dialect_name: str):
        self.dialect = SimpleNamespace(name=dialect_name)
        self.connection = _FakeConnection()

    def begin(self):
        return nullcontext(self.connection)


def test_clean_checkpoints_uses_payload_timestamp_and_cleans_related_rows(monkeypatch):
    engine = _FakeEngine("postgresql")
    monkeypatch.setattr(clean_checkpoints, "engine", engine)

    assert clean_checkpoints.clean_checkpoints(7) == 3

    statements = [sql for sql, _params in engine.connection.calls]
    assert len(statements) == 3
    assert "DELETE FROM checkpoint_writes" in statements[0]
    assert "checkpoint ->> 'ts'" in statements[0]
    assert "DELETE FROM checkpoints" in statements[1]
    assert "checkpoint ->> 'ts'" in statements[1]
    assert "DELETE FROM checkpoint_blobs" in statements[2]
    assert "channel_versions" in statements[2]


def test_clean_checkpoints_rejects_unsupported_database(monkeypatch):
    monkeypatch.setattr(clean_checkpoints, "engine", _FakeEngine("sqlite"))

    with pytest.raises(RuntimeError, match="仅支持 PostgreSQL"):
        clean_checkpoints.clean_checkpoints()
