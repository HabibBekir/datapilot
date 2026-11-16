"""
datapilot.devtools.mcp_inspect — inspect and call any DataPilot MCP server from the terminal.

Examples:
  uv run python -m datapilot.devtools.mcp_inspect warehouse
  uv run python -m datapilot.devtools.mcp_inspect warehouse --call run_sql '{"sql": "SELECT 1"}'
  uv run python -m datapilot.devtools.mcp_inspect --url http://127.0.0.1:8765/mcp
"""
import argparse
import asyncio
import json
import sys
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


@asynccontextmanager
async def open_session(server: str | None, url: str | None):
    """Yield an initialized MCP session, over stdio (server name) or HTTP (url)."""
    if url:
        async with streamable_http_client(url) as (read, write, _session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    else:
        params = StdioServerParameters(command=sys.executable,
                                       args=["-m", f"datapilot.mcp_servers.{server}"])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


async def inspect_server(session: ClientSession) -> None:
    print("TOOLS (what the LLM will see)")
    for t in (await session.list_tools()).tools:
        args = ", ".join(t.inputSchema.get("properties", {}))
        print(f"  🔧 {t.name}({args})\n      {t.description.splitlines()[0]}")
    resources = (await session.list_resources()).resources
    templates = (await session.list_resource_templates()).resourceTemplates
    print("RESOURCES:", [str(r.uri) for r in resources] + [t.uriTemplate for t in templates])
    print("PROMPTS:  ", [p.name for p in (await session.list_prompts()).prompts])


async def call(session: ClientSession, tool: str, args: dict) -> None:
    result = await session.call_tool(tool, args)
    print(f"\n▶ {tool}({json.dumps(args)})")
    for block in result.content:     # a list result = one text block per item                
        print(block.text)



async def main_async(args) -> None:
    async with open_session(args.server, args.url) as session:
        if args.call:
            await call(session, args.call[0], json.loads(args.call[1]) if len(args.call) > 1 else {})
        else:
            await inspect_server(session)
        if args.resource:
            res = await session.read_resource(args.resource)
            print(f"\n📄 {args.resource}\n{res.contents[0].text}")


def main():
    parser = argparse.ArgumentParser(description="Inspect a DataPilot MCP server")
    parser.add_argument("server", nargs="?", choices=["warehouse", "quality", "reports", "metrics"],
                        help="stdio server to spawn (module in datapilot.mcp_servers)")
    parser.add_argument("--url", help="HTTP server URL instead, e.g. http://127.0.0.1:8765/mcp")
    parser.add_argument("--call", nargs="+", metavar=("TOOL", "JSON_ARGS"),
                        help="call one tool with JSON arguments")
    parser.add_argument("--resource", help="read a resource by URI, e.g. warehouse://schema")
    args = parser.parse_args()
    if not args.server and not args.url:
        parser.error("give a server name or --url")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()