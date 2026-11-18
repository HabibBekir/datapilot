"""
datapilot.agents.mcp_client — every MCP server DataPilot uses, in one place.

Same shape as the config files of Claude Desktop or Cursor: to give DataPilot a
new ability, add a server here. No agent code changes.
"""
import sys

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from datapilot import settings


def _stdio(module: str) -> dict:
    # sys.executable = the Python of your uv virtual environment
    return {"transport": "stdio", "command": sys.executable, "args": ["-m", module]}


MCP_SERVERS = {
    "warehouse": _stdio("datapilot.mcp_servers.warehouse"),
    "quality": _stdio("datapilot.mcp_servers.quality"),
    "reports": _stdio("datapilot.mcp_servers.reports"),
    # HTTP: must already be running  (uv run datapilot metrics-server)
    "metrics": {"transport": "streamable_http", "url": settings.METRICS_URL},
}


async def load_tools() -> dict[str, list[BaseTool]]:
    """Connect to every server and return its tools GROUPED BY SERVER, so each
    specialist can receive only the tools it needs."""
    client = MultiServerMCPClient(MCP_SERVERS)
    tools = {}
    for name in MCP_SERVERS:
        try:
            tools[name] = await client.get_tools(server_name=name)
        except Exception as e:
            hint = " -> start it: uv run datapilot metrics-server" if name == "metrics" else ""
            raise RuntimeError(f"MCP server '{name}' unavailable{hint}") from e
    return tools


def text(result) -> str:
    """MCP tool results arrive as content blocks [{'type': 'text', 'text': ...}]."""
    if isinstance(result, str):
        return result
    return "\n".join(b.get("text", "") for b in result if isinstance(b, dict))