"""
datapilot.llm — the ONLY place that knows which language model the project uses.

ChatOllama talks to the Ollama app on your Mac (http://localhost:11434): free,
private, no API key. Switching model or provider later = changing this file only.
"""
from langchain_ollama import ChatOllama

from datapilot import settings


def get_llm(temperature: float = 0.0) -> ChatOllama:
    return ChatOllama(
        model=settings.OLLAMA_MODEL,
        temperature=temperature,          # 0 = predictable: best for SQL and tool use
        num_ctx=settings.OLLAMA_NUM_CTX,  # room for conversation + tool schemas + results
        # qwen3 can "think out loud" before answering: slow on a laptop, off by default.
        reasoning=False if settings.OLLAMA_DISABLE_THINKING else None,
    )