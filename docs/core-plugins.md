# 后端依赖

本文档记录项目在 `pyproject.toml` 中直接声明的依赖。版本约束以 `pyproject.toml` 为准，本文档不展开 `uv.lock` 中的传递依赖。

## 运行时依赖

### Web 服务与配置

- `fastapi`：Web API 框架。
- `uvicorn[standard]`：ASGI 服务器及其标准性能扩展。
- `python-multipart`：解析表单和文件上传请求。
- `slowapi`：API 请求限流。
- `pydantic[email]`：数据校验，并提供电子邮箱字段校验能力。
- `pydantic-settings`：从环境变量和配置文件加载应用设置。
- `python-dotenv`：读取 `.env` 环境变量文件。

### Agent 与模型集成

- `langchain`：LangChain 高层 Agent 与应用编排能力。
- `langchain-core`：LangChain 核心抽象和运行接口。
- `langchain-community`：社区维护的加载器、向量库等集成。
- `langchain-openai`：OpenAI 模型适配器。
- `langchain-anthropic`：Anthropic 模型适配器。
- `langchain-deepseek`：DeepSeek 模型适配器。
- `langchain-text-splitters`：文档文本切分工具。
- `langchain-tavily`：Tavily 联网搜索集成。
- `langgraph`：有状态 Agent 工作流编排。
- `tenacity`：为模型调用和外部服务提供重试机制。

### 数据库与状态持久化

- `sqlmodel`：基于 SQLAlchemy 和 Pydantic 的 ORM。
- `alembic`：数据库结构迁移工具。
- `psycopg[binary]`：Psycopg 3 PostgreSQL 驱动及二进制实现。
- `psycopg2-binary`：兼容仍使用 Psycopg 2 接口的 PostgreSQL 代码。
- `psycopg-pool`：Psycopg 3 数据库连接池。
- `pgvector`：PostgreSQL 向量类型和相似度检索支持。
- `langgraph-checkpoint-postgres`：将 LangGraph 检查点持久化到 PostgreSQL。
- `langgraph-checkpoint-sqlite`：将 LangGraph 检查点持久化到 SQLite。

### 认证与安全

- `python-jose[cryptography]`：JWT 的签发、解析和加密算法支持。
- `bcrypt`：密码哈希和校验。

### 文档与文件处理

- `docx2txt`：提取 Word 文档中的文本。
- `openpyxl`：读取和写入 Excel 工作簿。
- `path`：面向对象的文件路径操作工具。

### 可观测性与日志

- `langfuse`：记录和分析 LLM 调用链路。
- `prometheus-client`：采集并导出 Prometheus 指标。
- `opentelemetry-api`：OpenTelemetry 遥测 API。
- `opentelemetry-sdk`：OpenTelemetry 遥测数据采集和导出实现。
- `opentelemetry-instrumentation-fastapi`：自动采集 FastAPI 请求链路。
- `logger`：应用日志工具。

## 开发依赖

### 测试与调试

- `pytest`：测试框架。
- `pytest-asyncio`：异步代码测试支持。
- `pytest-mock`：基于 pytest 的 mock 工具。
- `httpx`：API 测试使用的异步 HTTP 客户端。
- `ipython`：交互式调试环境。

### 代码质量

- `black`：Python 代码格式化。
- `ruff`：代码检查和快速格式校验。
- `mypy`：静态类型检查。
- `pre-commit`：在 Git 提交前统一执行质量检查。
