import os

import pytest
from fastapi.testclient import TestClient

# 在导入应用前设置测试环境变量
os.environ["DATABASE_URL"] = "sqlite:///./test.db"  # 使用 SQLite 避免需要 PostgreSQL
os.environ["SECRET_KEY"] = "test-secret-key"
# 测试环境显式提供统一 LLM 配置，避免依赖开发者本地 .env。
os.environ["LLM_PROVIDER"] = "deepseek"
os.environ["LLM_API_KEY"] = "test-llm-key"
os.environ["LLM_MODELS"] = "deepseek-flash,deepseek-v4-pro"
os.environ["LLM_DEFAULT_MODEL"] = "deepseek-flash"
os.environ["LLM_FAST_MODEL"] = "deepseek-flash"
os.environ["LLM_TEXT2SQL_MODEL"] = "deepseek-flash"
os.environ["LLM_DEFAULT_TEMPERATURE"] = "0.7"
os.environ["LLM_MODEL_ALIASES"] = '{"deepseek-v4-flash":"deepseek-flash"}'
# 测试环境显式允许线上前端，确保 CORS 不依赖代码默认值。
os.environ["CORS_ALLOWED_ORIGINS"] = "https://ai.lihaichao.cn"

# 导入应用（需在环境变量设置后）
from app.main import app
from app.services.database import init_db

# 创建所有表（测试环境）
init_db()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
