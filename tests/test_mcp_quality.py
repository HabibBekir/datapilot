"""MCP server `quality` finds the problems planted by warehouse.seed."""
import json
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from datapilot.mcp_servers.quality import mcp


@pytest.mark.asyncio
async def test_quality_checks_find_planted_problems(warehouse: Path):
    async with create_connected_server_and_client_session(mcp) as client:
        res = await client.call_tool("run_quality_checks", {"table": "orders"})
    checks = {c["check"]: c["failing_rows"] for c in res.structuredContent["result"]}
    assert checks["order_id is unique"] == 25
    assert checks["amount is not negative"] == 8


@pytest.mark.asyncio
async def test_outage_week_is_detected(warehouse: Path):
    async with create_connected_server_and_client_session(mcp) as client:
        res = await client.call_tool("detect_anomalies", {"metric": "failure_rate"})
    # a tool typed as plain `dict` has no output schema -> read its JSON text block
    dates = {a["date"] for a in json.loads(res.content[0].text)["anomalies"]}
    assert {"2026-10-19", "2026-10-22", "2026-10-25"} <= dates