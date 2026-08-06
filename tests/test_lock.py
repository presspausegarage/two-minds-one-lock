"""Tests for the verdict-critical lock. A bug here would corrupt the Gate B grade."""

from tracer.lock import Lock, score


def test_score_no_duplicates():
    assert score("ABC", "ABC") == (3, 0)
    assert score("ABC", "CAB") == (0, 3)
    assert score("ABC", "AXC") == (2, 0)
    assert score("ABC", "XXX") == (0, 0)


def test_score_with_duplicates():
    # secret has one A; guess has two A's, one aligned -> 1 aligned, 0 displaced.
    assert score("ABC", "AAD") == (1, 0)
    # secret AAB, guess ABA: slot0 A aligned; the other A is displaced; B displaced.
    assert score("AAB", "ABA") == (1, 2)
    assert score("AABB", "BBAA") == (0, 4)


def test_seed_is_deterministic():
    a = Lock(seed=42, length=4, alphabet="ABCDEF")
    b = Lock(seed=42, length=4, alphabet="ABCDEF")
    assert a.secret == b.secret  # "One Lock": both agents face the identical secret
    c = Lock(seed=43, length=4, alphabet="ABCDEF")
    assert c.secret != a.secret  # seeds 42 and 43 are known to differ at this length/alphabet


def test_probe_gives_feedback_consumes_budget_never_opens():
    lock = Lock(seed=1, length=3, alphabet="ABCDE", max_attempts=8)
    secret = lock.secret
    r = lock.probe(secret)  # probing the exact code...
    assert r["aligned"] == 3
    assert r["displaced"] == 0
    assert r["solved"] is False  # ...does NOT open the lock
    assert lock.attempts_remaining == 7


def test_submit_correct_opens():
    lock = Lock(seed=2, length=3, alphabet="ABCDE", max_attempts=8)
    r = lock.submit_solution(lock.secret)
    assert r["opened"] is True
    assert lock.solved is True
    assert "aligned" not in r  # submit never leaks diagnostics


def test_submit_wrong_burns_budget_no_diagnostics():
    lock = Lock(seed=3, length=3, alphabet="ABCDE", max_attempts=8)
    wrong = "".join("A" if c != "A" else "B" for c in lock.secret)
    r = lock.submit_solution(wrong)
    assert r["opened"] is False
    assert "aligned" not in r and "displaced" not in r
    assert lock.attempts_remaining == 7


def test_lockout_after_budget_exhausted():
    lock = Lock(seed=4, length=3, alphabet="ABCDE", max_attempts=2)
    # use a definitely-wrong-but-valid code
    valid_wrong = next(
        g for g in ("AAA", "BBB", "CCC", "DDD", "EEE") if g != lock.secret
    )
    lock.probe(valid_wrong)
    lock.probe(valid_wrong)
    assert lock.locked_out is True
    r = lock.probe(valid_wrong)
    assert r["error"] == "locked_out"
    assert lock.attempts_remaining == 0


def test_malformed_does_not_burn_budget():
    lock = Lock(seed=5, length=3, alphabet="ABCDE", max_attempts=8)
    r = lock.probe("TOOLONG")
    assert r["error"] == "malformed"
    assert lock.attempts_remaining == 8  # malformed input is free -- only valid attempts cost
    r2 = lock.probe("XYZ")  # glyphs out of alphabet
    assert r2["error"] == "malformed"
    assert lock.attempts_remaining == 8


def test_status_counts():
    lock = Lock(seed=6, length=3, alphabet="ABCDE", max_attempts=8)
    valid = next(g for g in ("AAA", "BBB", "CCC") if g != lock.secret)
    lock.probe(valid)
    lock.submit_solution(valid)
    s = lock.status()
    assert s["probes_used"] == 1
    assert s["submits_used"] == 1
