"""Quine Gate — M0: baseline adversarial de sellos (test rojo).

This is milestone M0 of `.opencode/plans/quine-gate-reproducible-evidence.md`.
It fixes the CURRENT state in the tree before any fix lands:

- the receipt seal is an *unkeyed* digest (`seal == sha256(canonical(payload))`);
- therefore an attacker who edits a DENY to an ALLOW and recomputes the seal
  produces a receipt that `verify()` accepts.

The two ``xfail(strict=True)`` tests below assert the *desired* behaviour
(a re-sealed forgery must be rejected). They fail today for exactly that
reason, which is the point: when M3 adds a keyed seal, they will XPASS and
strict mode will turn that into a suite error, forcing the marker's removal.

The control test at the end is the protection that already exists and must
not regress: a mutation that does NOT recompute the seal is detected.

Scope note (what this does NOT claim): the attack is in-process and uses the
public dataclasses. It does not prove a remote exploit, only that the seal
carries no authority independent of the payload's own hash.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from isymotron.contracts import (
    ExecutionReceipt,
    HostIdentity,
    PolicyDecision,
    new_receipt_id,
)
from isymotron.verdicts import Decision, DenyReason, Evidence
from learning import LessonReceipt

# The reason text is shared so the two xfail markers cannot drift apart.
_HOLE = (
    "unkeyed digest: a DENY->ALLOW edit plus seal recomputation verifies today; "
    "M3 (keyed seal) must make this test XPASS and remove the marker"
)


def _denied_host_receipt() -> ExecutionReceipt:
    """A legitimate, sealed DENY receipt built from the real dataclasses."""
    return ExecutionReceipt(
        receipt_id=new_receipt_id(),
        request_digest="sha256:" + "0" * 64,
        request_id="req_quinegate_m0",
        host=HostIdentity(
            host_id="win11-quinegate",
            display_name="Quine Gate (test)",
            os_family="windows",
            os_release="11-24h2",
            engine="nt-modern/0.1",
        ),
        capability="filesystem.read",
        subject="mobile:quinegate",
        lease_id="lease_quinegate",
        decision=PolicyDecision(
            Decision.DENY,
            DenyReason.OUT_OF_SCOPE,
            "C:/Users/demo/Secrets/keys.txt is outside ['hostfs://photos']",
        ),
        started_at=1.0,
        ended_at=2.0,
        result={},
        effects=(),
        evidence=Evidence.DEMONSTRATED,
    ).sealed()


def _failed_lesson_receipt() -> LessonReceipt:
    """A legitimate, sealed FAIL lesson receipt (same digest machinery)."""
    return LessonReceipt(
        receipt_id=new_receipt_id(),
        lesson_id="quinegate-m0",
        exercise_id="quinegate-m0-1",
        learner_input="wrong",
        verdict="FAIL",
        expected={"opcode": 81},
        observed={"opcode": 0},
        execution=None,
        verified_by=["test fixture"],
        provenance=["tests/test_quine_gate_adversarial.py"],
        notes=["m0 baseline"],
        verdict_source="machine",
        started_at=1.0,
        ended_at=2.0,
    ).sealed()


def test_host_receipt_legitimate_deny_verifies():
    """Sanity: the baseline receipt is well-formed before we attack it."""
    rcpt = _denied_host_receipt()
    assert rcpt.decision.decision is Decision.DENY
    assert rcpt.verify(), "a freshly sealed receipt must verify"


def test_lesson_receipt_legitimate_fail_verifies():
    """Sanity: the second receipt family is well-formed before we attack it."""
    rcpt = _failed_lesson_receipt()
    assert rcpt.verdict == "FAIL"
    assert rcpt.verify(), "a freshly sealed receipt must verify"


@pytest.mark.xfail(strict=True, reason=_HOLE)
def test_rehashed_allow_host_receipt_is_rejected():
    """Attack A (receipt mutation) + B (internal rehash), host receipt.

    The attacker changes the decision to ALLOW and recomputes the seal. The
    receipt becomes self-consistent under the current scheme, so `verify()`
    returns True. The desired contract is REJECT; this test fails today.
    """
    forged = replace(
        _denied_host_receipt(),
        decision=PolicyDecision(Decision.ALLOW),
        result={"text": "exfiltrated"},
    )
    forged = forged.sealed()

    assert not forged.verify(), (
        "a re-sealed DENY->ALLOW receipt must not verify"
    )


@pytest.mark.xfail(strict=True, reason=_HOLE)
def test_rehashed_pass_lesson_receipt_is_rejected():
    """Attack B on the second receipt family: FAIL -> PASS, seal recomputed."""
    forged = replace(_failed_lesson_receipt(), verdict="PASS")
    forged = forged.sealed()

    assert not forged.verify(), (
        "a re-sealed FAIL->PASS lesson receipt must not verify"
    )


def test_plain_mutation_without_reseal_is_detected():
    """Control: the protection that already exists must not regress.

    Editing a sealed field without recomputing the seal is caught by both
    receipt families (this is what `verify()` does guarantee today).
    """
    host = replace(_denied_host_receipt(), result={"text": "leak"})
    lesson = replace(_failed_lesson_receipt(), verdict="PASS")

    assert not host.verify(), "an unre-sealed edit must break the host seal"
    assert not lesson.verify(), "an unre-sealed edit must break the lesson seal"
