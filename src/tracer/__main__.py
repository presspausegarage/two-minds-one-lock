"""CLI: `python -m tracer serve` (the MCP subprocess) and
`python -m tracer duel [--seed N] [--backends claude,gemma]` (the harness)."""

from __future__ import annotations

import argparse
import asyncio
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="tracer", description="'Two Minds, One Lock' duel harness")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("serve", help="run the MCP lock server over stdio (used as a subprocess)")

    duel = sub.add_parser("duel", help="run agents against one lock and record the transcripts")
    duel.add_argument("--seed", type=int, default=None, help="lock seed (default: TRACER_LOCK_SEED)")
    duel.add_argument(
        "--backends",
        default="claude,gemma",
        help="comma-separated agents to run (default: claude,gemma)",
    )

    args = parser.parse_args()

    if args.cmd == "serve":
        from .server import main as serve_main

        serve_main()
    elif args.cmd == "duel":
        from .duel import run_duel

        try:
            asyncio.run(run_duel(args.seed, args.backends.split(",")))
        except KeyboardInterrupt:
            sys.exit(130)


if __name__ == "__main__":
    main()
