"""text2sql SQL 静态校验（guard）规则的单元测试。"""

from app.services.dataquery.guard import validate_sql


def assert_ok(sql: str, **kwargs) -> str:
    normalized, error = validate_sql(sql, **kwargs)
    assert error is None, f"预期校验通过，实际错误：{error}"
    return normalized.upper()


def assert_fail(sql: str) -> str:
    _, error = validate_sql(sql)
    assert error is not None, f"预期校验失败，实际通过：{sql}"
    return error


class TestReadOnlyEnforcement:
    def test_simple_select_passes_and_limit_injected(self):
        normalized = assert_ok("SELECT COUNT(*) FROM products", max_rows=10)
        assert "LIMIT 10" in normalized

    def test_cte_and_union_pass(self):
        normalized = assert_ok(
            "WITH t AS (SELECT id FROM products) SELECT * FROM t UNION ALL SELECT id FROM plan_shows",
            max_rows=10,
        )
        assert "LIMIT 10" in normalized

    def test_insert_rejected(self):
        assert "仅允许" in assert_fail("INSERT INTO products (name) VALUES ('x')")

    def test_update_rejected(self):
        assert_fail("UPDATE products SET name = 'x'")

    def test_delete_rejected(self):
        assert_fail("DELETE FROM products")

    def test_drop_rejected(self):
        assert_fail("DROP TABLE products")

    def test_set_statement_rejected(self):
        assert_fail("SET statement_timeout = 0")

    def test_write_inside_cte_rejected(self):
        error = assert_fail("WITH t AS (DELETE FROM products RETURNING *) SELECT * FROM t")
        assert "DELETE" in error

    def test_multiple_statements_rejected(self):
        assert "单条" in assert_fail("SELECT 1 FROM products; SELECT 2 FROM products")

    def test_unparseable_rejected(self):
        assert "解析失败" in assert_fail("SELECT ~~ FROM products")


class TestTableWhitelist:
    def test_users_table_rejected(self):
        error = assert_fail("SELECT * FROM users")
        assert "users" in error

    def test_quoted_table_rejected(self):
        assert_fail('SELECT * FROM "USERS"')

    def test_uppercase_allowed_table_passes(self):
        assert_ok("SELECT id FROM Products", max_rows=10)

    def test_system_catalog_rejected(self):
        assert_fail("SELECT * FROM pg_catalog.pg_tables")

    def test_cross_join_allowed_tables_passes(self):
        assert_ok(
            "SELECT a.group_name FROM insurance_applications a "
            "JOIN plan_shows p ON a.group_code = p.group_code",
            max_rows=10,
        )


class TestFunctionBlacklist:
    def test_pg_sleep_rejected(self):
        assert "PG_SLEEP" in assert_fail("SELECT pg_sleep(10) FROM products").upper()

    def test_setval_rejected(self):
        assert "SETVAL" in assert_fail("SELECT setval('seq', 1)").upper()


class TestLimitEnforcement:
    def test_small_limit_kept(self):
        normalized = assert_ok("SELECT * FROM products LIMIT 3", max_rows=10)
        assert "LIMIT 3" in normalized

    def test_oversized_limit_shrunk(self):
        normalized = assert_ok("SELECT * FROM products LIMIT 1000", max_rows=10)
        assert "LIMIT 10" in normalized

    def test_empty_sql_rejected(self):
        assert "为空" in assert_fail("   ")
