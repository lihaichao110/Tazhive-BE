# 泰智汇

生产级 Python Agent 项目，基于 FastAPI + LangGraph + PostgreSQL，支持多模型容灾、RAG 检索、流式响应、多 Agent 管理、可观测性等企业级特性。

## ✨ 功能特性

- **对话式 AI**：支持流式/非流式聊天，自动保存历史消息及完整 AI 元数据（推理内容、token 用量等）
- **多模型容灾**：支持配置多个 LLM 提供商，故障时自动轮询切换
- **RAG 检索**：文档上传、自动分块、向量嵌入、混合检索与重排序
- **多 Agent 管理**：用户可自定义 Agent（系统提示、模型、温度等）
- **认证与安全**：JWT 认证、密码哈希、接口限流（预留）
- **可观测性**：结构化日志、Prometheus 指标、Langfuse 追踪（可选）
- **数据库迁移**：使用 Alembic 管理 schema
- **容器化部署**：提供 Dockerfile 和 docker-compose.yml，一键启动

## 🛠 技术栈

| 层次 | 技术 |
|------|------|
| API 框架 | FastAPI |
| Agent 编排 | LangGraph |
| LLM 接入 | LangChain `init_chat_model` |
| 数据库 | PostgreSQL 16 + pgvector |
| ORM | SQLModel |
| 迁移 | Alembic |
| 认证 | JWT + bcrypt |
| 限流 | slowapi（预留） |
| 可观测性 | Prometheus + Langfuse |
| 包管理 | uv + pyproject.toml |
| 部署 | Docker / docker-compose |

生产环境通过 GitHub Actions、阿里云 ACR、Docker Compose 和 Nginx 自动发布，初始化步骤与所需 Secrets
见 [生产环境部署文档](docs/deployment.md)。


## 📦 快速开始

### 本地开发

1. **克隆仓库**（如果已存在则跳过）

2. **初始化开发环境**：

   ```bash
   make setup
   ```

   该命令会安装项目依赖并启用 Git pre-commit hook。后续仅需同步依赖时，运行：

   ```bash
   uv sync
   ```

3. **启动开发服务器**：

   ```bash
   make dev
   ```

### 提交前检查

执行 `git commit` 时，pre-commit hook 会自动运行 Ruff 代码检查和格式化、基础文件检查以及 mypy 类型检查。

需要手动检查仓库中的全部文件时，运行：

```bash
uv run pre-commit run --all-files
```
