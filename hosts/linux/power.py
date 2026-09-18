"""LinuxPowerProvider — the seam, documented and deliberately not faked.

Status: `NOT_DEMONSTRATED`. This file exists so the core does not depend on
Windows, and so that whoever implements it does not have to rediscover the
design. It is not a working backend and does not pretend to be one:
`sample()` returns the same "I do not know" a `NullPowerProvider` would,
because a stub that reported ACTIVE would be exactly the lie this whole engine
was built to prevent.

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

Not implemented here, and not scheduled: macOS. There is no hardware to
demonstrate it on, so it stays `NOT_DEMONSTRATED` rather than becoming a third
untested stub.
"""
from __future__ import annotations

import time

from isymotron.awareness import NetworkState, PowerProvider, PowerSample


class LinuxPowerProvider(PowerProvider):
    """Seam only. Reports UNKNOWN until mechanism 1 above is implemented."""

    name = "linux-seam"
    implemented = False

    def sample(self) -> PowerSample:
        return PowerSample(
            wall_time=time.time(),
            monotonic_time=time.monotonic(),
            unbiased_time=None,
            suspend_bias_s=None,      # None, never 0.0: we do not know.
            network_state=NetworkState.UNKNOWN,
            source=self.name,
            detail={"status": "NOT_DEMONSTRATED",
                    "next_step": "CLOCK_BOOTTIME minus CLOCK_MONOTONIC"},
        )

    def describe(self) -> dict:
        return {
            "provider": self.name,
            "implemented": False,
            "evidence": "NOT_DEMONSTRATED",
            "planned_mechanism": "CLOCK_BOOTTIME - CLOCK_MONOTONIC, "
                                 "then logind PrepareForSleep for pre-suspend",
        }
