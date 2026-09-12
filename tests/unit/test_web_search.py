"""Tavily 搜索工具的配置与无密钥降级测试。"""

from langchain_tavily import TavilySearch

from app.core.langgraph.tools.web_search import build_tavily_search_tool


def test_build_tavily_search_tool_with_key():
    """有密钥时使用官方工具，并锁定影响响应体积的参数。"""
    search = build_tavily_search_tool(" test-tavily-key ")

    assert isinstance(search, TavilySearch)
    assert search.max_results == 5
    assert search.include_answer is False
    assert search.include_raw_content is False
    assert search.include_images is False
    # topic、时间和域名筛选等参数应继续暴露给模型按请求设置。
    schema_properties = search.args_schema.model_json_schema()["properties"]
    assert {"topic", "time_range", "include_domains", "exclude_domains"} <= set(
        schema_properties
    )


def test_tavily_search_invocation_returns_mocked_sources(monkeypatch):
    """通过 LangChain 工具调用入口验证查询参数和来源结果可以完整传递。"""
    search = build_tavily_search_tool("test-tavily-key")
    calls = []

    def fake_raw_results(_wrapper, **kwargs):
        calls.append(kwargs)
        return {
            "query": kwargs["query"],
            "results": [
                {
                    "title": "示例来源",
                    "url": "https://example.com/news",
                    "content": "示例搜索摘要",
                    "score": 0.99,
                }
            ],
            "response_time": 0.01,
        }

    # API wrapper 是 Pydantic 模型，实例方法不可直接赋值，因此在类型上替换网络入口。
    monkeypatch.setattr(type(search.api_wrapper), "raw_results", fake_raw_results)

    result = search.invoke(
        {
            "query": "今天的人工智能新闻",
            "topic": "news",
            "time_range": "day",
            # 即使模型请求图片，项目包装层也必须强制关闭。
            "include_images": True,
        }
    )

    assert result["results"][0]["url"] == "https://example.com/news"
    assert calls[0]["query"] == "今天的人工智能新闻"
    assert calls[0]["topic"] == "news"
    assert calls[0]["time_range"] == "day"
    assert calls[0]["max_results"] == 5
    assert calls[0]["include_images"] is False


def test_build_tavily_search_tool_without_key_returns_configuration_message():
    """空密钥不应创建 keyless 客户端或阻止应用启动。"""
    search = build_tavily_search_tool("  ")

    assert search.name == "tavily_search"
    result = search.invoke({"query": "今天有什么新闻"})
    assert "TAVILY_API_KEY" in result
    assert "重启服务" in result
