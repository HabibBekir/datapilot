"""
datapilot.agents.analytics_tools — small statistics tools an agent can call.

@tool turns a function into a tool. Its docstring and type hints are EXACTLY what
the model reads to decide when and how to call it: keep them short and precise.
Why tools for maths? LLMs are unreliable at arithmetic; a number must come from code.
"""
import statistics

from langchain_core.tools import tool


@tool
def percent_change(old: float, new: float) -> float:
    """Percentage change from old to new, e.g. 100 -> 80 gives -20.0."""
    return round((new - old) / old * 100, 2)


@tool
def mean_and_std(values: list[float]) -> dict:
    """Mean and standard deviation of a list of numbers."""
    return {"mean": round(statistics.mean(values), 2), "std": round(statistics.stdev(values), 2)}


@tool
def z_score(value: float, mean: float, std: float) -> float:
    """How many standard deviations a value is from the mean. |z| >= 3 is usually an anomaly."""
    return round((value - mean) / std, 2)


ANALYTICS_TOOLS = [percent_change, mean_and_std, z_score]