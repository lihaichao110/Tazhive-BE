from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.deps import get_current_user, get_db
from app.api.v1 import documents
from app.main import app
from app.models.document import Document
from app.services.rag.loader import DocumentParseError


class _FakeSession:
    """为上传接口提供最小数据库行为，避免单元测试依赖真实数据库。"""

    def get(self, model, document_id):
        return SimpleNamespace(
            id=document_id,
            filename="report.xlsx",
            status="done",
            chunk_count=2,
        )


@pytest.fixture
def document_client(client):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="user-id")
    app.dependency_overrides[get_db] = lambda: _FakeSession()
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_upload_accepts_xlsx_and_removes_temporary_file(document_client, tmp_path, monkeypatch):
    captured_path: Path | None = None

    def fake_ingest(file_path, filename, db):
        nonlocal captured_path
        captured_path = Path(file_path)
        assert captured_path.exists()
        assert captured_path.suffix == ".xlsx"
        assert filename == "report.xlsx"
        return "document-id"

    monkeypatch.setattr(documents.settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(documents, "ingest_document", fake_ingest)

    response = document_client.post(
        "/api/v1/documents/upload",
        files={
            "files": (
                "report.xlsx",
                b"xlsx-content-is-mocked-before-parsing",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "document_id": "document-id",
        "filename": "report.xlsx",
        "status": "done",
        "chunk_count": 2,
    }
    assert captured_path is not None
    assert not captured_path.exists()


def test_upload_maps_excel_parse_error_to_400_and_removes_temporary_file(
    document_client, tmp_path, monkeypatch
):
    captured_path: Path | None = None

    def fake_ingest(file_path, filename, db):
        nonlocal captured_path
        captured_path = Path(file_path)
        assert captured_path.exists()
        raise DocumentParseError("Excel 文件损坏、已加密或格式无效")

    monkeypatch.setattr(documents.settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(documents, "ingest_document", fake_ingest)

    response = document_client.post(
        "/api/v1/documents/upload",
        files={"files": ("broken.xlsx", b"broken", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Excel 文件损坏、已加密或格式无效"}
    assert captured_path is not None
    assert not captured_path.exists()


@pytest.mark.parametrize("filename", ["legacy.xls", "macros.xlsm"])
def test_upload_rejects_unsupported_excel_extensions(
    document_client, tmp_path, monkeypatch, filename
):
    monkeypatch.setattr(documents.settings, "upload_dir", str(tmp_path))

    response = document_client.post(
        "/api/v1/documents/upload",
        files={"files": (filename, b"unsupported", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": f"文件类型不支持: {Path(filename).suffix}"}
    assert list(tmp_path.iterdir()) == []


class _ChunkResult:
    def __init__(self, chunk):
        self._chunk = chunk

    def first(self):
        return self._chunk


class _ChunkSession:
    def __init__(self, document=None, chunk=None):
        self.document = document
        self.chunk = chunk

    def get(self, model, document_id):
        assert model is Document
        return self.document

    def exec(self, statement):
        return _ChunkResult(self.chunk)


def test_get_document_chunk_returns_authenticated_preview(client):
    document = SimpleNamespace(id="doc-1", filename="员工手册.pdf", file_type="pdf")
    chunk = SimpleNamespace(document_id="doc-1", chunk_index=3, content="报销制度正文")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="user-id")
    app.dependency_overrides[get_db] = lambda: _ChunkSession(document, chunk)
    try:
        response = client.get("/api/v1/documents/doc-1/chunks/3")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "document_id": "doc-1",
        "filename": "员工手册.pdf",
        "file_type": "pdf",
        "chunk_index": 3,
        "content": "报销制度正文",
    }


@pytest.mark.parametrize(
    ("document", "chunk", "detail"),
    [
        (None, None, "文档不存在"),
        (SimpleNamespace(id="doc-1"), None, "文档片段不存在"),
    ],
)
def test_get_document_chunk_returns_404(client, document, chunk, detail):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="user-id")
    app.dependency_overrides[get_db] = lambda: _ChunkSession(document, chunk)
    try:
        response = client.get("/api/v1/documents/doc-1/chunks/99")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": detail}


def test_get_document_chunk_requires_authentication(client):
    response = client.get("/api/v1/documents/doc-1/chunks/0")
    assert response.status_code == 401
