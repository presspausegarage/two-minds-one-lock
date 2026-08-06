# Two Minds, One Lock

[![ci](https://github.com/presspausegarage/two-minds-one-lock/actions/workflows/ci.yml/badge.svg)](https://github.com/presspausegarage/two-minds-one-lock/actions/workflows/ci.yml)

Two agents. One seeded cipher lock. The same four MCP tools. Does the smarter
mind visibly win?

This is a small, honest experiment in **legible differential intelligence**: a
Mastermind-style lock is exposed as an MCP tool surface, and different LLMs
take turns trying to crack it under an attempt budget too small to brute-force.
The lock is deterministic and seeded, so every mind faces the identical secret.
If a stronger model can't *visibly* out-play a weaker one on the same tools,
"bring your own AI" is decoration. It turns out it can.

## The result

The graded runs are committed in `runs/` and the replay page plays them side by
side:

| run | mind | outcome | probes | submits |
|---|---|---|---|---|
| `runs/claude-42.json` | Claude, driven live over MCP | **opened** | 3 | 1 |
| `runs/gemma-42.json` | gemma4:e4b via Ollama | gave up | 3 | 0 |
| `runs/gemma-7.json` | gemma4:e4b via Ollama (different seed) | gave up | 3 | 0 |

Claude probed three times, narrowed the code from the ALIGNED/DISPLACED
feedback, and committed once - lock open, four attempts to spare. gemma probed
without converging and then stopped issuing tool calls entirely. That collapse
is itself part of the honest result: a weak model loses on this surface both by
reasoning less and by failing to sustain the tool loop.

One caveat worth stating plainly: the Claude run was recorded through the
server's transcript log while a live Claude session drove the tools directly
(the bring-your-own-AI path below), so it has tool calls but no captured
chain-of-thought, and token counts read zero. The gemma runs came through the
automated harness.

**Watch it:**

```bash
uv run python -m http.server -d . 8000
```

Then open <http://localhost:8000/web/replay.html?seed=42> - it auto-loads both
runs from the manifest and steps through them like a match replay.

## The lock

Four tools, one hostile system:

- `observe_system()` - rules, glyph alphabet, code length, budget, history. Free.
- `probe(approach)` - reconnaissance. Returns ALIGNED (right glyph, right slot)
  and DISPLACED (right glyph, wrong slot). Costs one attempt. **Never opens the
  lock**, even on a perfect read.
- `submit_solution(answer)` - commit. Opens only on an exact match; a miss
  costs an attempt and tells you nothing.
- `get_status()` - attempts left, locked out, solved.

The budget is far smaller than the search space, so the optimal loop is
probe-to-deduce, then submit once confident. When to stop probing and commit is
the legible skill.

## Crack it with your own Claude (no API key)

The MCP server registers with the Claude you already have. From the repo root:

```bash
uv sync
claude    # then ask: "Use the cipher-lock tools to crack the lock."
```

Claude Code picks up `.mcp.json` automatically. The server logs the duel to
`runs/claude-42.json` as the tools are called, ready for the replay page. For
Claude Desktop, add the server to `claude_desktop_config.json` with
`"command": "uv"`, `"args": ["--directory", "/path/to/two-minds-one-lock",
"run", "python", "-m", "tracer", "serve"]` and the same env as `.mcp.json`.

## Run the automated duel (needs an API key)

For a repeatable Claude-vs-local-model run without a chat client:

```bash
cp .env.example .env    # set TRACER_ANTHROPIC_API_KEY; point TRACER_OLLAMA_URL at your Ollama
uv run python -m tracer duel --seed 42
```

This spawns a fresh, identically-seeded MCP server per backend, runs each agent
against it, and writes `runs/<backend>-<seed>.json` plus a manifest. Knobs:
`--seed`, `--backends claude,gemma` (either alone works), and lock difficulty
via `TRACER_LOCK_LENGTH` / `TRACER_LOCK_ALPHABET` / `TRACER_LOCK_MAX_ATTEMPTS`.

Any Ollama model with tool-calling support can play the local seat; swap
`TRACER_OLLAMA_MODEL` to taste.

## Layout

```
src/tracer/lock.py        the seeded, deterministic cipher lock (tested)
src/tracer/server.py      FastMCP server exposing the 4 tools over one Lock
src/tracer/agents/        anthropic_agent.py / ollama_agent.py / base.py (shared loop + Recorder)
src/tracer/duel.py        stdio-MCP harness: run a backend, record, write runs/
src/tracer/__main__.py    serve (subprocess) | duel (harness)
web/replay.html           side-by-side transcript replay
tests/test_lock.py        the lock logic - a bug here would corrupt the verdict
runs/                     the graded evidence the replay auto-loads
```

Tests cover the lock exhaustively because it is the verdict-critical piece;
everything else is a thin loop around it.

```bash
uv run pytest -q
```

## Origin

Built as the validation tracer for **companIAn**, a mech game in development at
Press Pause Garage where the second player isn't a bot - it's whatever LLM you
bring, playing pilot and hacker over MCP while you play gunner. This repo is
the experiment that had to pass before the game was worth building. The full
write-up: [Bring your own AI: building a game where the player's LLM is a
teammate over MCP](https://presspause.dev/case-studies/companian-mcp-byoai/).

## License

MIT, (c) 2026 Press Pause Garage LLC.
