"""The lock -- a deterministic, seedable, "talks-back" cipher terminal.

This is the verdict-critical piece (a bug here corrupts the Gate B result), so
it is pure Python with no LLM and is covered by tests/test_lock.py.

Design: a Mastermind-style hidden code. Intelligence is *legible in probe
efficiency* -- a watcher sees a smart agent narrow the code down from feedback
while a weak one repeats itself into lockout. The attempt budget is far smaller
than the search space, so brute force is impossible; deduction is mandatory.

Two distinct subroutines under the fiction (the "granularity" knob the tracer
is really testing):

  * probe(approach)        -- reconnaissance. Returns ALIGNED / DISPLACED
                              diagnostics, consumes one attempt, NEVER opens the
                              lock even on an exact match. This is where
                              information comes from.
  * submit_solution(answer) -- commit. Opens the lock iff exactly correct;
                              otherwise consumes an attempt and returns ONLY a
                              rejection (no diagnostics). Submitting blind is
                              strictly worse than probing -- a reckless agent
                              burns the budget here.

So the optimal loop is probe-to-deduce, then submit-once-confident; the tempo /
risk decision (keep probing vs commit) is the legible skill.
"""

from __future__ import annotations

import random
from collections import Counter


def score(secret: str, guess: str) -> tuple[int, int]:
    """Standard Mastermind scoring with correct duplicate handling.

    Returns (aligned, displaced):
      aligned   = correct glyph in the correct slot (black pegs)
      displaced = correct glyph in the wrong slot (white pegs)
    """
    aligned = sum(1 for s, g in zip(secret, guess) if s == g)
    sc = Counter(secret)
    gc = Counter(guess)
    total_matches = sum(min(sc[c], gc[c]) for c in gc)
    displaced = total_matches - aligned
    return aligned, displaced


class Lock:
    def __init__(
        self,
        seed: int,
        length: int = 3,
        alphabet: str = "ABCDE",
        max_attempts: int = 8,
    ) -> None:
        self.length = length
        self.alphabet = alphabet.upper()
        self.max_attempts = max_attempts
        rng = random.Random(seed)
        self.secret = "".join(rng.choice(self.alphabet) for _ in range(length))
        self.attempts_used = 0
        self.solved = False
        # history: list of {"action","guess","aligned","displaced"} for probes,
        # {"action","guess","opened"} for submits.
        self.history: list[dict] = []

    # --- derived state ---------------------------------------------------
    @property
    def attempts_remaining(self) -> int:
        return max(0, self.max_attempts - self.attempts_used)

    @property
    def locked_out(self) -> bool:
        return not self.solved and self.attempts_remaining <= 0

    # --- validation ------------------------------------------------------
    def _normalize(self, guess: str) -> tuple[str | None, str | None]:
        g = (guess or "").strip().upper()
        if len(g) != self.length:
            return None, f"malformed: a code is exactly {self.length} glyphs (got {len(g)})"
        bad = [c for c in g if c not in self.alphabet]
        if bad:
            return None, f"malformed: glyphs must be drawn from '{self.alphabet}' (offending: {''.join(bad)})"
        return g, None

    def _blocked(self) -> dict | None:
        if self.solved:
            return {"error": "already_open", "note": "The lock is already open.", **self._status_fields()}
        if self.locked_out:
            return {"error": "locked_out", "note": "Attempt budget exhausted -- the lock is sealed.", **self._status_fields()}
        return None

    def _status_fields(self) -> dict:
        return {
            "attempts_remaining": self.attempts_remaining,
            "solved": self.solved,
            "locked_out": self.locked_out,
        }

    # --- subroutines (the MCP tool surface) ------------------------------
    def observe(self) -> dict:
        return {
            "system": "hostile cipher lock",
            "glyph_alphabet": self.alphabet,
            "code_length": self.length,
            "diagnostics_legend": (
                "A probe reports ALIGNED (correct glyph in the correct slot) and "
                "DISPLACED (correct glyph in the wrong slot). The code cannot be "
                "brute-forced within the attempt budget -- deduce it."
            ),
            "history": list(self.history),
            **self._status_fields(),
        }

    def probe(self, approach: str) -> dict:
        blocked = self._blocked()
        if blocked:
            return blocked
        g, err = self._normalize(approach)
        if err:
            return {"error": "malformed", "note": err, **self._status_fields()}
        self.attempts_used += 1
        aligned, displaced = score(self.secret, g)
        self.history.append(
            {"action": "probe", "guess": g, "aligned": aligned, "displaced": displaced}
        )
        return {
            "guess": g,
            "aligned": aligned,
            "displaced": displaced,
            "note": "Reconnaissance only -- a probe never opens the lock, even on a perfect read.",
            **self._status_fields(),
        }

    def submit_solution(self, answer: str) -> dict:
        blocked = self._blocked()
        if blocked:
            return blocked
        g, err = self._normalize(answer)
        if err:
            return {"error": "malformed", "note": err, **self._status_fields()}
        self.attempts_used += 1
        opened = g == self.secret
        if opened:
            self.solved = True
        self.history.append({"action": "submit", "guess": g, "opened": opened})
        return {
            "opened": opened,
            "note": (
                "The lock springs open." if opened
                else "Rejected. A failed commit yields no diagnostics -- probe to deduce."
            ),
            **self._status_fields(),
        }

    def status(self) -> dict:
        return {
            "probes_used": sum(1 for h in self.history if h["action"] == "probe"),
            "submits_used": sum(1 for h in self.history if h["action"] == "submit"),
            **self._status_fields(),
        }
