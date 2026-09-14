# LLM 服务设计

## 概述

LLM 服务负责管理与大语言模型的交互，支持多提供商、多模型、自动容灾和令牌统计。当前实现以 OpenAI 兼容 API 为主，可扩展支持 Anthropic、通义千问等。Agent 主体由 `langchain.agents.create_agent` 构建，模型统一经 `init_chat_model` 创建。

## 组件

### LLMRegistry (`app/services/llm/registry.py`)

- 维护一个模型名称列表。
- 提供 `get_model(model_name=None, thinking=None)` 方法，返回模型实例。
  - `thinking` 为思考模式配置（DeepSeek 的 `{"type": "enabled"/"disabled"}` 等），
    经构造参数 `extra_body={"thinking": ...}` 透传给模型。
- 支持轮询（`rotate()`），用于故障切换。
- 模型实例缓存（按 model_name + thinking 组合键），避免重复创建实例。

### Supervisor 与意图 Agent 工厂

- `graph/supervisor.py` 用手写 `StateGraph` 建立显式路由：`intent_node` 分类后，
  通过 conditional edges 进入注册表对应的 `<intent>_node`。
- `intent/registry.py` 是意图、分类描述、示例、响应协议、RAG 开关和工具集的
  唯一映射源；图节点与分类 prompt 均从注册表动态生成。
- `agents/factory.py` 为每个 `IntentSpec` 构建独立 `create_agent` 子图，并在
  模型调用前把请求级基础提示词与该意图协议组合。
- 两个意图不走通用 Agent，而是「服务端确定性步骤 + 模型只负责措辞」的子图：
  `agents/search.py`（规划 → Tavily → 回答）与 `agents/insurance.py`
  （查 `plan_shows` 出 A2UI 卡片 → 回答），实现在 `factory.build_agent_for_intent`
  里按 `spec.id` 分派。
- checkpointer 仅挂在外层 supervisor；子 Agent 继承同一个 `thread_id` 上下文。
- `agents/chat_agent.py` 只保留旧 `get_chat_agent()` 导入的兼容封装。

### 中间件 (`app/core/langgraph/middleware/`)

按外层 → 内层顺序：

| 中间件 | 职责 |
| --- | --- |
| `MetricsMiddleware` | 成功调用后统计 Prometheus 指标（调用次数 / token 用量） |
| `ResilienceMiddleware` | tenacity 指数退避重试；每次失败 `registry.rotate()` 故障转移 |
| `ModelRoutingMiddleware` | 每次调用按 state（model / thinking）经 registry 解析模型实例 |
| `StreamingMiddleware` | 恢复 token 级流式（见下） |

以上四个横切中间件为模块级单例并由所有意图 Agent 复用。`RagMiddleware`
只负责“检索 + 注入”，仅在 `IntentSpec.use_rag=True` 的 Agent 中挂载；当前为
`general`，位置在 Metrics 内、Resilience 外，重试不会重复检索。

`ResilienceMiddleware` 在重试时会重新经过内层的 `ModelRoutingMiddleware`，
因此 rotate 切换的模型在下一次尝试立即生效。

## token 级流式说明（重要）

