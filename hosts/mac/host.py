"""A real macOS host. Touches the real filesystem and launches real processes.

Same contract and the same two-check design as the Linux engine
(hosts/linux/host.py) — which is the point made concrete: the security checks
are reused, the platform seams are replaced, and any future reader can list
exactly what macOS changed by reading this file alone:

- **There is no `/proc`.** Descriptor verification goes through
  `/dev/fd/<n>` instead. The check is the same check; only its path to the
  kernel differs.
- **APFS is case-insensitive by default.** The lexical scope check folds
  case and so does the default volume, so the successor allowing
  `/Data/PHOTOS` where `/data/Photos` was granted is *macOS agreeing with
  NTFS*. This engine still compares resolved paths case-sensitively: on a
  case-insensitive volume that can refuse a path the kernel would have
  served (a false deny, the safe direction), never the reverse. Volumes
  formatted case-sensitive are served exactly.
- **No process-verification source exists yet.** `isymotron.process` has
  sources for Linux (`/proc`) and Windows; on macOS it is
  `UnsupportedProcessSource` by design, so launches record
  `{"error": ..., "detail": "no process source for platform 'darwin'"}`
  instead of a fabricated fingerprint.

Scope of the claim (see docs/EVIDENCE.md): exercised on a real CI runner
(`macos-latest`, Apple Silicon). Power/awareness is *not* included: the
Linux provider reads `CLOCK_BOOTTIME`, which does not exist here, and no
macOS mechanism has been written or measured.
"""
from __future__ import annotations

import errno
import os
import platform
import stat
import subprocess
from typing import Any

from isymotron.contracts import ExecutionRequest, HostIdentity
from isymotron.host import Host, ScopeViolation
from isymotron.policy import normalize_path
from isymotron.process import ProcessError, observe
from isymotron.resources import app_entries, fs_roots
from isymotron.verdicts import DenyReason
from windows.win11 import CAPABILITIES, MAX_READ_BYTES, _as_text, _iso, _sha

from linux.host import LinuxHost

ENGINE = "mac-real/0.1"


class MacHost(LinuxHost):
    """The engine that serves NemoHostContract/v0 on macOS."""

    PLATFORM = "darwin"
    OS_FAMILY = "macos"
    ENGINE = ENGINE
    FD_BASE = "/dev/fd"

    def _os_name(self) -> str:
        version = platform.mac_ver()[0]
        return f"macOS {version}" if version else "macOS"

    def _release_tag(self) -> str:
        version = platform.mac_ver()[0]
        return f"macos-{version or platform.release()}"

    def _proc_names(self) -> list[str]:
        # No /proc: ask the same layer everyone else asks, but only for names.
        try:
            out = subprocess.run(
                ["ps", "-A", "-o", "comm="],
                capture_output=True, text=True, timeout=10, check=True,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        return sorted({line.strip() for line in out.splitlines() if line.strip()})

    # apps.launch: same as Linux but process verification is unsupported on macOS
    def _launch(self, p: dict[str, Any]) -> tuple[dict, list[dict]]:
        app = p["app"]
        args = list(p.get("args") or [])
        exe = self._resolve_app(app)
        proc = subprocess.Popen(
            [exe, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        return ({"app": app, "exe": exe, "pid": proc.pid, "args": args,
                 "proc": _observe_launch(proc.pid)},
                [{"kind": "process.spawn", "app": app, "pid": proc.pid}])
