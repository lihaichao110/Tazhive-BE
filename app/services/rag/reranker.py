import math
import re

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.services.rag.retriever import RetrievedChunk

# 中文按单字、英文/数字按整词切分；按空格分词对中文查询完全失效（整句是一个 token）。
_TERM_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")
_RERANK_TIMEOUT_SECONDS = 10.0


def _terms(content: str) -> set[str]:
    return set(_TERM_PATTERN.findall(content.lower()))


def _rerank_by_overlap(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """使用关键词重叠与向量相似度重排，作为在线服务的降级路径。"""
    query_terms = _terms(query)
    for chunk in chunks:
        # 降级时清除可能残留的在线模型分数，避免日志误判本次排序来源。
        chunk.rerank_score = None
        chunk.overlap_score = len(query_terms & _terms(chunk.content))

    # 先按关键词重叠数量排序，重叠数量相同时保留向量相似度的区分能力。
    chunks.sort(key=lambda c: (c.overlap_score, c.similarity), reverse=True)
    return chunks


def _parse_rerank_results(payload: object, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """校验在线服务响应并将结果索引安全映射回原始分块。"""
    if not isinstance(payload, dict):
        raise ValueError("重排序响应不是对象")

    results = payload.get("results")
    if not isinstance(results, list) or len(results) != len(chunks):
        raise ValueError("重排序结果数量与候选数量不一致")

    reranked: list[RetrievedChunk] = []
    seen_indexes: set[int] = set()
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("重排序结果项不是对象")

        index = item.get("index")
        raw_score = item.get("relevance_score")
        if type(index) is not int or index < 0 or index >= len(chunks):
            raise ValueError("重排序结果包含非法索引")
        if index in seen_indexes or raw_score is None or isinstance(raw_score, bool):
            raise ValueError("重排序结果包含重复索引或非法分数")

        try:
            score = float(raw_score)
        except (TypeError, ValueError) as exc:
            raise ValueError("重排序结果包含非法分数") from exc
        if not math.isfinite(score):
            raise ValueError("重排序结果包含非有限分数")

        chunk = chunks[index]
        chunk.rerank_score = score
        reranked.append(chunk)
        seen_indexes.add(index)

    # 服务通常已按分数排序；本地再次排序可确保同分时用原向量相似度稳定决胜。
    reranked.sort(
        key=lambda chunk: (
            chunk.rerank_score if chunk.rerank_score is not None else float("-inf"),
            chunk.similarity,
        ),
        reverse=True,
    )
    return reranked


def rerank_chunks(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """调用在线模型重排候选分块，配置缺失或调用失败时降级到字面规则。"""
    if not chunks:
        return chunks

    model_name = settings.rerank_model_name
    base_url = settings.embed_base_url
    api_key = settings.embed_api_key
    if not model_name or not base_url or not api_key or not query:
        logger.warning("在线重排序配置不完整或查询为空，使用关键词规则降级")
        return _rerank_by_overlap(query, chunks)

    # 每次请求前清空旧分数，确保复用分块对象时不会携带上一次结果。
    for chunk in chunks:
        chunk.rerank_score = None

    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/rerank",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_name,
                "query": query,
                "documents": [chunk.content for chunk in chunks],
                "top_n": len(chunks),
                "return_documents": False,
            },
            timeout=_RERANK_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return _parse_rerank_results(response.json(), chunks)
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        # 不记录请求正文或密钥，只保留异常类型用于定位服务可用性问题。
        logger.warning("在线重排序失败，使用关键词规则降级：error_type=%s", type(exc).__name__)
        return _rerank_by_overlap(query, chunks)
