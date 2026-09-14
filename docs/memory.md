# 记忆与状态管理

## 概述

系统使用两种记忆机制：
1. **短期记忆**：通过 LangGraph 的 checkpointer 将对话状态持久化到 PostgreSQL，实现多轮上下文。
2. **长期记忆**：将完整的对话消息（包括 token 用量、推理内容等）保存到 `messages` 表，可随时查询历史。

## 短期记忆（Checkpointer）

- 使用 `AsyncPostgresSaver`（基于 `langgraph-checkpoint-postgres`）。
- 每次图执行时，状态通过 `thread_id` 关联并自动保存/恢复。
- 存储内容：`AgentState` 的完整快照，包括消息列表、检索发现等。

## 长期记忆（Message 表）

- 每次聊天保存用户消息和助手消息。
- 助手消息保存完整元数据：
  - `content`：回复文本
  - `reasoning_content`：推理内容（如有）
  - `token_usage`、`usage_metadata`、`response_metadata`
  - `tool_calls`、`invalid_tool_calls`
  - `model_name`、`finish_reason` 等
- 可通过 API 查询历史，供前端展示。

## 设计权衡

- 前端目前每次请求会发送完整历史，因此 checkpointer 与数据库消息可能存在冗余。未来可优化为：前端仅发送最新消息，由 checkpointer 恢复历史，数据库仅用于审计和展示。

## 清理策略

- 可设置定时任务清理过期的 checkpoint 数据（`scripts/clean_checkpoints.py` 预留）。
- 消息表可根据业务需求归档或删除。
