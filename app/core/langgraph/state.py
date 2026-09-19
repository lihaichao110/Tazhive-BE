from typing import Any, NotRequired

from langchain.agents import AgentState


class ChatAgentState(AgentState):
    """supervisor 图与各意图子 Agent 共用的状态定义。

    messages（含 add_messages 累积语义）由父类 AgentState 提供，
    会话记忆由 checkpointer 按 thread_id 维护。以下为请求级字段：
    """

    model: NotRequired[str]
    """请求指定的模型名称，经 LLMRegistry 解析"""

    temperature: NotRequired[float]
    """请求对应的模型温度；自定义 Agent 可覆盖全局默认值"""

    thinking: NotRequired[dict | None]
    """思考模式配置，透传给大模型（DeepSeek 的 {"type": "enabled"/"disabled"} 等）"""

    system_prompt: NotRequired[str]
    """基础系统提示词；各意图 Agent 在模型调用前按注册表拼接自身协议"""

    intent: NotRequired[str]
    """意图识别结果（intent_node 写入），supervisor 按它路由到对应的子 Agent 节点"""

    intent_confidence: NotRequired[float]
    """意图分类置信度（0~1），目前仅随 SSE 广播给前端，不做控制"""

    x_card: NotRequired[dict[str, Any] | None]
    """A2UI 卡片信封 {"surfaceId","commands"}，由 insurance 子图查库生成。

    只走「状态 → API 出口」：不写进 checkpoint 消息，避免几十 KB 命令 JSON
    在后续轮次被反复塞进模型上下文；由 chat.py 追加到正文围栏并随消息落库。
    单轮生命周期：intent_node 每轮开始先置 None，insurance 轮再写入新信封。
    """

    table_markdown: NotRequired[str | None]
    """data_query 子图生成的查询结果 Markdown 表格。

    与 x_card 同样只走「状态 → API 出口」：由 chat.py 在流结束后并入图表
    信封的 content 字段并整体重新序列化（前端要求单一合法 JSON 信封，
    表格不能追加在信封之外），随消息落库保证历史重放与流式输出同形。
    单轮生命周期：intent_node 每轮开始先置 None。
    """


class SearchAgentState(ChatAgentState):
    """搜索子图内部状态；父级 Supervisor 只接收双方共有的字段。"""

    search_plan: NotRequired[dict[str, Any]]
    """规划器生成的结构化 Tavily 查询参数。"""

    search_results: NotRequired[list[dict[str, str]]]
    """去重、截断后的搜索结果，仅供本轮回答模型使用。"""

    search_error: NotRequired[str | None]
    """搜索不可用或失败时提供给回答模型的安全错误说明。"""


class InsuranceAgentState(ChatAgentState):
    """insurance 子图内部状态；父级 Supervisor 只接收双方共有的字段。"""

    plan_filter: NotRequired[dict[str, Any] | None]
    """筛选条件提取节点产出的结构化条件（category / keywords）。"""

    plan_match: NotRequired[dict[str, Any] | None]
    """方案查询的命中信息（mode / matched_by / count / available_titles），
    供回答节点按「全量 / 已筛选 / 零命中」组织说明。"""


class DataQueryState(ChatAgentState):
    """数据查询（text2sql）子图内部状态；父级 Supervisor 只接收双方共有的字段。"""

    sql_draft: NotRequired[str | None]
    """生成器产出的 SQL 草稿；None 表示不可回答或生成失败。"""

    unanswerable_reason: NotRequired[str | None]
    """问题超出可查表范围或生成失败时的说明，非空时直接进入回答节点。"""

    sql_error: NotRequired[str | None]
    """最近一次校验/执行的错误说明，回喂给生成节点重试。"""

    sql_attempts: NotRequired[int]
    """本轮已生成 SQL 的次数（含首次）。"""

    query_columns: NotRequired[list[str] | None]
    """执行成功的结果列名，与每行单元格对齐。"""

    query_rows: NotRequired[list[list[Any]] | None]
    """执行成功的行数据（已 JSON 序列化），仅供本轮回答模型与表格卡片使用。"""

    query_truncated: NotRequired[bool]
    """实际行数超过上限被截断时为 True。"""
