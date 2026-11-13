"""
datapilot.agents.assistant — a conversational data assistant with persistent memory.

Run:  uv run python -m datapilot.agents.assistant [--thread kpis]
"""
import argparse

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, MessagesState, StateGraph

from datapilot import settings
from datapilot.llm import get_llm

SYSTEM_PROMPT = ("You are DataPilot, a concise assistant for data analysts. "
                 "You explain SQL, metrics and data quality clearly.")


def build_assistant_graph(checkpointer=None):
    llm = get_llm(temperature=0.3)
    system = SystemMessage(SYSTEM_PROMPT)

    def chatbot(state: MessagesState) -> dict:
        # state["messages"] = the WHOLE history of this thread, restored by the checkpointer
        return {"messages": [llm.invoke([system] + state["messages"])]}

    builder = StateGraph(MessagesState)
    builder.add_node("chatbot", chatbot)
    builder.add_edge(START, "chatbot")
    builder.add_edge("chatbot", END)
    return builder.compile(checkpointer=checkpointer)


def main():
    parser = argparse.ArgumentParser(description="DataPilot chat assistant")
    parser.add_argument("--thread", default="default", help="conversation id")
    args = parser.parse_args()
    config = {"configurable": {"thread_id": args.thread}}

    # SqliteSaver holds a DB connection -> use it as a context manager
    with SqliteSaver.from_conn_string(str(settings.MEMORY_DB)) as checkpointer:
        graph = build_assistant_graph(checkpointer)
        saved = graph.get_state(config).values.get("messages", [])
        print(f"Model: {settings.OLLAMA_MODEL} | thread '{args.thread}' | "
              f"{len(saved)} messages in memory\nCommands: /history  /quit\n")

        while True:
            user = input("you> ").strip()
            if user in {"", "/quit"}:
                break
            if user == "/history":
                for m in graph.get_state(config).values.get("messages", []):
                    print(f"  [{m.type}] {m.text[:80]}")
                continue
            print("datapilot> ", end="", flush=True)
            # send ONLY the new message; the checkpointer restores the rest
            for chunk, _meta in graph.stream({"messages": [("user", user)]}, config,
                                             stream_mode="messages"):
                print(chunk.text, end="", flush=True)
            print("\n")


if __name__ == "__main__":
    main()