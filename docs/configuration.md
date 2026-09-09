# 配置说明

所有配置通过环境变量或 `.env` 文件加载，使用 Pydantic Settings 管理。

## 数据库

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DATABASE_URL` | `postgresql+psycopg://user:password@localhost:5432/agentdb` | PostgreSQL 连接字符串，需包含 pgvector 扩展 |

## 安全

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SECRET_KEY` | `change-me-in-production` | JWT 签名密钥 |
| `ALGORITHM` | `HS256` | JWT 算法 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | 令牌过期时间（分钟） |

## LLM API Keys

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `OPENAI_API_KEY` | 否 | OpenAI 兼容 API 密钥（DeepSeek 等） |
| `ANTHROPIC_API_KEY` | 否 | Anthropic API 密钥 |
| `QWEN_API_KEY` | 否 | 通义千问 API 密钥 |
 | `DEEPSEEK_API_KEY` | 否 | deepseek API 密钥 |

## 可观测性

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `LANGFUSE_PUBLIC_KEY` | - | Langfuse 公钥 |
| `LANGFUSE_SECRET_KEY` | - | Langfuse 私钥 |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse 服务地址 |

## 文件上传

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `UPLOAD_DIR` | `uploads` | 上传文件临时存储目录 |

## 其他

可在 `app/core/config.py` 中扩展更多配置项。