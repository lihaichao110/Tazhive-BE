from app.services.rag.reranker import rerank_chunks
from app.services.rag.retriever import RetrievedChunk


def test_rerank_puts_chunk_with_queried_name_first_for_chinese_query():
    """中文查询按字面重叠重排：含人名的 chunk 应排到相似度更高但无关的 chunk 之前。"""
    chunks = [
        RetrievedChunk(content="；预委；声誉风险", similarity=0.58),
        RetrievedChunk(
            content="【工作表: 人员信息表】单位名称: 应用开发一处；员工姓名: 李海超；负责业务: 开发一组",
            similarity=0.52,
        ),
    ]

    reranked = rerank_chunks("你知道李海超么", chunks)

    assert "李海超" in reranked[0].content
    assert reranked[0].overlap_score > reranked[1].overlap_score


def test_rerank_keeps_similarity_order_when_no_overlap():
    chunks = [
        RetrievedChunk(content="完全无关的内容甲", similarity=0.5),
        RetrievedChunk(content="完全无关的内容乙", similarity=0.6),
    ]

    reranked = rerank_chunks("换个话题", chunks)

    assert reranked[0].similarity == 0.6
    assert all(chunk.overlap_score == 0 for chunk in reranked)


def test_rerank_matches_english_words_and_numbers():
    chunks = [
        RetrievedChunk(content="分机号: 1016；姓名: 刘琬琪", similarity=0.4),
        RetrievedChunk(content="分机号: 2238；邮箱: zhangmeihong@cathaylife.cn", similarity=0.55),
    ]

    reranked = rerank_chunks("查询分机号 1016", chunks)

    assert "刘琬琪" in reranked[0].content
