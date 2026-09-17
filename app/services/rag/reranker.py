import re

from app.services.rag.retriever import RetrievedChunk

# 中文按单字、英文/数字按整词切分；按空格分词对中文查询完全失效（整句是一个 token）。
_TERM_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")


def _terms(content: str) -> set[str]:
    return set(_TERM_PATTERN.findall(content.lower()))


def rerank_chunks(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """
    根据查询与分块内容的关键词重叠程度进行简单重排序。
    可替换为更高级的重排序模型。
    """
    query_terms = _terms(query)
    for chunk in chunks:
        # 将重叠数量存储到分块载体上，用于排序
        chunk.overlap_score = len(query_terms & _terms(chunk.content))

    # 按 overlap_score 降序排序，若相同则按原相似度降序
    chunks.sort(key=lambda c: (c.overlap_score, c.similarity), reverse=True)
    return chunks
