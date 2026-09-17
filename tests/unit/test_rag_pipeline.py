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


def test_build_chunks_keeps_xlsx_row_records_whole():
    """xlsx 行记录足够短时直接作为 chunk，保持自包含。"""
    records = [
        "【工作表: 人员信息表】单位名称: 应用开发一处；员工姓名: 李海超",
        "【工作表: 人员信息表】单位名称: 人力资源部；员工姓名: 瞿玲",
    ]

    assert pipeline.build_chunks(records, "xlsx") == records


def test_build_chunks_falls_back_to_generic_chunking_for_long_xlsx_record(monkeypatch):
    """超长行记录回退通用切片，且不再按行拆散。"""
    long_record = "【工作表: 规范】内容: " + "长" * 1500
    monkeypatch.setattr(pipeline, "chunk_text", lambda _text: ["chunked-part"])

    assert pipeline.build_chunks([long_record], "xlsx") == ["chunked-part"]


def test_build_chunks_uses_generic_chunking_for_other_types(monkeypatch):
    monkeypatch.setattr(pipeline, "chunk_text", lambda _text: ["chunk-1", "chunk-2"])

    assert pipeline.build_chunks(["source text"], "md") == ["chunk-1", "chunk-2"]


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
