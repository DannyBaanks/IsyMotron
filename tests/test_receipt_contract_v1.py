"""Quine Gate — M1: receipt v1 con procedencia, sin romper los v0.

The contract header says: "Any change to a field name or meaning is a V1, not a
V0 edit: receipts already emitted must stay readable." This gate holds that
promise mechanically:

- loaded v0 receipts from `evidence/M0` and `evidence/M1` still verify;
- the v0 payload key set is frozen (a v1 field must not leak into it);
- a v1 receipt carries policy/capability/result digests and a `reproduce`
  block, and those digests are part of the sealed bytes.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from isymotron.canon import digest
from isymotron.contracts import (
    CONTRACT,
    CONTRACT_V1,
    ExecutionReceipt,
    HostIdentity,
    PolicyDecision,
    new_receipt_id,
)
from isymotron.verdicts import Decision, DenyReason, Evidence

REPO = Path(__file__).resolve().parent.parent

V0_PAYLOAD_KEYS = {
    "contract", "receipt_id", "request_digest", "request_id", "host",
    "capability", "subject", "lease_id", "decision", "started_at",
    "ended_at", "result", "effects", "evidence",
}


def _base_receipt(**overrides) -> ExecutionReceipt:
    fields = dict(
        receipt_id=new_receipt_id(),
        request_digest="sha256:" + "0" * 64,
        request_id="req_v1_test",
        host=HostIdentity(
            host_id="win11-m1",
            display_name="M1 (test)",
            os_family="windows",
            os_release="11-24h2",
            engine="nt-modern/0.1",
        ),
        capability="filesystem.read",
        subject="mobile:m1",
        lease_id="lease_m1",
        decision=PolicyDecision(Decision.DENY, DenyReason.OUT_OF_SCOPE, "outside"),
        started_at=1.0,
        ended_at=2.0,
        result={},
        effects=(),
        evidence=Evidence.DEMONSTRATED,
    )
    fields.update(overrides)
    return ExecutionReceipt(**fields).sealed()


def _all_evidence_receipts() -> list[Path]:
    paths: list[Path] = []
    for folder in ("M0", "M1"):
        paths.extend(sorted((REPO / "evidence" / folder).glob("*.json")))
    return paths


def test_v0_payload_key_set_is_frozen():
    """A v1 field must never appear in a v0 payload, or old seals break."""
    assert set(_base_receipt().payload()) == V0_PAYLOAD_KEYS


def test_v0_receipt_verifies_before_and_after_roundtrip():
    rcpt = _base_receipt()
    assert rcpt.verify()
    assert ExecutionReceipt.from_dict(rcpt.to_dict()).verify()


@pytest.mark.parametrize("path", _all_evidence_receipts(), ids=lambda p: p.name)
def test_emitted_evidence_receipts_still_verify(path):
    """The acceptance criterion: every receipt already on disk stays valid."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rcpt = ExecutionReceipt.from_dict(data)
    assert rcpt.contract == CONTRACT
    assert rcpt.verify(), f"{path} no longer verifies after the v1 change"


def test_v1_receipt_carries_and_seals_provenance():
    rcpt = _base_receipt(
        contract=CONTRACT_V1,
        policy_digest="sha256:" + "a" * 64,
        capability_digest="sha256:" + "b" * 64,
        result_digest=digest({}),
        reproduce={"command": "py -m isymotron.verify", "tool": "nt-real/0.1"},
        seal_kind="unkeyed",
    )
    assert rcpt.verify()
    payload = rcpt.payload()
    assert payload["contract"] == CONTRACT_V1
    for key in ("policy_digest", "capability_digest", "result_digest", "reproduce"):
        assert key in payload


def test_v1_provenance_is_part_of_the_sealed_bytes():
    rcpt = _base_receipt(contract=CONTRACT_V1, policy_digest="sha256:" + "a" * 64)
    assert rcpt.verify()
    forged = replace(rcpt, policy_digest="sha256:" + "f" * 64)
    assert not forged.verify(), "editing a provenance digest must break the seal"


def test_v1_roundtrips_through_json():
    rcpt = _base_receipt(
        contract=CONTRACT_V1,
        policy_digest="sha256:" + "a" * 64,
        reproduce={"command": "x"},
    )
    loaded = ExecutionReceipt.from_dict(json.loads(json.dumps(rcpt.to_dict())))
    assert loaded.contract == CONTRACT_V1
    assert loaded.policy_digest == "sha256:" + "a" * 64
    assert loaded.verify()
