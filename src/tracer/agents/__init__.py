"""Agent backends. Both consume the same MCP tool surface and the same task
prompt; only the mind differs."""

from .base import Recorder, call_tool, to_anthropic_tools, to_ollama_tools

__all__ = [
    "Recorder",
    "anthropic_play",
    "call_tool",
    "ollama_play",
    "to_anthropic_tools",
    "to_ollama_tools",
]


def __getattr__(name: str):
    # Lazy-import the LLM backends so importing the package never pulls in
    # anthropic/httpx until a duel actually needs them.
    if name == "anthropic_play":
        from .anthropic_agent import play

        return play
    if name == "ollama_play":
        from .ollama_agent import play

        return play
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
