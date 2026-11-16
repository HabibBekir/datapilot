"""
datapilot.warehouse.access — SAFE, read-only access to the warehouse.

An agent that writes SQL must never damage data or leak personal information.
Three layers of protection, the same ideas real data platforms use:

  1. READ-ONLY connection  (SQLite URI mode=ro): INSERT/UPDATE/DELETE/DROP fail.
  2. QUERY GUARD           : one statement only, must start with SELECT or WITH,
                             row limit, time limit.
  3. PII MASKING with VIEWS: a TEMP view named `customers` hides the real table.
                             SQLite looks in the temp schema first, so every query
                             on `customers` sees masked names and emails.
"""
import re
import sqlite3

from datapilot import settings

MAX_ROWS = 200
MAX_STEPS = 5_000_000   # SQLite VM steps before a query is aborted (~ a few seconds)

MASKED_VIEWS = """
CREATE TEMP VIEW customers AS
SELECT customer_id,
       substr(name, 1, 1) || '***' AS name,
       substr(email, 1, 1) || '***@' || substr(email, instr(email, '@') + 1) AS email,
       country, signup_date
FROM main.customers;
"""


class QueryError(ValueError):
    """A query refused by the guard: the message explains why, for the agent."""


def connect_readonly(db_path=None) -> sqlite3.Connection:
    db_path = db_path or settings.WAREHOUSE_DB   # read at call time (tests can swap it)
    if not db_path.exists():
        raise FileNotFoundError(f"{db_path} not found. Run: uv run datapilot seed")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.executescript(MASKED_VIEWS) 
    # abort runaway queries: the handler is called every 1000 VM steps
    steps = {"n": 0}
    def guard():
        steps["n"] += 1000
        return steps["n"] > MAX_STEPS        # True = abort the query
    con.set_progress_handler(guard, 1000)
    return con


def check_query(sql: str) -> str:
    """Return the cleaned SQL or raise QueryError with a helpful message."""
    cleaned = sql.strip().rstrip(";").strip()
    if ";" in cleaned:
        raise QueryError("Only ONE statement is allowed (remove the ';').")
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        raise QueryError("Only read queries are allowed: start with SELECT or WITH.")
    if re.search(r"\bmain\.|sqlite_|pragma\b|attach\b", cleaned, re.IGNORECASE):
        raise QueryError("Access to main.*, sqlite_* tables, PRAGMA and ATTACH is not allowed.")
    return cleaned


def run_query(sql: str, limit: int = 50) -> dict:
    """Run a guarded query and return columns + rows (as JSON-friendly lists)."""
    cleaned = check_query(sql)
    limit = max(1, min(limit, MAX_ROWS))
    con = connect_readonly()
    try:
        cur = con.execute(cleaned)
        rows = cur.fetchmany(limit + 1)      # fetch one extra row to know if we cut
        columns = [d[0] for d in cur.description]
    except sqlite3.Error as e:
        raise QueryError(f"SQL error: {e}") from e
    finally:
        con.close()
    return {
        "columns": columns,
        "rows": [list(r) for r in rows[:limit]],
        "row_count": min(len(rows), limit),
        "truncated": len(rows) > limit,
    }