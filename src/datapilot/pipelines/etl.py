"""
datapilot.pipelines.etl — a batch validation pipeline built as a LangGraph graph.

    extract -> validate --(bad rows?)--> clean --> validate ... --> load

Run:  uv run python -m datapilot.pipelines.etl
"""
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

MAX_CLEANING_PASSES = 3


# --- 1. STATE -------------------------------------------------------------------
class PipelineState(TypedDict):
    rows: list[dict]                          # the data batch
    bad_rows: int                             # result of the last validation
    attempts: int                             # cleaning passes so far
    log: Annotated[list[str], operator.add]   # REDUCER: updates are APPENDED


# --- 2. NODES: receive the full state, return ONLY the keys they change ----------
def extract(state: PipelineState) -> dict:
    rows = [{"order_id": 1, "amount": 120.0}, {"order_id": 2, "amount": -35.0},
            {"order_id": 3, "amount": None}, {"order_id": 3, "amount": 80.0},
            {"order_id": 4, "amount": 42.5}]
    return {"rows": rows, "attempts": 0, "log": [f"extract: {len(rows)} rows"]}


def validate(state: PipelineState) -> dict:
    bad = sum(1 for r in state["rows"] if r["amount"] is None or r["amount"] < 0)
    return {"bad_rows": bad, "log": [f"validate: {bad} bad rows"]}


def clean(state: PipelineState) -> dict:
    # one pass fixes ONE kind of problem, so the loop is visible
    rows = state["rows"]
    if any(r["amount"] is None for r in rows):
        rows = [r for r in rows if r["amount"] is not None]
        action = "dropped NULL amounts"
    else:
        rows = [{**r, "amount": abs(r["amount"])} for r in rows]
        action = "fixed negative amounts"
    return {"rows": rows, "attempts": state["attempts"] + 1,
            "log": [f"clean #{state['attempts'] + 1}: {action}"]}


def load(state: PipelineState) -> dict:
    total = sum(r["amount"] for r in state["rows"])
    return {"log": [f"load: {len(state['rows'])} rows, total amount {total:.2f}"]}


# --- 3. ROUTER for the conditional edge: returns the NAME of the next node ---------
def route_after_validation(state: PipelineState) -> str:
    if state["bad_rows"] == 0 or state["attempts"] >= MAX_CLEANING_PASSES:  # loop guard
        return "load"
    return "clean"


# --- 4. BUILD + COMPILE -----------------------------------------------------------
def build_etl_graph():
    builder = StateGraph(PipelineState)
    builder.add_node("extract", extract)
    builder.add_node("validate", validate)
    builder.add_node("clean", clean)
    builder.add_node("load", load)

    builder.add_edge(START, "extract")
    builder.add_edge("extract", "validate")
    builder.add_conditional_edges("validate", route_after_validation, ["clean", "load"])
    builder.add_edge("clean", "validate")        # the LOOP back
    builder.add_edge("load", END)
    return builder.compile()


def main():
    graph = build_etl_graph()
    print(graph.get_graph().draw_mermaid())      # paste into https://mermaid.live

    print("\n--- stream(): each node's update as it happens ---")
    for update in graph.stream({"log": []}, stream_mode="updates"):
        node, data = next(iter(update.items()))
        print(f"   {node:<9} -> {data['log']}")


if __name__ == "__main__":
    main()