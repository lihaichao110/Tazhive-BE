from app.services.wiki.indexing import service


def test_index_wiki_pages_marks_chunks_as_wiki(tmp_path, monkeypatch):
    vault_dir = tmp_path / "vault"
    page_path = vault_dir / "泰智汇.md"
    vault_dir.mkdir()
    page_path.write_text("# 泰智汇", encoding="utf-8")
    captured: dict = {}

    def fake_ingest_document(**kwargs):
        captured.update(kwargs)
        return "document-id"

    monkeypatch.setattr(service, "ingest_document", fake_ingest_document)
    fake_db = object()

    result = service.index_wiki_pages([page_path], vault_dir=vault_dir, db=fake_db)

    assert result == ["document-id"]
    assert captured["document_key"] == "wiki/泰智汇.md"
    assert captured["metadata"] == {
        "source": "wiki/泰智汇.md",
        "source_type": "wiki",
        "wiki_title": "泰智汇",
    }
    assert captured["db"] is fake_db
