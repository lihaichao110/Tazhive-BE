from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.core.logging import logger

def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "# ", "## ", "### ", "。", "；", "\n", " ", ""],
    )
    chunks = splitter.split_text(text)
    logger.info(f"切分数量：{len(chunks)} chunks")
    return chunks