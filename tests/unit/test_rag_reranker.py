from unittest.mock import Mock, patch

import httpx
import pytest

from app.core.config import settings
from app.services.rag.reranker import rerank_chunks
from app.services.rag.retriever import RetrievedChunk


@pytest.fixture(autouse=True)
def disable_online_reranker(monkeypatch):
    """默认关闭在线服务，使原有排序用例稳定覆盖降级逻辑。"""
    monkeypatch.setattr(settings, "rerank_model_name", None)


def _enable_online_reranker(monkeypatch):
    monkeypatch.setattr(settings, "rerank_model_name", "BAAI/bge-reranker-v2-m3")
    monkeypatch.setattr(settings, "embed_base_url", "https://api.example.com/v1/")
    monkeypatch.setattr(settings, "embed_api_key", "test-api-key")


def _response(payload: object) -> httpx.Response:
    request = httpx.Request("POST", "https://api.example.com/v1/rerank")
    return httpx.Response(200, json=payload, request=request)


def test_rerank_uses_online_scores_and_expected_request(monkeypatch):
    _enable_online_reranker(monkeypatch)
    chunks = [
        RetrievedChunk(content="向量分数较高", similarity=0.8),
        RetrievedChunk(content="重排模型认为更相关", similarity=0.5),
        RetrievedChunk(content="重排同分但向量更高", similarity=0.7),
    ]
    post_mock = Mock(
        return_value=_response(
            {
                "results": [
                    {"index": 0, "relevance_score": 0.2},
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 2, "relevance_score": 0.9},
                ]
            }
        )
    )

    with patch("app.services.rag.reranker.httpx.post", post_mock):
        reranked = rerank_chunks("哪个结果最相关", chunks)

    # 重排分数相同时使用原向量相似度作为稳定的次级排序依据。
    assert [chunk.content for chunk in reranked] == [
        "重排同分但向量更高",
        "重排模型认为更相关",
        "向量分数较高",
    ]
    assert [chunk.rerank_score for chunk in reranked] == [0.9, 0.9, 0.2]

    post_mock.assert_called_once()
    call = post_mock.call_args
    assert call.args == ("https://api.example.com/v1/rerank",)
    assert call.kwargs["headers"] == {
        "Authorization": "Bearer test-api-key",
        "Content-Type": "application/json",
    }
    assert call.kwargs["json"] == {
        "model": "BAAI/bge-reranker-v2-m3",
        "query": "哪个结果最相关",
        "documents": ["向量分数较高", "重排模型认为更相关", "重排同分但向量更高"],
        "top_n": 3,
        "return_documents": False,
    }
    assert call.kwargs["timeout"] == 10.0


def test_rerank_returns_empty_list_without_online_request(monkeypatch):
    _enable_online_reranker(monkeypatch)

    with patch("app.services.rag.reranker.httpx.post") as post_mock:
        assert rerank_chunks("查询", []) == []

    post_mock.assert_not_called()


def test_rerank_falls_back_when_online_request_fails(monkeypatch):
    _enable_online_reranker(monkeypatch)
    chunks = [
        RetrievedChunk(content="无关内容", similarity=0.8, rerank_score=0.7),
        RetrievedChunk(content="李海超的资料", similarity=0.5, rerank_score=0.2),
    ]
    error = httpx.ConnectTimeout(
        "rerank timeout",
        request=httpx.Request("POST", "https://api.example.com/v1/rerank"),
    )

    with patch("app.services.rag.reranker.httpx.post", side_effect=error):
        reranked = rerank_chunks("李海超", chunks)

    assert reranked[0].content == "李海超的资料"
    assert all(chunk.rerank_score is None for chunk in reranked)


@pytest.mark.parametrize(
    "response",
    [
        # 非 JSON 响应、缺失结果、结果数量不符以及越界索引都必须整体降级。
        httpx.Response(
            200,
            content=b"not-json",
            request=httpx.Request("POST", "https://api.example.com/v1/rerank"),
        ),
        _response({}),
        _response({"results": [{"index": 0, "relevance_score": 0.5}]}),
        _response(
            {
                "results": [
                    {"relevance_score": 0.5},
                    {"index": 1, "relevance_score": 0.4},
                ]
            }
        ),
        _response(
            {
                "results": [
                    {"index": 0, "relevance_score": 0.5},
                    {"index": 3, "relevance_score": 0.4},
                ]
            }
        ),
    ],
)
def test_rerank_falls_back_for_invalid_response(monkeypatch, response):
    _enable_online_reranker(monkeypatch)
    chunks = [
        RetrievedChunk(content="低相似度但命中 1016", similarity=0.4),
        RetrievedChunk(content="高相似度无匹配", similarity=0.8),
    ]

    with patch("app.services.rag.reranker.httpx.post", return_value=response):
        reranked = rerank_chunks("查询 1016", chunks)

    assert reranked[0].content == "低相似度但命中 1016"
    assert all(chunk.rerank_score is None for chunk in reranked)


def test_rerank_falls_back_for_http_error(monkeypatch):
    _enable_online_reranker(monkeypatch)
    request = httpx.Request("POST", "https://api.example.com/v1/rerank")
    response = httpx.Response(503, request=request)
    chunks = [
        RetrievedChunk(content="分机号 1016", similarity=0.4),
        RetrievedChunk(content="分机号 2238", similarity=0.8),
    ]

    with patch("app.services.rag.reranker.httpx.post", return_value=response):
        reranked = rerank_chunks("1016", chunks)

    assert reranked[0].content == "分机号 1016"


def test_rerank_puts_chunk_with_queried_name_first_for_chinese_query():
    """中文查询按字面重叠降级：含人名的 chunk 应排到更高相似度结果之前。"""
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
