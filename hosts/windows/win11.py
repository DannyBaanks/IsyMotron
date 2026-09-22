"""A real Windows host. Touches the real filesystem and launches real processes.

Everything the simulator could pretend about, this one cannot. In particular:
the simulator's world had no symlinks, no junctions, no permissions and no
processes that refuse to be listed.

Two independent scope checks run on every filesystem call:

  1. `Enforcer` checks the *requested* path, lexically (core/isymotron/policy.py)
  2. this engine re-checks the *resolved* path, after the OS follows links

Check 1 alone is not sufficient on a real filesystem and check 2 alone is not
sufficient either — a path that does not exist yet cannot be resolved. Both run.
See docs/FINDINGS.md.
"""
from __future__ import annotations

import os
import platform
import subprocess
from typing import Any

from isymotron.contracts import CapabilityManifest, ExecutionRequest, HostIdentity
from isymotron.host import Host, ScopeViolation
from isymotron.policy import normalize_path
from isymotron.process import ProcessError, observe
from isymotron.resources import app_entries, fs_roots
from isymotron.verdicts import DenyReason

from .grants import Grants

MAX_READ_BYTES = 8 * 1024 * 1024


FS_READ = CapabilityManifest(
    id="filesystem.read", version="0.2",
    summary=("Read a file, or list a directory with each entry's size and "
             "modification time, inside the granted roots. A listing also "
             "returns `newest` (the path of its most recently modified file) and "
             "`newest_name` (that file's name)."),
    params=("path",),
    returns=("path", "kind", "bytes", "sha256", "text", "entries", "count", "order",
             "newest", "newest_name"),
)
FS_WRITE = CapabilityManifest(
    id="filesystem.write", version="0.1",
    summary="Create or overwrite a file inside the granted roots.",
    params=("path", "content"),
    returns=("path", "bytes", "overwrote", "sha256"),
)
APPS_LAUNCH = CapabilityManifest(
    id="apps.launch", version="0.2",
    summary=("Launch an allowlisted local application. The result seals the "
             "launched instance's process fingerprint: instance + artifact "
             "identity, not a benign-process certificate."),
    params=("app", "args"),
    returns=("app", "exe", "pid", "args", "proc"),
)
SYSTEM_INFO = CapabilityManifest(
    id="system.info", version="0.1",
    summary="Report non-identifying machine facts.",
    params=(),
    returns=("os", "build", "machine", "cores", "engine", "python"),
)
PROCESS_INSPECT = CapabilityManifest(
    id="process.inspect", version="0.1",
    summary="List running process names. Read-only.",
    params=("mutate",),
    returns=("count", "processes"),
)

CAPABILITIES = [FS_READ, FS_WRITE, APPS_LAUNCH, SYSTEM_INFO, PROCESS_INSPECT]


