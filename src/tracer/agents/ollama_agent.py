"""Weak agent: local gemma via Ollama, same tool surface, same task prompt.

Uses Ollama's native /api/chat tool-calling. Single-GPU gemma is slow (~13-17s/verdict), and a tool loop multiplies
that, so the per-call timeout is generous.

FALLBACK (documented in README): if gemma's native tool-calling proves
unreliable, swap this loop for a schema-constrained "emit next action as JSON"
loop using Ollama's format=<schema> and dispatch to MCP from here. Same tool surface, different elicitation -- which is the honest
BYO-AI reality. If gemma returns no tool_calls at all, that's recorded as
'gave_up' and is itself a meaningful signal for the grade.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from .base import (
    KICKOFF,
    TASK_PROMPT,
    Recorder,
    call_tool,
    is_dead,
    is_won,
    to_ollama_tools,
)


async def play(session: Any, mcp_tools: list[Any], rec: Recorder, settings: Any) -> None:
    tools = to_ollama_tools(mcp_tools)
    url = settings.ollama_url.rstrip("/") + "/api/chat"
    messages: list[dict] = [
        {"role": "system", "content": TASK_PROMPT},
        {"role": "user", "content": KICKOFF},
    ]

    async with httpx.AsyncClient(timeout=180.0) as http:
        for turn in range(settings.max_turns):
            rec.turns = turn + 1
            body = {
                "model": settings.ollama_model,
                "messages": messages,
                "tools": tools,
                "stream": False,
                "options": {"temperature": 0},
            }
            resp = await http.post(url, json=body)
            resp.raise_for_status()
            payload = resp.json()
            rec.add_tokens(payload.get("prompt_eval_count", 0), payload.get("eval_count", 0))

            msg = payload.get("message", {}) or {}
            content = msg.get("content", "") or ""
            tool_calls = msg.get("tool_calls") or []
            if content or tool_calls:
                rec.reason(content or "(no text; issued tool calls)")

            messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})

            if not tool_calls:
                rec.final("gave_up")
                return

            terminal = False
            for tc in tool_calls:
                fn = tc.get("function", {}) or {}
                name = fn.get("name")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                if not name:
                    rec.note("malformed tool call (no name)")
                    continue
                result = await call_tool(session, name, args)
                rec.tool(name, args, result)
                messages.append({"role": "tool", "tool_name": name, "content": json.dumps(result)})
                if is_won(result):
                    rec.final("opened")
                    return
                if is_dead(result):
                    terminal = True
            if terminal:
                rec.final("locked_out")
                return

    rec.final("max_turns")
