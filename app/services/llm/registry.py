import json
from logging import getLogger
from typing import Any, cast

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.core.config import settings

logger = getLogger(__name__)


class LLMRegistry:
    def __init__(self, model_names: list[str]):
        self.model_names = model_names
        self.current_index = 0
        # 模型实例缓存：key 为 (model_name, thinking 的 JSON 串)，避免每次请求都重建
        self._cache: dict[str, BaseChatModel] = {}

    def get_model(
        self,
        model_name: str | None = None,
        thinking: dict | None = None,
        temperature: float | None = None,
    ) -> BaseChatModel:
        if model_name and model_name in self.model_names:
            return self._get_cached_model(
                model_name=model_name, thinking=thinking, temperature=temperature
            )

        name = self.model_names[self.current_index]
        return self._get_cached_model(
            model_name=name, thinking=thinking, temperature=temperature
        )

    def rotate(self):
        """切换到下一个模型（用于故障切换）"""
        self.current_index = (self.current_index + 1) % len(self.model_names)
        logger.info(f"LLM 切换到：{self.model_names[self.current_index]}")

    def _get_cached_model(
        self,
        model_name: str,
        thinking: dict | None = None,
        temperature: float | None = None,
    ) -> BaseChatModel:
        parts = [model_name]
        if thinking:
            parts.append(json.dumps(thinking, sort_keys=True))
        if temperature is not None:
            parts.append(f"temperature={temperature}")
        cache_key = ":".join(parts)
        if cache_key not in self._cache:
            self._cache[cache_key] = self._create_model(
                model_name=model_name, thinking=thinking, temperature=temperature
            )
        return self._cache[cache_key]

    def _create_model(
        self,
        model_name: str,
        thinking: dict | None = None,
        temperature: float | None = None,
    ) -> BaseChatModel:
        """根据模型名称创建模型实例，使用 OpenAI 兼容接口（DeepSeek 等）"""
        # 这里统一使用 init_chat_model，提供商可根据模型名推断，或显式指定
        # 实际项目中可根据模型名映射到不同提供商
        kwargs: dict[str, Any] = {
            "model": model_name,
            "model_provider": "deepseek",
            "api_key": settings.deepseek_api_key,
            "temperature": temperature if temperature is not None else 0.7,
            "streaming": True,
            # 如果需要 base_url，可在配置中增加，这里暂不处理
        }
        # 思考模式配置：DeepSeek 等通过 extra_body={"thinking": {...}} 控制思考开关，
        # 例如 {"type": "disabled"} 关闭思考、{"type": "enabled"} 开启思考
        if thinking:
            kwargs["extra_body"] = {"thinking": thinking}
        # init_chat_model 的返回类型含懒加载包装 _ConfigurableModel；本项目始终
        # 显式传入 model_provider，实际返回的一定是 BaseChatModel。
        return cast(BaseChatModel, init_chat_model(**kwargs))


# 默认注册表：至少包含一个模型，可后续扩展
default_registry = LLMRegistry(model_names=["deepseek-v4-flash", "deepseek-v4-pro"])
