"""API 层模型默认值、别名归一化和白名单校验测试。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.agents import create_agent
from app.api.v1.chat import chat
from app.core.config import settings
from app.schemas.agent import AgentCreate
from app.schemas.chat import ChatRequest


def test_create_agent_uses_unified_defaults():
    """未指定模型参数时，API 负责写入统一配置中的默认值。"""
    db = MagicMock()

    agent = create_agent(
        AgentCreate(name="默认模型 Agent"),
        current_user=SimpleNamespace(id="user-1"),
        db=db,
    )

    assert agent.model == settings.llm_default_model
    assert agent.temperature == settings.llm_default_temperature
    db.add.assert_called_once_with(agent)


def test_create_agent_rejects_unknown_model():
    """显式传入未注册模型时返回 422，且不写入数据库。"""
    db = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        create_agent(
            AgentCreate(name="非法模型 Agent", model="unknown-model"),
            current_user=SimpleNamespace(id="user-1"),
            db=db,
        )

    assert exc_info.value.status_code == 422
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_chat_rejects_unknown_model_before_graph_initialization():
    """聊天请求在构建图和开启 SSE 前完成模型白名单校验。"""
    db = MagicMock()
    db.get.return_value = SimpleNamespace(user_id="user-1")
    # 绕过限流装饰器，只验证端点自身在构建图之前执行的模型校验。
    chat_endpoint = getattr(chat, "__wrapped__", chat)

    with pytest.raises(HTTPException) as exc_info:
        await chat_endpoint(
            request=MagicMock(),
            thread_id="thread-1",
            payload=ChatRequest(
                model="unknown-model",
                messages=[{"role": "user", "content": "你好"}],
            ),
            current_user=SimpleNamespace(id="user-1"),
            db=db,
        )

    assert exc_info.value.status_code == 422
