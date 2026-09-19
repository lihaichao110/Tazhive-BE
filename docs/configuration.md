# 配置说明

所有配置通过环境变量或 `.env` 文件加载，使用 Pydantic Settings 管理。

## 数据库

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DATABASE_URL` | `postgresql+psycopg://user:password@localhost:5432/agentdb` | PostgreSQL 连接字符串，需包含 pgvector 扩展 |
| `CHECKPOINT_POOL_MIN_SIZE` | `0` | checkpoint 池保持的最小连接数；公网数据库建议为 0 |
| `CHECKPOINT_POOL_MAX_SIZE` | `10` | checkpoint 池最大连接数 |
| `CHECKPOINT_POOL_TIMEOUT_SECONDS` | `10` | 等待池中连接的最长秒数 |
| `CHECKPOINT_POOL_MAX_IDLE_SECONDS` | `300` | 空闲连接回收秒数 |
| `CHECKPOINT_POOL_MAX_LIFETIME_SECONDS` | `1800` | 单个连接的最长生命周期秒数 |
| `DB_CONNECT_TIMEOUT_SECONDS` | `5` | PostgreSQL 建连超时秒数 |
| `DB_KEEPALIVES_IDLE_SECONDS` | `60` | TCP 空闲多久后开始保活探测 |
| `DB_KEEPALIVES_INTERVAL_SECONDS` | `20` | TCP 保活探测间隔秒数 |
| `DB_KEEPALIVES_COUNT` | `3` | 判定连接断开前允许的保活失败次数 |

## 安全

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SECRET_KEY` | `change-me-in-production` | JWT 签名密钥 |
| `PII_ENCRYPTION_KEY` | 空 | 投保人员资料 Fernet 加密密钥；为空时投保动作接口不可用 |
| `ALGORITHM` | `HS256` | JWT 算法 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | 令牌过期时间（分钟） |
| `CORS_ALLOWED_ORIGINS` | 空 | 允许跨域访问 API 的前端 Origin，多个值用英文逗号分隔；为空时仅同源请求可用 |

## 统一 LLM 配置

聊天、意图分类、搜索规划、保险筛选和 Text2SQL 共用一套提供商连接配置。
以下字段缺失、为空或角色引用了未注册模型时，应用会在启动阶段直接失败。

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `LLM_PROVIDER` | 是 | LangChain 模型提供商，例如 `deepseek` |
| `LLM_API_KEY` | 是 | 当前提供商的 API 密钥 |
| `LLM_BASE_URL` | 否 | 自定义 API 地址；留空时使用提供商 SDK 默认地址 |
| `LLM_MODELS` | 是 | 逗号分隔的模型列表，顺序同时作为故障切换顺序 |
| `LLM_DEFAULT_MODEL` | 是 | 普通对话和新建 Agent 的默认模型，必须位于 `LLM_MODELS` |
| `LLM_FAST_MODEL` | 是 | 意图分类、搜索规划和保险筛选模型，必须位于 `LLM_MODELS` |
| `LLM_TEXT2SQL_MODEL` | 是 | SQL 生成模型，必须位于 `LLM_MODELS` |
| `LLM_DEFAULT_TEMPERATURE` | 是 | 普通模型默认温度，范围 `0`～`2` |
| `LLM_MODEL_ALIASES` | 否 | 旧模型名到规范名称的 JSON 对象；目标必须位于 `LLM_MODELS` |

修改后可运行 `make config-check`，在连接数据库或模型服务前完成配置校验。

## 联网搜索

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `TAVILY_API_KEY` | 否 | Tavily 联网搜索密钥；为空时服务仍可启动，但搜索意图会返回配置提示 |

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
