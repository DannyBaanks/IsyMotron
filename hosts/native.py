"""Which real host engine serves THIS machine -- one answer, used everywhere.

Before M2 every entry point imported the Windows engine directly, and
tools/host_cli.py ran it on Linux: a case-folding engine on a case-sensitive
filesystem, labelled `nt-real`. The choice now lives here only.

`real_host()` returns None where no engine is demonstrated (macOS until M3).
None means "no real host": callers attach fixtures or refuse, and say so.
"""
from __future__ import annotations

import sys

#: engine id prefix -> the platform where it is a real backend. Adding a row
#: is a claim that needs its own evidence (docs/PLATFORM_SUPPORT.md).
REAL_ENGINES = {"win32": "nt-real/", "linux": "linux-real/"}


def platform_key(plat: str | None = None) -> str:
    plat = plat or sys.platform
    return "linux" if plat.startswith("linux") else plat


def has_real_host(plat: str | None = None) -> bool:
    return platform_key(plat) in REAL_ENGINES


def real_host(grants=None):
    """The real engine for this OS, or None. Never a cross-OS stand-in."""
    key = platform_key()
    if key == "win32":
        from windows.win11 import Win11Host
        return Win11Host(grants)
    if key == "linux":
        from linux.host import LinuxHost
        return LinuxHost(grants)
    return None


def power_provider():
    """The native power/awareness provider, or None."""
    key = platform_key()
    if key == "win32":
        from windows.power import WindowsPowerProvider
        return WindowsPowerProvider()
    if key == "linux":
        from linux.power import LinuxPowerProvider
        return LinuxPowerProvider()
    return None
