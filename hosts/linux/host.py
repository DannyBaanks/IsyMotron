"""A real Linux host. Touches the real filesystem and launches real processes.

Same contract, same five capabilities and same two-check design as the Windows
engine (hosts/windows/win11.py):

  1. `Enforcer` checks the *requested* path, lexically (core/isymotron/policy.py)
  2. this engine re-checks the *resolved* path, after the kernel follows links

What Linux changes, and what this engine does about it:

- **Case is significant.** The lexical check folds case (right for NTFS). On
  Linux a root `/data/Photos` must not admit `/data/photos`, a different
  directory. Check 2 here compares resolved paths case-SENSITIVELY, so the
  engine overrides that lexical ALLOW with DENY. Measured escape before M2 --
  see docs/FINDINGS.md, Finding 10.
- **Symlinks are cheap, and can be swapped.** Resolving a path and then
  opening it by name leaves a window in which a component can be replaced.
  Here the opened descriptor itself is checked (`/proc/self/fd/<n>`), after
  open and before any byte moves, and a write opens its final component with
  O_NOFOLLOW relative to a verified directory descriptor.
- **Not every inode is a file.** A FIFO would hang a read forever and a device
  is not a document. Only regular files and directories are served.
- **Hardlinks share content.** Overwriting a file with more than one link would
  change bytes that are also reachable by a name outside the root. Refused.

Honest residue (docs/PLATFORM_SUPPORT.md): `makedirs` for a new nested write
can still race an attacker who owns a directory inside the root (empty
directories may be created before the descriptor check refuses the write);
bind mounts are the administrator's statement and are not second-guessed; a
launched app runs with this user's full authority, exactly as on Windows.
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

# One contract: the manifests are the Windows engine's, not a Linux copy that
# could drift. tests/test_linux_real.py asserts the identity.
from windows.grants import Grants
from windows.win11 import CAPABILITIES, MAX_READ_BYTES, _as_text, _iso, _sha

ENGINE = "linux-real/0.1"


class LinuxHost(Host):
    """The engine that serves NemoHostContract/v0 on Linux."""

    def __init__(self, grants: Grants | None = None) -> None:
        import sys
        if not sys.platform.startswith("linux"):
            raise RuntimeError(f"LinuxHost needs Linux; this is {sys.platform}.")
        self.grants = grants or Grants.load()
        identity = HostIdentity(
            host_id=self.grants.host_id,
            display_name=self.grants.display_name,
            os_family="linux",
            os_release=_release_tag(),
            engine=ENGINE,
        )
        super().__init__(
            identity,
            capabilities=list(CAPABILITIES),
            granted=list(self.grants.granted),
            grant_scopes=self.grants.scopes,
            admin_granted=self.grants.admin_granted,
            max_lease_ttl_s=self.grants.max_lease_ttl_s,
        )

    # -- the second, independent scope check --------------------------------
    def _real_roots(self, capability: str) -> list[str]:
        roots = [r.path for r in fs_roots(self.grants.scopes.get(capability, {}))]
        if not roots:
            raise ScopeViolation(DenyReason.OUT_OF_SCOPE, "no roots granted")
        return [os.path.realpath(os.path.abspath(r)) for r in roots]

    @staticmethod
    def _inside(real: str, real_roots: list[str]) -> bool:
        # Case-sensitive on purpose: this is the check the lexical one cannot do.
        for root in real_roots:
            base = root.rstrip("/")
            if not base:                      # the root is "/" itself
                return real.startswith("/")
            if real == base or real.startswith(base + "/"):
                return True
        return False

    def _resolve_inside(self, path: str, capability: str) -> str:
        """Resolve the path the way the kernel will, then re-check containment.

        For a path that does not exist yet, the nearest existing ancestor is
        resolved instead, which is what the write will really use.
        """
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
        """What the descriptor ACTUALLY names, re-checked. Closes the window
        between resolving a name and opening it."""
        try:
            opened = os.readlink(f"/proc/self/fd/{fd}")
        except OSError as exc:
            # No /proc: the check cannot run, so nothing proceeds.
            raise OSError(f"cannot verify the opened descriptor: {exc}") from exc
        if not self._inside(opened, self._real_roots(capability)):
            raise ScopeViolation(DenyReason.OUT_OF_SCOPE,
                                 "the opened object lies outside the granted roots")
        return opened

    # -- the engine ---------------------------------------------------------
    def run(self, req: ExecutionRequest) -> tuple[dict, list[dict]]:
        p = req.params

        if req.capability == "filesystem.read":
            return self._read(p["path"])
        if req.capability == "filesystem.write":
            return self._write(p["path"], p["content"])

        if req.capability == "apps.launch":
            app = p["app"]
            args = list(p.get("args") or [])
            exe = self._resolve_app(app)
            proc = subprocess.Popen(
                [exe, *args],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,      # the DETACHED_PROCESS analogue
            )
            return ({"app": app, "exe": exe, "pid": proc.pid, "args": args,
                     "proc": _observe_launch(proc.pid)},
                    [{"kind": "process.spawn", "app": app, "pid": proc.pid}])

        if req.capability == "system.info":
            return ({"os": _os_name(), "build": platform.release(),
                     "machine": platform.machine(), "cores": os.cpu_count(),
                     "engine": self._identity.engine,
                     "python": platform.python_version()}, [])

        if req.capability == "process.inspect":
            names = _proc_names()
            return ({"count": len(names), "processes": names}, [])

        raise NotImplementedError(req.capability)

    def _read(self, path: str) -> tuple[dict, list[dict]]:
        real = self._resolve_inside(path, "filesystem.read")
        try:
            # O_NOFOLLOW: `real` is already resolved, so a link here means the
            # name was swapped after the check. O_NONBLOCK: a FIFO must not
            # hang the host before fstat refuses it.
            fd = os.open(real, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ScopeViolation(DenyReason.OUT_OF_SCOPE,
                                     "the path changed into a link after it was checked")
            raise
        try:
            self._verify_fd(fd, "filesystem.read")
            st = os.fstat(fd)
            if stat.S_ISDIR(st.st_mode):
                entries = []
                for name in sorted(os.listdir(fd)):
                    try:
                        # lstat: a link's target may be outside the root, and
                        # its size or mtime is not ours to report.
                        est = os.stat(name, dir_fd=fd, follow_symlinks=False)
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
            chunks, total = [], 0
            while True:
                block = os.read(fd, 1 << 20)
                if not block:
                    break
                chunks.append(block)
                total += len(block)
                if total > MAX_READ_BYTES:
                    break
            data = b"".join(chunks)[:MAX_READ_BYTES]
        finally:
            os.close(fd)
        return ({"path": normalize_path(real), "kind": "file",
                 "bytes": len(data), "sha256": _sha(data), "text": _as_text(data)},
                [{"kind": "fs.read", "path": normalize_path(real), "bytes": len(data)}])

    def _write(self, path: str, content: Any) -> tuple[dict, list[dict]]:
        real = self._resolve_inside(path, "filesystem.write")
        parent, name = os.path.split(real)
        os.makedirs(parent, exist_ok=True)
        dfd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            self._verify_fd(dfd, "filesystem.write")
            try:
                os.stat(name, dir_fd=dfd, follow_symlinks=False)
                existed = True
            except FileNotFoundError:
                existed = False
            try:
                # No O_TRUNC yet: nothing is changed until the inode is known
                # to be a single-link regular file inside the root.
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
                             | os.O_CLOEXEC | os.O_NONBLOCK, 0o666, dir_fd=dfd)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENXIO):  # a link / a FIFO
                    raise ScopeViolation(DenyReason.OUT_OF_SCOPE,
                                         "the target is a link or not a regular file")
                raise
        finally:
            os.close(dfd)
        try:
            self._verify_fd(fd, "filesystem.write")
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise ScopeViolation(DenyReason.OUT_OF_SCOPE, "not a regular file")
            if st.st_nlink > 1:
                raise ScopeViolation(
                    DenyReason.OUT_OF_SCOPE,
                    "the file has other hard links: its bytes are reachable outside the root")
            data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
            os.ftruncate(fd, 0)
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
        finally:
            os.close(fd)
        return ({"path": normalize_path(real), "bytes": len(data),
                 "overwrote": existed, "sha256": _sha(data)},
                [{"kind": "fs.write", "path": normalize_path(real),
                  "bytes": len(data), "overwrote": existed}])

    def _resolve_app(self, app: str) -> str:
        """Same rule as the Windows engine: a bare allowlist entry resolves on
        PATH, a full path is used as written. Case-sensitive here: on Linux
        `Firefox` and `firefox` are different files."""
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
        # `_physical` already swapped in the entry as granted, so an exact
        # match always exists after an ALLOW. Never fall through to "just run it".
        raise ScopeViolation(DenyReason.OUT_OF_SCOPE, f"{app} is not on the allowlist")


def _observe_launch(pid: int) -> dict:
    """Same trust root as the Windows engine: observe at spawn time, seal the
    fingerprint; never fabricate one when observation fails."""
    try:
        return observe(pid).to_dict()
    except ProcessError as exc:
        return {"error": exc.reason, "detail": exc.detail}


def _os_release() -> dict:
    try:
        return platform.freedesktop_os_release()
    except OSError:
        return {}


def _os_name() -> str:
    info = _os_release()
    return info.get("PRETTY_NAME") or info.get("NAME") or "Linux"


def _release_tag() -> str:
    info = _os_release()
    distro = info.get("ID") or "linux"
    version = info.get("VERSION_ID") or platform.release()
    return f"{distro}-{version}"


def _proc_names() -> list[str]:
    names = set()
    try:
        pids = [d for d in os.listdir("/proc") if d.isdigit()]
    except OSError:
        return []
    for pid in pids:
        try:
            with open(f"/proc/{pid}/comm", "r", encoding="utf-8", errors="replace") as fh:
                names.add(fh.read().strip())
        except OSError:
            continue           # exited, or hidden by hidepid: not ours to list
    names.discard("")
    return sorted(names)
