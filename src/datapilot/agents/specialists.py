"""
datapilot.agents.specialists — the data team.

Each specialist = a small ReAct agent (create_agent = the loop of agents/react.py) with
FEW tools and a FOCUSED prompt. Small local models do far better this way.

  sql_analyst       : metrics catalog + warehouse    -> answers with numbers
  quality_engineer  : quality checks + schema        -> says if data is trustworthy
  reporter          : charts + report files          -> produces deliverables
"""
from dataclasses import dataclass
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.tools import BaseTool

from datapilot.llm import get_llm

# Tools with side effects visible to others: a human must approve them.
SENSITIVE_TOOLS = {"write_report", "propose_metric"}


@dataclass
class Specialist:
    name: str
    description: str         # read by the SUPERVISOR to choose who works next
    tools: list[str]         # tool names it receives
    prompt: str              # its own system prompt


SPECIALISTS = [
    Specialist(
        name="sql_analyst",
        description="answers business questions with numbers: finds the official metric "
                    "definition, writes and runs read-only SQL on the warehouse",
        tools=["today", "list_metrics", "metric_sql", "propose_metric",
               "list_tables", "describe_table", "run_sql"],
        prompt=(
            "You are a senior SQL analyst at ShopFlow (SQLite warehouse).\n"
            "Rules:\n"
            "1. For any metric (revenue, orders, average_order_value, payment_failure_rate, "
            "active_customers), call metric_sql to get the OFFICIAL SQL, then run it with run_sql.\n"
            "2. For other questions, call describe_table first, then write SQL yourself.\n"
            "3. Call today before resolving relative dates ('last month').\n"
            "4. If a query fails, read the error, fix the SQL and retry (max 3 tries).\n"
            "Answer with the numbers in a small markdown table and show the SQL you ran."),
    ),
    Specialist(
        name="quality_engineer",
        description="checks whether data can be trusted: profiles tables, runs data "
                    "quality rules, detects anomalous days in a metric",
        tools=["profile_table", "run_quality_checks", "detect_anomalies", "describe_table"],
        prompt=(
            "You are a data quality engineer. Use the tools to check the data, then report: "
            "each failed check with its number of failing rows, each anomaly with its date "
            "and z-score, and what it means for someone using this data. Be factual."),
    ),
    Specialist(
        name="reporter",
        description="produces deliverables: PNG charts from given numbers and markdown "
                    "reports for stakeholders",
        tools=["create_chart", "write_report", "list_reports"],
        prompt=(
            "You are a data reporter. Use ONLY numbers given in your task or context; never "
            "invent data. Make a chart with create_chart when numbers are given, then write a "
            "short report with write_report: summary, key numbers, the chart as "
            "![title](path), data quality caveats. Reply with the file paths."),
    ),
]


def build_specialists(tools_by_server: dict[str, list[BaseTool]],
                      human_approval: bool = False) -> dict:
    """One compiled agent per specialist, each with only its own tools."""
    llm = get_llm()
    all_tools = {t.name: t for tools in tools_by_server.values() for t in tools}
    agents = {}
    for spec in SPECIALISTS:
        tools = [all_tools[name] for name in spec.tools if name in all_tools]

        middleware = []
        if human_approval:
            # Pause BEFORE a sensitive tool runs (uses langgraph interrupt() inside).
            guarded = {t.name: {"allowed_decisions": ["approve", "reject"]}
                       for t in tools if t.name in SENSITIVE_TOOLS}
            if guarded:
                middleware.append(HumanInTheLoopMiddleware(interrupt_on=guarded))

        agents[spec.name] = create_agent(llm, tools, system_prompt=spec.prompt,
                                         middleware=middleware, name=spec.name)
    return agents