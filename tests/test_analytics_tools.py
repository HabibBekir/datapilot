"""datapilot.agents.analytics_tools — tools are plain functions: test them directly."""
from datapilot.agents.analytics_tools import mean_and_std, percent_change, z_score


def test_percent_change():
    assert percent_change.invoke({"old": 100, "new": 80}) == -20.0


def test_outage_week_is_an_anomaly():
    stats = mean_and_std.invoke({"values": [20477, 17602, 21780, 23113]})
    z = z_score.invoke({"value": 6222, **stats})
    assert z < -3