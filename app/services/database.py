from sqlmodel import SQLModel, create_engine, Session
from app.core.config import settings

engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True)

def init_db() -> None:
    """创建所有表（仅用于开发，生产建议用 Alembic）"""
    SQLModel.metadata.create_all(engine)

def get_session():
    """FastAPI 依赖注入用"""
    with Session(engine) as session:
        yield session