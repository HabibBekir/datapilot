"""MCP server `reports` writes charts and reports inside the reports folder only."""
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from datapilot import settings
from datapilot.mcp_servers.reports import mcp


@pytest.mark.asyncio
async def test_chart_and_report_are_written():
    async with create_connected_server_and_client_session(mcp) as client:
        chart = await client.call_tool("create_chart", {
            "title": "Weekly revenue", "chart_type": "bar",
            "labels": ["W41", "W42"], "values": [23008, 6222]})
        report = await client.call_tool("write_report", {
            "title": "../../Revenue drop", "markdown": "Payment outage."})
    assert chart.content[0].text.endswith("charts/weekly-revenue.png")
    report_path = report.content[0].text
    assert report_path.startswith(str(settings.REPORTS_DIR))   # no path traversal
    assert report_path.endswith("-revenue-drop.md")


@pytest.mark.asyncio
async def test_mismatched_data_is_refused():
    async with create_connected_server_and_client_session(mcp) as client:
        res = await client.call_tool("create_chart", {
            "title": "x", "chart_type": "bar", "labels": ["a", "b"], "values": [1]})
    assert res.content[0].text.startswith("Error")