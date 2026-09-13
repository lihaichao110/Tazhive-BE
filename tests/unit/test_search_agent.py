"""确定性搜索子图测试：强制执行、降级、结果约束与历史隔离。"""

import json

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import StructuredTool

from app.core.langgraph.agents.search import (
    MAX_RESULT_CONTENT_CHARS,
    SearchPlan,
    SearchQuery,
    build_search_agent,
)
from app.core.langgraph.intent.registry import get_intent_spec


class FakePlanner:
    def __init__(self, plan=None, error=None):
        self.plan = plan
        self.error = error
        self.messages = None

    async def aplan(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        return self.plan


class CaptureModel(BaseChatModel):
    """记录回答模型实际收到的消息，并提供可流式聚合的固定回答。"""

    content: str
    captured: list = []

    @property
    def _llm_type(self) -> str:
        return "search-capture-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.captured.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.content))])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop, run_manager, **kwargs)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        self.captured.append(list(messages))
        yield ChatGenerationChunk(message=AIMessageChunk(content=self.content))


class CaptureRegistry:
    def __init__(self, model):
        self.model = model
        self.calls = []

    def get_model(self, model_name=None, thinking=None):
        self.calls.append((model_name, thinking))
        return self.model

    def rotate(self):
        pass


def make_search_tool(handler):
    async def search(
        query: str,
        topic: str = "general",
        search_depth: str = "basic",
        time_range: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ):
        params = {
            "query": query,
            "topic": topic,
            "search_depth": search_depth,
            "time_range": time_range,
            "start_date": start_date,
            "end_date": end_date,
            "include_domains": include_domains,
            "exclude_domains": exclude_domains,
        }
        return await handler(**{key: value for key, value in params.items() if value is not None})

    return StructuredTool.from_function(
        coroutine=search,
        name="tavily_search",
        description="搜索互联网中的实时信息。",
    )


@pytest.mark.asyncio
async def test_search_pipeline_forces_tavily_and_isolates_old_assistant_history():
    calls = []

    async def handler(**kwargs):
        calls.append(kwargs)
        suffix = len(calls)
        return {
            "results": [
                {
                    "title": f"来源{suffix}",
                    "url": f"https://example.com/{suffix}",
                    "content": "可信的搜索摘要",
                }
            ]
        }

    planner = FakePlanner(
        SearchPlan(
            queries=[
                SearchQuery(query="AI 今日新闻", topic="news", time_range="day"),
                SearchQuery(
                    query="AI company announcements",
                    include_domains=["openai.com"],
                    search_depth="advanced",
                ),
            ]
        )
    )
    answer = CaptureModel(
        content=json.dumps(
            {"content": "结果见[来源](https://example.com/1)", "charts": []},
            ensure_ascii=False,
        )
    )
    registry = CaptureRegistry(answer)
    graph = build_search_agent(
        get_intent_spec("search"),
        planner=planner,
        search_tool=make_search_tool(handler),
        answer_model=answer,
        registry=registry,
    )

    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(content="今天有什么新闻"),
                AIMessage(content="我没有联网能力，只能使用计算器。"),
                HumanMessage(content="今日 AI 圈有什么大新闻？"),
            ],
            "thinking": {"type": "enabled"},
        }
    )

    assert len(calls) == 2
    assert calls[0]["topic"] == "news"
    assert calls[0]["time_range"] == "day"
    assert calls[1]["include_domains"] == ["openai.com"]
    assert calls[1]["search_depth"] == "advanced"
    assert result["search_error"] is None
    assert len(result["search_results"]) == 2
    assert "https://example.com/1" in result["messages"][-1].content
    # 回答模型保留当前问题，但看不到旧 Assistant 的错误能力声明。
    captured_text = "\n".join(str(message.content) for message in answer.captured[-1])
    assert "今日 AI 圈有什么大新闻" in captured_text
    assert "我没有联网能力" not in captured_text
    assert "<search_results>" in captured_text
    # 用户选择的 thinking 只进入回答模型；搜索执行不依赖 tool_choice。
    assert registry.calls[-1] == (None, {"type": "enabled"})


