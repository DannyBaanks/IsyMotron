"""The 8-operation host surface, and the base class every engine implements.

Adding a ninth operation is a contract change, not a feature. The point of the
number is that a Windows 98 bridge can plausibly implement all of it.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Mapping

from .canon import digest
from .contracts import (
    CONTRACT_V1,
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
from .resources import (
    app_entries,
    fs_roots,
    logical_bounds,
    resolve_app,
    resolve_path,
    to_uri,
)
from .seal import HMAC_SHA256, UNKEYED, resolve_key
from .verdicts import Decision, DenyReason, Evidence
from .verify import ClaimBundle

OPERATIONS = (
    "identify", "describe", "list_capabilities", "request_lease",
    "validate_lease", "execute_capability", "return_receipt", "health",
)


class ScopeViolation(Exception):
    """An engine refused on *authority* grounds after the enforcer said ALLOW.

    This exists because `Enforcer` decides on the request as written, and some
    scope facts are only knowable once the OS resolves it — a junction inside a
    granted root, a case-folding collision, a device path. The engine is
    therefore the second half of enforcement, and it needs a way to say DENY
    rather than a way to fail.

    Raising a plain exception instead would record the refusal as ALLOW with an
    UNKNOWN outcome, which reads as an allowed action in the receipt ledger.
    See docs/FINDINGS.md, finding 1.
    """

    def __init__(self, reason: DenyReason, detail: str = "") -> None:
        super().__init__(detail or reason.value)
        self.reason = reason
        self.detail = detail


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
                 max_lease_ttl_s: float = 900.0,
                 tool_profile: str = "security",
                 custom: Mapping[str, Any] | None = None,
                 inert: bool = False) -> None:
        self._identity = identity
        self._capabilities = capabilities
        self._granted = list(granted)
        self._grant_scopes = {k: dict(v) for k, v in grant_scopes.items()}
        self._admin_granted = admin_granted
        self._max_ttl = max_lease_ttl_s
        self._tool_profile = tool_profile if tool_profile in ("full", "security", "custom") else "security"
        self._inert = inert
        self._custom = dict(custom) if isinstance(custom, Mapping) else None
        # capability -> (horizon, approved_scope) for approval-minted grants.
        self._approved: dict[str, tuple[float, dict[str, Any]]] = {}
        self._leases: dict[str, Lease] = {}
        self._receipts: dict[str, ExecutionReceipt] = {}
        self._claim_bundles: dict[str, ClaimBundle] = {}
        self._enforcer = Enforcer(self.describe(), admin_granted=admin_granted)

    # -- tool profile view --------------------------------------------------

    @property
    def tool_profile(self) -> str:
        return self._tool_profile

    @property
    def custom_profile(self) -> dict[str, Any] | None:
        return dict(self._custom) if isinstance(self._custom, Mapping) else None

    def _prune_expired_approvals(self) -> bool:
        import time as _t
        now = _t.time()
        expired = [c for c, (horizon, _scope) in self._approved.items() if horizon <= now]
        for c in expired:
            del self._approved[c]
        return bool(expired)

    def _rebuild_enforcer(self) -> None:
        self._enforcer = Enforcer(self.describe(), admin_granted=self._admin_granted)

    def _effective_granted(self) -> list[str]:
        static = list(self._granted)
        extra = []
        import time as _t
        now = _t.time()
        for cap, (horizon, _scope) in self._approved.items():
            if horizon > now:
                extra.append(cap)
        # Planner-visible catalogue per profile:
        # full and security expose all manifest capabilities; the difference
        # is at the lease gate (no prompt vs prompt). custom exposes only its
        # pre-selected set plus live approval grants.
        if self._inert:
            return []
        if self._tool_profile == "full":
            return [c.id for c in self._capabilities]
        if self._tool_profile == "custom":
            allowed = self._custom.get("capabilities") if isinstance(self._custom, Mapping) else None
            allowed_ids = set(allowed) if isinstance(allowed, list) else set()
            ids = [c.id for c in self._capabilities if c.id in allowed_ids]
            ids.extend(extra)
            return ids
        return [c.id for c in self._capabilities]

    # -- 1 ------------------------------------------------------------------
    def identify(self) -> HostIdentity:
        return self._identity

    # -- 2 ------------------------------------------------------------------
    def describe(self) -> HostDescription:
        granted = self._effective_granted()
        granted_scopes = {c: self._grant_scopes.get(c, {}) for c in granted}
        return HostDescription(self._identity, list(self._capabilities),
                               granted, logical_bounds(granted_scopes))

    # -- 3 ------------------------------------------------------------------
    def list_capabilities(self) -> list[CapabilityManifest]:
        """Only granted capabilities are listed. Ungranted ones are absent from
        the agent's world, not merely forbidden in it (invariant 2.5)."""
        effective = self._effective_granted()
        return [c for c in self._capabilities if c.id in effective]

    # -- 4 ------------------------------------------------------------------
    def request_lease(self, subject: str, capability: str,
                      ttl_s: float, scope: Mapping[str, Any] | None = None
                      ) -> tuple[Lease | None, PolicyDecision]:
        """The host, not the caller, decides the scope of a lease.

        A caller may ask for less than it was granted (`scope` narrows), never
        for more. Anything outside the local grant is dropped, not refused, so
        that narrowing is always safe to attempt.
        """
        known = any(c.id == capability for c in self._capabilities)
        if not known:
            return None, PolicyDecision(Decision.DENY, DenyReason.CAPABILITY_UNAVAILABLE, capability)
        if self._inert:
            return None, PolicyDecision(
                Decision.DENY, DenyReason.CAPABILITY_UNAVAILABLE,
                f"host is inert: {self._tool_profile} profile with no grant file")
        cap = next(c for c in self._capabilities if c.id == capability)
        if cap.requires_admin and not self._admin_granted:
            return None, PolicyDecision(Decision.DENY, DenyReason.EXCESS_AUTHORITY, capability)
        if self._prune_expired_approvals():
            self._rebuild_enforcer()

        if self._tool_profile == "security":
            approved = self._approved.get(capability)
            if approved is None:
                return None, PolicyDecision(
                    Decision.DENY, DenyReason.NEEDS_APPROVAL,
                    f"{capability} needs approval in security mode")
            horizon, approved_scope = approved
            effective = _narrow(approved_scope, scope)
            ttl = min(float(ttl_s), self._max_ttl, max(horizon - time.time(), 0.0))
            lease = Lease.issue(self._identity.host_id, subject, capability, effective, ttl)
            self._leases[lease.lease_id] = lease
            return lease, PolicyDecision(Decision.ALLOW)

        if self._tool_profile == "custom":
            allowed = self._custom.get("capabilities") if isinstance(self._custom, Mapping) else []
            prompts = bool(self._custom.get("allow_request_prompts", False)) if isinstance(self._custom, Mapping) else False
            if capability in allowed:
                granted_scope = dict(self._grant_scopes.get(capability, {}))
                effective = _narrow(granted_scope, scope)
                ttl = min(float(ttl_s), self._max_ttl)
                lease = Lease.issue(self._identity.host_id, subject, capability, effective, ttl)
                self._leases[lease.lease_id] = lease
                return lease, PolicyDecision(Decision.ALLOW)
            approved = self._approved.get(capability)
            if approved is not None:
                horizon, approved_scope = approved
                effective = _narrow(approved_scope, scope)
                ttl = min(float(ttl_s), self._max_ttl, max(horizon - time.time(), 0.0))
                lease = Lease.issue(self._identity.host_id, subject, capability, effective, ttl)
                self._leases[lease.lease_id] = lease
                return lease, PolicyDecision(Decision.ALLOW)
            if prompts:
                return None, PolicyDecision(
                    Decision.DENY, DenyReason.NEEDS_APPROVAL,
                    f"{capability} needs approval in custom mode")
            return None, PolicyDecision(
                Decision.DENY, DenyReason.CAPABILITY_NOT_GRANTED,
                f"{capability} is not in the custom allow-list")

        # full: every manifest capability may lease immediately.
        granted_scope = dict(self._grant_scopes.get(capability, {}))
        effective = _narrow(granted_scope, scope)
        ttl = min(float(ttl_s), self._max_ttl)
        lease = Lease.issue(self._identity.host_id, subject, capability, effective, ttl)
        self._leases[lease.lease_id] = lease
        return lease, PolicyDecision(Decision.ALLOW)

    def record_external_approval(self, subject: str, capability: str,
                                 scope: Mapping[str, Any] | None, ttl_s: float) -> None:
        """Apply an approval fact recorded in the shared permission queue
        (decisions arrive from process(); this host just needs to honor the
        bound for its TTL). No new lease is minted here."""
        import time as _t
        horizon = _t.time() + max(float(ttl_s), 0.0)
        self._approved[capability] = (horizon, dict(scope or {}))
        self._rebuild_enforcer()

    def mint_approved_lease(self, subject: str, capability: str,
                            scope: Mapping[str, Any] | None, ttl_s: float) -> tuple[Lease | None, PolicyDecision]:
        """Approval mints: a human said yes; enforce bounds, omit the profile gate."""
        known = any(c.id == capability for c in self._capabilities)
        if not known:
            return None, PolicyDecision(Decision.DENY, DenyReason.CAPABILITY_UNAVAILABLE, capability)
        if self._inert:
            return None, PolicyDecision(
                Decision.DENY, DenyReason.CAPABILITY_UNAVAILABLE,
                f"host is inert: no grant file")
        # The grants file bounds anything a human may approve.
        if capability not in self._granted and self._tool_profile != "full":
            return None, PolicyDecision(
                Decision.DENY, DenyReason.CAPABILITY_NOT_GRANTED,
                f"capability {capability} is not declared on this host")
        cap = next(c for c in self._capabilities if c.id == capability)
        if cap.requires_admin and not self._admin_granted:
            return None, PolicyDecision(Decision.DENY, DenyReason.EXCESS_AUTHORITY, capability)
        # The declared file scope bounds anything human approval may widen to.
        scope = _narrow(dict(self._grant_scopes.get(capability, {})), dict(scope or {}))
        ttl = min(float(ttl_s), self._max_ttl)
        lease = Lease.issue(self._identity.host_id, subject, capability, scope, ttl)
        self._leases[lease.lease_id] = lease
        import time as _t
        self._approved[capability] = (_t.time() + ttl, scope)
        self._rebuild_enforcer()
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
        # Pin the decision instant. The receipt is reproduced at this exact
        # time, so a lease alive at decision time stays alive during
        # re-derivation instead of looking expired against the wall clock.
        decided_at = started if now is None else now
        lease = self._leases.get(req.lease_id) if req.lease_id else None
        policy_input = self._enforcer.description
        decision = self._enforcer.decide(req, lease, now=decided_at)
        engine_overrode = False

        result: dict[str, Any] = {}
        effects: list[dict[str, Any]] = []
        if decision.decision is Decision.ALLOW:
            try:
                result, effects = self.run(_physical(req, lease.scope))
                result = _logical(req.capability, result, lease.scope)
                evidence = Evidence.DEMONSTRATED
            except ScopeViolation as exc:
                # The engine overrides the enforcer's ALLOW. A refusal is a
                # refusal wherever it is discovered, and it carries no payload.
                decision = PolicyDecision(Decision.DENY, exc.reason, exc.detail)
                engine_overrode = True
                result, effects = {}, []
                evidence = Evidence.DEMONSTRATED
            except Exception as exc:  # engine failure is not a policy verdict
                result = {"error": type(exc).__name__, "message": str(exc)}
                effects = []
                evidence = Evidence.UNKNOWN
        else:
            evidence = Evidence.DEMONSTRATED  # the refusal itself is demonstrated

        # Quine Gate v1 provenance. A decision the enforcer alone produced is
        # re-derivable from the bundle; an engine override is not -- it depends
        # on OS state the verifier does not have -- so no claim is made for it.
        bundle = None
        if not engine_overrode:
            bundle = ClaimBundle(
                host=policy_input,
                request=req,
                lease=lease,
                decided_at=decided_at,
                expected=decision,
                admin_granted=self._enforcer.admin_granted,
            )
        capability = next((c for c in policy_input.capabilities
                           if c.id == req.capability), None)

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
            contract=CONTRACT_V1,
            claim_digest=bundle.digest() if bundle is not None else None,
            policy_digest=digest(policy_input.to_dict()),
            capability_digest=digest(capability.to_dict()) if capability else None,
            result_digest=digest(result),
            reproduce={"tool": self._identity.engine,
                       "request_digest": req.digest(),
                       "decided_at": decided_at},
            seal_kind=HMAC_SHA256 if resolve_key() else UNKEYED,
        ).sealed()
        self._receipts[receipt.receipt_id] = receipt
        if bundle is not None:
            self._claim_bundles[receipt.receipt_id] = bundle
        return receipt

    def claim_bundle(self, receipt_id: str) -> ClaimBundle | None:
        """The reproduction inputs for a v1 receipt.

        An evidence helper, not one of the 8 contract operations: the receipt
        travels without the raw params, and the bundle stays local.
        """
        return self._claim_bundles.get(receipt_id)

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


