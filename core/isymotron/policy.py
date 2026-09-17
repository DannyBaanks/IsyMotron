"""L0 authority enforcer. Deny-by-default.

Order of checks is part of the contract: a request that fails several checks
reports the *first* one, so that a client cannot probe the scope of a
capability it was never granted.
"""
from __future__ import annotations

import posixpath
from typing import Any, Callable, Mapping

from .contracts import (
    CapabilityManifest,
    ExecutionRequest,
    HostDescription,
    Lease,
    PolicyDecision,
)
from .verdicts import Decision, DenyReason

ALLOW = PolicyDecision(Decision.ALLOW)


def _deny(reason: DenyReason, detail: str = "") -> PolicyDecision:
    return PolicyDecision(Decision.DENY, reason, detail)


# --------------------------------------------------------------------------
# Scope checkers: one per capability family. Unregistered family -> DENY.
# --------------------------------------------------------------------------

ScopeChecker = Callable[[CapabilityManifest, Mapping[str, Any], Mapping[str, Any]], PolicyDecision]
_CHECKERS: dict[str, ScopeChecker] = {}


def scope_checker(family: str) -> Callable[[ScopeChecker], ScopeChecker]:
    def wrap(fn: ScopeChecker) -> ScopeChecker:
        _CHECKERS[family] = fn
        return fn
    return wrap


def normalize_path(p: str) -> str:
    """One path grammar for every host generation.

    Win98 and Win11 disagree about separators and case; the contract does not.
    Backslashes fold to '/', drive letters uppercase, case-insensitive compare
    is done by the caller on the normalized form.
    """
    p = p.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        p = p[0].upper() + p[1:]
    p = posixpath.normpath(p)
    return p


def _under(root: str, path: str) -> bool:
    """True iff `path` is `root` or lives beneath it. Rejects '..' escapes,
    and rejects sibling prefixes ('/Photos2' is not under '/Photos')."""
    r = normalize_path(root).rstrip("/").lower()
    q = normalize_path(path).rstrip("/").lower()
    return q == r or q.startswith(r + "/")


@scope_checker("filesystem")
def _fs_scope(cap: CapabilityManifest, granted_scope: Mapping[str, Any],
              params: Mapping[str, Any]) -> PolicyDecision:
    path = params.get("path")
    if not isinstance(path, str) or not path:
        return _deny(DenyReason.MALFORMED_REQUEST, "filesystem.* requires a 'path' string")
    roots = granted_scope.get("roots") or []
    if not roots:
        # Empty grant set is a refusal, not a wildcard. Fail closed.
        return _deny(DenyReason.OUT_OF_SCOPE, "no roots granted for this capability")
    for root in roots:
        if _under(root, path):
            return ALLOW
    return _deny(DenyReason.OUT_OF_SCOPE, f"{normalize_path(path)} is outside {list(roots)}")


@scope_checker("apps")
def _apps_scope(cap: CapabilityManifest, granted_scope: Mapping[str, Any],
                params: Mapping[str, Any]) -> PolicyDecision:
    target = params.get("app")
    if not isinstance(target, str) or not target:
        return _deny(DenyReason.MALFORMED_REQUEST, "apps.* requires an 'app' string")
    allow = [a.lower() for a in (granted_scope.get("allowlist") or [])]
    if not allow:
        return _deny(DenyReason.OUT_OF_SCOPE, "no app allowlist granted")
    if target.lower() in allow:
        return ALLOW
    return _deny(DenyReason.OUT_OF_SCOPE, f"'{target}' is not in the app allowlist")


@scope_checker("system")
def _system_scope(cap: CapabilityManifest, granted_scope: Mapping[str, Any],
                  params: Mapping[str, Any]) -> PolicyDecision:
    # system.info is read-only and unparameterized in V0.
    return ALLOW


@scope_checker("process")
def _process_scope(cap: CapabilityManifest, granted_scope: Mapping[str, Any],
                   params: Mapping[str, Any]) -> PolicyDecision:
    if params.get("mutate"):
        return _deny(DenyReason.EXCESS_AUTHORITY, "process.* is read-only in V0")
    return ALLOW


# --------------------------------------------------------------------------
# The enforcer
# --------------------------------------------------------------------------

class Enforcer:
    """Pure function over (host description, leases, request) -> decision.

    Holds no I/O and performs no execution. It is the only thing in the system
    allowed to return ALLOW.
    """

    def __init__(self, description: HostDescription, admin_granted: bool = False) -> None:
        self.description = description
        self.admin_granted = admin_granted
        self._by_id = {c.id: c for c in description.capabilities}
        self._granted = set(description.granted)

    def decide(self, req: ExecutionRequest, lease: Lease | None,
               now: float | None = None) -> PolicyDecision:
        if req.host_id != self.description.identity.host_id:
            return _deny(DenyReason.MALFORMED_REQUEST, "request addressed to another host")

        cap = self._by_id.get(req.capability)
        if cap is None:
            return _deny(DenyReason.CAPABILITY_UNAVAILABLE,
                         f"{self.description.identity.host_id} does not implement {req.capability}")

        if req.capability not in self._granted:
            return _deny(DenyReason.CAPABILITY_NOT_GRANTED,
                         f"{req.capability} is not granted on this host")

        if cap.requires_admin and not self.admin_granted:
            return _deny(DenyReason.EXCESS_AUTHORITY,
                         f"{req.capability} declares requires_admin and admin is not granted")

        if lease is None:
            return _deny(DenyReason.LEASE_MISSING, "no lease presented")
        if lease.lease_id != req.lease_id:
            return _deny(DenyReason.LEASE_MISMATCH, "presented lease is not the requested one")
        if lease.revoked:
            return _deny(DenyReason.LEASE_REVOKED, lease.lease_id)
        if not lease.alive(now):
            return _deny(DenyReason.LEASE_EXPIRED, lease.lease_id)
        if (lease.host_id != req.host_id or lease.subject != req.subject
                or lease.capability != req.capability):
            return _deny(DenyReason.LEASE_MISMATCH, "lease does not bind this host/subject/capability")

        unknown = [k for k in req.params if k not in cap.params]
        if unknown:
            return _deny(DenyReason.MALFORMED_REQUEST, f"undeclared params: {sorted(unknown)}")

        family = req.capability.split(".", 1)[0]
        checker = _CHECKERS.get(family)
        if checker is None:
            # Preregistered else-branch: an unmapped family is never the
            # permissive case.
            return _deny(DenyReason.CAPABILITY_UNAVAILABLE,
                         f"no scope checker registered for family '{family}'")

        return checker(cap, lease.scope, req.params)
