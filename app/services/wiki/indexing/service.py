from pathlib import Path

from sqlmodel import Session

from app.services.rag.pipeline import ingest_document


def index_wiki_pages(
    page_paths: list[Path],
    *,
    vault_dir: Path,
    db: Session,
) -> list[str]:
    """将生成的 Wiki 页面幂等写入现有 RAG 向量库。"""
    vault_root = vault_dir.resolve()
    document_ids: list[str] = []
    for page_path in page_paths:
        resolved_page = page_path.resolve()
        if not resolved_page.is_relative_to(vault_root):
            raise ValueError(f"Wiki 页面不在 vault 目录中: {page_path}")
        relative_path = resolved_page.relative_to(vault_root).as_posix()
        document_key = f"wiki/{relative_path}"
        document_ids.append(
            ingest_document(
                file_path=str(resolved_page),
                filename=resolved_page.name,
                db=db,
                document_key=document_key,
                metadata={
                    "source": document_key,
                    "source_type": "wiki",
                    "wiki_title": resolved_page.stem,
                },
            )
        )
    return document_ids
