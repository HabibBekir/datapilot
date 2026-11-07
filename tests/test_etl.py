"""datapilot.pipelines.etl — the validation loop runs until the batch is clean."""
from datapilot.pipelines.etl import build_etl_graph


def test_pipeline_cleans_then_loads():
    final = build_etl_graph().invoke({"log": []})
    assert final["bad_rows"] == 0
    assert final["attempts"] == 2                      # two cleaning passes
    assert final["log"][-1] == "load: 4 rows, total amount 277.50"