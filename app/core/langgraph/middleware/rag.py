from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.langgraph.prompts.system_chat import SYSTEM_CHAT_PROMPT
from app.core.logging import logger
from app.services.rag.embedder import get_embedder
from app.services.rag.reranker import rerank_chunks
from app.services.rag.retriever import retrieve_similar_chunks


class RagMiddleware(AgentMiddleware):
    """每次模型调用前执行 RAG 检索，并将检索结果注入 system message。

    迁移自原 rag_retrieve 节点，行为保持一致：取最后一条用户消息 →
    向量检索 top_k → 重排序 → 以“参考资料”形式拼接到系统提示词后。
    检索结果只在本中间件内使用，不再写入 agent state。
    """

    def __init__(self, top_k: int = 5):
        self.top_k = top_k

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        system_prompt = request.state.get("system_prompt") or SYSTEM_CHAT_PROMPT

        query = self._last_user_text(request.messages)
        findings = await self._retrieve(query) if query else []

        if findings:
            rag_context = "\n\n".join(findings)
            system_prompt = f"{system_prompt}\n\n参考资料：\n{rag_context}"

        return await handler(
            request.override(system_message=SystemMessage(content=system_prompt))
        )

    @staticmethod
    def _last_user_text(messages: list[Any]) -> str | None:
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                if not msg.content:
                    break
                return msg.content if isinstance(msg.content, str) else str(msg.content)
        logger.warning("没有找到用于检索 RAG 的用户消息")
        return None

    async def _retrieve(self, query: str) -> list[str]:
        logger.info(f"RAG 用户查询信息：{query}")
        embedder = get_embedder()
        query_embedding = await embedder.aembed_query(query)

        chunks = retrieve_similar_chunks(query_embedding, top_k=self.top_k)
        chunks = rerank_chunks(query, chunks)

        findings = [chunk.content for chunk in chunks]
        logger.info(f"RAG 检索 {len(findings)} chunks for query: {query[:50]}...")
        return findings
