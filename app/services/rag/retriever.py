import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlmodel import Session

from app.core.logging import logger
from app.services.database import engine


@dataclass
class RetrievedChunk:
    """检索结果载体：携带分块内容及各阶段评分，避免给 ORM 模型附加临时属性。"""

    content: str
    similarity: float = 0.0
    overlap_score: int = 0
    rerank_score: float | None = None
    document_id: str | None = None
    chunk_index: int | None = None
    id: str | None = None
    meta_data: dict[str, Any] | None = None


# 连续中文（≥2 字）与英文/数字（≥3 字符）片段作为字面检索的关键词候选。
_CJK_RUN_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}")
_WORD_RUN_PATTERN = re.compile(r"[a-zA-Z0-9]{3,}")
# 口语包裹词：先剥掉前缀/后缀，再按连接词拆分，剩余片段才作为关键词。
_STRIP_PREFIXES = sorted(
    (
        "请问你知道",
        "那你知道",
        "你知道吗",
        "帮我查一下",
        "帮我查",
        "查一下",
        "查查",
        "查找",
        "搜索",
        "查询",
        "我想查",
        "请问",
        "你知道",
        "我想",
        "我要",
        "帮我",
        "麻烦",
    ),
    key=len,
    reverse=True,
)
_STRIP_SUFFIXES = sorted(
    (
        "相关信息",
        "的信息",
        "是干什么的",
        "干什么的",
        "是谁",
        "怎么样",
        "如何",
        "一下",
        "吗",
        "呢",
        "啊",
        "吧",
        "么",
        "的",
    ),
    key=len,
    reverse=True,
)
_PARTICLE_SPLIT_PATTERN = re.compile(r"[的了呢和与及跟同或者还有以及]+")


def extract_query_keywords(query: str) -> list[str]:
    """从查询中抽取用于字面召回的关键词。

    启发式规则：抽取连续中文/英文数字片段，剥掉常见口语包裹词、按连接词
    拆分，如“那你知道信息技术部的李海超么”→[“信息技术部”, “李海超”]。
    抽不出关键词时返回空列表，调用方退化为纯向量检索。
    """
    keywords: list[str] = []
    for run in _CJK_RUN_PATTERN.findall(query) + _WORD_RUN_PATTERN.findall(query):
        for prefix in _STRIP_PREFIXES:
            if run.startswith(prefix) and len(run) > len(prefix):
                run = run[len(prefix) :]
                break
        for suffix in _STRIP_SUFFIXES:
            if run.endswith(suffix) and len(run) > len(suffix):
                run = run[: -len(suffix)]
                break
        for part in _PARTICLE_SPLIT_PATTERN.split(run):
            if len(part) >= 2 and part not in keywords:
                keywords.append(part)
    return keywords


def select_final_chunks(
    chunks: list[RetrievedChunk],
    lexical_ids: set[str],
    top_k: int,
    score_threshold: float | None = None,
) -> list[RetrievedChunk]:
    """从重排后的候选池选择最终结果。

    字面命中的记录精确包含查询关键词，不受相似度阈值约束；
    纯向量候选需达到阈值，宁缺毋滥。
    """
    final: list[RetrievedChunk] = []
    for chunk in chunks:
        if len(final) >= top_k:
            break
        if chunk.id is not None and chunk.id in lexical_ids:
            final.append(chunk)
        elif score_threshold is None or chunk.similarity >= score_threshold:
            final.append(chunk)
    return final


def _row_to_chunk(row: Any) -> RetrievedChunk:
    return RetrievedChunk(
        content=row.content,
        similarity=float(row.similarity),
        document_id=row.document_id,
        chunk_index=row.chunk_index,
        id=row.id,
        meta_data=row.meta_data,
    )


