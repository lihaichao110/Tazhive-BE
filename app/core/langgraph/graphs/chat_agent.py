from app.core.langgraph import AgentState
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from app.core.langgraph.nodes.llm_call import llm_call
from app.core.langgraph.checkpointer import get_async_checkpointer

# 缓存编译后的图
_agent = None

async def get_chat_agent():
    """构建简单的对话 Agent 图"""
    global _agent
    if _agent is None:
        # 获取异步 checkpointer
        checkpointer = await get_async_checkpointer()
        graph = StateGraph(AgentState)

        # 添加节点
        graph.add_node('llm', llm_call)

        # 添加边：开始 -> llm -> 结束
        graph.add_edge(START, 'llm')
        graph.add_edge('llm', END)

        # 编译图，并附加 checkpointer
        _agent = graph.compile(checkpointer=checkpointer)
    return _agent