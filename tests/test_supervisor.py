"""datapilot.agents.supervisor — the graph wiring, checked without calling any LLM."""
from datapilot.agents.supervisor import build_graph


def test_graph_has_the_team_and_the_reviewer():
    graph = build_graph({}, review=True)          # no tools needed to check the wiring
    nodes = set(graph.get_graph().nodes)
    assert {"supervisor", "sql_analyst", "quality_engineer", "reporter",
            "respond", "reviewer"} <= nodes


def test_reviewer_is_optional():
    assert "reviewer" not in set(build_graph({}).get_graph().nodes)