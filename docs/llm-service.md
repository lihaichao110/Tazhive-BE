# LLM 服务设计

## 概述

LLM 服务负责管理与大语言模型的交互，支持多提供商、多模型、自动容灾和令牌统计。当前实现以 OpenAI 兼容 API 为主，可扩展支持 Anthropic、通义千问等。

## 组件

### LLMRegistry (`app/services/llm/registry.py`)

- 维护一个模型名称列表。
- 提供 `get_model(model_name=None)` 方法，返回当前模型实例。
- 支持轮询（`rotate()`），用于故障切换。
- 模型缓存：避免重复创建实例。

### 节点调用 (`app/core/langgraph/nodes/llm_call.py`)

- 从状态中获取模型名和系统提示。
- 调用 `model.ainvoke()` 获取完整响应。
- 记录 token 用量指标（Prometheus）。

## 多模型容灾流程

1. 默认使用注册表中的第一个模型。
2. 调用失败时，触发 `rotate()` 切换到下一个模型。
3. 使用 `tenacity` 进行指数退避重试。
4. 若所有模型均失败，抛出异常。

## 扩展指南

- 添加新提供商：在 `_create_model` 中根据模型名或配置选择不同 `model_provider`。
- 添加 API Key 管理：可在配置中增加多个密钥，按模型分配。
- 接入 Langfuse 自动追踪：使用 LangChain 回调集成。

## 相关配置

- `OPENAI_API_KEY`：OpenAI 兼容 API 密钥。
- `ANTHROPIC_API_KEY`：Anthropic API 密钥（预留）。
- `QWEN_API_KEY`：通义千问 API 密钥（预留）。