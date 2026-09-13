from types import SimpleNamespace

import pytest

from app.models.document import Document
from app.services.rag import pipeline


class _FakeSession:
    """记录摄入管道的最小 Session 行为，避免单元测试连接真实数据库。"""

    def __init__(self):
        self.added = []
        self.commit_count = 0

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commit_count += 1

    def refresh(self, _value):
        return None


def test_ingest_document_rejects_embedding_count_mismatch(monkeypatch):
    """向量数量不一致时标记文档失败，且不留下部分 DocumentChunk。"""
    session = _FakeSession()
    embedder = SimpleNamespace(embed_documents=lambda _chunks: [[0.1, 0.2]])
    monkeypatch.setattr(pipeline, "load_document", lambda _path: ["source text"])
    monkeypatch.setattr(pipeline, "chunk_text", lambda _text: ["chunk-1", "chunk-2"])
    monkeypatch.setattr(pipeline, "get_embedder", lambda: embedder)

    with pytest.raises(ValueError, match=r"zip\(\) argument 2 is shorter"):
        pipeline.ingest_document("report.txt", "report.txt", session)

    assert len(session.added) == 1
    assert isinstance(session.added[0], Document)
    assert session.added[0].status == "error"
    assert session.added[0].chunk_count == 0
    assert session.commit_count == 2
