import os
import pytest
from fastapi.testclient import TestClient

# 在导入应用前设置测试环境变量
os.environ["DATABASE_URL"] = "sqlite:///./test.db"  # 使用 SQLite 避免需要 PostgreSQL
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["OPENAI_API_KEY"] = "test-openai-key"

# 导入应用（需在环境变量设置后）
from app.main import app

from app.services.database import init_db

# 创建所有表（测试环境）
init_db()

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c