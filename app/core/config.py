from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """
    项目全局配置类，基于 pydantic‑settings，自动从 .env 文件读取环境变量覆盖默认值
    """
    # -------------------------- 数据库配置 --------------------------
    # PostgreSQL数据库连接地址，sqlalchemy 连接串格式：驱动://账号:密码@主机:端口/数据库名
    database_url: str = "postgresql+psycopg://user:password@localhost:5432/agentdb"

    # -------------------------- JWT登录鉴权配置 --------------------------
    # JWT签名密钥，生产环境必须替换为复杂随机字符串，泄露会导致伪造token
    secret_key: str = "change-me-in-production"
    # JWT加密算法，HS256 代表 HMAC‑SHA256 对称加密算法
    algorithm: str = "HS256"
    # access_token访问令牌过期时间，单位分钟
    access_token_expire_minutes: int = 60

    # -------------------------- 各大LLM大模型API密钥 --------------------------
    # OpenAI系列接口密钥，为None时不启用该模型
    openai_api_key: str | None = None
    # Anthropic(Claude)接口密钥，为None时不启用该模型
    anthropic_api_key: str | None = None
    # 通义千问qwen接口密钥，为None时不启用该模型
    qwen_api_key: str | None = None
    # deepseek接口密钥，为None时不启用该模型
    deepseek_api_key: str | None = None

    # -------------------------- Langfuse 大模型观测平台配置 --------------------------
    # Langfuse公钥，用于上报Agent/LLM调用链路、token消耗、trace追踪
    langfuse_public_key: str | None = None
    # Langfuse私钥，服务端鉴权，不要暴露给前端
    langfuse_secret_key: str | None = None

    class Config:
        # 指定读取 .env 文件，会用env内变量覆盖上面类属性的默认值
        env_file = ".env"
        # 环境变量大小写不敏感，例如 .env 写 DATABASE_URL 和 database_url 效果一样
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """
    获取全局配置单例
    lru_cache缓存装饰器：只实例化一次Settings对象，避免重复读取解析.env文件
    """
    return Settings()


# 项目全局直接导入使用的配置实例
settings = get_settings()