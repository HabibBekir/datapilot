"""MCP server `warehouse`, tested through the real protocol IN MEMORY (no subprocess)."""
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from datapilot.mcp_servers.warehouse import mcp


@pytest.mark.asyncio
async def test_tools_listed():
    async with create_connected_server_and_client_session(mcp) as client:
        names = {t.name for t in (await client.list_tools()).tools}
    assert names == {"list_tables", "describe_table", "run_sql"}


@pytest.mark.asyncio
async def test_run_sql_returns_rows(warehouse):
    async with create_connected_server_and_client_session(mcp) as client:
        res = await client.call_tool("run_sql", {"sql": "SELECT COUNT(*) FROM products"})
    # a tool returning `dict | str` is wrapped as {"result": ...} in structuredContent
    assert res.structuredContent["result"]["rows"] == [[12]]


@pytest.mark.asyncio
async def test_errors_come_back_as_text(warehouse):
    async with create_connected_server_and_client_session(mcp) as client:
        res = await client.call_tool("run_sql", {"sql": "DELETE FROM orders"})
    assert "Only read queries" in res.content[0].text