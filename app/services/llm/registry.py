from typing import List, Optional
from logging import getLogger

from langchain.chat_models import init_chat_model
from langchain.chat_models.base import _ConfigurableModel
from langchain_core.language_models import BaseChatModel

from app.core.config import settings

logger = getLogger(__name__)


class LLMRegistry:
    def __init__(self, model_names: List[str]):
        self.model_names = model_names
        self.current_index = 0

    def get_model(self, model_name: Optional[str] = None) -> BaseChatModel | _ConfigurableModel:
        if model_name and model_name in self.model_names:
            return self._create_model(model_name=model_name)

        name = self.model_names[self.current_index]
        return self._create_model(model_name=name)

    def rotate(self):
        """切换到下一个模型（用于故障切换）"""
        self.current_index = (self.current_index + 1) % len(self.model_names)
        logger.info(f"LLM 切换到：{self.model_names[self.current_index]}")

    def _create_model(self, model_name: str) -> BaseChatModel | _ConfigurableModel:
        """根据模型名称创建模型实例，使用 OpenAI 兼容接口（DeepSeek 等）"""
        # 这里统一使用 init_chat_model，提供商可根据模型名推断，或显式指定
        # 实际项目中可根据模型名映射到不同提供商
        return init_chat_model(
            model=model_name,
            model_provider="deepseek",
            api_key=settings.deepseek_api_key,
            temperature=0.7,
            streaming=True,
            # 如果需要 base_url，可在配置中增加，这里暂不处理
        )

# 默认注册表：至少包含一个模型，可后续扩展
default_registry = LLMRegistry(model_names=["gpt-4o-mini", "deepseek-v4-flash", 'deepseek-v4-pro'])