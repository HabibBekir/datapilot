"""
datapilot.mcp_servers.warehouse — MCP server: explore and query the warehouse SAFELY.
(stdio transport; safety layer in datapilot.warehouse.access)

STDIO: the client starts this file as a subprocess and talks over stdin/stdout.
  !! Never print() here: stdout carries the protocol.

Launch command used by clients:  python -m datapilot.mcp_servers.warehouse
"""
from mcp.server.fastmcp import FastMCP
from datapilot.warehouse.access import QueryError, connect_readonly, run_query

mcp = FastMCP("warehouse", log_level="WARNING")


@mcp.tool()
def list_tables() -> list[dict]:
    """List the warehouse tables with their row counts. Start here to explore the data."""
    con = connect_readonly()
    names = [r[0] for r in con.execute(
        "SELECT name FROM main.sqlite_master WHERE type='table' ORDER BY name")]
    result = [{"table": n, "rows": con.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0]}
              for n in names]
    con.close()
    return result


@mcp.tool()
def describe_table(table: str) -> dict | str:
    """Columns (name, type) of a table plus 3 example rows. Use before writing SQL on it."""
    con = connect_readonly()
    known = {r[0] for r in con.execute("SELECT name FROM main.sqlite_master WHERE type='table'")}
    if table not in known:
        con.close()
        return f"Unknown table '{table}'. Available: {sorted(known)}"
    columns = [{"name": r["name"], "type": r["type"]}
               for r in con.execute(f"PRAGMA table_info({table})")]
    sample = [dict(r) for r in con.execute(f"SELECT * FROM {table} LIMIT 3")] 
    con.close()
    return {"table": table, "columns": columns, "sample_rows": sample}


@mcp.tool()
def run_sql(sql: str, limit: int = 50) -> dict | str:
    """Run ONE read-only SQLite query (SELECT or WITH) and return columns and rows.
    Dates are TEXT 'YYYY-MM-DD': use strftime('%Y-%m', order_date) for months.
    Customer names and emails are masked. limit = max rows returned (up to 200)."""
    try:
        return run_query(sql, limit)
    except QueryError as e:
        # Errors go back to the model as text so it can FIX its query and retry.
        return f"Query refused or failed: {e}"


@mcp.resource("warehouse://schema")
def schema() -> str:
    """The whole schema as text: every table and its columns."""
    con = connect_readonly()
    lines = []
    for (name,) in con.execute("SELECT name FROM main.sqlite_master WHERE type='table'"):
        cols = ", ".join(f"{r['name']} {r['type']}" for r in con.execute(f"PRAGMA table_info({name})"))
        lines.append(f"{name}({cols})")
    con.close()
    return "\n".join(lines)


@mcp.prompt()
def answer_business_question(question: str) -> str:
    """Template: answer a business question with data, step by step."""
    return (f"Business question: {question}\n"
            "1. Find the official metric definition if one applies.\n"
            "2. Look at the tables you need with describe_table.\n"
            "3. Write and run the SQL with run_sql. Fix it if it fails.\n"
            "4. Answer with the numbers and the SQL you used.")


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()