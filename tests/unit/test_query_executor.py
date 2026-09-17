"""QueryExecutor 执行层测试：真实 SQLite 执行、行数截断与类型序列化。"""

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models.product import Product
from app.services.dataquery.executor import MAX_CELL_CHARS, QueryExecutor


@pytest.fixture
def sqlite_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # 只建 products 表，避免 pgvector 等方言专属列在 SQLite 上建表失败
    SQLModel.metadata.create_all(engine, tables=[Product.__table__])
    with Session(engine) as session:
        session.add(
            Product(
                name="超长产品名称" + "长" * 300,
                terms_url="https://example.com/terms.pdf",
                classification="P1",
            )
        )
        session.add_all(
            [
                Product(name="重疾险", terms_url="https://t/1.pdf", classification="P1"),
                Product(name="医疗险", terms_url="https://t/2.pdf", classification="P2"),
                Product(name="意外险", terms_url="https://t/3.pdf", classification="P2"),
            ]
        )
        session.commit()
    return engine


def test_run_returns_serialized_rows(sqlite_engine):
    executor = QueryExecutor(engine_override=sqlite_engine)
    outcome = executor.run(
        "SELECT classification, COUNT(*) AS total FROM products "
        "WHERE name NOT LIKE '超长%' GROUP BY classification ORDER BY classification"
    )
    assert outcome.error is None
    assert outcome.columns == ["classification", "total"]
    assert outcome.rows == [["P1", 1], ["P2", 2]]
    assert outcome.truncated is False


def test_run_truncates_rows_beyond_max(sqlite_engine):
    executor = QueryExecutor(engine_override=sqlite_engine, max_rows=2)
    outcome = executor.run("SELECT name FROM products ORDER BY name")
    assert outcome.error is None
    assert len(outcome.rows) == 2
    assert outcome.truncated is True


def test_run_truncates_long_text_cells(sqlite_engine):
    executor = QueryExecutor(engine_override=sqlite_engine)
    outcome = executor.run("SELECT name FROM products WHERE name LIKE '超长%'")
    assert outcome.error is None
    cell = outcome.rows[0][0]
    assert len(cell) == MAX_CELL_CHARS + 1  # 截断标记「…」占 1 个字符
    assert cell.endswith("…")


def test_run_returns_error_for_bad_sql(sqlite_engine):
    executor = QueryExecutor(engine_override=sqlite_engine)
    outcome = executor.run("SELECT * FROM not_exists_table")
    assert outcome.error is not None
    assert "not_exists_table" in outcome.error
    assert outcome.rows == []
