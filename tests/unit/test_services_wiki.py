import json
from types import SimpleNamespace

import pytest

from app.services.wiki.ingestion.pipeline import WikiCompiler
from app.services.wiki.service import WikiService


def test_wiki_status():
    service = WikiService()
    status = service.get_status()

    assert status["schema_exists"] is True
    assert status["raw_dir_exists"] is True
    assert status["vault_dir_exists"] is True
    assert status["vault_page_count"] >= 0


def _wiki_response(title: str = "泰智汇") -> SimpleNamespace:
    return SimpleNamespace(
        content=json.dumps(
            {
                "pages": [
                    {
                        "type": "entity",
                        "title": title,
                        "aliases": [],
                        "summary": "泰智汇是智能 Agent 系统。",
                        "body": "系统基于 FastAPI 和 LangGraph 构建。",
                        "related": [],
                        "sources": ["demo.md"],
                        "confidence": "high",
                        "conflicts": [],
                    }
                ],
                "notes": "",
            },
            ensure_ascii=False,
        )
    )


def test_wiki_compiler_invokes_langchain_model_and_writes_page(tmp_path):
    raw_path = tmp_path / "raw" / "demo.md"
    vault_dir = tmp_path / "vault"
    schema_path = tmp_path / "SCHEMA.md"
    raw_path.parent.mkdir()
    raw_path.write_text("泰智汇支持 RAG。", encoding="utf-8")
    schema_path.write_text("测试 Schema", encoding="utf-8")
    model = SimpleNamespace(invoke=lambda _messages: _wiki_response())

    compiler = WikiCompiler(model, vault_dir, schema_path)
    batch = compiler.compile_file(raw_path)

    assert [page.title for page in batch.pages] == ["泰智汇"]
    page_text = (vault_dir / "泰智汇.md").read_text(encoding="utf-8")
    assert "FastAPI 和 LangGraph" in page_text
    assert "[[泰智汇]]" in (vault_dir / "index.md").read_text(encoding="utf-8")
    assert "demo.md" in (vault_dir / "log.md").read_text(encoding="utf-8")


def test_wiki_compiler_sanitizes_generated_filename(tmp_path):
    compiler = WikiCompiler(SimpleNamespace(), tmp_path, tmp_path / "SCHEMA.md")
    page = _wiki_response("项目/架构").content
    parsed_page = compiler._parse_output(page).pages[0]

    assert compiler.page_path(parsed_page) == tmp_path / "项目-架构.md"


def test_wiki_service_rejects_source_outside_raw_dir(tmp_path):
    service = WikiService()
    service.raw_dir = tmp_path / "raw"
    service.vault_dir = tmp_path / "vault"
    service.ensure_dirs()
    outside = tmp_path / "secret.md"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="raw 目录"):
        service.resolve_source(outside)


def test_wiki_service_compiles_and_indexes_pages(tmp_path, monkeypatch):
    service = WikiService()
    service.raw_dir = tmp_path / "raw"
    service.vault_dir = tmp_path / "vault"
    service.schema_path = tmp_path / "SCHEMA.md"
    service.ensure_dirs()
    (service.raw_dir / "demo.md").write_text("泰智汇支持 RAG。", encoding="utf-8")
    service.schema_path.write_text("测试 Schema", encoding="utf-8")
    model = SimpleNamespace(invoke=lambda _messages: _wiki_response())
    captured: dict = {}

    def fake_index(page_paths, *, vault_dir, db):
        captured["page_paths"] = page_paths
        captured["vault_dir"] = vault_dir
        captured["db"] = db
        return ["wiki-document-id"]

    monkeypatch.setattr("app.services.wiki.service.index_wiki_pages", fake_index)
    fake_db = SimpleNamespace()

    result = service.compile_file("demo.md", model, db=fake_db)

    assert result["indexed_document_ids"] == ["wiki-document-id"]
    assert captured["page_paths"] == [service.vault_dir / "泰智汇.md"]
    assert captured["vault_dir"] == service.vault_dir
    assert captured["db"] is fake_db
