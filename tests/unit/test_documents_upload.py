from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.deps import get_current_user, get_db
from app.api.v1 import documents
from app.main import app
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
