"""
datapilot.agents.analyst — ONE agent connected to ALL the MCP servers (baseline).

Kept as a baseline to compare with the supervisor team: a small local model with
13 tools and a multi-step request gets confused (wrong tool, skipped steps,
invented numbers). The team in agents/supervisor.py fixes that.

Run:  uv run python -m datapilot.agents.analyst      (metrics server must be running)
"""
import asyncio

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from datapilot.agents.mcp_client import load_tools, text
from datapilot.llm import get_llm

SYSTEM_PROMPT = ("You are DataPilot, a data analyst for ShopFlow. Use metric_sql for official metrics, run_sql to query, the quality tools to check data, and the reports tools for charts and reports. Never invent numbers.")


async def build_analyst():
    tools_by_server = await load_tools()
    all_tools = [t for tools in tools_by_server.values() for t in tools]
    for server, tools in tools_by_server.items():
        print(f"  {server:<10} {[t.name for t in tools]}")
    print(f"-> {len(all_tools)} tools for ONE agent\n")
    return create_agent(get_llm(), all_tools, system_prompt=SYSTEM_PROMPT,
                        checkpointer=InMemorySaver())


async def main():
    agent = await build_analyst()
    config = {"configurable": {"thread_id": "analyst"}, "recursion_limit": 30}
    while (user := input("you> ").strip()) not in {"", "/quit"}:
        async for update in agent.astream({"messages": [("user", user)]}, config,
                                          stream_mode="updates"):
            for _node, data in update.items():
                for msg in (data or {}).get("messages", []):
                    if msg.type == "tool":
                        print(f"   ↳ {msg.name}: {text(msg.content)[:110]!r}")
                    elif getattr(msg, "tool_calls", None):
                        for tc in msg.tool_calls:
                            print(f"  {tc['name']}({str(tc['args'])[:120]})")
                    elif msg.type == "ai":
                        print(f"\ndatapilot> {msg.text}\n")


if __name__ == "__main__":
    asyncio.run(main())