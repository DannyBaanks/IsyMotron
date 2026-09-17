"""The 8-operation host surface, and the base class every engine implements.

Adding a ninth operation is a contract change, not a feature. The point of the
number is that a Windows 98 bridge can plausibly implement all of it.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Mapping

from .contracts import (
    CapabilityManifest,
    ExecutionReceipt,
    ExecutionRequest,
    HostDescription,
    HostIdentity,
    Lease,
    PolicyDecision,
    new_receipt_id,
)
from .policy import Enforcer
from .verdicts import Decision, DenyReason, Evidence

OPERATIONS = (
    "identify", "describe", "list_capabilities", "request_lease",
    "validate_lease", "execute_capability", "return_receipt", "health",
)


class Host(ABC):
    """A participation surface on one device.

    Subclasses provide identity, manifests and the local execution engine.
    Authority is enforced here, in the base class, identically for every OS.
    """

    def __init__(self, identity: HostIdentity,
                 capabilities: list[CapabilityManifest],
                 granted: list[str],
                 grant_scopes: Mapping[str, Mapping[str, Any]],
                 admin_granted: bool = False,
                 max_lease_ttl_s: float = 900.0) -> None:
        self._identity = identity
        self._capabilities = capabilities
        self._granted = list(granted)
        self._grant_scopes = {k: dict(v) for k, v in grant_scopes.items()}
        self._admin_granted = admin_granted
        self._max_ttl = max_lease_ttl_s
        self._leases: dict[str, Lease] = {}
        self._receipts: dict[str, ExecutionReceipt] = {}
        self._enforcer = Enforcer(self.describe(), admin_granted=admin_granted)

    # -- 1 ------------------------------------------------------------------
    def identify(self) -> HostIdentity:
        return self._identity

    # -- 2 ------------------------------------------------------------------
    def describe(self) -> HostDescription:
        return HostDescription(self._identity, list(self._capabilities), list(self._granted))

    # -- 3 ------------------------------------------------------------------
    def list_capabilities(self) -> list[CapabilityManifest]:
        """Only granted capabilities are listed. Ungranted ones are absent from
        the agent's world, not merely forbidden in it (invariant 2.5)."""
        return [c for c in self._capabilities if c.id in self._granted]

    # -- 4 ------------------------------------------------------------------
    def request_lease(self, subject: str, capability: str,
                      ttl_s: float, scope: Mapping[str, Any] | None = None
                      ) -> tuple[Lease | None, PolicyDecision]:
        """The host, not the caller, decides the scope of a lease.

        A caller may ask for less than it was granted (`scope` narrows), never
        for more. Anything outside the local grant is dropped, not refused, so
        that narrowing is always safe to attempt.
        """
        if capability not in self._granted:
            known = any(c.id == capability for c in self._capabilities)
            reason = DenyReason.CAPABILITY_NOT_GRANTED if known else DenyReason.CAPABILITY_UNAVAILABLE
            return None, PolicyDecision(Decision.DENY, reason, capability)

        granted_scope = dict(self._grant_scopes.get(capability, {}))
        effective = _narrow(granted_scope, scope)
        ttl = min(float(ttl_s), self._max_ttl)
        lease = Lease.issue(self._identity.host_id, subject, capability, effective, ttl)
        self._leases[lease.lease_id] = lease
        return lease, PolicyDecision(Decision.ALLOW)

    # -- 5 ------------------------------------------------------------------
    def validate_lease(self, lease_id: str, now: float | None = None) -> bool:
        lease = self._leases.get(lease_id)
        return bool(lease and lease.alive(now))

    def revoke_lease(self, lease_id: str) -> bool:
        lease = self._leases.get(lease_id)
        if not lease:
            return False
        from dataclasses import replace
        self._leases[lease_id] = replace(lease, revoked=True)
        return True

    # -- 6 ------------------------------------------------------------------
    def execute_capability(self, req: ExecutionRequest, now: float | None = None) -> ExecutionReceipt:
        started = time.time()
        lease = self._leases.get(req.lease_id) if req.lease_id else None
        decision = self._enforcer.decide(req, lease, now=now)

        result: dict[str, Any] = {}
        effects: list[dict[str, Any]] = []
        if decision.decision is Decision.ALLOW:
            try:
                result, effects = self.run(req)
                evidence = Evidence.DEMONSTRATED
            except Exception as exc:  # engine failure is not a policy verdict
                result = {"error": type(exc).__name__, "message": str(exc)}
                evidence = Evidence.UNKNOWN
        else:
            evidence = Evidence.DEMONSTRATED  # the refusal itself is demonstrated

        receipt = ExecutionReceipt(
            receipt_id=new_receipt_id(),
            request_digest=req.digest(),
            request_id=req.request_id,
            host=self._identity,
            capability=req.capability,
            subject=req.subject,
            lease_id=req.lease_id,
            decision=decision,
            started_at=started,
            ended_at=time.time(),
            result=result,
            effects=effects,
            evidence=evidence,
        ).sealed()
        self._receipts[receipt.receipt_id] = receipt
        return receipt

    # -- 7 ------------------------------------------------------------------
    def return_receipt(self, receipt_id: str) -> ExecutionReceipt | None:
        return self._receipts.get(receipt_id)

    # -- 8 ------------------------------------------------------------------
    def health(self) -> dict:
        return {
            "host_id": self._identity.host_id,
            "contract": self._identity.contract,
            "engine": self._identity.engine,
            "ok": True,
            "granted_capabilities": len(self._granted),
            "live_leases": sum(1 for l in self._leases.values() if l.alive()),
            "receipts": len(self._receipts),
        }

    # -- local engine -------------------------------------------------------
    @abstractmethod
    def run(self, req: ExecutionRequest) -> tuple[dict, list[dict]]:
        """Perform the already-authorized action.

        Contract: this is called only after ALLOW. It must never consult policy
        and must never widen scope. It returns (result, effects), where effects
        are the observable side effects this engine believes it produced.
        """


def _narrow(granted: Mapping[str, Any], asked: Mapping[str, Any] | None) -> dict:
    """Intersect a requested scope with the locally granted one."""
    if not asked:
        return dict(granted)
    out = dict(granted)
    for key, want in asked.items():
        have = granted.get(key)
        if isinstance(have, list) and isinstance(want, list):
            keep = [v for v in want if v in have]
            out[key] = keep
        # keys the local grant never mentioned are ignored, not added
    return out
