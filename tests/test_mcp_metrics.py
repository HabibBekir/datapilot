"""MCP server `metrics`: the official revenue removes duplicates and negative amounts."""
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from datapilot.mcp_servers.metrics import mcp
from datapilot.warehouse.access import run_query

OCTOBER = {"start_date": "2026-10-01", "end_date": "2026-10-31"}


@pytest.mark.asyncio
async def test_official_revenue_differs_from_naive(warehouse):
    async with create_connected_server_and_client_session(mcp) as client:
        res = await client.call_tool("metric_sql", {"metric": "revenue", **OCTOBER})
    official = run_query(res.content[0].text)["rows"][0][0]
    naive = run_query("SELECT ROUND(SUM(amount), 2) FROM orders WHERE status = 'paid' "
                      "AND order_date BETWEEN '2026-10-01' AND '2026-10-31'")["rows"][0][0]
    assert (naive, official) == (77208.0, 76887.0)


@pytest.mark.asyncio
async def test_unknown_metric_is_explained():
    async with create_connected_server_and_client_session(mcp) as client:
        res = await client.call_tool("metric_sql", {"metric": "profit"})
    assert "list_metrics" in res.content[0].text
    