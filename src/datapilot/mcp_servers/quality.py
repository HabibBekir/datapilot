"""
datapilot.mcp_servers.quality — MCP server for data quality (stdio transport).

The checks a data engineer runs BEFORE trusting a number:

  profile_table      -> per column: nulls, distinct values, min, max
  run_quality_checks -> declared rules (unique, not null, ranges, accepted values)
                        = the same idea as dbt tests or Great Expectations
  detect_anomalies   -> days whose value is far from the recent normal (z-score)

Notice: rules are DATA (the RULES dict), not code. Adding a check = adding a line.
"""
import statistics
from typing import Literal

from mcp.server.fastmcp import FastMCP

from datapilot.warehouse.access import connect_readonly

mcp = FastMCP("quality", log_level="WARNING")

# (check name, SQL counting the rows that BREAK the rule)
RULES: dict[str, list[tuple[str, str]]] = {
    "orders": [
        ("order_id is unique",
         "SELECT COUNT(*) FROM (SELECT order_id FROM orders GROUP BY order_id HAVING COUNT(*) > 1)"),
        ("amount is not negative", "SELECT COUNT(*) FROM orders WHERE amount < 0"),
        ("status in (paid, refunded, failed)",
         "SELECT COUNT(*) FROM orders WHERE status NOT IN ('paid', 'refunded', 'failed')"),
        ("customer_id exists in customers",
         "SELECT COUNT(*) FROM orders o LEFT JOIN customers c USING (customer_id) "
         "WHERE c.customer_id IS NULL"),
    ],
    "customers": [
        ("country is not null", "SELECT COUNT(*) FROM customers WHERE country IS NULL"),
        ("email is unique",
         "SELECT COUNT(*) FROM (SELECT email FROM main.customers GROUP BY email HAVING COUNT(*) > 1)"),
    ],
    "order_items": [
        ("quantity is positive", "SELECT COUNT(*) FROM order_items WHERE quantity <= 0"),
        ("order_id exists in orders",
         "SELECT COUNT(*) FROM order_items i LEFT JOIN (SELECT DISTINCT order_id FROM orders) o "
         "USING (order_id) WHERE o.order_id IS NULL"),
    ],
}

# Daily series the anomaly detector can watch
SERIES = {
    "revenue": "SUM(CASE WHEN status = 'paid' AND amount > 0 THEN amount ELSE 0 END)",
    "orders": "COUNT(DISTINCT order_id)",
    "failure_rate": "ROUND(AVG(status = 'failed'), 3)",
}


@mcp.tool()
def profile_table(table: Literal["orders", "customers", "products", "order_items"]) -> dict:
    """Profile every column of a table: null count and %, distinct values, min and max."""
    con = connect_readonly()
    total = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    columns = [r["name"] for r in con.execute(f"PRAGMA table_info({table})")]
    profile = []
    for c in columns:
        nulls, distinct, lo, hi = con.execute(
            f"SELECT SUM({c} IS NULL), COUNT(DISTINCT {c}), MIN({c}), MAX({c}) FROM {table}").fetchone()
        profile.append({"column": c, "nulls": nulls, "null_pct": round(100 * nulls / total, 2),
                        "distinct": distinct, "min": lo, "max": hi})
    con.close()
    return {"table": table, "rows": total, "columns": profile}


@mcp.tool()
def run_quality_checks(table: Literal["orders", "customers", "order_items"]) -> list[dict]:
    """Run the declared data quality rules on a table. Each result: check, status, failing_rows."""
    con = connect_readonly()
    results = []
    for name, sql in RULES[table]:
        failing = con.execute(sql).fetchone()[0]
        results.append({"check": name, "status": "PASS" if failing == 0 else "FAIL",
                        "failing_rows": failing})
    con.close()
    return results


@mcp.tool()
def detect_anomalies(metric: Literal["revenue", "orders", "failure_rate"] = "revenue",
                     threshold: float = 3.0, window_days: int = 28) -> dict:
    """Find days where the metric is abnormal compared with the previous `window_days` days.
    A day is an anomaly when |z-score| >= threshold. Returns the anomalous days, oldest first."""
    con = connect_readonly()
    series = con.execute(f"SELECT order_date, {SERIES[metric]} FROM orders "
                         "GROUP BY order_date ORDER BY order_date").fetchall()
    con.close()
    anomalies, baseline = [], [v for _, v in series[:window_days]]
    for day, value in series[window_days:]:
        past = baseline[-window_days:]          # the last `window_days` NORMAL days
        mean, std = statistics.mean(past), statistics.stdev(past)
        z = (value - mean) / std if std else 0.0
        if abs(z) >= threshold:
            anomalies.append({"date": day, "value": round(value, 2),
                              "expected": round(mean, 2), "z_score": round(z, 2)})
        else:
            baseline.append(value)   # anomalies are kept OUT of the baseline,
                                     # otherwise a 7-day outage would hide itself
    return {"metric": metric, "days_checked": len(series) - window_days,
            "threshold": threshold, "anomalies": anomalies}


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()