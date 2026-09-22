"""Quine Gate — adversarial seal gate (M0 baseline, completed by M3).

History, kept because it is the point:

- M0 froze the CURRENT state: the seal was an *unkeyed* digest, so a receipt
  edited DENY->ALLOW and re-sealed verified. Two ``xfail(strict=True)`` tests
  asserted the desired behaviour and were expected to XPASS when M3 landed.
- M3 added keyed sealing (``isymotron.seal``, HMAC-SHA256, no third-party
  dependency). The markers are gone; these are now real passing tests.

The unkeyed scheme is not deleted: v0 receipts already emitted use it and must
stay readable. It is *integrity only* -- anyone can recompute it -- and the
boundary is asserted explicitly below. Authority-bearing receipts are keyed,
and even then authority is reproduction (M2), not the seal.
"""
from __future__ import annotations

from dataclasses import replace

from isymotron.canon import digest
from isymotron.contracts import (
    CONTRACT_V1,
    ExecutionReceipt,
    HostIdentity,
    PolicyDecision,
    new_receipt_id,
)
from isymotron.seal import HMAC_SHA256, MissingKey, seal_payload
from isymotron.verdicts import Decision, DenyReason, Evidence
from learning import LessonReceipt

SECRET = "test-key-not-a-secret"
WRONG = "another-key"


def _denied_fields(**overrides) -> ExecutionReceipt:
    """An unsealed DENY receipt built from the real dataclasses."""
    fields = dict(
        receipt_id=new_receipt_id(),
        request_digest="sha256:" + "0" * 64,
        request_id="req_quinegate",
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
    )
    fields.update(overrides)
    return ExecutionReceipt(**fields)


def _denied_host_receipt(**overrides) -> ExecutionReceipt:
    """A legitimate, sealed (unkeyed) DENY receipt."""
    return _denied_fields(**overrides).sealed()


def _failed_lesson_receipt() -> LessonReceipt:
    return LessonReceipt(
        receipt_id=new_receipt_id(),
        lesson_id="quinegate",
        exercise_id="quinegate-1",
        learner_input="wrong",
        verdict="FAIL",
        expected={"opcode": 81},
        observed={"opcode": 0},
        execution=None,
        verified_by=["test fixture"],
        provenance=["tests/test_quine_gate_adversarial.py"],
        notes=[],
        verdict_source="machine",
        started_at=1.0,
        ended_at=2.0,
    ).sealed()


def test_host_receipt_legitimate_deny_verifies():
    rcpt = _denied_host_receipt()
    assert rcpt.decision.decision is Decision.DENY
    assert rcpt.verify(), "a freshly sealed receipt must verify"


def test_lesson_receipt_legitimate_fail_verifies():
    rcpt = _failed_lesson_receipt()
    assert rcpt.verdict == "FAIL"
    assert rcpt.verify(), "a freshly sealed receipt must verify"


def test_unkeyed_seal_is_integrity_only_not_authority():
    """Boundary: the legacy unkeyed scheme can be recomputed by anyone.

    This is not a bug to fix -- it is why an unkeyed receipt carries no
    authority on its own, and why authority lives in reproduction (M2) and in
    keyed receipts (M3).
    """
    forged = replace(_denied_host_receipt(),
                     decision=PolicyDecision(Decision.ALLOW),
                     result={"text": "exfiltrated"})
    forged = forged.sealed()
    assert forged.verify(), "unkeyed is integrity-only; anyone can recompute it"


def test_hmac_seal_rejects_an_unkeyed_reseal():
    """Attack: edit DENY->ALLOW and reseal with the unkeyed scheme.

    The forged receipt keeps ``seal_kind='hmac-sha256'`` but its seal is an
    unkeyed digest, so verification fails.
    """
    rcpt = _denied_fields(contract=CONTRACT_V1, seal_kind=HMAC_SHA256)
    rcpt = rcpt.sealed(key=SECRET)
    assert rcpt.verify(key=SECRET)

    forged = replace(rcpt, decision=PolicyDecision(Decision.ALLOW))
    forged = replace(forged, seal=digest(forged.payload()))  # attacker's reseal
    assert not forged.verify(key=SECRET)


def test_hmac_seal_rejects_a_wrong_key():
    rcpt = _denied_fields(contract=CONTRACT_V1, seal_kind=HMAC_SHA256)
    rcpt = rcpt.sealed(key=SECRET)

    forged = replace(rcpt, decision=PolicyDecision(Decision.ALLOW))
    forged = forged.sealed(key=WRONG)  # attacker has *a* key, not the key
    assert not forged.verify(key=SECRET)


def test_hmac_seal_requires_a_key_and_is_not_forgeable_without_it():
    rcpt = _denied_fields(contract=CONTRACT_V1, seal_kind=HMAC_SHA256)
    sealed = rcpt.sealed(key=SECRET)

    assert sealed.verify(key=SECRET)
    assert not sealed.verify(), "no key available: fail closed"
    try:
        rcpt.sealed()
    except MissingKey:
        pass
    else:  # pragma: no cover - explicit failure if the guard disappears
        raise AssertionError("sealing HMAC without a key must raise MissingKey")


def test_unkeyed_helpers_still_work_for_v0():
    """v0 receipts keep the old scheme byte-for-byte."""
    rcpt = _denied_host_receipt()
    assert rcpt.seal == digest(rcpt.payload())
    assert seal_payload(rcpt.payload()) == rcpt.seal


def test_plain_mutation_without_reseal_is_detected():
    """Control: the protection that always existed must not regress."""
    host = replace(_denied_host_receipt(), result={"text": "leak"})
    lesson = replace(_failed_lesson_receipt(), verdict="PASS")

    assert not host.verify(), "an unre-sealed edit must break the host seal"
    assert not lesson.verify(), "an unre-sealed edit must break the lesson seal"
