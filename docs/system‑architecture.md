# 项目架构
```cmd
泰智汇/
├── pyproject.toml                  # 项目元数据与依赖
├── uv.lock                         # uv 锁文件
├── langgraph.json                  # LangGraph 部署配置
├── .env / .env.example             # 环境变量
├── .gitignore
├── README.md
├── Dockerfile                      # 生产镜像
├── docker-compose.yml              # 本地 Postgres/Redis 等服务
├── Makefile                        # 常用命令 (make dev/test/lint)
│
├── alembic.ini                     # 数据库迁移配置
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                   # 迁移脚本
│       └── 001_initial.py
│
├── app/                            # 主应用
│   ├── main.py                     # FastAPI 入口
│   ├── api/                        # HTTP 层（薄）
│   │   ├── deps.py                 # 依赖注入 (db, current_user, limiter)
│   │   └── v1/
│   │       ├── router.py           # 聚合所有 v1 路由
│   │       ├── chat.py             # POST /chat/{thread_id}
│   │       ├── agents.py           # Agent 管理
│   │       ├── documents.py        # 文档上传/RAG入库
│   │       ├── threads.py          # 会话历史
│   │       └── health.py           # /healthz, /readyz
│   │
│   ├── core/                       # 核心基础设施
│   │   ├── config.py               # Pydantic Settings
│   │   ├── logging.py              # 结构化日志
│   │   ├── security.py             # JWT/密码哈希
│   │   ├── middleware.py           # metrics/logging中间件
│   │   ├── limiter.py              # slowapi 限流
│   │   └── exceptions.py           # 全局异常处理
│   │
│   ├── models/                     # SQLModel ORM
│   │   ├── base.py                 # 公共基类 (id, created_at, updated_at)
│   │   ├── user.py
│   │   ├── thread.py               # 会话
│   │   ├── message.py              # 消息历史
│   │   └── document.py             # RAG 文档元数据
│   │
│   ├── schemas/                    # Pydantic 请求/响应模型
│   │   ├── chat.py
│   │   ├── agent.py
│   │   └── document.py
│   │
│   ├── services/                   # 业务逻辑层
│   │   ├── llm/                    # LLM 服务
│   │   │   ├── registry.py         # 多模型轮询
│   │   │   ├── base.py
│   │   │   └── providers/          # openai.py, anthropic.py, qwen.py
│   │   ├── rag/                    # RAG 检索
│   │   │   ├── loader.py           # PDF/DOCX/MD解析
│   │   │   ├── chunker.py          # 切分策略
│   │   │   ├── embedder.py         # embedding 调用
│   │   │   ├── retriever.py        # 向量+关键词混合检索
│   │   │   ├── reranker.py         # 重排序
│   │   │   └── pipeline.py         # 端到端 ingest→embed→store
│   │   ├── memory/                 # 长记忆
│   │   │   └── mem0_store.py       # mem0 + pgvector
│   │   ├── auth/                   # jwt.py
│   │   └── database.py             # SQLAlchemy 引擎 + Session
│   │
│   ├── core/langgraph/             # ⭐ Agent 编排核心
│   │   ├── graphs/                 # chat_agent.py, multi_agent.py, deep_agent.py
│   │   ├── nodes/                  # llm_call.py, rag_retrieve.py, tool_call.py, human_approval.py, reflect.py
│   │   ├── tools/                  # web_search.py, code_exec.py, http_request.py, db_query.py
│   │   ├── prompts/                # system_chat.py, system_rag.py, system_deep.py
│   │   ├── state.py                # AgentState TypedDict (核心状态)
│   │   └── checkpointer.py         # PostgresSaver 配置
│   │
│   ├── observability/              # 可观测性
│   │   ├── langfuse.py             # LLM trace
│   │   ├── metrics.py              # Prometheus
│   │   └── tracing.py              # OpenTelemetry
│   │
│   └── evals/                      # 评估
│       ├── datasets/               # qa_golden.jsonl
│       ├── evaluators/             # correctness.py, faithfulness.py, relevance.py
│       └── run_eval.py
│
├── tests/                          # 测试
│   ├── conftest.py
│   ├── unit/                       # test_services_llm.py, test_services_rag.py, test_langgraph_nodes.py
│   ├── integration/                # test_api_chat.py, test_rag_pipeline.py
│   └── e2e/                        # test_full_conversation.py
│
├── scripts/                        # 运维脚本
│   ├── init_db.sh
│   ├── seed_demo_data.py
│   └── clean_checkpoints.py
│
└── docs/                           # 文档
    ├── architecture.md
    ├── llm-service.md
    ├── memory.md
    └── configuration.md
```