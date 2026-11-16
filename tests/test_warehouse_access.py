"""datapilot.warehouse.access — the safety layer refuses anything but read queries."""
import pytest

from datapilot.warehouse import access


@pytest.mark.parametrize("sql", [
    "DELETE FROM orders",
    "SELECT 1; DROP TABLE orders",
    "SELECT * FROM main.customers",
    "PRAGMA table_info(orders)",
])
def test_guard_refuses_dangerous_sql(warehouse, sql):
    with pytest.raises(access.QueryError):
        access.run_query(sql)


def test_emails_are_masked(warehouse):
    rows = access.run_query("SELECT email FROM customers", limit=5)["rows"]
    assert all("***@" in r[0] for r in rows)


def test_limit_and_truncation(warehouse):
    res = access.run_query("SELECT * FROM orders", limit=10)
    assert res["row_count"] == 10 and res["truncated"] is True