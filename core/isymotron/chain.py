"""Quine Gate state chain (milestone M4).

A linear chain of states, each naming its parent and the transition that
produced it::

    GENESIS -> S1 -> S2 -> ... -> HEAD

    state.sha = sha256(canonical({"parent": <parent sha>, "transition": {...}}))

The rule the whole thing exists to enforce: *no state without a verified
parent*.

Anchoring is the load-bearing part. A chain is internally self-consistent even
if an attacker rewrites all of it, so internal consistency alone proves
nothing. The verifier therefore requires BOTH an externally anchored GENESIS
and an externally anchored HEAD, and reports them as separate properties.

Reference experiment (`.opencode/plans/quine-gate-reproducible-evidence.md`):
genesis-only verification accepted a fork and a rollback; genesis+HEAD rejected
both. When no anchor is supplied this module refuses to claim PASS
(``NOT_VERIFIABLE``) rather than fall back to internal consistency.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .canon import digest

PASS = "PASS"
REJECT = "REJECT"
CONFLICT = "CONFLICT"
NOT_VERIFIABLE = "NOT_VERIFIABLE"


def state_body(parent: str | None, transition: Mapping[str, Any]) -> dict:
    """The bytes a state's digest commits to."""
    return {"parent": parent, "transition": dict(transition)}


def make_state(parent: str | None, transition: Mapping[str, Any]) -> dict:
    """Build a state that names its parent and the transition that made it."""
    body = state_body(parent, transition)
    return {**body, "sha": digest(body)}


@dataclass(frozen=True)
class ChainVerification:
    """Each property is reported on its own. Never a global 'secure'."""

    passed: bool
    status: str
    reason: str
    length: int
    internal_ok: bool
    genesis_matched: bool
    head_matched: bool

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "status": self.status,
            "reason": self.reason,
            "length": self.length,
            "internal_ok": self.internal_ok,
            "genesis_matched": self.genesis_matched,
            "head_matched": self.head_matched,
        }


def _internal_ok(chain: Sequence[Mapping[str, Any]]) -> bool:
    prev: str | None = None
    for state in chain:
        body = {"parent": state.get("parent"), "transition": state.get("transition", {})}
        if digest(body) != state.get("sha"):
            return False
        if prev is not None and state.get("parent") != prev:
            return False
        prev = state.get("sha")
    return True


def verify_chain(chain: Sequence[Mapping[str, Any]] | None,
                 *, anchored_genesis: str | None,
                 anchored_head: str | None) -> ChainVerification:
    """Verify a chain against an externally anchored genesis and head.

    Fail-closed: without both anchors the result is ``NOT_VERIFIABLE`` and
    ``passed`` is False. A head that does not match the published one is a
    ``CONFLICT`` (fork or rollback); a genesis that does not match is a
    ``REJECT``; broken internal linkage is a ``REJECT``.
    """
    if not chain:
        return ChainVerification(False, NOT_VERIFIABLE,
                                 "empty or missing chain", 0, False, False, False)

    internal = _internal_ok(chain)
    length = len(chain)

    if not internal:
        return ChainVerification(False, REJECT, "chain is not internally consistent",
                                 length, False, False, False)

    if anchored_genesis is None:
        return ChainVerification(False, NOT_VERIFIABLE,
                                 "no anchored genesis: refusing to claim validity",
                                 length, True, False, False)
    genesis_matched = chain[0].get("sha") == anchored_genesis
    if not genesis_matched:
        return ChainVerification(False, REJECT, "chain genesis is not the anchored one",
                                 length, True, False, False)

    if anchored_head is None:
        return ChainVerification(False, NOT_VERIFIABLE,
                                 "no anchored HEAD: genesis-only cannot detect fork/rollback",
                                 length, True, True, False)
    head_matched = chain[-1].get("sha") == anchored_head
    if not head_matched:
        return ChainVerification(False, CONFLICT,
                                 "chain head is not the published HEAD (fork or rollback)",
                                 length, True, True, False)

    return ChainVerification(True, PASS, "chain matches anchored genesis and HEAD",
                             length, True, True, True)


def load_anchor(path: str | Path, field: str) -> str | None:
    """Read one anchor value from a JSON file. Missing/broken -> None, which
    the verifier treats as NOT_VERIFIABLE, never as a wildcard."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    value = data.get(field) if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else None
