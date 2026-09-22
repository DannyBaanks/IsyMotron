"""Quine Gate verifier — M2: re-derive a receipt's decision from its claim.

A receipt is an *affirmation*; the authority is the reproduction. This module
re-runs the L0 enforcer (`isymotron.policy.Enforcer`, a pure function) over the
inputs a receipt claims, and compares the re-derived decision with the one the
receipt states.

The inputs travel in a ``ClaimBundle``: the host description, the request
params, the lease and the decision instant. A receipt points at its bundle via
``claim_digest`` (v1). Raw params live in the bundle, never in the receipt --
the receipt may be rendered on a phone, and a physical path is the one thing
the planner was never told.

What this defeats: a receipt edited and re-sealed on its own (the M0 hole),
and a bundle whose request/policy does not match the receipt.

What this does NOT defeat: an attacker who rewrites *both* the bundle and the
receipt consistently. That needs an external anchor (M4) and a keyed seal (M3).
Properties are reported separately, never collapsed into "secure".
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from .canon import digest
from .contracts import (
    CapabilityManifest,
    ExecutionReceipt,
    ExecutionRequest,
    HostDescription,
    HostIdentity,
    Lease,
    PolicyDecision,
)
from .policy import Enforcer
from .verdicts import Decision, DenyReason

BUNDLE_CONTRACT = "quine-claim/v1"

NOT_VERIFIABLE = "NOT_VERIFIABLE"


@dataclass(frozen=True)
class ClaimBundle:
    """Everything needed to re-run the decision a receipt claims."""

    host: HostDescription
    request: ExecutionRequest
    lease: Lease | None
    decided_at: float
    expected: PolicyDecision
    admin_granted: bool = False
    contract: str = BUNDLE_CONTRACT

    def payload(self) -> dict:
        return {
            "contract": self.contract,
            "host": self.host.to_dict(),
            "admin_granted": self.admin_granted,
            "request": self.request.to_dict(),
            "lease": self.lease.to_dict() if self.lease is not None else None,
            "decided_at": self.decided_at,
            "expected": self.expected.to_dict(),
        }

    def digest(self) -> str:
        return digest(self.payload())

    def to_dict(self) -> dict:
        data = self.payload()
        data["claim_digest"] = self.digest()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ClaimBundle":
        host = data["host"]
        capabilities = [
            CapabilityManifest(
                id=str(c["id"]),
                version=str(c["version"]),
                summary=str(c.get("summary", "")),
                scopes=dict(c.get("scopes", {})),
                requires_admin=bool(c.get("requires_admin", False)),
                params=tuple(c.get("params", ())),
                returns=tuple(c.get("returns", ())),
            )
            for c in host.get("capabilities", ())
        ]
        description = HostDescription(
            identity=HostIdentity(**dict(host["identity"])),
            capabilities=capabilities,
            granted=list(host.get("granted", ())),
            bounds=dict(host.get("bounds", {})),
        )

        raw_req = data["request"]
        request = ExecutionRequest.make(
            raw_req["host_id"], raw_req["subject"], raw_req["capability"],
            dict(raw_req["params"]),
            lease_id=raw_req.get("lease_id"), plan_id=raw_req.get("plan_id"),
        )
        if raw_req.get("request_id"):
            # `make` mints a fresh id; the bundle must keep the one it was
            # built with or its digest would not round-trip.
            request = replace(request, request_id=raw_req["request_id"])

        lease = None
        if data.get("lease") is not None:
            raw_lease = data["lease"]
            lease = Lease(
                lease_id=raw_lease["lease_id"],
                host_id=raw_lease["host_id"],
                subject=raw_lease["subject"],
                capability=raw_lease["capability"],
                scope=dict(raw_lease.get("scope", {})),
                issued_at=raw_lease["issued_at"],
                expires_at=raw_lease["expires_at"],
                revoked=bool(raw_lease.get("revoked", False)),
            )

        raw_expected = data["expected"]
        reason = raw_expected.get("reason")
        expected = PolicyDecision(
            Decision(raw_expected["decision"]),
            DenyReason(reason) if reason else None,
            raw_expected.get("detail", ""),
        )

        return cls(
            host=description,
            request=request,
            lease=lease,
            decided_at=data["decided_at"],
            expected=expected,
            admin_granted=bool(data.get("admin_granted", False)),
            contract=data.get("contract", BUNDLE_CONTRACT),
        )


@dataclass(frozen=True)
class Verification:
    """Outcome of re-deriving a claim. Each property is reported separately."""

    passed: bool
    status: str
    reason: str
    rederived: PolicyDecision | None
    claim_matched: bool
    request_matched: bool
    decision_matched: bool

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "status": self.status,
            "reason": self.reason,
            "claim_matched": self.claim_matched,
            "request_matched": self.request_matched,
            "decision_matched": self.decision_matched,
            "rederived": self.rederived.to_dict() if self.rederived else None,
        }


def rederive(bundle: ClaimBundle) -> PolicyDecision:
    """Re-run the policy over the bundle's inputs at the claimed instant.

    ``decided_at`` is used instead of the wall clock on purpose: a receipt from
    the past would otherwise look expired and its DENY could never be
    reproduced.
    """
    enforcer = Enforcer(bundle.host, admin_granted=bundle.admin_granted)
    return enforcer.decide(bundle.request, bundle.lease, now=bundle.decided_at)


def verify_receipt(receipt: ExecutionReceipt | None,
                   bundle: ClaimBundle | None) -> Verification:
    """Verify a receipt by re-deriving it. Fail-closed on every axis."""
    if receipt is None or bundle is None:
        return Verification(False, NOT_VERIFIABLE,
                            "no receipt/bundle pair to reproduce", None,
                            False, False, False)

    if not receipt.verify():
        return Verification(False, "REJECT", "receipt seal does not verify",
                            None, False, False, False)

    claim_matched = bool(receipt.claim_digest) and receipt.claim_digest == bundle.digest()
    request_matched = receipt.request_digest == bundle.request.digest()

    rederived = rederive(bundle)
    decision_matched = (
        rederived.decision == receipt.decision.decision
        and rederived.reason == receipt.decision.reason
    )

    passed = claim_matched and request_matched and decision_matched
    if passed:
        reason = "claim re-derived and matches the receipt"
    elif not claim_matched:
        reason = "receipt does not point at this claim bundle"
    elif not request_matched:
        reason = "receipt request digest does not match the bundle request"
    else:
        reason = "re-derived decision does not match the receipt"

    return Verification(passed, "PASS" if passed else "REJECT", reason,
                        rederived, claim_matched, request_matched, decision_matched)
