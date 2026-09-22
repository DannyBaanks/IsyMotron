"""Quine Gate — M4: anchored chains reject forks and rollbacks.

Reproduces the researcher's experiment mechanically:

- genesis-only verification is NOT_VERIFIABLE (it accepts both a fork and a
  rollback, so it must never claim validity);
- genesis + HEAD rejects a fork;
- genesis + HEAD rejects a rollback;
- a wrong genesis is REJECT;
- a chain edited without re-hashing its states is REJECT.
"""
from __future__ import annotations

from isymotron.chain import (
    CONFLICT,
    NOT_VERIFIABLE,
    PASS,
    REJECT,
    make_state,
    verify_chain,
)

GENESIS = make_state(None, {"kind": "genesis", "base": "debian-min"})
S1 = make_state(GENESIS["sha"], {"kind": "install", "artifact": "python"})
S2 = make_state(S1["sha"], {"kind": "execute", "plan": "plan7", "result": "DENY"})
CHAIN = [GENESIS, S1, S2]

# attacker rewrites the last transition (DENY -> ALLOW) and re-hashes the suffix
S2_FORK = make_state(S1["sha"], {"kind": "execute", "plan": "plan7", "result": "ALLOW"})
FORK = [GENESIS, S1, S2_FORK]
ROLLBACK = [GENESIS, S1]  # an older but valid prefix


def test_legit_chain_passes_with_both_anchors():
    result = verify_chain(CHAIN, anchored_genesis=GENESIS["sha"],
                          anchored_head=S2["sha"])
    assert result.passed, result.to_dict()
    assert result.status == PASS
    assert result.length == 3


def test_genesis_only_is_not_verifiable():
    """The core correction: genesis alone must not claim validity."""
    result = verify_chain(CHAIN, anchored_genesis=GENESIS["sha"], anchored_head=None)
    assert not result.passed
    assert result.status == NOT_VERIFIABLE
    assert result.genesis_matched and not result.head_matched


def test_fork_is_rejected_with_head_anchor():
    result = verify_chain(FORK, anchored_genesis=GENESIS["sha"],
                          anchored_head=S2["sha"])
    assert not result.passed
    assert result.status == CONFLICT
    assert result.internal_ok, "the fork is internally consistent -- that is the trap"
    assert result.genesis_matched and not result.head_matched


def test_rollback_is_rejected_with_head_anchor():
    result = verify_chain(ROLLBACK, anchored_genesis=GENESIS["sha"],
                          anchored_head=S2["sha"])
    assert not result.passed
    assert result.status == CONFLICT
    assert result.internal_ok


def test_wrong_genesis_is_rejected():
    other_genesis = make_state(None, {"kind": "genesis", "base": "other"})
    result = verify_chain(CHAIN, anchored_genesis=other_genesis["sha"],
                          anchored_head=S2["sha"])
    assert not result.passed
    assert result.status == REJECT
    assert not result.genesis_matched


def test_tampered_state_without_rehash_is_rejected():
    tampered = dict(S1)
    tampered["transition"] = {"kind": "install", "artifact": "backdoor"}
    result = verify_chain([GENESIS, tampered, S2],
                          anchored_genesis=GENESIS["sha"], anchored_head=S2["sha"])
    assert not result.passed
    assert result.status == REJECT
    assert not result.internal_ok


def test_empty_chain_is_not_verifiable():
    result = verify_chain([], anchored_genesis=GENESIS["sha"], anchored_head=S2["sha"])
    assert not result.passed
    assert result.status == NOT_VERIFIABLE


def test_no_anchors_at_all_is_not_verifiable():
    result = verify_chain(CHAIN, anchored_genesis=None, anchored_head=None)
    assert not result.passed
    assert result.status == NOT_VERIFIABLE
