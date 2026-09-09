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
| LangGraph 引擎 |
| ├── 状态管理 |
| ├── 节点 (LLM/RAG) |
| └── 检查点 (Postgres)|
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

- **状态 (`state.py`)**：定义 `AgentState`，包含消息历史、检索发现、错误记录等。
- **节点 (`nodes/`)**：可复用的处理单元，如 `llm_call`、`rag_retrieve`。
- **图 (`graphs/`)**：构建节点间流程，当前为 `START -> rag_retrieve -> llm -> END`。
- **检查点 (`checkpointer.py`)**：使用 `AsyncPostgresSaver` 持久化对话状态，支持多轮上下文。

### 4.3 服务层 (`app/services`)

- **LLM Registry**：管理多个模型，支持轮询和故障切换。
- **RAG Pipeline**：文档加载 → 分块 → 嵌入 → 存储 → 检索 → 重排序。
- **Database**：SQLAlchemy 引擎与会话管理。

### 4.4 数据模型 (`app/models`)

- 用户、会话、消息、文档、文档分块、Agent 配置等。
- 消息表存储完整 AI 响应元数据（token 用量、推理内容等）。

## 5. 数据流

### 5.1 聊天请求（非流式）

1. 客户端发送 `POST /api/v1/chat/{thread_id}`，携带消息历史和可选 `agent_id`。
2. 路由验证 JWT 和会话归属。
3. 若指定 `agent_id`，加载 Agent 配置（系统提示、模型名）。
4. 构建 `AgentState` 并传入 LangGraph 图。
5. LangGraph 执行 `rag_retrieve` 节点（检索相关文档）→ `llm_call` 节点（调用 LLM）。
6. 返回最终助手消息，同时保存用户和助手消息到数据库。

### 5.2 流式聊天

- 与上述类似，但通过 `StreamingResponse` 使用 SSE 逐 token 返回。
- 在 `finally` 块中保存完整消息和元数据（从 `on_chat_model_end` 事件获取）。

### 5.3 文档上传与 RAG

1. 客户端上传文件到 `POST /api/v1/documents/upload`。
2. 保存临时文件，调用 `ingest_document`。
3. 加载文件内容，分块，生成嵌入，存入 `document_chunks` 表（pgvector）。
4. 返回处理状态。

## 6. 关键设计决策

- **状态覆盖 vs 累加**：`messages` 字段采用覆盖方式，由前端传入完整历史；`findings` 等采用累加（`Annotated[list, add]`）。
- **异步 Checkpointer**：使用 `AsyncPostgresSaver` 以支持异步图执行，避免阻塞事件循环。
- **多模型容灾**：`LLMRegistry` 实现简单轮询，结合 `tenacity` 重试机制。
- **完整元数据存储**：消息表包含 JSONB 列，保存所有原始响应信息，便于审计和分析。
- **RAG 重排序**：先向量检索，再基于关键词重叠简单重排，后续可替换为交叉编码器。

## 7. 扩展点

- **工具调用**：在 `nodes/` 中添加工具调用节点，并扩展状态。
- **多 Agent 协作**：使用 LangGraph 的 supervisor 模式。
- **更强大的评估**：集成 LangSmith 或使用 LLM-as-judge。
- **水平扩展**：使用连接池和分布式任务队列处理文档摄入。

## 8. 部署架构

- 使用 Docker Compose 编排应用和数据库。
- 应用容器启动时自动执行数据库迁移。
- 生产环境建议使用托管 PostgreSQL（如 RDS）并配置持久化存储。

---

本文档将随项目演进持续更新。