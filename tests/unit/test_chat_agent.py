"""create_agent 端到端测试：工具调用循环 + checkpointer 记忆 + token 流。

使用脚本式 FakeChatModel（支持 bind_tools）避免真实模型调用。
"""

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
    message_chunk_to_message,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from app.core.langgraph.middleware import (
    MetricsMiddleware,
    ModelRoutingMiddleware,
    StreamingMiddleware,
)
from app.core.langgraph.state import ChatAgentState
from app.core.langgraph.tools import calculator, get_current_time


class ScriptedToolModel(BaseChatModel):
    """按脚本顺序返回预设消息的假模型，支持 bind_tools 与流式。

    流式时把文本拆成小块逐个 yield（模拟 token），带 tool_calls 的消息
    以 tool_call_chunks 形式 yield——与真实模型（ChatOpenAI/ChatDeepSeek）
    的 _astream 行为一致，且遵循 yield ChatGenerationChunk 的接口约定。
    """

    responses: list[BaseMessage] = []
    index: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._next()

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._next()

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        message = self._peek()
        self.index += 1
        text = message.content if isinstance(message.content, str) else ""
        for i in range(0, len(text), 2):
            yield ChatGenerationChunk(message=AIMessageChunk(content=text[i : i + 2]))
        for tc in message.tool_calls or []:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": tc["name"],
                            "args": str(tc["args"]).replace("'", '"'),
                            "id": tc["id"],
                            "index": 0,
                            "type": "tool_call_chunk",
                        }
                    ],
                )
            )

    def _peek(self) -> BaseMessage:
        return self.responses[min(self.index, len(self.responses) - 1)]

    def _next(self) -> ChatResult:
        message = self._peek()
        self.index += 1
        return ChatResult(generations=[ChatGeneration(message=message)])


class PassthroughRegistry:
    """始终返回预置模型的假注册表"""

    def __init__(self, model):
        self.model = model
        self.last_request = None

    def get_model(self, model_name=None, thinking=None):
        self.last_request = (model_name, thinking)
        return self.model


def _build_agent(model, middleware=None):
    if middleware is None:
        middleware = [
            MetricsMiddleware(),
            ModelRoutingMiddleware(registry=PassthroughRegistry(model)),
            StreamingMiddleware(),
        ]
    return create_agent(
        model,
        tools=[calculator, get_current_time],
        middleware=middleware,
        state_schema=ChatAgentState,
        checkpointer=InMemorySaver(),
    )


@pytest.mark.asyncio
async def test_tool_calling_loop_executes_calculator():
    model = ScriptedToolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "calculator",
                        "args": {"expression": "1+2"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="1+2 的结果是 3"),
        ]
    )
    agent = _build_agent(model)

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="帮我计算 1+2")], "model": "test-model"},
        config={"configurable": {"thread_id": "t-tool"}},
    )

    messages = result["messages"]
    tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1
    assert tool_messages[0].content == "3"
    assert messages[-1].content == "1+2 的结果是 3"


@pytest.mark.asyncio
async def test_checkpointer_memory_accumulates_across_turns():
    model = ScriptedToolModel(
        responses=[
            AIMessage(content="你好！"),
            AIMessage(content="你刚才说了你好"),
        ]
    )
    agent = _build_agent(model)
    config = {"configurable": {"thread_id": "t-memory"}}

    await agent.ainvoke({"messages": [HumanMessage(content="你好")]}, config=config)
    # 第二轮只发新消息（与 chat.py 的增量发送方式一致），历史由 checkpointer 补全
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="我刚才说了什么？")]}, config=config
    )

    messages = result["messages"]
    assert len(messages) == 4  # u1 + a1 + u2 + a2
    assert isinstance(messages[0], HumanMessage)
    assert messages[1].content == "你好！"
    assert messages[3].content == "你刚才说了你好"


@pytest.mark.asyncio
async def test_thread_ids_are_isolated():
    model = ScriptedToolModel(
        responses=[
            AIMessage(content="回复A"),
            AIMessage(content="回复B"),
        ]
    )
    agent = _build_agent(model)

    result_a = await agent.ainvoke(
        {"messages": [HumanMessage(content="问题1")]},
        config={"configurable": {"thread_id": "t-a"}},
    )
    result_b = await agent.ainvoke(
        {"messages": [HumanMessage(content="问题2")]},
        config={"configurable": {"thread_id": "t-b"}},
    )

    # 不同 thread 互不串扰：各自只有自己的 1 问 1 答
    assert len(result_a["messages"]) == 2
    assert len(result_b["messages"]) == 2
    assert result_a["messages"][-1].content == "回复A"
    assert result_b["messages"][-1].content == "回复B"


@pytest.mark.asyncio
async def test_custom_state_fields_reach_middleware():
    model = ScriptedToolModel(responses=[AIMessage(content="ok")])
    registry = PassthroughRegistry(model)

    agent = create_agent(
        model,
        tools=[],
        middleware=[
            MetricsMiddleware(),
            ModelRoutingMiddleware(registry=registry),
        ],
        state_schema=ChatAgentState,
        checkpointer=InMemorySaver(),
    )

    await agent.ainvoke(
        {
            "messages": [HumanMessage(content="hi")],
            "model": "deepseek-v4-flash",
            "thinking": {"type": "enabled"},
        },
        config={"configurable": {"thread_id": "t-state"}},
    )

    assert registry.last_request == ("deepseek-v4-flash", {"type": "enabled"})


@pytest.mark.asyncio
async def test_streaming_tokens_via_custom_stream():
    """token 级流式 + 完整消息双通道（chat.py SSE 的数据源）。

    create_agent（langchain 1.3）模型调用不透传 config，on_chat_model_stream
    事件断链；StreamingMiddleware 通过 stream_writer 把模型 chunk 转发到
    custom 流恢复 token 输出——这里固化该行为，防止依赖升级后悄悄破坏。
    """
    model = ScriptedToolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "calculator",
                        "args": {"expression": "2+3"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content='{"content":"答案是 5","charts":[]}',
            ),
        ]
    )
    agent = _build_agent(model)

    tokens = []
    final_chunk = None
    async for mode, payload in agent.astream(
        {"messages": [HumanMessage(content="算一下 2+3")]},
        config={"configurable": {"thread_id": "t-stream"}},
        stream_mode=["custom", "messages"],
    ):
        if mode == "custom":
            content = payload.content
            if isinstance(content, str) and content:
                tokens.append(content)
        else:
            chunk, meta = payload
            if isinstance(chunk, AIMessageChunk) and meta.get("langgraph_node") == "model":
                # 同一消息 ID 的 token chunk 需要累加；新 ID 表示工具调用后的新一轮回复。
                if final_chunk is not None and final_chunk.id == chunk.id:
                    final_chunk += chunk
                else:
                    final_chunk = chunk

    # token 级增量（工具调用轮的空 chunk 应被过滤）
    expected_response = '{"content":"答案是 5","charts":[]}'
    assert "".join(tokens) == expected_response
    # 完整消息含工具调用中间轮 + 最终回复，最后一条是最终回复
    assert final_chunk is not None
    final_message = message_chunk_to_message(final_chunk)
    assert final_message.content == expected_response
    assert not final_message.tool_calls
