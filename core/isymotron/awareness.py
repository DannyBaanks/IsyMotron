"""HostAwarenessEngine — deterministic facts about the machine itself.

Why this exists
---------------
On 2026-09-17 a 25-call measurement against NVIDIA NIM produced one request
that appeared to take 793 s despite `timeout=120`, followed by eighteen
status-less transport failures, followed by clean recovery. The obvious reading
was provider throttling. The truth was that the laptop had been closed and
carried out of the house.

No amount of reasoning could have recovered that. The process was frozen; the
evidence was not in the process. And critically, on Windows **neither of
Python's clocks would have revealed it** — measured on this machine,
`time.monotonic()` is exactly `GetTickCount64()`, and both it and `time.time()`
advance through suspend. A 793-second sleep looks like a 793-second call.

The principle, frozen:

    Do not ask a model to infer host state when the host can report it
    deterministically.

What it is not
--------------
This engine produces **facts, not policy**. It grants no capability, executes
nothing, and cannot alter authority. Sentinel/`Enforcer` decides what is
allowed; the Doctor observes effects; a model interprets. This answers only
"what happened to the machine", and it is allowed to answer `UNKNOWN`.

A model may read these events. A model may never create one.
"""
from __future__ import annotations

import os
import time
import uuid
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .canon import digest
from .verdicts import Evidence

CONTRACT = "HostAwareness/v0"


class PowerState(str, Enum):
    """Observed power state.

    A process cannot run while its machine is suspended, so `SUSPENDED` is
    never the answer to "what are you now" — it is only ever reconstructed
    afterwards from evidence. `SUSPENDING` requires a pre-suspend notification
    we do not currently receive. Both are in the vocabulary because a future
    provider may observe them; neither is ever guessed.
    """

    ACTIVE = "ACTIVE"
    SUSPENDING = "SUSPENDING"
    SUSPENDED = "SUSPENDED"
    RESUMING = "RESUMING"
    UNKNOWN = "UNKNOWN"


