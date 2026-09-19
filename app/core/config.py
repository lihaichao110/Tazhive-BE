import json
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# pydantic-settings 只会把 .env 读进 Settings 对象，不会写入 os.environ。
# 而 Langfuse 等 SDK 是直接读 os.environ 的，所以这里手动加载一次，确保两者都生效。
load_dotenv()


class Settings(BaseSettings):
    """
    项目全局配置类，基于 pydantic‑settings，自动从 .env 文件读取环境变量覆盖默认值
    """

    # -------------------------- 数据库配置 --------------------------
    # PostgreSQL数据库连接地址，sqlalchemy 连接串格式：驱动://账号:密码@主机:端口/数据库名
    database_url: str = "postgresql+psycopg://xxxxxxx"
    # 数据库用户名
    PG_USER: str = ""
    # 数据库密码
    PG_PASSWORD: str = ""
    # 数据库名
    PG_DB: str = ""
    # LangGraph checkpoint 异步连接池配置。公网数据库需要在复用前检查连接，
    # 并及时回收空闲连接，避免拿到已被 NAT 或防火墙回收的 TCP 连接。
    # 连接池最小连接数；设为 0 表示没有请求时可以释放全部空闲连接。
    checkpoint_pool_min_size: int = 0
    # 连接池最大连接数，用于限制 checkpoint 并发占用的数据库连接。
    checkpoint_pool_max_size: int = 10
    # 从连接池获取连接的最长等待时间，单位为秒。
    checkpoint_pool_timeout_seconds: float = 10.0
    # 超过该空闲时间的连接允许被回收，单位为秒。
    checkpoint_pool_max_idle_seconds: float = 300.0
    # 单个连接允许存活的最长时间，单位为秒，到期后会自动更换连接。
    checkpoint_pool_max_lifetime_seconds: float = 1800.0
    # psycopg 客户端连接和 TCP keepalive 配置。
    # 建立 PostgreSQL 连接的超时时间，单位为秒。
    db_connect_timeout_seconds: int = 5
    # TCP 连接空闲多久后开始发送 keepalive 探测，单位为秒。
    db_keepalives_idle_seconds: int = 60
    # 相邻两次 TCP keepalive 探测之间的间隔，单位为秒。
    db_keepalives_interval_seconds: int = 20
    # 连续多少次 keepalive 探测失败后判定 TCP 连接已经断开。
    db_keepalives_count: int = 3

    # -------------------------- JWT登录鉴权配置 --------------------------
    # JWT签名密钥，生产环境必须替换为复杂随机字符串，泄露会导致伪造token
    secret_key: str = "change-me-in-production"
    # JWT加密算法，HS256 代表 HMAC‑SHA256 对称加密算法
    algorithm: str = "HS256"
    # access_token访问令牌过期时间，单位分钟
    access_token_expire_minutes: int = 60
    # refresh_token刷新令牌过期时间，单位天；每次刷新轮换，旧令牌立即作废
    refresh_token_expire_days: int = 7

    # -------------------------- 投保敏感信息加密配置 --------------------------
    # 独立于 JWT 密钥；未配置时只禁用投保动作接口，不影响普通聊天服务。
    pii_encryption_key: str | None = None

    # -------------------------- 跨域访问配置 --------------------------
    # 允许访问 API 的前端 Origin，多个地址使用英文逗号分隔。
    # 默认为空，未通过环境变量显式配置时不允许任何跨域来源。
    # Origin 只包含协议、域名和端口，末尾不要添加路径或斜杠。
    cors_allowed_origins: str = ""

    @property
    def cors_origins(self) -> list[str]:
        """将逗号分隔的 Origin 配置转换为 CORS 中间件所需的列表。"""
        return list(
            dict.fromkeys(
                origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()
            )
        )

    # -------------------------- 统一 LLM 配置 --------------------------
    # 所有聊天类模型共用一套提供商连接配置；角色模型必须注册在 llm_models 中。
    llm_provider: str
    llm_api_key: SecretStr
    llm_base_url: str | None = None
    # 逗号分隔，顺序同时决定模型故障切换顺序。
    llm_models: str
    llm_default_model: str
    llm_fast_model: str
    llm_text2sql_model: str
    llm_default_temperature: float = Field(ge=0.0, le=2.0)
    # JSON 对象，键为旧模型名，值为 llm_models 中的规范模型名。
    llm_model_aliases: str = "{}"

    @field_validator(
        "llm_provider",
        "llm_models",
        "llm_default_model",
        "llm_fast_model",
        "llm_text2sql_model",
    )
    @classmethod
    def validate_non_empty_llm_text(cls, value: str) -> str:
        """LLM 核心文本配置不允许用空白绕过必填校验。"""
        value = value.strip()
        if not value:
            raise ValueError("LLM 配置不能为空")
        return value

    @field_validator("llm_api_key")
    @classmethod
    def validate_llm_api_key(cls, value: SecretStr) -> SecretStr:
        """API key 缺失时在应用启动阶段失败，而不是等到首次模型调用。"""
        if not value.get_secret_value().strip():
            raise ValueError("LLM_API_KEY 不能为空")
        return value

    @field_validator("llm_base_url", mode="before")
    @classmethod
    def normalize_optional_base_url(cls, value):
        """允许 .env 用空值表示沿用提供商 SDK 的默认地址。"""
        return value or None

    @property
    def llm_model_names(self) -> list[str]:
        """将逗号分隔的模型注册表转换为保持顺序的列表。"""
        return [name.strip() for name in self.llm_models.split(",") if name.strip()]

    @property
    def llm_alias_map(self) -> dict[str, str]:
        """解析模型兼容别名；格式错误由启动校验统一报告。"""
        aliases = json.loads(self.llm_model_aliases)
        return {str(alias).strip(): str(target).strip() for alias, target in aliases.items()}

    @model_validator(mode="after")
    def validate_llm_registry(self):
        """确保角色和兼容别名都指向唯一、已注册的模型。"""
        model_names = self.llm_model_names
        if not model_names:
            raise ValueError("LLM_MODELS 至少要配置一个模型")
        if len(model_names) != len(set(model_names)):
            raise ValueError("LLM_MODELS 不能包含重复模型")

        for field_name in ("llm_default_model", "llm_fast_model", "llm_text2sql_model"):
            model_name = getattr(self, field_name)
            if model_name not in model_names:
                raise ValueError(f"{field_name.upper()} 必须存在于 LLM_MODELS 中")

        try:
            aliases = self.llm_alias_map
        except (json.JSONDecodeError, AttributeError) as exc:
            raise ValueError("LLM_MODEL_ALIASES 必须是 JSON 对象") from exc
        if not isinstance(json.loads(self.llm_model_aliases), dict):
            raise ValueError("LLM_MODEL_ALIASES 必须是 JSON 对象")
        if any(not alias or not target for alias, target in aliases.items()):
            raise ValueError("LLM_MODEL_ALIASES 的名称不能为空")
        invalid_targets = sorted(set(aliases.values()) - set(model_names))
        if invalid_targets:
            raise ValueError(
                "LLM_MODEL_ALIASES 目标必须存在于 LLM_MODELS 中：" + ", ".join(invalid_targets)
            )
        return self

    # -------------------------- 联网搜索配置 --------------------------
    # Tavily 联网搜索接口密钥；为空时不影响服务启动，搜索工具会返回配置提示
    tavily_api_key: str | None = None

    # -------------------------- Langfuse 大模型观测平台配置 --------------------------
    # Langfuse公钥，用于上报Agent/LLM调用链路、token消耗、trace追踪
    langfuse_public_key: str | None = None
    # Langfuse私钥，服务端鉴权，不要暴露给前端
    langfuse_secret_key: str | None = None

    # -------------------------- 嵌入式模型平台配置 --------------------------
    # 嵌入式模型密钥
    embed_api_key: str | None = None
    # 嵌入式模型地址
    embed_base_url: str | None = None
    # 嵌入式模型名称
    embed_model_name: str | None = None
    # 重排序模型名称；地址与密钥复用嵌入式模型平台配置
    rerank_model_name: str | None = None

    # -------------------------- RAG 检索配置 --------------------------
    # 混合检索参数：向量召回扩大候选池后交给在线模型重排，调用失败时按字面重叠降级。
    # 向量召回的候选池大小（重排在其上进行）。
    rag_recall_k: int = 30
    # 关键词字面召回的单路上限。
    rag_lexical_limit: int = 10
    # 纯向量候选的相似度阈值（余弦相似度），低于该分数的 chunk 不注入提示词；
    # 字面命中的记录不受该阈值约束。设为 0 表示不过滤。
    rag_score_threshold: float = 0.4

    # -------------------------- 上传文档存放地址 --------------------------
    upload_dir: str = "uploads"

    # -------------------------- 保险方案卡片（A2UI）配置 --------------------------
    # insurance 意图 createSurface 下发的 catalogId，必须与前端 registerCatalog
    # 注册的 id 完全一致，否则 X-Card 会把未知组件渲染成占位文本。
    # 默认用 A2UI 官方基本目录；前端若注册本地目录，改成 local://plan_show_catalog.json
    plan_show_catalog_id: str = "https://a2ui.org/specification/v0_9/basic_catalog.json"

    # -------------------------- text2sql 数据查询配置 --------------------------
    # 单次查询返回的最大行数，同时是 SQL 强制 LIMIT 的上限。
    text2sql_max_rows: int = 50
    # 查询执行超时时间（PostgreSQL statement_timeout，SQLite 测试环境跳过），单位秒。
    text2sql_statement_timeout_seconds: float = 5.0
    # 可选的只读数据库连接串；配置后数据查询走独立只读 engine，
    # 未配置时用主库 engine，安全依赖 sqlglot 白名单校验。
    text2sql_readonly_database_url: str | None = None

    # 环境变量大小写不敏感；迁移期间忽略旧版厂商密钥等已废弃变量。
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """
    获取全局配置单例
    lru_cache缓存装饰器：只实例化一次Settings对象，避免重复读取解析.env文件
    """
    # 必填字段由 pydantic-settings 从环境注入，静态类型检查器无法推断该行为。
    return Settings()  # type: ignore[call-arg]


# 项目全局直接导入使用的配置实例
settings = get_settings()
