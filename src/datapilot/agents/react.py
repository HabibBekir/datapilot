"""
datapilot.agents.react — the ReAct loop, built by hand.

Run the demo:  uv run python -m datapilot.agents.react
"""
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from datapilot.agents.analytics_tools import ANALYTICS_TOOLS
from datapilot.llm import get_llm


def build_react_agent(tools: list[BaseTool], system_prompt: str):
    llm_with_tools = get_llm().bind_tools(tools)
    system = SystemMessage(system_prompt)

    def agent(state: MessagesState) -> dict:
        return {"messages": [llm_with_tools.invoke([system] + state["messages"])]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)   # -> "tools" or END
    builder.add_edge("tools", "agent")                        # the LOOP
    return builder.compile()


def main():
    graph = build_react_agent(ANALYTICS_TOOLS, "You are a data analyst. Use the tools for "
                                               "EVERY calculation; never compute numbers yourself.")
    question = ("Weekly revenue for the 4 previous weeks was 20477, 17602, 21780 and 23113 EUR. "
                "This week it is 6222 EUR. What is the % change versus last week, "
                "and is this week an anomaly (z-score against the 4 previous weeks)?")
    # stream_mode="values" -> the whole state after each step; print the newest message
    for state in graph.stream({"messages": [("user", question)]},
                              {"recursion_limit": 15}, stream_mode="values"):
        state["messages"][-1].pretty_print()


if __name__ == "__main__":
    main()