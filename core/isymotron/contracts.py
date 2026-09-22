"""NemoHostContract V0 data types.

Frozen for M0. Any change to a field name or meaning is a V1, not a V0 edit:
receipts already emitted must stay readable.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Mapping, Sequence

from .canon import digest
from .verdicts import Decision, DenyReason, Evidence

CONTRACT = "NemoHostContract/v0"

#: Receipt contract v1 (Quine Gate, milestone M1). Adds provenance digests and
#: a ``reproduce`` block. A v1 receipt emits the extra keys in its payload; a
#: v0 receipt does not, so the key set -- and therefore the seal -- of every
#: receipt already emitted is unchanged. See ``ExecutionReceipt.payload``.
CONTRACT_V1 = "NemoHostContract/v1"


def _now() -> float:
    return time.time()


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


# --------------------------------------------------------------------------
# Capability declaration
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class CapabilityManifest:
    """What a host declares it can do, and under what bounds.

    `scopes` is capability-specific and interpreted by the capability's own
    scope checker, never by free-form string matching at the policy layer.
    """

    id: str                      # e.g. "filesystem.read"
    version: str                 # e.g. "0.1"
    summary: str
    scopes: Mapping[str, Any] = field(default_factory=dict)
    requires_admin: bool = False
    params: Sequence[str] = field(default_factory=tuple)
    # The keys a successful result is guaranteed to carry. Added in v0 after
    # two engines returned the same value under different names and a plan
    # referencing one of them stopped at execution -- see docs/FINDINGS.md #5.
    # Without this, a cross-step reference is a guess.
    returns: Sequence[str] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scopes"] = dict(self.scopes)
        d["params"] = list(self.params)
        d["returns"] = list(self.returns)
        return d


@dataclass(frozen=True)
class HostIdentity:
    """Answer to identify(). Stable across restarts, unique per device."""

    host_id: str
    display_name: str
    os_family: str               # "windows"
    os_release: str              # "10-22h2", "11-24h2"
    engine: str                  # which local implementation serves the contract
    contract: str = CONTRACT

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HostDescription:
    """Answer to describe(): identity + declared capabilities + grants.

    `granted` is the subset the local human has actually authorized on this
    device. A capability that is implemented but not granted is not a policy
    note; it is absent from the agent's world.
    """

    identity: HostIdentity
    capabilities: Sequence[CapabilityManifest]
    granted: Sequence[str]
    # Per granted capability, the resources a planner may name: logical ids
    # and `hostfs://` URIs, never a physical path (see isymotron.resources).
    bounds: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "identity": self.identity.to_dict(),
            "capabilities": [c.to_dict() for c in self.capabilities],
            "granted": list(self.granted),
            "bounds": dict(self.bounds),
        }


# --------------------------------------------------------------------------
# Authority
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Lease:
    """A time-bounded, scope-bounded grant for one subject on one host."""

    lease_id: str
    host_id: str
    subject: str                 # who acts: "mobile:iphone-danny"
    capability: str
    scope: Mapping[str, Any]
    issued_at: float
    expires_at: float
    revoked: bool = False

    @staticmethod
    def issue(host_id: str, subject: str, capability: str,
              scope: Mapping[str, Any], ttl_s: float, now: float | None = None) -> "Lease":
        t = _now() if now is None else now
        return Lease(
            lease_id=_uid("lease"),
            host_id=host_id,
            subject=subject,
            capability=capability,
            scope=dict(scope),
            issued_at=t,
            expires_at=t + ttl_s,
        )

    def alive(self, now: float | None = None) -> bool:
        t = _now() if now is None else now
        return (not self.revoked) and t < self.expires_at

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scope"] = dict(self.scope)
        return d


@dataclass(frozen=True)
class ExecutionRequest:
    """What a client asks a host to do. Carries no authority of its own."""

    request_id: str
    host_id: str
    subject: str
    capability: str
    params: Mapping[str, Any]
    lease_id: str | None = None
    plan_id: str | None = None   # set when a planner produced this step

    @staticmethod
    def make(host_id: str, subject: str, capability: str,
             params: Mapping[str, Any], lease_id: str | None = None,
             plan_id: str | None = None) -> "ExecutionRequest":
        return ExecutionRequest(
            request_id=_uid("req"), host_id=host_id, subject=subject,
            capability=capability, params=dict(params),
            lease_id=lease_id, plan_id=plan_id,
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["params"] = dict(self.params)
        return d

    def digest(self) -> str:
        """Identity of the *intent*, independent of request_id and timing."""
        return digest({
            "contract": CONTRACT,
            "host_id": self.host_id,
            "subject": self.subject,
            "capability": self.capability,
            "params": dict(self.params),
        })


@dataclass(frozen=True)
class PolicyDecision:
    """Output of the L0 enforcer. A model can read it; a model cannot produce it."""

    decision: Decision
    reason: DenyReason | None = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.value,
            "reason": self.reason.value if self.reason else None,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ExecutionReceipt:
    """Tamper-evident record of what a host did, or refused to do.

    A DENY produces a receipt too. Silence is not an outcome.
    """

    receipt_id: str
    request_digest: str
    request_id: str
    host: HostIdentity
    capability: str
    subject: str
    lease_id: str | None
    decision: PolicyDecision
    started_at: float
    ended_at: float
    result: Mapping[str, Any]
    effects: Sequence[Mapping[str, Any]]
    evidence: Evidence
    seal: str = ""

    # -- v1 provenance (CONTRACT_V1) ---------------------------------------
    # v0 receipts leave every field below at its default, so `payload()`
    # reproduces the exact v0 key set and already-emitted seals keep
    # verifying. A v1 receipt opts in by setting `contract=CONTRACT_V1`.
    contract: str = CONTRACT
    policy_digest: str | None = None
    capability_digest: str | None = None
    result_digest: str | None = None
    reproduce: Mapping[str, Any] | None = None
    seal_kind: str = "unkeyed"
    claim_digest: str | None = None

    def payload(self) -> dict:
        base = {
            "contract": self.contract,
            "receipt_id": self.receipt_id,
            "request_digest": self.request_digest,
            "request_id": self.request_id,
            "host": self.host.to_dict(),
            "capability": self.capability,
            "subject": self.subject,
            "lease_id": self.lease_id,
            "decision": self.decision.to_dict(),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "result": dict(self.result),
            "effects": [dict(e) for e in self.effects],
            "evidence": self.evidence.value,
        }
        if self.contract == CONTRACT_V1:
            # Provenance is part of the sealed bytes: changing a digest is as
            # visible as changing the decision.
            base["policy_digest"] = self.policy_digest
            base["capability_digest"] = self.capability_digest
            base["result_digest"] = self.result_digest
            base["reproduce"] = dict(self.reproduce) if self.reproduce is not None else None
            base["seal_kind"] = self.seal_kind
            base["claim_digest"] = self.claim_digest
        return base

    def sealed(self) -> "ExecutionReceipt":
        from dataclasses import replace
        return replace(self, seal=digest(self.payload()))

    def verify(self) -> bool:
        return bool(self.seal) and self.seal == digest(self.payload())

    def to_dict(self) -> dict:
        d = self.payload()
        d["seal"] = self.seal
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionReceipt":
        """Round-trip a receipt from its JSON. Required by the Quine Gate
        verifier (M2/M7), which reads receipts off disk. Unknown keys are
        dropped; a tampered value still fails its own seal at ``verify()``."""
        host = data.get("host") or {}
        decision = data.get("decision") or {}
        reason = decision.get("reason")
        return cls(
            receipt_id=data["receipt_id"],
            request_digest=data["request_digest"],
            request_id=data["request_id"],
            host=HostIdentity(**dict(host)),
            capability=data["capability"],
            subject=data["subject"],
            lease_id=data.get("lease_id"),
            decision=PolicyDecision(
                Decision(decision["decision"]),
                DenyReason(reason) if reason else None,
                decision.get("detail", ""),
            ),
            started_at=data["started_at"],
            ended_at=data["ended_at"],
            result=data.get("result", {}),
            effects=data.get("effects", ()),
            evidence=Evidence(data["evidence"]),
            seal=data.get("seal", ""),
            contract=data.get("contract", CONTRACT),
            policy_digest=data.get("policy_digest"),
            capability_digest=data.get("capability_digest"),
            result_digest=data.get("result_digest"),
            reproduce=data.get("reproduce"),
            seal_kind=data.get("seal_kind", "unkeyed"),
            claim_digest=data.get("claim_digest"),
        )


def new_receipt_id() -> str:
    return _uid("rcpt")
