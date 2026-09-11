# 系统架构文档

## 1. 概述

本系统是一个生产级 AI Agent 平台，提供对话式 AI、RAG 检索、多 Agent 管理、可观测性等能力。采用模块化设计，便于扩展和维护。

## 2. 技术选型

- **API 层**：FastAPI（异步、自动文档、类型安全）
- **Agent 编排**：LangGraph（图结构、状态机、检查点）
- **LLM 接入**：LangChain `init_chat_model`（支持多家提供商）
- **数据库**：PostgreSQL 16 + pgvector（业务数据 + 向量检索）
- **ORM**：SQLModel（SQLAlchemy + Pydantic）
- **认证**：JWT + bcrypt
- **可观测性**：结构化日志、Prometheus 指标、Langfuse 追踪（可选）
- **部署**：Docker + docker-compose

## 3. 系统架构图
```commandline
[客户端]
|
| HTTP/SSE
v
[FastAPI 应用] ------> [认证/限流中间件]
| |
| 路由层 (api/v1) |
| |
| 服务层 (services) |
| ├── LLM Registry |
| ├── RAG Pipeline |
| └── Database |
| |
| LangGraph Supervisor |
| ├── intent_node (LLM 分类) |
| ├── conditional edges (注册表生成) |
| ├── 意图 create_agent 子图 |
| └── 外层检查点 (Postgres)|
| |
v v
[PostgreSQL] <------ [pgvector 扩展]
| |
| v
+-----------------> [Langfuse / Prometheus]
```


## 4. 核心组件说明

### 4.1 API 层 (`app/api`)

- 提供 REST 端点，处理请求验证、依赖注入。
- 薄路由，业务逻辑委托给服务层和 LangGraph。
- 支持流式响应（Server-Sent Events）。

### 4.2 Agent 编排 (`app/core/langgraph`)

- **Supervisor (`graph/supervisor.py`)**：显式 `StateGraph`，先识别意图，再通过
  注册表生成的 conditional edges 路由到对应子 Agent。
- **意图注册表 (`intent/registry.py`)**：声明意图 id、分类描述/示例、响应协议、
  RAG 开关和可选工具，是分类与路由的共同数据源。
- **Agent 工厂 (`agents/factory.py`)**：为每个意图构建独立 `create_agent` 子图；
  checkpointer 仅挂外层 supervisor。
- **状态 (`state.py`)**：`ChatAgentState` 扩展自 langchain 的 `AgentState`，
  `messages` 为 `add_messages` 累积语义（会话记忆由 checkpointer 按 thread_id
  维护），另有请求级字段 `model` / `thinking` / `system_prompt`。
- **工具 (`tools/`)**：模型可自主调用的工具（当前时间、计算器等）。
- **中间件 (`middleware/`)**：指标统计、RAG 检索注入、重试与故障转移、
  按请求路由模型、token 级流式恢复（外层 → 内层次序见 llm-service.md）。
- **检查点 (`checkpointer.py`)**：使用 `AsyncPostgresSaver` 持久化对话状态，支持多轮上下文。

### 4.3 服务层 (`app/services`)

- **LLM Registry**：管理多个模型，支持轮询和故障切换。
- **RAG Pipeline**：文档加载 → 分块 → 嵌入 → 存储 → 检索 → 重排序。
- **Database**：SQLAlchemy 引擎与会话管理。

### 4.4 数据模型 (`app/models`)

- 用户、会话、消息、文档、文档分块、Agent 配置等。
- 消息表存储完整 AI 响应元数据（token 用量、推理内容等）。

## 5. 数据流

### 5.1 聊天请求（流式）

1. 客户端发送 `POST /api/v1/chat/{thread_id}`，携带消息历史和可选 `agent_id`，统一以 SSE 流式返回。
2. 路由验证 JWT 和会话归属。
3. 若指定 `agent_id`，加载 Agent 配置（系统提示、模型名）。
4. 构建 `ChatAgentState` 输入；增量发送——checkpointer 中该 thread 已有记忆时
   只发本轮新 user 消息，空 thread 才发全量历史。
5. `intent_node` 使用 flash 模型结构化分类；超时或异常兜底为 `general`，并
   通过 custom 流发送 intent 事件。
6. conditional edges 路由到对应意图 Agent。四个共享横切中间件固定为
   Metrics → Resilience → ModelRouting → Streaming；仅 `general` 额外挂 RAG。
7. 通过 `StreamingResponse` 使用 SSE 逐 token 返回。token 增量经
   `astream(stream_mode=["custom", "messages"], subgraphs=True)` 的 custom 通道接收
   （`StreamingMiddleware` 转发，规避 create_agent 回调断链，详见 llm-service.md）。
8. 在 `finally` 块中保存完整用户和助手消息及元数据（来自子图 model 节点）到数据库。

### 5.2 文档上传与 RAG

1. 客户端上传文件到 `POST /api/v1/documents/upload`，支持 `.txt`、`.md`、`.pdf`、`.docx` 和 `.xlsx`。
2. 保存临时文件，调用 `ingest_document`。
3. 加载文件内容，分块，生成嵌入，存入 `document_chunks` 表（pgvector）。
4. 返回处理状态。

## 6. 关键设计决策

- **消息累积 + checkpointer 记忆**：`messages` 采用 `add_messages` 累积语义，
  会话记忆由 checkpointer 按 thread_id 维护；chat.py 增量发送（有记忆只发本轮
  新 user 消息，空 thread 发全量），前端契约不变。
- **create_agent + 中间件**：Agent 主体为 `langchain.agents.create_agent`，
  每个意图管线自包含；业务扩展走注册表，四个共享横切中间件不随意图增长。
- **显式意图路由**：意图到处理节点的映射是 Studio 可视化的 conditional
  edges，不隐藏在中间件分支中；未知意图统一回退 `general`。
- **token 流式 workaround**：create_agent（langchain 1.3）模型调用不透传
  config 导致回调断链（[langchain#37869](https://github.com/langchain-ai/langchain/issues/37869)），
  由 `StreamingMiddleware` 经 custom 流恢复，上游修复后可移除。
- **异步 Checkpointer**：使用 `AsyncPostgresSaver` 以支持异步图执行，避免阻塞事件循环。
- **多模型容灾**：`LLMRegistry` 实现简单轮询，结合 `tenacity` 重试机制。
- **完整元数据存储**：消息表包含 JSONB 列，保存所有原始响应信息，便于审计和分析。
- **RAG 重排序**：先向量检索，再基于关键词重叠简单重排，后续可替换为交叉编码器。

## 7. 扩展点

- **工具调用**：在 `app/core/langgraph/tools/` 添加工具并加入 `tools` 列表，
  模型即可自主调用。
- **中间件**：在 `app/core/langgraph/middleware/` 添加中间件并加入 agent 工厂
  的 middleware 列表（langchain 官方中间件同样可用）。
- **多 Agent 协作**：将 create_agent 构建的 agent 作为子图挂入更大的图（supervisor 模式）。
- **更强大的评估**：集成 LangSmith 或使用 LLM-as-judge。
- **水平扩展**：使用连接池和分布式任务队列处理文档摄入。

## 8. 部署架构

- 使用 Docker Compose 编排应用和数据库。
- 应用容器启动时自动执行数据库迁移。
- 生产环境建议使用托管 PostgreSQL（如 RDS）并配置持久化存储。

---

本文档将随项目演进持续更新。
