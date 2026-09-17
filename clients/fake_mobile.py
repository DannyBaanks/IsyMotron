"""Fake mobile client.

Stands in for the phone app. It can express intent, ask for leases and read
receipts. It cannot decide anything: every ALLOW in this file comes back from a
host. There is no model here, on purpose — M0 proves the authority grammar
before any planner exists (roadmap section 31, step 11).
"""
from __future__ import annotations

from typing import Any, Mapping

from isymotron.contracts import ExecutionReceipt, ExecutionRequest, Lease
from isymotron.verdicts import Decision
from relay.loopback import LoopbackRelay


class FakeMobile:
    def __init__(self, relay: LoopbackRelay, subject: str) -> None:
        self.relay = relay
        self.subject = subject
        self.leases: dict[tuple[str, str], Lease] = {}

    def devices(self) -> list[dict]:
        return self.relay.hosts()

    def capabilities(self, host_id: str) -> list[str]:
        return [c["id"] for c in self.relay.describe(host_id)["capabilities"]]

    def granted(self, host_id: str) -> list[str]:
        return self.relay.describe(host_id)["granted"]

    def approve(self, host_id: str, capability: str, ttl_s: float = 300.0,
                scope: Mapping[str, Any] | None = None) -> Lease | None:
        """The human tapping 'allow' in the app. Returns None if the host refuses."""
        lease, decision = self.relay.request_lease(host_id, self.subject, capability, ttl_s, scope)
        if decision.decision is Decision.ALLOW and lease is not None:
            self.leases[(host_id, capability)] = lease
            return lease
        return None

    def act(self, host_id: str, capability: str, **params: Any) -> ExecutionReceipt:
        lease = self.leases.get((host_id, capability))
        req = ExecutionRequest.make(
            host_id=host_id, subject=self.subject, capability=capability,
            params=params, lease_id=lease.lease_id if lease else None,
        )
        return self.relay.execute(req)
