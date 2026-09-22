"""Quine Gate — host wiring: real receipts are v1 and re-derivable.

Before this, only tests could build a v1 receipt with a `claim_digest`; the
host emitted v0. Now `Host.execute_capability` emits v1 with the provenance
digests and stores the claim bundle, and the verifier can reproduce it.

Boundary asserted here: when the *engine* overrides an enforcer ALLOW (a
junction, a case-fold collision), the decision depends on OS state the
verifier does not have, so the receipt makes NO claim for it.
"""
from __future__ import annotations

import json
from pathlib import Path

from isymotron.bundle import verify_bundle
from isymotron.chain import PASS
from isymotron.contracts import CONTRACT_V1, ExecutionReceipt, ExecutionRequest
from isymotron.host import ScopeViolation
from isymotron.seal import HMAC_SHA256
from isymotron.verify import verify_receipt
from isymotron.verdicts import Decision, DenyReason, Evidence
from simulator.engines import ModernHost

SECRET = "host-wiring-key"
SUBJECT = "mobile:wiring"
HOST_ID = "win11-wiring"
IN_SCOPE = "C:/Users/demo/Photos/shot.png"
OUT_OF_SCOPE = "C:/Users/demo/Secrets/keys.txt"


def _host() -> ModernHost:
    return ModernHost(
        fs={IN_SCOPE: "PNGDATA", OUT_OF_SCOPE: "hunter2"},
        granted=["filesystem.read"],
        grant_scopes={"filesystem.read": {"roots": ["C:/Users/demo/Photos"]}},
        host_id=HOST_ID,
        display_name="Wiring",
    )


def _execute(path: str = OUT_OF_SCOPE):
    host = _host()
    lease, _ = host.request_lease(SUBJECT, "filesystem.read", 300)
    request = ExecutionRequest.make(HOST_ID, SUBJECT, "filesystem.read",
                                    {"path": path}, lease_id=lease.lease_id)
    return host, host.execute_capability(request)


def test_host_emits_v1_receipt_with_provenance():
    _, receipt = _execute()
    assert receipt.contract == CONTRACT_V1
    assert receipt.claim_digest, "a v1 receipt must name its claim"
    assert receipt.policy_digest and receipt.capability_digest
    assert receipt.result_digest
    assert receipt.reproduce["tool"] == "nt-modern/0.1"
    assert receipt.verify(), "unkeyed in this environment"


def test_host_stores_a_bundle_that_reproduces_the_receipt():
    host, receipt = _execute()
    bundle = host.claim_bundle(receipt.receipt_id)
    assert bundle is not None
    result = verify_receipt(receipt, bundle)
    assert result.passed, result.to_dict()
    assert result.rederived.decision is Decision.DENY


def test_allow_receipt_is_reproducible_too():
    host, receipt = _execute(IN_SCOPE)
    assert receipt.decision.decision is Decision.ALLOW
    bundle = host.claim_bundle(receipt.receipt_id)
    assert verify_receipt(receipt, bundle).passed


def test_written_receipt_and_bundle_verify_as_a_bundle(tmp_path):
    host, receipt = _execute()
    bundle = host.claim_bundle(receipt.receipt_id)
    (tmp_path / "receipt.json").write_text(json.dumps(receipt.to_dict()), encoding="utf-8")
    (tmp_path / "claim.json").write_text(json.dumps(bundle.to_dict()), encoding="utf-8")

    report = verify_bundle(tmp_path)
    assert report.passed, report.to_dict()
    assert report.properties["reproducibility"]["status"] == PASS


def test_receipt_roundtrips_through_json():
    _, receipt = _execute()
    loaded = ExecutionReceipt.from_dict(json.loads(json.dumps(receipt.to_dict())))
    assert loaded.verify()
    assert loaded.claim_digest == receipt.claim_digest


def test_forged_host_receipt_is_rejected_by_its_bundle():
    host, receipt = _execute()
    bundle = host.claim_bundle(receipt.receipt_id)
    forged = ExecutionReceipt.from_dict(receipt.to_dict())
    from dataclasses import replace
    forged = replace(forged, decision=replace(forged.decision, decision=Decision.ALLOW))
    forged = forged.sealed()
    assert forged.verify(), "the attacker's unkeyed reseal is self-consistent"
    assert not verify_receipt(forged, bundle).passed


def test_hmac_receipt_when_key_is_present(monkeypatch):
    monkeypatch.setenv("ISYMOTRON_RECEIPT_KEY", SECRET)
    host, receipt = _execute()
    bundle = host.claim_bundle(receipt.receipt_id)
    assert receipt.seal_kind == HMAC_SHA256
    assert receipt.verify(SECRET)
    assert verify_receipt(receipt, bundle, SECRET).passed

    # Remove the key: verification must fail closed, not fall back.
    monkeypatch.delenv("ISYMOTRON_RECEIPT_KEY")
    assert not receipt.verify(), "without the key, fail closed"
    assert not verify_receipt(receipt, bundle).passed


class _OverridingHost(ModernHost):
    """Simulates win11.py's engine-level ScopeViolation after an ALLOW."""

    def run(self, req):
        raise ScopeViolation(DenyReason.OUT_OF_SCOPE, "engine refuses after ALLOW")


def test_engine_override_makes_no_reproducible_claim():
    host = _OverridingHost(
        fs={IN_SCOPE: "PNGDATA"},
        granted=["filesystem.read"],
        grant_scopes={"filesystem.read": {"roots": ["C:/Users/demo/Photos"]}},
        host_id=HOST_ID,
        display_name="Override",
    )
    lease, _ = host.request_lease(SUBJECT, "filesystem.read", 300)
    request = ExecutionRequest.make(HOST_ID, SUBJECT, "filesystem.read",
                                    {"path": IN_SCOPE}, lease_id=lease.lease_id)
    receipt = host.execute_capability(request)

    assert receipt.decision.decision is Decision.DENY
    assert receipt.evidence is Evidence.DEMONSTRATED
    assert receipt.claim_digest is None, "an OS-level override is not re-derivable"
    assert host.claim_bundle(receipt.receipt_id) is None
    assert not verify_receipt(receipt, None).passed
