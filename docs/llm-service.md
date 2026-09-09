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

### Agent 工厂 (`app/core/langgraph/agents/chat_agent.py`)

- `create_agent(base_model, tools, middleware, state_schema, checkpointer)` 构建 Agent。
- 基础模型经 `init_chat_model`（LLMRegistry）创建后传入；每次调用实际使用的
  模型由 `ModelRoutingMiddleware` 按 state 覆盖（支持按请求选模型/思考模式）。
- 工具真正挂载（`app/core/langgraph/tools/`），模型可自主调用并进入工具循环。
- 后续扩展：往 `tools` 列表加工具，或往 `middleware` 列表加中间件。

### 中间件 (`app/core/langgraph/middleware/`)

按外层 → 内层顺序：

| 中间件 | 职责 |
| --- | --- |
| `MetricsMiddleware` | 成功调用后统计 Prometheus 指标（调用次数 / token 用量） |
| `RagMiddleware` | 每轮模型调用前检索 top-5 并重排，以“参考资料”注入 system message |
| `ResilienceMiddleware` | tenacity 指数退避重试；每次失败 `registry.rotate()` 故障转移 |
| `ModelRoutingMiddleware` | 每次调用按 state（model / thinking）经 registry 解析模型实例 |
| `StreamingMiddleware` | 恢复 token 级流式（见下） |

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

因此 `chat.py` 的流式接口使用 `astream(stream_mode=["custom", "messages"])`：

- `custom` 通道：token 级增量（content + reasoning_content），转 SSE；
- `messages` 通道：完整消息（含 tool_calls / usage_metadata），用于落库。

上游修复后（模型节点透传 config），`StreamingMiddleware` 可直接从
middleware 列表移除，`chat.py` 的接收逻辑无需变化。

## 多模型容灾流程

1. 默认使用注册表中的第一个模型（或请求指定的模型）。
2. 调用失败时，`ResilienceMiddleware` 触发 `rotate()` 切换到下一个模型。
3. 使用 `tenacity` 进行指数退避重试（最多 3 次尝试）。
4. 若所有尝试均失败，异常向上冒泡（接口返回 500 / SSE error 帧）。

## 扩展指南

- 添加工具：在 `app/core/langgraph/tools/` 新增并加入 `tools` 列表。
- 添加中间件：在 `app/core/langgraph/middleware/` 新增并加入 agent 工厂的
  middleware 列表（注意顺序语义：靠前为外层）。
- 添加新提供商：在 `_create_model` 中根据模型名或配置选择不同 `model_provider`。
- 添加 API Key 管理：可在配置中增加多个密钥，按模型分配。
- 官方中间件（`langchain.agents.middleware`）也开箱可用，如
  `SummarizationMiddleware`（长对话自动摘要）、`HumanInTheLoopMiddleware` 等。

## 相关配置

- `OPENAI_API_KEY`：OpenAI 兼容 API 密钥。
- `ANTHROPIC_API_KEY`：Anthropic API 密钥（预留）。
- `QWEN_API_KEY`：通义千问 API 密钥（预留）。
- `DEEPSEEK_API_KEY`：DeepSeek API 密钥（当前 registry 默认提供商）。
