"""Tavily 联网搜索工具及未配置密钥时的安全降级实现。"""

from langchain_core.tools import BaseTool, tool
from langchain_tavily import TavilySearch

from app.core.config import settings


class _TextOnlyTavilySearch(TavilySearch):
    """强制关闭图片结果，同时保留 Tavily 原生的动态筛选参数。"""

    def _run(self, query: str, **kwargs):  # type: ignore[override]
        # Tavily 原生实现允许调用时覆盖 include_images，这里统一改回 False。
        kwargs["include_images"] = False
        return super()._run(query, **kwargs)

    async def _arun(self, query: str, **kwargs):  # type: ignore[override]
        # 异步工具调用路径同样禁止图片，避免额外响应体积。
        kwargs["include_images"] = False
        return await super()._arun(query, **kwargs)


def build_tavily_search_tool(api_key: str | None) -> BaseTool:
    """按 API Key 构建搜索工具；缺少 Key 时保持服务可启动。"""
    normalized_key = api_key.strip() if api_key else ""
    if normalized_key:
        # 固定大响应相关参数，避免单次搜索产生过多上下文；筛选参数仍由模型按需传入。
        # tavily_api_key 由 TavilySearch.__init__ 显式消费（转成 api_wrapper），
        # 但 pydantic 模型字段未声明该参数，mypy 视为未知 kwarg。
        return _TextOnlyTavilySearch(
            max_results=5,
            include_answer=False,
            include_raw_content=False,
            include_images=False,
            tavily_api_key=normalized_key,
        )  # type: ignore[call-arg]

    @tool("tavily_search")
    def unavailable_tavily_search(query: str) -> str:
        """搜索互联网中的实时或外部信息。"""
        # 返回工具结果而非抛出异常，让 Agent 能向用户说明配置问题。
        return "联网搜索暂不可用：服务端尚未配置 TAVILY_API_KEY。请配置密钥并重启服务后再试。"

    return unavailable_tavily_search


# 工具在进程启动时构建；更新 .env 中的 Key 后需要重启服务。
tavily_search = build_tavily_search_tool(settings.tavily_api_key)
