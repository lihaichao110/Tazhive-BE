"""旧版单 Agent 入口的兼容封装。"""


async def get_chat_agent():
    """以旧 API 名称返回新的 supervisor 图。"""
    from app.core.langgraph.graph import get_supervisor_graph

    return await get_supervisor_graph()