class NetworkState(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


class HostEventType(str, Enum):
    HOST_BOOT = "HOST_BOOT"
    HOST_SHUTDOWN = "HOST_SHUTDOWN"
    HOST_SUSPEND_REQUESTED = "HOST_SUSPEND_REQUESTED"
    HOST_RESUMED = "HOST_RESUMED"
    NETWORK_UP = "NETWORK_UP"
    NETWORK_DOWN = "NETWORK_DOWN"
    NETWORK_CHANGED = "NETWORK_CHANGED"
    PROCESS_STARTED = "PROCESS_STARTED"
    PROCESS_RESTARTED = "PROCESS_RESTARTED"


@dataclass(frozen=True)
class HostEvent:
    """One operational fact, traceable to the mechanism that produced it.

    `source` names that mechanism. `evidence` says how firmly it is known:
    a suspend reconstructed from a clock bias is `DEMONSTRATED` (the bias is
    mechanical); one inferred from a wall-clock gap alone is `INFERRED`.
    """

    event_id: str
    host_id: str
    event_type: HostEventType
    wall_time: float
    source: str
    evidence: Evidence = Evidence.DEMONSTRATED
    monotonic_time: float | None = None
    unbiased_time: float | None = None
    boot_id: str = ""
    session_id: str = ""
    power_epoch: int = 0
    network_epoch: int = 0
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        d["evidence"] = self.evidence.value
        d["detail"] = dict(self.detail)
        return d


@dataclass(frozen=True)
class HostAwarenessSnapshot:
    """Everything an operation needs to know it was not interrupted.

    Take one before, one after, compare the epochs. That comparison is the
    whole product of this engine.
    """

    host_id: str
    boot_id: str
    session_id: str
    power_state: PowerState
    power_epoch: int
    network_state: NetworkState
    network_epoch: int
    wall_time: float
    monotonic_time: float
    unbiased_time: float | None
    contract: str = CONTRACT

    def to_dict(self) -> dict:
        d = asdict(self)
        d["power_state"] = self.power_state.value
        d["network_state"] = self.network_state.value
        return d

    def same_continuity_as(self, other: "HostAwarenessSnapshot") -> bool:
        """True iff nothing discontinuous happened between the two."""
        return (self.boot_id == other.boot_id
                and self.session_id == other.session_id
                and self.power_epoch == other.power_epoch
                and self.network_epoch == other.network_epoch)

    def elapsed_wall(self, other: "HostAwarenessSnapshot") -> float:
        return abs(other.wall_time - self.wall_time)

    def elapsed_awake(self, other: "HostAwarenessSnapshot") -> float | None:
        """Seconds the machine was actually running between two snapshots.

        `None` when no unbiased clock is available -- which is a different
        thing from zero, and is reported as such.
        """
        if self.unbiased_time is None or other.unbiased_time is None:
            return None
        return abs(other.unbiased_time - self.unbiased_time)


# --------------------------------------------------------------------------
# Provider seam
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PowerSample:
    """Raw facts from one platform reading. No interpretation.

    `suspend_bias_s` is the total wall-clock time this machine has spent
    suspended since boot. It is monotonically non-decreasing, and any increase
    between two samples is exactly the time slept in between. Where the
    platform cannot supply it, it is `None` -- never 0.0.
    """

    wall_time: float
    monotonic_time: float
    unbiased_time: float | None = None
    suspend_bias_s: float | None = None
    boot_wall_time: float | None = None
    network_state: NetworkState = NetworkState.UNKNOWN
    source: str = "unknown"
    detail: Mapping[str, Any] = field(default_factory=dict)


class PowerProvider(ABC):
    """A platform's window onto power and network facts."""

    name = "abstract"

    @abstractmethod
    def sample(self) -> PowerSample:
        """Read the platform now. Must not block for long and must not raise:
        an unreadable fact is `None`, not an exception."""

    def describe(self) -> dict:
        return {"provider": self.name}

    def history(self) -> list[HostEvent]:
        """Corroborating events from an OS log, if the platform has one.

        Optional. These are a *second* source and are never required for a
        verdict -- the clock bias is the primary mechanism.
        """
        return []


class NullPowerProvider(PowerProvider):
    """Knows nothing and says so. Used where no platform backend exists.

    Deliberately not a stub that reports ACTIVE: reporting a state we cannot
    observe is precisely the failure this engine exists to prevent.
    """

    name = "null"

    def sample(self) -> PowerSample:
        return PowerSample(
            wall_time=time.time(),
            monotonic_time=time.monotonic(),
            unbiased_time=None,
            suspend_bias_s=None,
            network_state=NetworkState.UNKNOWN,
            source="null",
        )


class TestPowerProvider(PowerProvider):
    """Deterministic provider for tests. Suspends and network drops on demand.

    Exists so that proving attribution never requires physically closing a
    laptop. Follows the same shape as `ScriptedProvider` in agents/provider.py.
    """

    name = "test"
    #: pytest would otherwise try to collect this as a test class.
    __test__ = False

    def __init__(self, wall: float = 1_000_000.0, boot_wall: float | None = None) -> None:
        self._wall = wall
        self._mono = 1000.0
        self._unbiased = 1000.0
        self._bias = 0.0
        self._boot_wall = wall - 1000.0 if boot_wall is None else boot_wall
        self._network = NetworkState.UP

    # -- knobs --------------------------------------------------------------
    def advance(self, seconds: float) -> None:
        """Time passes with the machine awake."""
        self._wall += seconds
        self._mono += seconds
        self._unbiased += seconds

    def suspend(self, seconds: float) -> None:
        """The machine sleeps for `seconds` of wall clock.

        Mirrors the measured Windows behaviour exactly: wall and monotonic both
        advance, the unbiased clock does not, and the bias grows by the gap.
        """
        self._wall += seconds
        self._mono += seconds
        self._bias += seconds

    def network_down(self) -> None:
        self._network = NetworkState.DOWN

    def network_up(self) -> None:
        self._network = NetworkState.UP

    def reboot(self, down_seconds: float = 30.0) -> None:
        self._wall += down_seconds
        self._mono = 0.0
        self._unbiased = 0.0
        self._bias = 0.0
        self._boot_wall = self._wall

    # -- provider -----------------------------------------------------------
    def sample(self) -> PowerSample:
        return PowerSample(
            wall_time=self._wall,
            monotonic_time=self._mono,
            unbiased_time=self._unbiased,
            suspend_bias_s=self._bias,
            boot_wall_time=self._boot_wall,
            network_state=self._network,
            source="test",
        )


# --------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------

# A bias reading has measurement noise. On the real machine the bias moved
# 2.2 ms across a two-second awake interval, so anything under a second is
# noise and anything over it is a machine that actually slept.
SUSPEND_THRESHOLD_S = 1.0


class HostAwarenessEngine:
    """Tracks continuity. Four operations, no policy, no execution.

    `describe`, `snapshot`, `recent_events`, `health` -- the same shape the
    host contract uses, deliberately.
    """

    def __init__(self, host_id: str, provider: PowerProvider | None = None,
                 keep_events: int = 256) -> None:
        self.host_id = host_id
        self.provider = provider or NullPowerProvider()
        self.session_id = "sess_" + uuid.uuid4().hex[:16]
        self._events: deque[HostEvent] = deque(maxlen=keep_events)
        self._power_epoch = 0
        self._network_epoch = 0

        first = self.provider.sample()
        self._last_bias = first.suspend_bias_s
        self._last_network = first.network_state
        self._boot_id = self._derive_boot_id(first)
        self._power_state = (PowerState.ACTIVE if first.suspend_bias_s is not None
                             else PowerState.UNKNOWN)
        self._record(HostEventType.PROCESS_STARTED, first,
                     detail={"pid": os.getpid()})

    # -- 1 ------------------------------------------------------------------
    def describe(self) -> dict:
        return {
            "contract": CONTRACT,
            "host_id": self.host_id,
            "session_id": self.session_id,
            "boot_id": self._boot_id,
            "power_provider": self.provider.describe(),
            "observable": {
                # Honest about what this platform can and cannot see.
                "suspend_retrospective": self._last_bias is not None,
                "suspend_pre_notification": False,
                "network": self._last_network is not NetworkState.UNKNOWN,
            },
        }

    # -- 2 ------------------------------------------------------------------
    def snapshot(self) -> HostAwarenessSnapshot:
        """Read the host and fold any discontinuity into the epochs.

        Calling this is what advances `power_epoch`: a suspend that nobody
        looked for is still recorded the next time anybody looks.
        """
        s = self.provider.sample()
        self._detect_suspend(s)
        self._detect_network(s)
        self._detect_reboot(s)
        return HostAwarenessSnapshot(
            host_id=self.host_id,
            boot_id=self._boot_id,
            session_id=self.session_id,
            power_state=self._power_state,
            power_epoch=self._power_epoch,
            network_state=self._last_network,
            network_epoch=self._network_epoch,
            wall_time=s.wall_time,
            monotonic_time=s.monotonic_time,
            unbiased_time=s.unbiased_time,
        )

    # -- 3 ------------------------------------------------------------------
    def recent_events(self, limit: int = 20,
                      types: Iterable[HostEventType] | None = None) -> list[HostEvent]:
        wanted = set(types) if types else None
        out = [e for e in self._events if wanted is None or e.event_type in wanted]
        return out[-limit:]

    # -- 4 ------------------------------------------------------------------
    def health(self) -> dict:
        return {
            "contract": CONTRACT,
            "host_id": self.host_id,
            "power_state": self._power_state.value,
            "power_epoch": self._power_epoch,
            "network_state": self._last_network.value,
            "network_epoch": self._network_epoch,
            "events": len(self._events),
            "provider": self.provider.name,
            "suspend_observable": self._last_bias is not None,
        }

    def corroborating_history(self) -> list[HostEvent]:
        """OS-log events, when the platform has a log. Never load-bearing."""
        return self.provider.history()

    # -- detection ----------------------------------------------------------
    def _detect_suspend(self, s: PowerSample) -> None:
        if s.suspend_bias_s is None or self._last_bias is None:
            self._last_bias = s.suspend_bias_s
            if s.suspend_bias_s is None:
                # No mechanism. Absence of evidence is not ACTIVE.
                self._power_state = PowerState.UNKNOWN
            return

        gap = s.suspend_bias_s - self._last_bias
        self._last_bias = s.suspend_bias_s
        if gap <= SUSPEND_THRESHOLD_S:
            self._power_state = PowerState.ACTIVE
            return

        previous = self._power_epoch
        self._power_epoch += 1
        self._power_state = PowerState.ACTIVE
        self._record(
            HostEventType.HOST_RESUMED, s,
            detail={
                "previous_power_epoch": previous,
                "suspend_wall_gap_s": round(gap, 3),
                "mechanism": "suspend-bias delta (tick - unbiased interrupt time)",
            },
        )

    def _detect_network(self, s: PowerSample) -> None:
        if s.network_state is NetworkState.UNKNOWN:
            return
        if s.network_state is self._last_network:
            return
        previous = self._last_network
        self._last_network = s.network_state
        self._network_epoch += 1
        kind = (HostEventType.NETWORK_UP if s.network_state is NetworkState.UP
                else HostEventType.NETWORK_DOWN)
        self._record(kind, s, detail={"previous": previous.value,
                                      "previous_network_epoch": self._network_epoch - 1})

    def _detect_reboot(self, s: PowerSample) -> None:
        new_boot = self._derive_boot_id(s)
        if new_boot == self._boot_id:
            return
        previous = self._boot_id
        self._boot_id = new_boot
        self._record(HostEventType.HOST_BOOT, s,
                     detail={"previous_boot_id": previous})

    # -- helpers ------------------------------------------------------------
    def _derive_boot_id(self, s: PowerSample) -> str:
        """Stable for the life of one boot, derived rather than stored.

        Uses the boot wall time to one second. A machine that reboots gets a
        new id without anything having to be persisted across the reboot.
        """
        boot = s.boot_wall_time
        if boot is None:
            boot = s.wall_time - s.monotonic_time
        return digest({"host": self.host_id, "boot_wall": int(boot)})[:23]

    def _record(self, kind: HostEventType, s: PowerSample,
                detail: Mapping[str, Any] | None = None,
                evidence: Evidence = Evidence.DEMONSTRATED) -> HostEvent:
        event = HostEvent(
            event_id="evt_" + uuid.uuid4().hex[:16],
            host_id=self.host_id,
            event_type=kind,
            wall_time=s.wall_time,
            source=s.source,
            evidence=evidence,
            monotonic_time=s.monotonic_time,
            unbiased_time=s.unbiased_time,
            boot_id=self._boot_id,
            session_id=self.session_id,
            power_epoch=self._power_epoch,
            network_epoch=self._network_epoch,
            detail=dict(detail or {}),
        )
        self._events.append(event)
        return event

    def ingest_external(self, *_args: Any, **_kwargs: Any) -> None:
        """Deliberately not implemented.

        Invariant: a model can interpret these events and can never create one.
        The method exists so that the refusal is explicit rather than an
        oversight someone later 'fixes'.
        """
        raise NotImplementedError(
            "host events come from mechanisms, not from callers or models")
