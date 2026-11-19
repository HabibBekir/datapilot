"""
datapilot.agents.supervisor — the DataPilot multi-agent graph.

  START ─► supervisor ─┬─► sql_analyst ──────┐
           ▲ ▲         ├─► quality_engineer ─┤ (each reports back)
           | └─────────┼─► reporter ─────────┘
           |           └─► respond ─► reviewer ─► END
           |                              └─ not good enough ───────┐
           └────────────────────────────────────────────────────────┘
"""
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command
from pydantic import BaseModel, Field

from datapilot.agents.specialists import SPECIALISTS, build_specialists
from datapilot.llm import get_llm

MAX_STEPS = 6        # max specialist calls per user request
MAX_REVISIONS = 2    # max times the reviewer can send the work back


# STATE = the conversation + our own bookkeeping
class DataPilotState(MessagesState):
    task: str        # instruction for the next specialist
    steps: int       # specialist calls so far for this request
    revisions: int   # reviewer rejections so far for this request


# STRUCTURED OUTPUTS
class Route(BaseModel):
    """The supervisor's decision."""
    reasoning: str = Field(description="One short sentence: why this choice")
    next: Literal["sql_analyst", "quality_engineer", "reporter", "FINISH"] = Field(
        description="Who acts next, or FINISH when the request is fully handled")
    task: str = Field(description="Precise, self-contained instruction for that specialist, "
                                  "including any numbers it needs. Empty if FINISH.")


class Review(BaseModel):
    """The reviewer's verdict on the final answer."""
    approved: bool = Field(description="True if the answer fully handles the user's request")
    feedback: str = Field(description="If not approved: exactly what is missing")


def transcript(messages: list[BaseMessage], last: int = 12) -> str:
    lines = []
    for m in messages[-last:]:
        who = (m.name or ("user" if m.type == "human" else "datapilot")).upper()
        lines.append(f"{who}: {m.text}")
    return "\n\n".join(lines)


def build_graph(tools_by_server: dict[str, list[BaseTool]], *, human_approval: bool = False, review: bool = False, checkpointer=None):
    llm = get_llm()
    router = llm.with_structured_output(Route)
    reviewer_llm = llm.with_structured_output(Review)
    specialists = build_specialists(tools_by_server, human_approval=human_approval)
    team = "\n".join(f"- {s.name}: {s.description}" for s in SPECIALISTS)

    # supervisor
    async def supervisor(state: DataPilotState) -> Command:
        if state.get("steps", 0) >= MAX_STEPS: 
            return Command(goto="respond")
        decision: Route = await router.ainvoke([
            SystemMessage(
                "You lead DataPilot, the data team of ShopFlow (e-commerce). Your team:\n"
                f"{team}\n\n"
                "Read the conversation. Pick the ONE specialist who should act next and write "
                "its task. Reuse results specialists already reported; never redo finished "
                "work. Typical order: numbers (sql_analyst) -> trust (quality_engineer) -> "
                "deliverable (reporter), only the steps the user needs. Choose FINISH when "
                "the latest request is fully handled or needs no tools."),
            HumanMessage(f"CONVERSATION:\n{transcript(state['messages'])}\n\n"
                         f"Specialist calls so far for this request: {state.get('steps', 0)}"),
        ])
        if decision.next == "FINISH":
            return Command(goto="respond")
        return Command(goto=decision.next, update={"task": decision.task})

    # specialists
    def make_worker(name: str):
        agent = specialists[name]

        async def worker(state: DataPilotState) -> dict:
            # The specialist starts with a FRESH, short context: its task + recent history.
            # Its own tool-calling loop stays inside its subgraph.
            context = transcript(state["messages"], last=6)
            result = await agent.ainvoke({"messages": [HumanMessage(
                f"YOUR TASK: {state['task']}\n\nRECENT CONVERSATION (context):\n{context}")]})
            report = result["messages"][-1].text
            return {"messages": [AIMessage(content=report, name=name)],
                    "steps": state.get("steps", 0) + 1}
        return worker

    # respond
    async def respond(state: DataPilotState) -> dict:
        answer = await llm.ainvoke([
            SystemMessage("You are DataPilot. Write the final answer to the user based ONLY on "
                          "the specialists' reports. Lead with the answer and its key number, "
                          "then details in markdown. Keep numbers, SQL, file paths and data "
                          "quality caveats exactly as reported. If something failed, say so."),
            HumanMessage(transcript(state["messages"])),
        ])
        return {"messages": [AIMessage(content=answer.text, name="datapilot")]}

    # reviewer
    async def reviewer(state: DataPilotState) -> Command:
        verdict: Review = await reviewer_llm.ainvoke([
            SystemMessage("You are a demanding analytics lead. Check that DataPilot's LAST "
                          "answer fully handles the user's LATEST request with numbers backed "
                          "by the specialists' reports. Actions the user rejected count as "
                          "handled. Approve if nothing important is missing."),
            HumanMessage(transcript(state["messages"])),
        ])
        if verdict.approved or state.get("revisions", 0) >= MAX_REVISIONS:
            return Command(goto=END)
        return Command(goto="supervisor", update={
            "revisions": state.get("revisions", 0) + 1,
            "messages": [HumanMessage(f"Missing: {verdict.feedback}", name="reviewer")]})

    # wiring
    names = [s.name for s in SPECIALISTS]
    builder = StateGraph(DataPilotState)
    builder.add_node("supervisor", supervisor, destinations=(*names, "respond"))
    for name in names:
        builder.add_node(name, make_worker(name))
        builder.add_edge(name, "supervisor")            # always report back
    builder.add_node("respond", respond)
    builder.add_edge(START, "supervisor")
    if review:
        builder.add_node("reviewer", reviewer, destinations=("supervisor", END))
        builder.add_edge("respond", "reviewer")
    else:
        builder.add_edge("respond", END)
    return builder.compile(checkpointer=checkpointer)


def new_request(user_text: str) -> dict:
    """Input for one request: the message + reset the per-request counters."""
    return {"messages": [HumanMessage(user_text)], "steps": 0, "revisions": 0}