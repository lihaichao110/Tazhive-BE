from langchain_core.messages import HumanMessage
from app.core.langgraph.state import AgentState
from app.services.rag.embedder import get_embedder
from app.services.rag.retriever import retrieve_similar_chunks
from app.services.rag.reranker import rerank_chunks
from app.core.logging import logger

async def rag_retrieve(state: AgentState) -> dict:
    """
    RAG 检索节点：
    - 从状态中提取最新的用户消息
    - 生成查询嵌入
    - 检索相似文档分块并重排序
    - 将检索到的文本片段存入 findings（或 document_ids），并返回状态更新
    """
    # 获取最后一条用户消息
    user_message = None
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            user_message = msg
            break

    if not user_message or not user_message.content:
        logger.warning("没有找到用于检索 RAG 的用户消息")
        return {"findings": []}

    query = user_message.content
    logger.info(f'RAG 用户查询信息：{query}')
    # 生成查询嵌入
    embedder = get_embedder()
    logger.info('向量开始')
    query_embedding = await embedder.aembed_query(query)

    # 检索（top 5）
    chunks = retrieve_similar_chunks(query_embedding, top_k=5)
    logger.info(f'RAG 检索结果：{chunks}')

    # 重排序
    chunks = rerank_chunks(query, chunks)

    # 提取文本片段
    findings = [chunk.content for chunk in chunks]
    logger.info(f"RAG 检索 {len(findings)} chunks for query: {query[:50]}...")

    return {"findings": findings}