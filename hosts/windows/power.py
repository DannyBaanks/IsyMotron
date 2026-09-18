"""WindowsPowerProvider — suspend detection without a message pump.

The mechanism, measured on this machine on 2026-09-17
-----------------------------------------------------
Windows keeps two counters since boot:

    GetTickCount64()              42365.203 s   (11.77 h)  includes sleep
    QueryUnbiasedInterruptTime()  35038.317 s   ( 9.73 h)  excludes sleep
    ----------------------------------------------------
    difference                     7326.886 s   ( 2.04 h)  = time spent asleep

The difference is the **suspend bias**: total wall-clock time the machine has
spent suspended since it booted. It is monotonically non-decreasing, and any
increase between two readings is exactly the time slept in between.

Measured across a two-second awake interval the bias moved 2.2 ms, so noise is
milliseconds and a real suspend is seconds. `SUSPEND_THRESHOLD_S` sits at 1 s.

Why not compare `time.time()` against `time.monotonic()`
-------------------------------------------------------
Because on Windows that does not work, which is the whole reason this file
exists. Measured here, `time.monotonic()` **is** `GetTickCount64()` to within
20 ms, and both it and `time.time()` advance through suspend. A 793-second
sleep is indistinguishable from a 793-second request using Python's clocks
alone. Only the unbiased counter knows the difference.

Why not WM_POWERBROADCAST / PowerRegisterSuspendResumeNotification
-----------------------------------------------------------------
Both are real and both would give a *pre-suspend* notification, which this
approach cannot. But `WM_POWERBROADCAST` needs a window and a message pump,
and `PowerRegisterSuspendResumeNotification` needs a callback serviced by a
thread that Windows is about to freeze anyway. Each adds a thread, a handle and
a platform dependency to a process that is otherwise a CLI.

The retrospective reading needs none of that: no admin, no pump, no thread, no
handle, two ctypes calls. It cannot say "we are about to sleep" — so this
provider never claims `SUSPENDING`, and `PowerState.SUSPENDING` stays
`NOT_DEMONSTRATED` rather than being faked. It answers the question we actually
have, which is asked after the fact: *did we just sleep, and for how long?*

Corroboration
-------------
`history()` reads Kernel-Power events from the Windows System log, which
gives wall-clock timestamps for suspend and resume. It needs no admin. It is a
**second** source and never load-bearing: the bias is the mechanism, the log is
the cross-check.
"""
from __future__ import annotations

import ctypes
import subprocess
import time
from typing import Any

from isymotron.awareness import (
    HostEvent,
    HostEventType,
    NetworkState,
    PowerProvider,
    PowerSample,
)
from isymotron.verdicts import Evidence

_HUNDRED_NS = 1e7

# Kernel-Power / system log ids we can read without elevation.
_EVENT_IDS = {
    42: HostEventType.HOST_SUSPEND_REQUESTED,   # entering sleep
    107: HostEventType.HOST_RESUMED,            # resumed from sleep
    109: HostEventType.HOST_SHUTDOWN,           # kernel initiated shutdown
    506: HostEventType.HOST_SUSPEND_REQUESTED,  # entering modern standby
    507: HostEventType.HOST_RESUMED,            # exiting modern standby
}


