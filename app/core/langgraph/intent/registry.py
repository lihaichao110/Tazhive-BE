"""意图注册表：意图 -> 处理配置的声明式映射。

每个意图一条 IntentSpec：分类描述与示例供分类器拼装 prompt，
协议片段由 supervisor 图的 intent_node 拼接到基础提示词后，
use_rag 决定该意图的子 Agent 是否挂载 RagMiddleware。

新增意图只需在 INTENT_SPECS 中加一条配置：图构建器（graph/supervisor.py）
会自动为它生成子 Agent 节点和路由表条目，分类器的 prompt 也会自动包含它。
"""

from dataclasses import dataclass, field

from langchain_core.tools import BaseTool

from app.core.langgraph.prompts.system_chat import (
    CHART_ANALYSIS_PROTOCOL_PROMPT,
    CHART_RESPONSE_PROTOCOL_PROMPT,
    INSURANCE_PROTOCOL_PROMPT,
    SEARCH_PROTOCOL_PROMPT,
)
from app.core.langgraph.tools import calculator, get_current_time, tavily_search

DEFAULT_INTENT_ID = "general"
"""兜底意图：分类失败、超时或未注册意图都路由到这里，保证主流程永不中断。"""


@dataclass(frozen=True)
class IntentSpec:
    """单个意图的处理配置。"""

    id: str
    """意图标识，同时作为 supervisor 图中的路由键（节点名 f"{id}_node"）"""

    description: str
    """意图含义描述，拼入分类器 prompt"""

    examples: list[str] = field(default_factory=list)
    """典型示例问句，作为分类器 few-shot，提高区分度"""

    protocol_prompt: str | None = None
    """响应协议片段；None 表示纯文本回复，不附加协议"""

    use_rag: bool = False
    """是否为该意图的子 Agent 挂载 RagMiddleware（检索知识库）"""

    tools: list[BaseTool] | None = None
    """子 Agent 的工具集；None 使用默认工具集（app.core.langgraph.tools.tools）"""


INTENT_SPECS: dict[str, IntentSpec] = {
    spec.id: spec
    for spec in [
        IntentSpec(
            id="chitchat",
            description="闲聊、问候、寒暄，或与业务无关的日常对话",
            examples=["你好", "你是谁呀", "今天心情不太好，聊两句"],
            protocol_prompt=None,
            use_rag=False,
        ),
        IntentSpec(
            id="general",
            description="通用问答与业务知识咨询：用户想获得解答、说明、介绍等，不明确属于其他意图时也归入此类",
            examples=[
                "公司的报销流程是什么",
                "介绍一下你们公司",
                "DeepSeek 和 GPT 有什么区别",
            ],
            protocol_prompt=CHART_RESPONSE_PROTOCOL_PROMPT,
            use_rag=True,
        ),
        IntentSpec(
            id="search",
            description="联网搜索与实时信息查询：用户明确要求搜索、查找网络资料，或询问新闻、最新动态、实时数据、当前行情等时效性内容",
            examples=[
                "帮我搜索一下今天的人工智能新闻",
                "查一下这家公司最近有什么新动态",
                "现在黄金的市场行情怎么样",
                "请联网核实这个说法是否准确",
            ],
            protocol_prompt=SEARCH_PROTOCOL_PROMPT,
            use_rag=False,
            tools=[tavily_search, get_current_time, calculator],
        ),
        IntentSpec(
            id="chart_analysis",
            description="图表分析：用户提供了数据，希望做可视化、统计分析、趋势解读",
            examples=[
                "把这几个月的销售额画个柱状图",
                "帮我分析一下这组数据的占比，用饼图展示",
                "各季度利润变化趋势画条折线",
            ],
            protocol_prompt=CHART_ANALYSIS_PROTOCOL_PROMPT,
            use_rag=False,
        ),
        IntentSpec(
            id="insurance",
            description="买保险、投保咨询：想了解保险产品、保费、保障方案或办理投保",
            examples=[
                "我想给父母买份医疗险，有什么推荐",
                "重疾险一年大概多少钱",
                "帮我设计一份家庭保险方案",
                "你们现在有哪些保险产品在售",
            ],
            protocol_prompt=INSURANCE_PROTOCOL_PROMPT,
            use_rag=False,
        ),
    ]
}


def get_intent_spec(intent_id: str | None) -> IntentSpec:
    """按 id 取意图配置；未注册的 id 一律兜底到 DEFAULT_INTENT_ID。"""
    if isinstance(intent_id, str) and intent_id in INTENT_SPECS:
        return INTENT_SPECS[intent_id]
    return INTENT_SPECS[DEFAULT_INTENT_ID]


def iterate_intent_specs() -> list[IntentSpec]:
    """按注册顺序返回全部意图配置（supervisor 图按此顺序建节点）。"""
    return list(INTENT_SPECS.values())
