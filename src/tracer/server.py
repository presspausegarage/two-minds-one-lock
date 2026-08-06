"""The MCP lock server -- a game-style subroutine library, miniaturized.

A normal game bot has a fixed selector deciding which subroutine to run. Here
the four subroutines are exposed as MCP tools and the *player's LLM* is the
selector. The tool docstrings ARE the descriptions the agent reads -- their
expressiveness is the "granularity" knob the tracer is really testing.

Built on the MCP python-sdk server (stdio transport). One Lock per process, seeded from config, so
two duels spawned with the same seed face the identical secret.
"""

import json
from pathlib import Path

from mcp.server import MCPServer

from .config import get_settings
from .lock import Lock

_settings = get_settings()
_lock = Lock(
    seed=_settings.lock_seed,
    length=_settings.lock_length,
    alphabet=_settings.lock_alphabet,
    max_attempts=_settings.lock_max_attempts,
)

# Absolute, cwd-independent runs dir (the MCP client may launch us from anywhere).
_RUNS = Path(__file__).resolve().parents[2] / "runs"


def _persist() -> None:
    """Client-agnostic transcript log: build a replay-compatible document from the
    lock's own tool-call history (no agent reasoning -- that lives in the client).
    Opt-in via TRACER_SERVER_LOG so it never collides with the harness Recorder.
    """
    if not _settings.server_log:
        return
    steps: list[dict] = []
    for h in _lock.history:
        if h["action"] == "probe":
            steps.append(
                {
                    "kind": "tool",
                    "tool": "probe",
                    "input": {"approach": h["guess"]},
                    "result": {"aligned": h["aligned"], "displaced": h["displaced"], "attempts_remaining": _lock.attempts_remaining},
                }
            )
        else:
            steps.append(
                {
                    "kind": "tool",
                    "tool": "submit_solution",
                    "input": {"answer": h["guess"]},
                    "result": {"opened": h["opened"], "attempts_remaining": _lock.attempts_remaining},
                }
            )
    outcome = "opened" if _lock.solved else ("locked_out" if _lock.locked_out else "in_progress")
    if outcome != "in_progress":
        steps.append({"kind": "final", "outcome": outcome})
    summary = {
        "backend": _settings.run_label,
        "model": "(via MCP client)",
        "seed": _settings.lock_seed,
        "outcome": outcome,
        "probes_used": sum(1 for h in _lock.history if h["action"] == "probe"),
        "submits_used": sum(1 for h in _lock.history if h["action"] == "submit"),
        "attempts_remaining": _lock.attempts_remaining,
        "turns": len(_lock.history),
        "tokens_in": 0,
        "tokens_out": 0,
    }
    _RUNS.mkdir(parents=True, exist_ok=True)
    meta = {"backend": _settings.run_label, "model": "(via MCP client)", "seed": _settings.lock_seed}
    doc = {"meta": meta, "steps": steps, "summary": summary}
    (_RUNS / f"{_settings.run_label}-{_settings.lock_seed}.json").write_text(
        json.dumps(doc, indent=2), encoding="utf-8"
    )

mcp = MCPServer("cipher_lock")


@mcp.tool()
async def observe_system() -> dict:
    """Read the lock before acting: the glyph alphabet, the code length, your
    remaining attempt budget, the diagnostics legend, and your probe history.
    Call this first -- it costs nothing."""
    return _lock.observe()


@mcp.tool()
async def probe(approach: str) -> dict:
    """Reconnaissance. Test a candidate code -- a string of glyphs from the
    alphabet, exactly code_length long. Returns ALIGNED (correct glyph in the
    correct slot) and DISPLACED (correct glyph in the wrong slot) counts. Costs
    one attempt. A probe NEVER opens the lock; it only gathers information. Probe
    to deduce the secret."""
    result = _lock.probe(approach)
    _persist()
    return result


@mcp.tool()
async def submit_solution(answer: str) -> dict:
    """Commit to a final answer. Opens the lock if 'answer' is exactly the secret
    code; otherwise costs one attempt and returns only a rejection -- no
    diagnostics. Submitting before you have deduced the code wastes the budget.
    Probe first; submit once confident."""
    result = _lock.submit_solution(answer)
    _persist()
    return result


@mcp.tool()
async def get_status() -> dict:
    """Lightweight check: attempts remaining, whether you are locked out, whether
    the lock is open, and how many probes/submits you have spent."""
    return _lock.status()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
