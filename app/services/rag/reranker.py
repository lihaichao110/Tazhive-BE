from typing import List
from app.services.rag.retriever import RetrievedChunk

def rerank_chunks(query: str, chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
    """
    根据查询与分块内容的关键词重叠程度进行简单重排序。
    可替换为更高级的重排序模型。
    """
    query_terms = set(query.lower().split())
    for chunk in chunks:
        content_terms = set(chunk.content.lower().split())
        overlap = len(query_terms & content_terms)
        # 将重叠数量存储到分块载体上，用于排序
        chunk.overlap_score = overlap

    # 按 overlap_score 降序排序，若相同则按原相似度降序
    chunks.sort(key=lambda c: (c.overlap_score, c.similarity), reverse=True)
    return chunks