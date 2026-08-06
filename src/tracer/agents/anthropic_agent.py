"""Capable agent: cloud Claude (Sonnet 4.6 by default) over a manual tool-use loop.

Manual loop (not the SDK tool-runner) so every step is logged into the Recorder
for grading + replay. Standard shape: create -> if stop_reason=="tool_use",
execute each tool_use via the MCP session, feed tool_result blocks back, repeat
until end_turn / win / lockout. Adaptive thinking is on; the assistant content
(including thinking blocks) is passed back unchanged each turn.
"""

from __future__ import annotations

import json
from typing import Any

import anthropic

from .base import (
    KICKOFF,
    TASK_PROMPT,
    Recorder,
    call_tool,
    is_dead,
    is_won,
    to_anthropic_tools,
)


async def play(session: Any, mcp_tools: list[Any], rec: Recorder, settings: Any) -> None:
    if not settings.anthropic_api_key:
        rec.note("no TRACER_ANTHROPIC_API_KEY set")
        rec.final("error")
        return

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    tools = to_anthropic_tools(mcp_tools)
    messages: list[dict] = [{"role": "user", "content": KICKOFF}]

    for turn in range(settings.max_turns):
        rec.turns = turn + 1
        resp = await client.messages.create(
            model=settings.capable_model,
            max_tokens=settings.capable_max_tokens,
            system=TASK_PROMPT,
            tools=tools,
            messages=messages,
            thinking={"type": "adaptive"},
        )
        rec.add_tokens(resp.usage.input_tokens, resp.usage.output_tokens)

        text_parts: list[str] = []
        think_parts: list[str] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "thinking":
                t = getattr(block, "thinking", "") or ""
                if t:
                    think_parts.append(t)
        if text_parts or think_parts:
            rec.reason("\n".join(text_parts), thinking="\n".join(think_parts) or None)

        if resp.stop_reason != "tool_use":
            rec.final("gave_up")
            return

        # Echo the assistant turn back verbatim (preserves thinking + tool_use blocks).
        messages.append({"role": "assistant", "content": resp.content})

        tool_results = []
        terminal = False
        for block in resp.content:
            if block.type != "tool_use":
                continue
            result = await call_tool(session, block.name, block.input)
            rec.tool(block.name, block.input, result)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                }
            )
            if is_won(result):
                rec.final("opened")
                return
            if is_dead(result):
                terminal = True

        messages.append({"role": "user", "content": tool_results})
        if terminal:
            rec.final("locked_out")
            return

    rec.final("max_turns")
