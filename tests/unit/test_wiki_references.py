from app.services.rag.retriever import RetrievedChunk
from app.services.references import build_rag_references


def test_wiki_chunk_builds_wiki_reference():
    references = build_rag_references(
        [
            RetrievedChunk(
                content="泰智汇基于 FastAPI 和 LangGraph。",
                document_id="doc-1",
                chunk_index=0,
                meta_data={
                    "source": "wiki/泰智汇.md",
                    "source_type": "wiki",
                    "wiki_title": "泰智汇",
                },
            )
        ]
    )

    assert references == [
        {
            "source_type": "wiki",
            "title": "泰智汇",
            "url": "/api/v1/documents/doc-1/chunks/0",
            "snippet": "泰智汇基于 FastAPI 和 LangGraph。",
            "document_id": "doc-1",
            "chunk_index": 0,
        }
    ]
