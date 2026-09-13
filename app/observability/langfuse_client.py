from langfuse import Langfuse

from app.core.config import settings
from app.core.logging import logger

_langfuse_client = None


def get_langfuse_client() -> Langfuse | None:
    global _langfuse_client
    if _langfuse_client is None:
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            logger.warning("Langfuse keys 未设置，禁用跟踪")
            return None
        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=getattr(settings, "langfuse_host", "https://cloud.langfuse.com"),
        )
    return _langfuse_client


def trace_generation(prompt: str, completion: str, model: str, metadata: dict | None = None):
    """手动记录一次生成（供评估或调试）"""
    client = get_langfuse_client()
    if client:
        # 创建一条根追踪（Trace）
        with client.start_as_current_observation(
            as_type="span",
            name="chat",
            metadata=metadata or {},
        ) as root_trace:
            with root_trace.start_as_current_observation(
                as_type="generation",
                name="llm-call",
                model=model,
                input=prompt,
                output=completion,
            ):
                # 进入 observation 上下文即可完成追踪；如需补充 token 用量再显式绑定对象。
                pass
