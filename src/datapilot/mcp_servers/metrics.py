"""
datapilot.mcp_servers.metrics — metrics catalog, a mini SEMANTIC LAYER (HTTP transport).

Why HTTP and not stdio? The catalog is SHARED by the whole team: it runs as a
standalone service at a URL, and many clients connect to it at the same time.

Start it in its own terminal and leave it running:
    uv run python -m datapilot.mcp_servers.metrics   (or: uv run datapilot metrics-server)
It listens on settings.METRICS_URL (default http://127.0.0.1:8765/mcp)
"""
import sqlite3
from datetime import date
from typing import Literal

from mcp.server.fastmcp import FastMCP

from datapilot import settings

mcp = FastMCP("metrics", host=settings.METRICS_HOST, port=settings.METRICS_PORT,
              log_level="WARNING")

# Shared cleaning step: removes the duplicated rows and the negative amounts.
CLEAN_ORDERS = ("clean_orders AS (SELECT DISTINCT order_id, customer_id, order_date, "
                "status, amount FROM orders WHERE amount >= 0)")

DEFAULT_METRICS = [
    # name, description, SQL expression, filter, unit
    ("revenue", "Money collected: sum of amounts of PAID orders (deduplicated, no negatives).", "ROUND(SUM(amount), 2)", "status = 'paid'", "EUR"),
    ("orders", "Number of distinct orders, whatever their status.", "COUNT(DISTINCT order_id)", "1 = 1", "orders"),
    ("average_order_value", "Revenue divided by the number of paid orders.", "ROUND(SUM(amount) / COUNT(DISTINCT order_id), 2)", "status = 'paid'", "EUR"),
    ("payment_failure_rate", "Share of orders whose payment failed (0 to 1).", "ROUND(AVG(status = 'failed'), 4)", "1 = 1", "ratio"),
    ("active_customers", "Distinct customers with at least one paid order.", "COUNT(DISTINCT customer_id)", "status = 'paid'", "customers"),
]

GROUPINGS = {
    "day": "o.order_date",
    "week": "strftime('%Y-W%W', o.order_date)",
    "month": "strftime('%Y-%m', o.order_date)",
    "country": "COALESCE(c.country, 'Unknown')",
}


def db() -> sqlite3.Connection:
    con = sqlite3.connect(settings.METRICS_DB)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS metrics(
        name TEXT PRIMARY KEY, description TEXT, expression TEXT, filter TEXT,
        unit TEXT, status TEXT DEFAULT 'official')""")
    if con.execute("SELECT COUNT(*) FROM metrics").fetchone()[0] == 0:
        con.executemany("INSERT INTO metrics(name, description, expression, filter, unit) "
                        "VALUES (?,?,?,?,?)", DEFAULT_METRICS)
        con.commit()
    return con


@mcp.tool()
def today() -> str:
    """Today's date (YYYY-MM-DD). Use it to resolve 'last month', 'this week'..."""
    return date.today().isoformat()


@mcp.tool()
def list_metrics() -> list[dict]:
    """List the metrics of the catalog with their description, unit and status."""
    with db() as con:
        return [dict(r) for r in con.execute(
            "SELECT name, description, unit, status FROM metrics ORDER BY name")]


@mcp.tool()
def metric_sql(metric: str,
               group_by: Literal["day", "week", "month", "country"] | None = None,
               start_date: str | None = None, end_date: str | None = None) -> str:
    """Build the OFFICIAL SQL for a metric, optionally grouped and filtered by dates
    (YYYY-MM-DD, inclusive). It does not run it: pass the result to run_sql."""
    with db() as con:
        m = con.execute("SELECT * FROM metrics WHERE name = ?", (metric,)).fetchone()
    if not m:
        return f"Unknown metric '{metric}'. Call list_metrics to see the catalog."
    where = [m["filter"]]
    if start_date:
        where.append(f"o.order_date >= '{date.fromisoformat(start_date)}'")
    if end_date:
        where.append(f"o.order_date <= '{date.fromisoformat(end_date)}'")
    select = f"{m['expression']} AS {m['name']}"
    sql = f"WITH {CLEAN_ORDERS}\nSELECT "
    if group_by:
        sql += f"{GROUPINGS[group_by]} AS {group_by}, "
    sql += f"{select}\nFROM clean_orders o"
    if group_by == "country":
        sql += "\nLEFT JOIN customers c ON c.customer_id = o.customer_id"
    sql += "\nWHERE " + " AND ".join(where)
    if group_by:
        sql += f"\nGROUP BY {group_by}\nORDER BY {group_by}"
    return sql


@mcp.tool()
def propose_metric(name: str, description: str, expression: str,
                   filter: str = "1 = 1", unit: str = "") -> str:
    """Add a NEW metric to the shared catalog with status 'proposed' (a human reviews it).
    expression = SQL aggregate on clean_orders columns, e.g. 'SUM(amount)'."""
    try:
        with db() as con:
            con.execute("INSERT INTO metrics VALUES (?,?,?,?,?, 'proposed')",
                        (name, description, expression, filter, unit))
    except sqlite3.IntegrityError:
        return f"A metric named '{name}' already exists."
    return f"Metric '{name}' proposed. It will become official after review."


@mcp.resource("metrics://catalog")
def catalog() -> str:
    """The full catalog with each metric's SQL expression and filter."""
    with db() as con:
        rows = con.execute("SELECT * FROM metrics ORDER BY name").fetchall()
    return "\n".join(f"{r['name']} [{r['status']}] = {r['expression']} WHERE {r['filter']}"
                     f" ({r['unit']}): {r['description']}" for r in rows)


def main():
    db().close()   
    print(f"Metrics catalog MCP server on {settings.METRICS_URL}  (Ctrl+C to stop)")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()