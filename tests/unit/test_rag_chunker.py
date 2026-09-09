from app.services.rag.chunker import chunk_text

def test_chunk_text_basic():
    text = "This is a test document. " * 100
    chunks = chunk_text(text, chunk_size=100, chunk_overlap=20)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) > 0