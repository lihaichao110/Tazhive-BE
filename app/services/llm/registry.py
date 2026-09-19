import json
from logging import getLogger
from typing import Any, cast

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.core.config import settings

logger = getLogger(__name__)


class LLMRegistry:
    def __init__(
        self,
        model_names: list[str] | None = None,
        *,
        default_model: str | None = None,
        aliases: dict[str, str] | None = None,
    ):
        self.model_names = model_names or settings.llm_model_names
        self.default_model = default_model or settings.llm_default_model
        self.aliases = aliases if aliases is not None else settings.llm_alias_map
        self.current_index = self.model_names.index(self.default_model)
        # 模型实例缓存：key 为 (model_name, thinking 的 JSON 串)，避免每次请求都重建
        self._cache: dict[str, BaseChatModel] = {}

    def normalize_model_name(self, model_name: str | None) -> str:
        """把旧模型别名归一化，并拒绝未注册模型。"""
        if model_name is None:
            return self.model_names[self.current_index]

        normalized = self.aliases.get(model_name, model_name)
        if normalized != model_name:
            logger.warning("模型名称 %s 已弃用，自动使用 %s", model_name, normalized)
        if normalized not in self.model_names:
            raise ValueError(
                f"不支持的模型 {model_name!r}，可用模型：{', '.join(self.model_names)}"
            )
        return normalized

    def get_model(
        self,
        model_name: str | None = None,
        thinking: dict | None = None,
        temperature: float | None = None,
    ) -> BaseChatModel:
        name = self.normalize_model_name(model_name)
        return self._get_cached_model(model_name=name, thinking=thinking, temperature=temperature)

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
        """根据统一环境配置创建模型实例。"""
        kwargs: dict[str, Any] = {
            "model": model_name,
            "model_provider": settings.llm_provider,
            "api_key": settings.llm_api_key.get_secret_value(),
            "temperature": (
                temperature if temperature is not None else settings.llm_default_temperature
            ),
            "streaming": True,
        }
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        # 思考模式配置：DeepSeek 等通过 extra_body={"thinking": {...}} 控制思考开关，
        # 例如 {"type": "disabled"} 关闭思考、{"type": "enabled"} 开启思考
        if thinking:
            kwargs["extra_body"] = {"thinking": thinking}
        # init_chat_model 的返回类型含懒加载包装 _ConfigurableModel；本项目始终
        # 显式传入 model_provider，实际返回的一定是 BaseChatModel。
        return cast(BaseChatModel, init_chat_model(**kwargs))


# 默认注册表完全由环境配置构建，导入应用时即完成合法性校验。
default_registry = LLMRegistry()
