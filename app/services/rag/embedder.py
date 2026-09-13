from typing import Any, cast

from langchain_openai import OpenAIEmbeddings

from app.core.config import settings
from app.core.logging import logger

_embedder = None


def get_embedder() -> OpenAIEmbeddings:
    global _embedder
    logger.info(
        f"向量配置：{settings.embed_model_name},{settings.embed_api_key},{settings.embed_base_url}"
    )
    if _embedder is None:
        model_name = settings.embed_model_name
        if not model_name:
            raise ValueError("embed_model_name 未配置，无法初始化向量嵌入模型")
        _embedder = OpenAIEmbeddings(
            model=model_name,
            # langchain_openai 将 api_key 标注为 SecretStr，运行时接受明文 str。
            api_key=cast(Any, settings.embed_api_key),
            base_url=settings.embed_base_url,
        )
    return _embedder
