from langchain_openai import OpenAIEmbeddings
from app.core.config import settings
from app.core.logging import logger

_embedder = None

def get_embedder() -> OpenAIEmbeddings:
    global _embedder
    logger.info(f'向量配置：{settings.embed_model_name},{settings.embed_api_key},{settings.embed_base_url}')
    if _embedder is None:
        _embedder = OpenAIEmbeddings(
            model=settings.embed_model_name,
            api_key=settings.embed_api_key,
            base_url=settings.embed_base_url,
        )
    return _embedder