langchain 1.3 的 `create_agent` 模型节点（`trace=False`）调用模型时**不透传
RunnableConfig**，导致 `on_chat_model_stream` 回调、`get_config()`、
`stream_writer` 全部断链（上游 issue：
[langchain#37869](https://github.com/langchain-ai/langchain/issues/37869)，1.4.0 仍未修复）。

`StreamingMiddleware` 的 workaround：

1. 模型调用前手动设置最小 config contextvar，恢复 `stream_writer` 可用性；
2. 用流式 tap 包装模型：内部改用 `astream` 消费，每个 chunk 通过
   `stream_writer` 发到 **custom 流**，聚合后返回完整消息（tool_calls 保留）。

因此 `chat.py` 的流式接口使用
`astream(stream_mode=["custom", "messages"], subgraphs=True)`。启用
`subgraphs=True` 是必要条件：否则子 Agent 的 custom token 不会冒泡，messages
事件也只会显示外层意图节点。

- `custom` 通道：token 级增量（content + reasoning_content），转 SSE；
- `messages` 通道：完整消息（含 tool_calls / usage_metadata），用于落库。

`chat.py` 对 `custom` 载荷做了类型判断：只处理 `AIMessageChunk`，其他结构化
载荷直接跳过（防止未来新增事件类型时抛 `AttributeError` 并被吞成 error 帧）。
`intent_node` 目前只把意图写进图状态，不广播意图事件。

上游修复后（模型节点透传 config），`StreamingMiddleware` 可直接从
middleware 列表移除，`chat.py` 的接收逻辑无需变化。

## insurance 意图：确定性卡片管线

用户表达投保意向（「我想买保险」等）时，产品数据必须来自数据库而不是模型记忆，
因此该意图由 `agents/insurance.py` 的确定性子图处理：

```
START → plan_query_node → insurance_answer_node → END
```

1. `plan_query_node`：`app/services/plans/` 查 `plan_shows`（排序、上限、不过滤
   `has_sale`），用纯函数 `build_plan_card_envelope` 生成 A2UI v0.9 命令信封
   `{"surfaceId","commands"}`，写入 `state["x_card"]`。查询失败或没有方案时
   置 `None` 并记日志，本轮降级为纯文本，不打断对话。
2. `insurance_answer_node`：`create_agent` 只写 2~3 句自然语言说明。它的动态
   提示词会把「本轮已下发 N 张卡片」或「未取到方案数据」注入系统提示，避免
   模型承诺了卡片却没有卡，或凭记忆编造产品与保费。

卡片数据的出口在 `chat.py`：流正常结束后读一次图状态，把 `x_card` 渲染成
`\`\`\`a2ui` 围栏，作为最后一段正文增量下发（在 stop 帧之前），并拼进落库的
assistant content。**围栏不写进 checkpoint 消息**——25 张卡的命令 JSON 实测约
35KB，若进入对话记忆，之后每轮请求都要多烧这些 token；落库则保证历史消息
重放能复现同样的卡片。

协议细节（组件契约、按钮颜色与 action、围栏解析）见
[a2ui-plan-cards.md](a2ui-plan-cards.md)。

## 多模型容灾流程

1. 默认使用注册表中的第一个模型（或请求指定的模型）。
2. 调用失败时，`ResilienceMiddleware` 触发 `rotate()` 切换到下一个模型。
3. 使用 `tenacity` 进行指数退避重试（最多 3 次尝试）。
4. 若所有尝试均失败，异常向上冒泡（接口返回 500 / SSE error 帧）。

## 添加新意图

在 `intent/registry.py` 的 `INTENT_SPECS` 新增一条 `IntentSpec`，填写 id、分类
描述与示例、协议提示词、`use_rag` 和可选工具集。分类 prompt、子 Agent 节点和
conditional edge 会自动生成；无需修改 supervisor 或增加横切中间件。若该意图
未来需要事务流程，可把对应节点扩为专属子图，其他意图不受影响。

其他扩展：

- 添加默认工具：在 `app/core/langgraph/tools/` 新增并加入 `tools` 列表；某个
  意图的专用工具直接配置在它的 `IntentSpec.tools`。
- 添加新提供商：在 `_create_model` 中根据模型名或配置选择不同 `model_provider`。
- 添加 API Key 管理：可在配置中增加多个密钥，按模型分配。
- 官方中间件（`langchain.agents.middleware`）也开箱可用，如
  `SummarizationMiddleware`（长对话自动摘要）、`HumanInTheLoopMiddleware` 等。

## 相关配置

- `OPENAI_API_KEY`：OpenAI 兼容 API 密钥。
- `ANTHROPIC_API_KEY`：Anthropic API 密钥（预留）。
- `QWEN_API_KEY`：通义千问 API 密钥（预留）。
- `DEEPSEEK_API_KEY`：DeepSeek API 密钥（当前 registry 默认提供商）。
- `TAVILY_API_KEY`：Tavily 联网搜索密钥；为空时仅禁用搜索调用。
