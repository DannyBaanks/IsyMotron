"""Loopback relay.

The relay routes typed messages to hosts and nothing else. It holds no policy,
issues no leases and cannot execute. If this file were replaced by a WebSocket
server the rest of the system would not notice — which is invariant 2.3.
"""
from __future__ import annotations

from typing import Any, Mapping

from isymotron.contracts import ExecutionReceipt, ExecutionRequest, Lease, PolicyDecision
from isymotron.host import Host
from isymotron.verdicts import Decision, DenyReason


class RelayError(Exception):
    pass


class LoopbackRelay:
    """In-process transport. One dict lookup where a network will later sit."""

    def __init__(self) -> None:
        self._hosts: dict[str, Host] = {}
        self.log: list[dict[str, Any]] = []

    def attach(self, host: Host) -> None:
        self._hosts[host.identify().host_id] = host

    def hosts(self) -> list[dict]:
        return [h.identify().to_dict() for h in self._hosts.values()]

    def _host(self, host_id: str) -> Host:
        host = self._hosts.get(host_id)
        if host is None:
            raise RelayError(f"no host attached with id {host_id!r}")
        return host

    # -- routed operations --------------------------------------------------
    def describe(self, host_id: str) -> dict:
        self.log.append({"op": "describe", "host": host_id})
        return self._host(host_id).describe().to_dict()

    def request_lease(self, host_id: str, subject: str, capability: str,
                      ttl_s: float, scope: Mapping[str, Any] | None = None
                      ) -> tuple[Lease | None, PolicyDecision]:
        self.log.append({"op": "request_lease", "host": host_id, "capability": capability})
        return self._host(host_id).request_lease(subject, capability, ttl_s, scope)

    def execute(self, req: ExecutionRequest) -> ExecutionReceipt:
        self.log.append({"op": "execute", "host": req.host_id, "capability": req.capability})
        return self._host(req.host_id).execute_capability(req)

    def receipt(self, host_id: str, receipt_id: str) -> ExecutionReceipt | None:
        return self._host(host_id).return_receipt(receipt_id)

    def health(self, host_id: str) -> dict:
        return self._host(host_id).health()
