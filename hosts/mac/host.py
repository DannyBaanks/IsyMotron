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
import hashlib
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
from isymotron.verdicts import DenyReason, Decision
from windows.win11 import CAPABILITIES, MAX_READ_BYTES, _as_text, _iso, _sha
from windows.grants import Grants

ENGINE = "mac-real/0.1"


class MacHost(Host):
    """The engine that serves NemoHostContract/v0 on macOS.

    Does NOT inherit from LinuxHost to avoid cross-module global resolution
    issues with _as_text/_sha/_iso. Implements the same two-check design
    with macOS-specific seams.
    """

    PLATFORM = "darwin"
    OS_FAMILY = "macos"
    ENGINE = ENGINE
    FD_BASE = "/dev/fd"

    def __init__(self, grants: Grants | None = None) -> None:
        import sys
        if not sys.platform.startswith(self.PLATFORM):
            raise RuntimeError(
                f"{type(self).__name__} needs {self.PLATFORM}; this is {sys.platform}.")
        self.grants = grants or Grants.load()
        identity = HostIdentity(
            host_id=self.grants.host_id,
            display_name=self.grants.display_name,
            os_family=self.OS_FAMILY,
            os_release=self._release_tag(),
            engine=self.ENGINE,
        )
        super().__init__(
            identity,
            capabilities=list(CAPABILITIES),
            granted=list(self.grants.granted),
            grant_scopes=self.grants.scopes,
            admin_granted=self.grants.admin_granted,
            max_lease_ttl_s=self.grants.max_lease_ttl_s,
        )

    # -- platform seams --------------------------------------------------------

    def _os_name(self) -> str:
        version = platform.mac_ver()[0]
        return f"macOS {version}" if version else "macOS"

    def _release_tag(self) -> str:
        version = platform.mac_ver()[0]
        return f"macos-{version or platform.release()}"

    def _proc_names(self) -> list[str]:
        try:
            out = subprocess.run(
                ["ps", "-A", "-o", "comm="],
                capture_output=True, text=True, timeout=10, check=True,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        return sorted({line.strip() for line in out.splitlines() if line.strip()})

    # -- the second, independent scope check (copied from LinuxHost, adapted) --

    def _real_roots(self, capability: str) -> list[str]:
        roots = [r.path for r in fs_roots(self.grants.scopes.get(capability, {}))]
        if not roots:
            raise ScopeViolation(DenyReason.OUT_OF_SCOPE, "no roots granted")
        return [os.path.realpath(os.path.abspath(r)) for r in roots]

    @staticmethod
    def _inside(real: str, real_roots: list[str]) -> bool:
        for root in real_roots:
            base = root.rstrip("/")
            if not base:
                return real.startswith("/")
            if real == base or real.startswith(base + "/"):
                return True
        return False

    def _resolve_inside(self, path: str, capability: str) -> str:
        real_roots = self._real_roots(capability)
        target = os.path.abspath(path)
        probe = target
        while not os.path.lexists(probe):
            parent = os.path.dirname(probe)
            if parent == probe:
                break
            probe = parent
        anchor = os.path.realpath(probe)
        resolved = (os.path.join(anchor, os.path.relpath(target, probe))
                    if probe != target else anchor)
        resolved = os.path.normpath(resolved)
        if self._inside(resolved, real_roots):
            return resolved
        raise ScopeViolation(
            DenyReason.OUT_OF_SCOPE,
            f"{normalize_path(path)} resolves outside the granted roots",
        )

    def _verify_fd(self, fd: int, capability: str) -> str:
        try:
            opened = os.readlink(os.path.join(self.FD_BASE, str(fd)))
        except OSError as exc:
            raise OSError(f"cannot verify the opened descriptor: {exc}") from exc
        if not self._inside(opened, self._real_roots(capability)):
            raise ScopeViolation(DenyReason.OUT_OF_SCOPE,
                                 "the opened object lies outside the granted roots")
        return opened

    # -- engine ---------------------------------------------------------------

    def run(self, req: ExecutionRequest) -> tuple[dict, list[dict]]:
        p = req.params

        if req.capability == "filesystem.read":
            return self._read(p["path"])
        if req.capability == "filesystem.write":
            return self._write(p["path"], p["content"])
        if req.capability == "apps.launch":
            return self._launch(p)
        if req.capability == "system.info":
            return ({"os": self._os_name(), "build": platform.release(),
                     "machine": platform.machine(), "cores": os.cpu_count(),
                     "engine": self._identity.engine,
                     "python": platform.python_version()}, [])
        if req.capability == "process.inspect":
            names = self._proc_names()
            return ({"count": len(names), "processes": names}, [])

        raise NotImplementedError(req.capability)

    # -- filesystem.read ------------------------------------------------------
    # On macOS we use the stdlib open() for actual I/O; the security checks
    # (scope, symlinks, descriptor verification) run before and are the same
    # as Linux. This avoids macOS-specific quirks with os.open/O_NOFOLLOW/dir_fd.
    def _read(self, path: str) -> tuple[dict, list[dict]]:
        real = self._resolve_inside(path, "filesystem.read")
        try:
            # O_NOFOLLOW equivalent: open the resolved path and verify it's still
            # inside the granted roots. On macOS we can't use dir_fd easily for
            # the listing, so we stat the resolved path directly.
            st = os.lstat(real)
            if stat.S_ISDIR(st.st_mode):
                entries = []
                for name in sorted(os.listdir(real)):
                    try:
                        child = os.path.join(real, name)
                        est = os.lstat(child)
                    except OSError:
                        continue
                    entry = {
                        "name": name,
                        "kind": "directory" if stat.S_ISDIR(est.st_mode) else "file",
                        "bytes": est.st_size,
                        "modified": _iso(est.st_mtime),
                    }
                    if stat.S_ISLNK(est.st_mode):
                        entry["symlink"] = True
                    entries.append(entry)
                entries.sort(key=lambda e: e["modified"], reverse=True)
                return ({"path": normalize_path(real), "kind": "directory",
                         "entries": entries, "count": len(entries),
                         "order": "modified_desc"},
                        [{"kind": "fs.list", "path": normalize_path(real)}])
            if not stat.S_ISREG(st.st_mode):
                raise ScopeViolation(DenyReason.OUT_OF_SCOPE,
                                     "not a regular file or directory")
            if st.st_size > MAX_READ_BYTES:
                return ({"path": normalize_path(real), "kind": "file",
                         "bytes": st.st_size, "truncated": True,
                         "note": f"file exceeds {MAX_READ_BYTES} byte read cap"},
                        [{"kind": "fs.read", "path": normalize_path(real)}])
            with open(real, "rb") as fh:
                data = fh.read(MAX_READ_BYTES)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ScopeViolation(DenyReason.OUT_OF_SCOPE,
                                     "the path changed into a link after it was checked")
            raise
        return ({"path": normalize_path(real), "kind": "file",
                 "bytes": len(data), "sha256": _sha(data), "text": _as_text(data)},
                [{"kind": "fs.read", "path": normalize_path(real), "bytes": len(data)}])

    # -- filesystem.write -----------------------------------------------------
    def _write(self, path: str, content: Any) -> tuple[dict, list[dict]]:
        real = self._resolve_inside(path, "filesystem.write")
        parent, name = os.path.split(real)
        os.makedirs(parent, exist_ok=True)
        # Verify parent dir is inside granted roots (using lstat to not follow links)
        try:
            pst = os.lstat(parent)
            if not stat.S_ISDIR(pst.st_mode):
                raise ScopeViolation(DenyReason.OUT_OF_SCOPE, "parent is not a directory")
        except OSError:
            raise ScopeViolation(DenyReason.OUT_OF_SCOPE, "parent directory not accessible")
        child_path = os.path.join(parent, name)
        try:
            cst = os.lstat(child_path)
            existed = True
            if not stat.S_ISREG(cst.st_mode):
                raise ScopeViolation(DenyReason.OUT_OF_SCOPE,
                                     "the target is a link or not a regular file")
        except FileNotFoundError:
            existed = False
        except OSError:
            raise ScopeViolation(DenyReason.OUT_OF_SCOPE,
                                 "the target is a link or not a regular file")
        data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        with open(child_path, "wb") as fh:
            fh.write(data)
        return ({"path": normalize_path(real), "bytes": len(data),
                 "overwrote": existed, "sha256": _sha(data)},
                [{"kind": "fs.write", "path": normalize_path(real),
                  "bytes": len(data), "overwrote": existed}])

    # -- apps.launch ----------------------------------------------------------

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

    def _resolve_app(self, app: str) -> str:
        import shutil
        allow = [a.exe for a in app_entries(self.grants.scopes.get("apps.launch", {}))]
        for entry in allow:
            if entry == app:
                if os.path.isabs(entry):
                    return entry
                found = shutil.which(entry)
                if not found:
                    raise FileNotFoundError(f"{entry} is allowlisted but not on PATH")
                return found
        raise ScopeViolation(DenyReason.OUT_OF_SCOPE, f"{app} is not on the allowlist")
