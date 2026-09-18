"""Attribution — deciding what actually caused a failed operation.

The rule this file exists to enforce:

    HOST_SUSPENDED != PROVIDER_ERROR

A measurement taken across a suspend, a reboot or a lost network says nothing
about the provider, and must not be counted as if it did. On 2026-09-17 one
such measurement was minutes away from being written up as NVIDIA throttling.

Order matters. Host discontinuity is checked **before** anything about the
error, because a transport failure during a suspend is a suspend, not a
transport failure. The error only gets to speak once continuity is established.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .awareness import HostAwarenessSnapshot, NetworkState


class Attribution(str, Enum):
    OK = "OK"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    HOST_NETWORK_LOSS = "HOST_NETWORK_LOSS"
    HOST_SUSPENDED = "HOST_SUSPENDED"
    PROCESS_INTERRUPTED = "PROCESS_INTERRUPTED"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    UNKNOWN = "UNKNOWN"


#: Attributions that say something about the provider. Only these belong in a
#: provider-reliability corpus.
PROVIDER_FAULTS = frozenset({Attribution.PROVIDER_ERROR})

#: Attributions caused by this machine. They are excluded from provider stats,
#: explicitly rather than silently.
HOST_FAULTS = frozenset({
    Attribution.HOST_SUSPENDED,
    Attribution.HOST_NETWORK_LOSS,
    Attribution.PROCESS_INTERRUPTED,
})


@dataclass(frozen=True)
class OperationOutcome:
    """What happened to one operation, and how firmly we know it."""

    attribution: Attribution
    reason: str
    wall_elapsed_s: float
    awake_elapsed_s: float | None
    host_interruption: bool
    provider_fault: bool
    countable: bool
    before: Mapping[str, Any] = field(default_factory=dict)
    after: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "attribution": self.attribution.value,
            "reason": self.reason,
            "wall_elapsed_s": round(self.wall_elapsed_s, 3),
            "awake_elapsed_s": (None if self.awake_elapsed_s is None
                                else round(self.awake_elapsed_s, 3)),
            "host_interruption": self.host_interruption,
            "provider_fault": self.provider_fault,
            "countable_for_provider_stats": self.countable,
            "before": dict(self.before),
            "after": dict(self.after),
        }


def attribute(before: HostAwarenessSnapshot, after: HostAwarenessSnapshot, *,
              error: Exception | None = None,
              http_status: int | None = None,
              transport: bool = False,
              deadline_s: float | None = None) -> OperationOutcome:
    """Classify one operation from two snapshots and whatever went wrong.

    `error`, `http_status` and `transport` describe what the caller saw.
    Nothing here trusts a model, a prompt or a heuristic about "how long this
    usually takes": every branch below is either a mechanical fact or an
    explicit `UNKNOWN`.
    """
    wall = before.elapsed_wall(after)
    awake = before.elapsed_awake(after)

    def out(attr: Attribution, reason: str) -> OperationOutcome:
        return OperationOutcome(
            attribution=attr,
            reason=reason,
            wall_elapsed_s=wall,
            awake_elapsed_s=awake,
            host_interruption=attr in HOST_FAULTS,
            provider_fault=attr in PROVIDER_FAULTS,
            # A host fault is not evidence about the provider, and neither is
            # an UNKNOWN. Only a clean run or a real provider error counts.
            countable=attr in PROVIDER_FAULTS or attr is Attribution.OK,
            before=before.to_dict(),
            after=after.to_dict(),
        )

    # -- 1. did this process survive intact? --------------------------------
    if before.session_id != after.session_id:
        return out(Attribution.PROCESS_INTERRUPTED,
                   "the session id changed: this is not the same process")
    if before.boot_id != after.boot_id:
        return out(Attribution.PROCESS_INTERRUPTED,
                   f"the machine rebooted during the operation "
                   f"({before.boot_id} -> {after.boot_id})")

    # -- 2. did the machine stay awake? -------------------------------------
    if before.power_epoch != after.power_epoch:
        slept = wall - awake if awake is not None else None
        detail = f", approximately {slept:.1f}s asleep" if slept is not None else ""
        return out(Attribution.HOST_SUSPENDED,
                   f"power_epoch {before.power_epoch} -> {after.power_epoch}: the "
                   f"machine suspended during the operation{detail}. This says "
                   f"nothing about the provider.")

    # -- 3. did the network stay up? ----------------------------------------
    if before.network_epoch != after.network_epoch:
        return out(Attribution.HOST_NETWORK_LOSS,
                   f"network_epoch {before.network_epoch} -> {after.network_epoch}: "
                   f"this machine's connectivity changed during the operation")
    if after.network_state is NetworkState.DOWN:
        return out(Attribution.HOST_NETWORK_LOSS,
                   "this machine reports no network connectivity")

    # -- 4. continuity held. Now the error may speak. -----------------------
    if error is None and http_status is None and not transport:
        if deadline_s is not None and wall > deadline_s:
            return out(Attribution.DEADLINE_EXCEEDED,
                       f"completed, but took {wall:.1f}s against a {deadline_s:.0f}s "
                       f"deadline, with the host awake throughout")
        return out(Attribution.OK, "completed with no host discontinuity")

    if http_status is not None:
        return out(Attribution.PROVIDER_ERROR,
                   f"the provider answered HTTP {http_status} with the host awake "
                   f"throughout")

    if deadline_s is not None and wall > deadline_s:
        # Host was awake the whole time, so the elapsed time is real.
        return out(Attribution.DEADLINE_EXCEEDED,
                   f"{wall:.1f}s against a {deadline_s:.0f}s deadline, host awake "
                   f"throughout")

    if transport:
        if after.network_state is NetworkState.UNKNOWN:
            # We cannot see the network, so we cannot tell a local drop from a
            # remote one. Saying TRANSPORT_ERROR here would quietly blame the
            # provider for something we did not measure.
            return out(Attribution.UNKNOWN,
                       "the connection failed and this host cannot observe its own "
                       "network state; local and remote causes are indistinguishable")
        return out(Attribution.TRANSPORT_ERROR,
                   "the connection failed with this host awake and its network up")

    return out(Attribution.UNKNOWN,
               f"{type(error).__name__ if error else 'failure'} with no host "
               f"discontinuity and no status; not enough evidence to attribute")
