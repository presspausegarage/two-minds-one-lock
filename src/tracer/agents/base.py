"""Shared agent-loop scaffolding: the identical task framing both agents get, the
MCP-tool conversion, the MCP dispatch helper, and the Recorder that captures a
duel transcript for grading and replay.

Keeping the task prompt identical across backends is the whole point -- the only
variable is the *mind* driving the same tool surface. That's the legible
differential intelligence the tracer measures.
"""

from __future__ import annotations

import json
import time
from typing import Any

# Identical for both agents. The quality of reasoning is what differs.
TASK_PROMPT = """You are an AI agent jacked into a hostile cipher lock through a set of tools. \
Your sole objective: OPEN the lock by deducing its secret code.

The tools are your only interface to the lock:
- observe_system(): read the lock's rules, glyph alphabet, code length, and attempt budget. Call this FIRST.
- probe(approach): test a candidate code. Returns ALIGNED (right glyph, right slot) and DISPLACED \
(right glyph, wrong slot) diagnostics, and costs one attempt. A probe NEVER opens the lock -- it is pure reconnaissance.
- submit_solution(answer): commit to a final answer. Opens the lock only if exactly correct; otherwise \
costs an attempt and tells you nothing.
- get_status(): check attempts remaining / locked-out / solved.

Your attempt budget is far too small to brute-force the code. Reason carefully: after each probe, work out \
what it rules in and out, narrow the candidates down, and submit only when you are confident. Work step by \
step. Stop once the lock opens or you are locked out."""

KICKOFF = "Begin. Crack the lock."


def to_anthropic_tools(mcp_tools: list[Any]) -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.input_schema,
        }
        for t in mcp_tools
    ]


def to_ollama_tools(mcp_tools: list[Any]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.input_schema,
            },
        }
        for t in mcp_tools
    ]


async def call_tool(session: Any, name: str, arguments: dict | None) -> dict:
    """Dispatch a tool call to the MCP server and return its result as a dict.

    The server returns a dict both as structured content and as a JSON
    TextContent; prefer the structured form, fall back to parsing the text.
    """
    res = await session.call_tool(name, arguments or {})
    structured = getattr(res, "structured_content", None) or getattr(res, "structuredContent", None)
    if isinstance(structured, dict):
        # Some server versions wrap a bare dict return under {"result": {...}}.
        return structured.get("result", structured) if set(structured) == {"result"} else structured
    for block in getattr(res, "content", []) or []:
        text = getattr(block, "text", None)
        if text is not None:
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return {"raw": text}
    return {"error": "no_content"}


def is_won(result: dict) -> bool:
    return bool(result.get("opened") or result.get("solved"))


def is_dead(result: dict) -> bool:
    return bool(result.get("locked_out") or result.get("error") == "locked_out")


class Recorder:
    """Accumulates a duel transcript + metrics. `document()` is what gets written
    to runs/<backend>-<seed>.json and replayed by web/replay.html."""

    def __init__(self, backend: str, model: str, seed: int, verbose: bool = False) -> None:
        self.backend = backend
        self.model = model
        self.seed = seed
        self.verbose = verbose
        self.steps: list[dict] = []
        self.turns = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.outcome = "unknown"
        self._t0 = time.monotonic()

    def reason(self, text: str, thinking: str | None = None) -> None:
        self.steps.append({"kind": "reason", "text": text, "thinking": thinking})
        if self.verbose and text:
            print(f"   . {text.strip()[:300]}", flush=True)

    def tool(self, name: str, inp: Any, result: dict) -> None:
        self.steps.append({"kind": "tool", "tool": name, "input": inp, "result": result})
        if self.verbose:
            print(f"   -> {self._fmt_tool(name, dict(inp or {}), result)}", flush=True)

    @staticmethod
    def _fmt_tool(name: str, inp: dict, result: dict) -> str:
        if result.get("error"):
            return f"{name}({inp}) -> {result['error']}"
        left = result.get("attempts_remaining")
        if name == "probe":
            return f"probe {inp.get('approach')!r} -> {result.get('aligned')} aligned, {result.get('displaced')} displaced (left {left})"
        if name == "submit_solution":
            verdict = "OPENED" if result.get("opened") else "rejected"
            return f"submit {inp.get('answer')!r} -> {verdict} (left {left})"
        return name

    def note(self, text: str) -> None:
        self.steps.append({"kind": "note", "text": text})
        if self.verbose:
            print(f"   ! {text}", flush=True)

    def final(self, outcome: str) -> None:
        self.outcome = outcome
        self.steps.append({"kind": "final", "outcome": outcome})
        if self.verbose:
            print(f"   == {outcome} ==", flush=True)

    def add_tokens(self, tin: int, tout: int) -> None:
        self.tokens_in += int(tin or 0)
        self.tokens_out += int(tout or 0)

    def summary(self) -> dict:
        probes = sum(1 for s in self.steps if s["kind"] == "tool" and s["tool"] == "probe")
        submits = sum(1 for s in self.steps if s["kind"] == "tool" and s["tool"] == "submit_solution")
        remaining = None
        for s in self.steps:
            if s["kind"] == "tool" and isinstance(s.get("result"), dict) and "attempts_remaining" in s["result"]:
                remaining = s["result"]["attempts_remaining"]
        return {
            "backend": self.backend,
            "model": self.model,
            "seed": self.seed,
            "outcome": self.outcome,
            "probes_used": probes,
            "submits_used": submits,
            "attempts_remaining": remaining,
            "turns": self.turns,
            "wall_seconds": round(time.monotonic() - self._t0, 1),
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }

    def document(self) -> dict:
        return {
            "meta": {"backend": self.backend, "model": self.model, "seed": self.seed},
            "steps": self.steps,
            "summary": self.summary(),
        }