@pytest.mark.asyncio
async def test_planner_failure_falls_back_to_latest_question():
    calls = []

    async def handler(**kwargs):
        calls.append(kwargs)
        return {"results": []}

    answer = CaptureModel(content='{"content":"没有找到结果","charts":[]}')
    registry = CaptureRegistry(answer)
    graph = build_search_agent(
        get_intent_spec("search"),
        planner=FakePlanner(error=TimeoutError()),
        search_tool=make_search_tool(handler),
        answer_model=answer,
        registry=registry,
    )

    result = await graph.ainvoke({"messages": [HumanMessage(content="请搜索最新的 Python 新闻")]})

    assert len(calls) == 1
    assert calls[0]["query"] == "请搜索最新的 Python 新闻"
    assert result["search_results"] == []
    assert "没有搜索到足够的信息" in result["search_error"]


@pytest.mark.asyncio
async def test_search_results_are_interleaved_deduplicated_and_limited():
    async def handler(**kwargs):
        prefix = "a" if kwargs["query"] == "query-a" else "b"
        urls = ["shared", f"{prefix}-1", f"{prefix}-2", f"{prefix}-3"]
        return {
            "results": [
                {
                    "title": url,
                    "url": f"https://example.com/{url}",
                    "content": "x" * (MAX_RESULT_CONTENT_CHARS + 100),
                }
                for url in urls
            ]
        }

    answer = CaptureModel(content='{"content":"完成","charts":[]}')
    graph = build_search_agent(
        get_intent_spec("search"),
        planner=FakePlanner(
            SearchPlan(queries=[SearchQuery(query="query-a"), SearchQuery(query="query-b")])
        ),
        search_tool=make_search_tool(handler),
        answer_model=answer,
        registry=CaptureRegistry(answer),
    )

    result = await graph.ainvoke({"messages": [HumanMessage(content="搜索测试")]})

    assert len(result["search_results"]) == 5
    assert len({item["url"] for item in result["search_results"]}) == 5
    assert {"https://example.com/a-1", "https://example.com/b-1"} <= {
        item["url"] for item in result["search_results"]
    }
    assert all(
        len(item["content"]) <= MAX_RESULT_CONTENT_CHARS for item in result["search_results"]
    )


@pytest.mark.asyncio
async def test_missing_key_message_becomes_safe_search_error():
    async def handler(**kwargs):
        return "联网搜索暂不可用：服务端尚未配置 TAVILY_API_KEY。"

    answer = CaptureModel(content='{"content":"搜索未配置","charts":[]}')
    graph = build_search_agent(
        get_intent_spec("search"),
        planner=FakePlanner(SearchPlan(queries=[SearchQuery(query="今日新闻")])),
        search_tool=make_search_tool(handler),
        answer_model=answer,
        registry=CaptureRegistry(answer),
    )

    result = await graph.ainvoke({"messages": [HumanMessage(content="今日新闻")]})

    assert result["search_results"] == []
    assert "TAVILY_API_KEY" in result["search_error"]
    system_text = "\n".join(str(message.content) for message in answer.captured[-1])
    assert "不要依据记忆补写实时事实" in system_text


@pytest.mark.asyncio
async def test_search_answer_tokens_bubble_through_nested_subgraph():
    """搜索前两步保持静默，最终回答 token 继续通过 custom 流冒泡给 SSE。"""

    async def handler(**kwargs):
        return {
            "results": [
                {
                    "title": "来源",
                    "url": "https://example.com/source",
                    "content": "摘要",
                }
            ]
        }

    expected = '{"content":"[来源](https://example.com/source)","charts":[]}'
    answer = CaptureModel(content=expected)
    graph = build_search_agent(
        get_intent_spec("search"),
        planner=FakePlanner(SearchPlan(queries=[SearchQuery(query="测试")])),
        search_tool=make_search_tool(handler),
        answer_model=answer,
        registry=CaptureRegistry(answer),
    )

    token_text = ""
    model_nodes = set()
    async for _namespace, mode, payload in graph.astream(
        {"messages": [HumanMessage(content="搜索测试")]},
        stream_mode=["custom", "messages"],
        subgraphs=True,
    ):
        if mode == "custom":
            token_text += payload.content if isinstance(payload.content, str) else ""
        else:
            _chunk, metadata = payload
            model_nodes.add(str(metadata.get("langgraph_node") or ""))

    assert token_text == expected
    assert "model" in model_nodes
