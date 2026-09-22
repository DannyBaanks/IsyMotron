"""Quine Gate — M2: the receipt is re-derived, not trusted.

This gate proves the central property: a receipt whose decision was edited and
re-sealed (the M0 hole) is still rejected, because the decision is a pure
function of anchored inputs and the verifier recomputes it.

It also proves it fails closed: changed input, changed policy, a receipt with
no claim, or a missing bundle are never a PASS.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from isymotron.canon import digest
from isymotron.contracts import (
    CONTRACT_V1,
    ExecutionRequest,
    HostDescription,
    PolicyDecision,
)
from isymotron.verify import ClaimBundle, NOT_VERIFIABLE, rederive, verify_receipt
from isymotron.verdicts import Decision, DenyReason
from simulator.engines import ModernHost

SUBJECT = "mobile:quinegate"
HOST_ID = "win11-quinegate"
IN_SCOPE = "C:/Users/demo/Photos/shot.png"
OUT_OF_SCOPE = "C:/Users/demo/Secrets/keys.txt"


def _host() -> ModernHost:
    return ModernHost(
        fs={
            IN_SCOPE: "PNGDATA",
            OUT_OF_SCOPE: "hunter2",
        },
        granted=["filesystem.read"],
        grant_scopes={"filesystem.read": {"roots": ["C:/Users/demo/Photos"]}},
        host_id=HOST_ID,
        display_name="Quine Gate (M2)",
    )


def _scenario(path: str):
    """Produce a real receipt and the bundle that can reproduce it."""
    host = _host()
    lease, _ = host.request_lease(SUBJECT, "filesystem.read", 300)
    assert lease is not None
    request = ExecutionRequest.make(HOST_ID, SUBJECT, "filesystem.read",
                                    {"path": path}, lease_id=lease.lease_id)
    receipt = host.execute_capability(request)

    description = host.describe()
    capability_digest = digest(
        next(c.to_dict() for c in description.capabilities
             if c.id == request.capability)
    )
    bundle = ClaimBundle(
        host=description,
        request=request,
        lease=lease,
        decided_at=receipt.started_at,
        expected=receipt.decision,
    )
    v1 = replace(
        receipt,
        contract=CONTRACT_V1,
        claim_digest=bundle.digest(),
        policy_digest=digest({"enforcer": "isymotron.policy.Enforcer"}),
        capability_digest=capability_digest,
        result_digest=digest(receipt.result),
        seal_kind="unkeyed",
    ).sealed()
    return v1, bundle


def test_legit_deny_rederives_and_passes():
    receipt, bundle = _scenario(OUT_OF_SCOPE)
    assert receipt.decision.decision is Decision.DENY
    result = verify_receipt(receipt, bundle)
    assert result.passed, result.to_dict()
    assert rederive(bundle).decision is Decision.DENY


def test_legit_allow_rederives_and_passes():
    receipt, bundle = _scenario(IN_SCOPE)
    assert receipt.decision.decision is Decision.ALLOW
    assert verify_receipt(receipt, bundle).passed


def test_receipt_only_forgery_is_rejected_by_rederivation():
    """The M0 attack, now defeated without a key: edit DENY->ALLOW and reseal.

    The forged receipt is self-consistent (its own seal verifies), but the
    re-derived decision is still DENY, so the claim is rejected.
    """
    receipt, bundle = _scenario(OUT_OF_SCOPE)
    forged = replace(receipt, decision=PolicyDecision(Decision.ALLOW)).sealed()

    assert forged.verify(), "the attacker's seal is internally consistent"
    result = verify_receipt(forged, bundle)
    assert not result.passed
    assert result.rederived is not None
    assert result.rederived.decision is Decision.DENY
    assert "re-derived" in result.reason


def test_changed_input_is_rejected():
    receipt, bundle = _scenario(OUT_OF_SCOPE)
    other = replace(
        bundle,
        request=ExecutionRequest.make(HOST_ID, SUBJECT, "filesystem.read",
                                      {"path": IN_SCOPE},
                                      lease_id=bundle.request.lease_id),
    )
    result = verify_receipt(receipt, other)
    assert not result.passed
    assert not result.request_matched


def test_changed_policy_is_rejected():
    receipt, bundle = _scenario(OUT_OF_SCOPE)
    # Same host, but the grant is gone: the policy now answers differently.
    stripped = replace(bundle, host=replace(bundle.host, granted=[]))
    result = verify_receipt(receipt, stripped)
    assert not result.passed
    assert result.rederived is not None
    assert result.rederived.reason is DenyReason.CAPABILITY_NOT_GRANTED


def test_missing_bundle_is_not_verifiable():
    receipt, _ = _scenario(OUT_OF_SCOPE)
    result = verify_receipt(receipt, None)
    assert not result.passed
    assert result.status == NOT_VERIFIABLE


def test_v0_receipt_without_claim_is_not_reproducible():
    """A legacy receipt carries no claim_digest, so it cannot be re-derived."""
    receipt, bundle = _scenario(OUT_OF_SCOPE)
    legacy = replace(receipt, contract="NemoHostContract/v0", claim_digest=None)
    result = verify_receipt(legacy, bundle)
    assert not result.passed
    assert not result.claim_matched


def test_bundle_roundtrips_through_json():
    _, bundle = _scenario(OUT_OF_SCOPE)
    loaded = ClaimBundle.from_dict(bundle.to_dict())
    assert loaded.digest() == bundle.digest()
    assert loaded.request.digest() == bundle.request.digest()
    assert loaded.expected.decision is bundle.expected.decision