def _physical(req: ExecutionRequest, scope: Mapping[str, Any]) -> ExecutionRequest:
    """The request an engine runs: logical names turned into what they name.

    Only called after ALLOW, so every name here already resolved once in the
    enforcer. The receipt keeps the request as the planner wrote it; the
    engine alone sees where things physically are.
    """
    family = req.capability.split(".", 1)[0]
    params = dict(req.params)
    if family == "filesystem" and "path" in params:
        physical = resolve_path(params["path"], fs_roots(scope))
        if physical is None:
            raise ScopeViolation(DenyReason.OUT_OF_SCOPE, f"{params['path']} names no granted resource")
        params["path"] = physical
    elif family == "apps" and "app" in params:
        app = resolve_app(params["app"], app_entries(scope))
        if app is None:
            raise ScopeViolation(DenyReason.OUT_OF_SCOPE, f"'{params['app']}' is not in the app allowlist")
        params["app"] = app.exe
    else:
        return req
    from dataclasses import replace
    return replace(req, params=params)


def _logical(capability: str, result: dict, scope: Mapping[str, Any]) -> dict:
    """Results name resources the way the planner does.

    A later step references an earlier result (`{"$from": ...}`), so a result
    that answered in physical paths would hand the plan a name it cannot use
    -- and leak the folder layout the catalogue kept back. Listings gain a
    `uri` per entry, `newest` and `newest_name`, which is what "the most recent one" means.
    """
    if not capability.startswith("filesystem.") or not isinstance(result, dict):
        return result
    roots = fs_roots(scope)
    out = dict(result)
    uri = to_uri(out.get("path"), roots)
    if uri is not None:
        out["path"] = uri
    if out.get("kind") == "directory" and uri is not None:
        entries = [dict(e, uri=f"{uri}/{e['name']}") for e in out.get("entries") or []]
        out["entries"] = entries
        files = [e for e in entries if e.get("kind") == "file"]
        # By timestamp, not by position: the engine's sort order is its own.
        newest = max(files, key=lambda e: e.get("modified") or "") if files else None
        out["newest"] = newest["uri"] if newest else None
        out["newest_name"] = newest["name"] if newest else None
    return out


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
