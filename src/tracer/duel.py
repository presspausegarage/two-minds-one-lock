"""The harness. Spawns the MCP lock server as a stdio subprocess, connects a
client, hands the tool surface to a chosen agent backend, records the duel, and
writes runs/<backend>-<seed>.json (+ a manifest the replay loads).

Each backend runs against its OWN freshly-spawned server seeded identically, so
both face the same secret ("One Lock") without sharing live state.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, stdio_client

from .agents import Recorder, anthropic_play, ollama_play
from .config import get_settings

BACKENDS = {"claude": anthropic_play, "gemma": ollama_play}


def _model_label(backend: str, settings: Any) -> str:
    return settings.capable_model if backend == "claude" else settings.ollama_model


async def run_one(backend: str, seed: int, settings: Any) -> Recorder:
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend '{backend}' (choose from {sorted(BACKENDS)})")

    env = {
        **os.environ,
        "TRACER_LOCK_SEED": str(seed),
        "TRACER_LOCK_LENGTH": str(settings.lock_length),
        "TRACER_LOCK_ALPHABET": settings.lock_alphabet,
        "TRACER_LOCK_MAX_ATTEMPTS": str(settings.lock_max_attempts),
    }
    params = StdioServerParameters(command=sys.executable, args=["-m", "tracer", "serve"], env=env)
    rec = Recorder(backend=backend, model=_model_label(backend, settings), seed=seed, verbose=True)

    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        mcp_tools = (await session.list_tools()).tools
        try:
            await BACKENDS[backend](session, mcp_tools, rec, settings)
        except Exception as exc:  # noqa: BLE001 -- a dying agent shouldn't kill the duel
            rec.note(f"agent error: {type(exc).__name__}: {exc}")
            rec.final("error")
    return rec


async def run_duel(seed: int | None, backends: list[str]) -> None:
    settings = get_settings()
    if seed is None:
        seed = settings.lock_seed

    runs = Path(settings.runs_dir)
    runs.mkdir(parents=True, exist_ok=True)

    written: dict[str, str] = {}
    summaries = []
    for raw in backends:
        backend = raw.strip()
        print(f"[..] {backend} vs lock (seed {seed}) ...", flush=True)
        rec = await run_one(backend, seed, settings)
        out = runs / f"{backend}-{seed}.json"
        out.write_text(json.dumps(rec.document(), indent=2), encoding="utf-8")
        written[backend] = out.name
        s = rec.summary()
        summaries.append(s)
        print(
            f"[OK] {backend}: outcome={s['outcome']} probes={s['probes_used']} "
            f"submits={s['submits_used']} turns={s['turns']} "
            f"tokens={s['tokens_in']}/{s['tokens_out']} -> {out}",
            flush=True,
        )

    manifest = runs / f"manifest-{seed}.json"
    manifest.write_text(json.dumps({"seed": seed, "runs": written}, indent=2), encoding="utf-8")

    print(f"\n--- duel summary (seed {seed}) ---")
    for s in summaries:
        print(
            f"  {s['backend']:7} {s['model']:22} outcome={s['outcome']:10} "
            f"probes={s['probes_used']} submits={s['submits_used']} "
            f"left={s['attempts_remaining']}"
        )
    print(
        "\nWatch the duel: open web/replay.html and load the two run files "
        f"({', '.join(written.values())})."
    )