def retrieve_similar_chunks(
    query: str,
    query_embedding: list[float],
    top_k: int = 5,
    recall_k: int = 30,
    lexical_limit: int = 10,
    score_threshold: float | None = None,
    session: Session | None = None,
) -> list[RetrievedChunk]:
    """
    混合检索：向量召回 + 关键词字面召回，合并去重后交给在线模型重排。
    纯向量检索对“按人名/编号查记录”类查询区分度不足（模板化记录的相似度
    高度聚簇），字面命中作为确定性补充。
    参数：
        query: 用户查询原文（用于关键词抽取与重排）
        query_embedding: 查询向量
        top_k: 最终返回数量
        recall_k: 向量召回的候选池大小（重排在其上进行）
        lexical_limit: 字面召回的单路上限
        session: 可选的 SQLModel Session（若未提供，则创建新的）
        score_threshold: 纯向量候选的相似度下限，低于该分数的结果被过滤；
            None 或非正数表示不过滤。字面命中的记录不受该阈值约束。
    返回：
        RetrievedChunk 对象列表（在线模型不可用时按字面重叠与相似度降级），最多 top_k 条
    """
    own_session = False
    if session is None:
        session = Session(engine)
        own_session = True

    if score_threshold is not None and score_threshold <= 0:
        score_threshold = None

    try:
        # reranker 依赖本模块的 RetrievedChunk，顶层互相导入会成环，这里延迟导入。
        from app.services.rag.reranker import rerank_chunks

        # 将向量列表转换为 PostgreSQL vector 可接受的字符串格式
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # 使用原生 SQL 执行向量检索（pgvector 支持 <=> 表示余弦距离）
        vector_sql = text("""
            SELECT id, document_id, chunk_index, content, meta_data,
                   1 - (embedding <=> (:embedding)::vector) AS similarity
            FROM document_chunks
            ORDER BY embedding <=> (:embedding)::vector
            LIMIT :recall_k
        """)
        # 原生 SQL（text）需走 execute，SQLModel 的 exec 只接受 Select/Update。
        vector_rows = session.execute(
            vector_sql, params={"embedding": embedding_str, "recall_k": recall_k}
        ).all()
        logger.info(f"向量库结果：{vector_rows}")

        keywords = extract_query_keywords(query)
        lexical_rows: Sequence[Row[Any]] = []
        if keywords:
            patterns = [f"%{keyword}%" for keyword in keywords]
            lexical_sql = text("""
                SELECT id, document_id, chunk_index, content, meta_data,
                       1 - (embedding <=> (:embedding)::vector) AS similarity
                FROM document_chunks
                WHERE content ILIKE ANY (:patterns)
                ORDER BY embedding <=> (:embedding)::vector
                LIMIT :lexical_limit
            """)
            lexical_rows = session.execute(
                lexical_sql,
                params={
                    "embedding": embedding_str,
                    "patterns": patterns,
                    "lexical_limit": lexical_limit,
                },
            ).all()
            logger.info(f"字面召回关键词 {keywords} 命中 {len(lexical_rows)} 条")

        # 合并两路结果：字面命中优先登记，向量结果按 id 去重补充。
        chunks_by_id: dict[str, RetrievedChunk] = {}
        lexical_ids: set[str] = set()
        for row in lexical_rows:
            chunk = _row_to_chunk(row)
            # 数据库主键理论上非空；显式收窄类型也可避免异常数据参与去重。
            if chunk.id is None:
                continue
            chunks_by_id[chunk.id] = chunk
            lexical_ids.add(chunk.id)
        for row in vector_rows:
            chunk = _row_to_chunk(row)
            if chunk.id is None:
                continue
            if chunk.id not in chunks_by_id:
                chunks_by_id[chunk.id] = chunk

        merged = rerank_chunks(query, list(chunks_by_id.values()))
        final = select_final_chunks(merged, lexical_ids, top_k, score_threshold)
        logger.info(
            f"混合检索：向量 {len(vector_rows)} 条 / 字面 {len(lexical_rows)} 条，"
            f"重排后保留 {len(final)} 条："
            + "; ".join(
                f"[{'字面' if chunk.id in lexical_ids else '向量'} "
                f"rerank={chunk.rerank_score if chunk.rerank_score is not None else 'fallback'} "
                f"overlap={chunk.overlap_score} sim={chunk.similarity:.4f}] {chunk.content[:40]}"
                for chunk in final
            )
        )
        return final
    finally:
        if own_session:
            session.close()