class WindowsPowerProvider(PowerProvider):
    name = "windows-power-bias"

    def __init__(self, read_event_log: bool = True) -> None:
        self._kernel32 = ctypes.windll.kernel32
        self._wininet: Any = None
        try:
            self._wininet = ctypes.windll.wininet
        except OSError:
            self._wininet = None
        self._read_event_log = read_event_log
        self._unbiased_ok = hasattr(self._kernel32, "QueryUnbiasedInterruptTime")

    # -- the mechanism ------------------------------------------------------
    def _unbiased_seconds(self) -> float | None:
        if not self._unbiased_ok:
            return None
        value = ctypes.c_ulonglong(0)
        if not self._kernel32.QueryUnbiasedInterruptTime(ctypes.byref(value)):
            return None
        return value.value / _HUNDRED_NS

    def _tick_seconds(self) -> float:
        return self._kernel32.GetTickCount64() / 1000.0

    def _network(self) -> NetworkState:
        """Cheap, local, and honest about not knowing.

        `InternetGetConnectedState` reports whether this machine believes it
        has a connection. It does not prove reachability of any endpoint, and
        we never claim it does -- it is only used to tell "my wifi dropped"
        apart from "the provider went away".
        """
        if self._wininet is None:
            return NetworkState.UNKNOWN
        flags = ctypes.c_ulong(0)
        try:
            connected = self._wininet.InternetGetConnectedState(ctypes.byref(flags), 0)
        except OSError:
            return NetworkState.UNKNOWN
        return NetworkState.UP if connected else NetworkState.DOWN

    def sample(self) -> PowerSample:
        wall = time.time()
        tick = self._tick_seconds()
        unbiased = self._unbiased_seconds()
        bias = None if unbiased is None else max(0.0, tick - unbiased)
        return PowerSample(
            wall_time=wall,
            monotonic_time=tick,
            unbiased_time=unbiased,
            suspend_bias_s=bias,
            boot_wall_time=wall - tick,
            network_state=self._network(),
            source=self.name,
            detail={"tick_s": round(tick, 3),
                    "unbiased_s": None if unbiased is None else round(unbiased, 3)},
        )

    def describe(self) -> dict:
        s = self.sample()
        return {
            "provider": self.name,
            "mechanism": "GetTickCount64 minus QueryUnbiasedInterruptTime",
            "unbiased_clock_available": self._unbiased_ok,
            "network_probe": "wininet.InternetGetConnectedState"
                             if self._wininet else "none",
            "event_log": self._read_event_log,
            "suspend_bias_since_boot_s": (None if s.suspend_bias_s is None
                                          else round(s.suspend_bias_s, 3)),
            "pre_suspend_notification": False,
        }

    # -- corroboration ------------------------------------------------------
    def history(self, limit: int = 12) -> list[HostEvent]:
        """Kernel-Power events from the System log. Best effort, never required."""
        if not self._read_event_log:
            return []
        ids = ",".join(str(i) for i in sorted(_EVENT_IDS))
        script = (
            "$ErrorActionPreference='Stop';"
            "Get-WinEvent -FilterHashtable @{LogName='System';"
            f"ProviderName='Microsoft-Windows-Kernel-Power';Id={ids}}}"
            f" -MaxEvents {limit} |"
            " ForEach-Object { '{0}|{1}' -f "
            "$_.TimeCreated.ToUniversalTime().ToString('o'), $_.Id }"
        )
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=25,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return []

        events: list[HostEvent] = []
        for line in out.splitlines():
            if "|" not in line:
                continue
            stamp, _, raw_id = line.partition("|")
            try:
                kind = _EVENT_IDS[int(raw_id.strip())]
                wall = _iso_to_epoch(stamp.strip())
            except (ValueError, KeyError):
                continue
            events.append(HostEvent(
                event_id="evt_winlog_" + raw_id.strip() + "_" + str(int(wall)),
                host_id="",                      # filled by the caller if it cares
                event_type=kind,
                wall_time=wall,
                source="windows-event-log/Kernel-Power",
                # The log says when, not how long. A duration derived from two
                # log lines is INFERRED; the bias delta is DEMONSTRATED.
                evidence=Evidence.INFERRED,
                detail={"event_id_windows": int(raw_id.strip())},
            ))
        events.sort(key=lambda e: e.wall_time)
        return events


def _iso_to_epoch(stamp: str) -> float:
    import datetime
    # PowerShell 'o' round-trip format, already converted to UTC.
    txt = stamp.replace("Z", "+00:00")
    if "." in txt:
        head, _, tail = txt.partition(".")
        frac, sign, offset = tail.partition("+")
        txt = f"{head}.{frac[:6]}" + (sign + offset if sign else "")
    return datetime.datetime.fromisoformat(txt).timestamp()


def make_engine(host_id: str, read_event_log: bool = True):
    """Convenience: a HostAwarenessEngine wired to the Windows provider."""
    from isymotron.awareness import HostAwarenessEngine
    return HostAwarenessEngine(host_id, WindowsPowerProvider(read_event_log))