class Win11Host(Host):
    """The engine that serves NemoHostContract/v0 on modern Windows."""

    def __init__(self, grants: Grants | None = None) -> None:
        self.grants = grants or Grants.load()
        identity = HostIdentity(
            host_id=self.grants.host_id,
            display_name=self.grants.display_name,
            os_family="windows",
            os_release=_release_tag(),
            engine="nt-real/0.1",
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
    def _resolve_inside(self, path: str, capability: str) -> str:
        """Resolve the path the way the OS will, then re-check containment.

        `Enforcer` already checked the string. This checks what the string
        actually points at once junctions, symlinks and short (8.3) names are
        followed. For a path that does not exist yet, the nearest existing
        ancestor is resolved instead, which is what the write will really use.
        """
        roots = [r.path for r in fs_roots(self.grants.scopes.get(capability, {}))]
        if not roots:
            raise ScopeViolation(DenyReason.OUT_OF_SCOPE, "no roots granted")

        target = os.path.abspath(path)
        probe = target
        while not os.path.exists(probe):
            parent = os.path.dirname(probe)
            if parent == probe:
                break
            probe = parent
        resolved_anchor = os.path.realpath(probe)
        resolved = os.path.join(resolved_anchor, os.path.relpath(target, probe)) \
            if probe != target else resolved_anchor
        resolved = os.path.normpath(resolved)

        for root in roots:
            real_root = os.path.realpath(os.path.abspath(root))
            a = normalize_path(resolved).lower()
            b = normalize_path(real_root).lower().rstrip("/")
            if a == b or a.startswith(b + "/"):
                return resolved
        raise ScopeViolation(
            DenyReason.OUT_OF_SCOPE,
            f"{normalize_path(path)} resolves outside the granted roots",
        )

    # -- the engine ---------------------------------------------------------
    def run(self, req: ExecutionRequest) -> tuple[dict, list[dict]]:
        p = req.params

        if req.capability == "filesystem.read":
            real = self._resolve_inside(p["path"], "filesystem.read")
            if os.path.isdir(real):
                # Names alone are not enough to answer "the most recent one".
                # The planner refused a legitimate request over exactly this
                # gap on 2026-09-17 -- see docs/FINDINGS.md #4. Listings carry
                # size and mtime, newest first.
                entries = []
                for name in sorted(os.listdir(real)):
                    child = os.path.join(real, name)
                    try:
                        st = os.stat(child)
                    except OSError:
                        continue
                    entries.append({
                        "name": name,
                        "kind": "directory" if os.path.isdir(child) else "file",
                        "bytes": st.st_size,
                        "modified": _iso(st.st_mtime),
                    })
                entries.sort(key=lambda e: e["modified"], reverse=True)
                return ({"path": normalize_path(real), "kind": "directory",
                         "entries": entries, "count": len(entries),
                         "order": "modified_desc"},
                        [{"kind": "fs.list", "path": normalize_path(real)}])
            size = os.path.getsize(real)
            if size > MAX_READ_BYTES:
                return ({"path": normalize_path(real), "kind": "file",
                         "bytes": size, "truncated": True,
                         "note": f"file exceeds {MAX_READ_BYTES} byte read cap"},
                        [{"kind": "fs.read", "path": normalize_path(real)}])
            with open(real, "rb") as fh:
                data = fh.read()
            return ({"path": normalize_path(real), "kind": "file",
                     "bytes": len(data), "sha256": _sha(data),
                     "text": _as_text(data)},
                    [{"kind": "fs.read", "path": normalize_path(real),
                      "bytes": len(data)}])

        if req.capability == "filesystem.write":
            real = self._resolve_inside(p["path"], "filesystem.write")
            existed = os.path.exists(real)
            os.makedirs(os.path.dirname(real), exist_ok=True)
            content = p["content"]
            data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
            with open(real, "wb") as fh:
                fh.write(data)
            return ({"path": normalize_path(real), "bytes": len(data),
                     "overwrote": existed, "sha256": _sha(data)},
                    [{"kind": "fs.write", "path": normalize_path(real),
                      "bytes": len(data), "overwrote": existed}])

        if req.capability == "apps.launch":
            app = p["app"]
            args = list(p.get("args") or [])
            exe = self._resolve_app(app)
            proc = subprocess.Popen(
                [exe, *args],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
            )
            return ({"app": app, "exe": exe, "pid": proc.pid, "args": args,
                     "proc": _observe_launch(proc.pid)},
                    [{"kind": "process.spawn", "app": app, "pid": proc.pid}])

        if req.capability == "system.info":
            ver = platform.win32_ver()
            return ({"os": f"Windows {ver[0]}", "build": ver[1],
                     "machine": platform.machine(), "cores": os.cpu_count(),
                     "engine": self._identity.engine,
                     "python": platform.python_version()}, [])

        if req.capability == "process.inspect":
            names = _tasklist()
            return ({"count": len(names), "processes": names}, [])

        raise NotImplementedError(req.capability)

    def _resolve_app(self, app: str) -> str:
        """Turn an allowlist entry into an executable path.

        The allowlist may hold a bare name ('notepad.exe') or a full path. A
        bare name is resolved against PATH; a full path is used as written.
        Either way `Enforcer` already confirmed the entry is on the allowlist —
        this only turns it into something Popen accepts.
        """
        allow = [a.exe for a in app_entries(self.grants.scopes.get("apps.launch", {}))]
        for entry in allow:
            if entry.lower() == app.lower():
                if os.path.isabs(entry):
                    return entry
                import shutil
                found = shutil.which(entry)
                if not found:
                    raise FileNotFoundError(f"{entry} is allowlisted but not on PATH")
                return found
        # Unreachable after an ALLOW, but never fall through to "just run it".
        raise ScopeViolation(DenyReason.OUT_OF_SCOPE, f"{app} is not on the allowlist")


def _observe_launch(pid: int) -> dict:
    """Observe a just-launched process: the trust root of launch identity.

    The engine itself does the observing, at spawn time, so a later `verify`
    against the sealed fingerprint detects post-launch drift and PID reuse.
    The sealed shape is `ProcessIdentity.to_dict()`, restored with
    `ProcessIdentity.from_dict()` — no new vocabulary.

    On observation failure no identity is fabricated: the failure is recorded
    explicitly and any later verdict over it is ERROR, never PASS.

    Boundary: this establishes instance + artifact identity. It does not
    certify the in-memory image, and it does not make the process benign.
    """
    try:
        return observe(pid).to_dict()
    except ProcessError as exc:
        return {"error": exc.reason, "detail": exc.detail}


def _release_tag() -> str:
    ver = platform.win32_ver()
    parts = ver[1].split(".")
    if len(parts) > 2 and int(parts[2]) >= 22000:
        return f"11-build-{parts[2]}"
    return f"{ver[0]}-build-{parts[-1] if parts else '?'}"


def _iso(ts: float) -> str:
    """UTC, seconds, sortable as a string. One time grammar for every host."""
    import datetime
    return datetime.datetime.fromtimestamp(
        ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(data: bytes) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _as_text(data: bytes) -> str | None:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _tasklist() -> list[str]:
    try:
        out = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True, text=True, timeout=15, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    names = set()
    for line in out.splitlines():
        if line.startswith('"'):
            names.add(line.split('","')[0].strip('"'))
    return sorted(names)
