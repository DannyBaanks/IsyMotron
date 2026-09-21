"""LinuxPowerProvider — native Linux power and network observations.

The retrospective power mechanism is implemented here using Linux's
``CLOCK_BOOTTIME`` and ``CLOCK_MONOTONIC`` clocks.  The former advances during
suspend while the latter does not, so their difference is the accumulated
suspend bias.  Network state is read from local interface ``operstate`` files.
Neither observation requires root or a network request.

The two mechanisms to use, in order
-----------------------------------
1. **`CLOCK_BOOTTIME` vs `CLOCK_MONOTONIC`** — the direct analogue of the
   Windows bias, and the one to build on. On Linux `CLOCK_MONOTONIC` does NOT
   advance during suspend while `CLOCK_BOOTTIME` does, so

       suspend_bias = CLOCK_BOOTTIME - CLOCK_MONOTONIC

   is the same monotonically non-decreasing counter this provider's Windows
   sibling derives from `GetTickCount64 - QueryUnbiasedInterruptTime`. Both are
   reachable from Python without ctypes:

       time.clock_gettime(time.CLOCK_BOOTTIME)
       time.clock_gettime(time.CLOCK_MONOTONIC)

   Note the polarity is inverted relative to Windows: there the *unbiased*
   clock is the one that stops, here it is the *monotonic* one. Getting that
   backwards yields a provider that reports a suspend on every sample.

2. **systemd-logind `PrepareForSleep` over D-Bus** — the pre-suspend
   notification Windows would need a message pump for. Subscribing gives a
   signal with `True` before sleeping and `False` after resuming, which is what
   would let a Linux host legitimately report `SUSPENDING` and
   `HOST_SUSPEND_REQUESTED` rather than only reconstructing them. It needs a
   D-Bus client and a running loop, so it belongs behind mechanism 1, not
   instead of it.

Network state has no single portable mechanism. `/sys/class/net/*/operstate`
is the cheapest honest reading; NetworkManager's D-Bus interface is richer and
not always present. Until one is implemented, `NetworkState.UNKNOWN` is the
correct answer, and `attribute()` already treats UNKNOWN network as a reason to
return `UNKNOWN` rather than to blame a provider.

The pre-suspend notification is not implemented here, so this provider is
retrospective, like the Windows provider.  It can demonstrate that a suspend
occurred after the fact, but never claims ``SUSPENDING`` before it happens.

Not implemented here, and not scheduled: macOS. There is no hardware to
demonstrate it on, so it stays `NOT_DEMONSTRATED` rather than becoming a third
untested stub.
"""
from __future__ import annotations

import os
import time

from isymotron.awareness import NetworkState, PowerProvider, PowerSample


class LinuxPowerProvider(PowerProvider):
    """Read retrospective suspend time and local interface state on Linux."""

    name = "linux-seam"
    implemented = True
    _NET_ROOT = "/sys/class/net"

    @staticmethod
    def _network() -> NetworkState:
        """Return the aggregate state of non-loopback Linux interfaces."""
        net_root = LinuxPowerProvider._NET_ROOT
        try:
            names = [name for name in os.listdir(net_root)
                     if name != "lo"]
        except OSError:
            return NetworkState.UNKNOWN
        if not names:
            return NetworkState.UNKNOWN
        states: list[str] = []
        for name in names:
            try:
                with open(f"{net_root}/{name}/operstate", encoding="ascii") as f:
                    states.append(f.read().strip().lower())
            except OSError:
                continue
        if not states:
            return NetworkState.UNKNOWN
        return (NetworkState.UP if any(state == "up" for state in states)
                else NetworkState.DOWN)

    def sample(self) -> PowerSample:
        wall = time.time()
        monotonic = time.clock_gettime(time.CLOCK_MONOTONIC)
        boottime = time.clock_gettime(time.CLOCK_BOOTTIME)
        bias = max(0.0, boottime - monotonic)
        return PowerSample(
            wall_time=wall,
            monotonic_time=monotonic,
            unbiased_time=monotonic,
            suspend_bias_s=bias,
            boot_wall_time=wall - boottime,
            network_state=self._network(),
            source=self.name,
            detail={"status": "DEMONSTRATED",
                    "clock": "CLOCK_BOOTTIME - CLOCK_MONOTONIC",
                    "network": "/sys/class/net/*/operstate"},
        )

    def describe(self) -> dict:
        return {
            "provider": self.name,
            "implemented": True,
            "evidence": "DEMONSTRATED",
            "mechanism": "CLOCK_BOOTTIME - CLOCK_MONOTONIC",
            "network_probe": "/sys/class/net/*/operstate",
            "pre_suspend_notification": False,
        }
