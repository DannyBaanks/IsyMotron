"""Two simulated hosts that implement the SAME contract with DIFFERENT engines.

This is the cheap half of Target Claim F. It demonstrates that the contract can
be served by unlike engines; it does NOT demonstrate anything about real
Windows machines. See docs/EVIDENCE.md.

- ModernHost  : rich engine, NT-style absolute paths, process inspection.
- LegacyHost  : minimal engine, 8.3-ish uppercase paths, no process family,
                app launch by INI-style allowlist.
"""
from __future__ import annotations

from typing import Any

from isymotron.contracts import CapabilityManifest, ExecutionRequest, HostIdentity
from isymotron.host import Host
from isymotron.policy import normalize_path


def _sha(text: str) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()

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
    summary="Create or overwrite a file inside granted roots.",
    params=("path", "content"),
    returns=("path", "bytes", "overwrote", "sha256"),
)
APPS_LAUNCH = CapabilityManifest(
    id="apps.launch", version="0.1",
    summary="Launch an allowlisted local application.",
    params=("app",),
    returns=("app", "pid"),
)
SYSTEM_INFO = CapabilityManifest(
    id="system.info", version="0.1",
    summary="Report non-identifying machine facts.",
    params=(),
    returns=("os", "engine", "cores"),
)
PROCESS_INSPECT = CapabilityManifest(
    id="process.inspect", version="0.1",
    summary="List running processes. Read-only.",
    params=("mutate",),
    returns=("processes",),
)
ADMIN_TASK = CapabilityManifest(
    id="system.admin_task", version="0.1",
    summary="A capability that declares it needs administrator authority.",
    requires_admin=True, params=("action",),
)


class _VirtualFS:
    """In-memory tree. Keys are normalized, lowercased paths.

    Entries carry a fake but monotonic mtime so the fixture can answer
    "the most recent one" the same way a real host does.
    """

    def __init__(self, files: dict[str, str]) -> None:
        self.files = {normalize_path(k).lower(): v for k, v in files.items()}
        self.mtimes = {k: f"2026-09-{10 + i:02d}T12:00:00Z"
                       for i, k in enumerate(sorted(self.files))}

    def read(self, path: str) -> str:
        key = normalize_path(path).lower()
        if key not in self.files:
            raise FileNotFoundError(path)
        return self.files[key]

    def write(self, path: str, content: str) -> bool:
        key = normalize_path(path).lower()
        existed = key in self.files
        self.files[key] = content
        self.mtimes[key] = "2026-09-17T23:59:00Z"
        return existed

    def isdir(self, path: str) -> bool:
        key = normalize_path(path).lower().rstrip("/")
        return key not in self.files and any(
            p.startswith(key + "/") for p in self.files)

    def listdir(self, path: str) -> list[dict]:
        key = normalize_path(path).lower().rstrip("/")
        out = [
            {"name": p.rsplit("/", 1)[1], "kind": "file",
             "bytes": len(self.files[p]), "modified": self.mtimes.get(p, "")}
            for p in self.files if p.rsplit("/", 1)[0] == key
        ]
        out.sort(key=lambda e: e["modified"], reverse=True)
        return out


class ModernHost(Host):
    """Windows 11-shaped engine."""

    def __init__(self, fs: dict[str, str], **kw: Any) -> None:
        self.fs = _VirtualFS(fs)
        self.processes = ["explorer.exe", "isymotron-host.exe", "notepad.exe"]
        identity = HostIdentity(
            host_id=kw.pop("host_id", "win11-victus"),
            display_name=kw.pop("display_name", "Victus (Windows 11)"),
            os_family="windows", os_release="11-24h2",
            engine="nt-modern/0.1",
        )
        super().__init__(
            identity,
            capabilities=[FS_READ, FS_WRITE, APPS_LAUNCH, SYSTEM_INFO,
                          PROCESS_INSPECT, ADMIN_TASK],
            **kw,
        )

    def run(self, req: ExecutionRequest) -> tuple[dict, list[dict]]:
        p = req.params
        if req.capability == "filesystem.read":
            if self.fs.isdir(p["path"]):
                entries = self.fs.listdir(p["path"])
                return ({"path": normalize_path(p["path"]), "kind": "directory",
                         "entries": entries, "count": len(entries),
                         "order": "modified_desc"},
                        [{"kind": "fs.list", "path": normalize_path(p["path"])}])
            data = self.fs.read(p["path"])
            return ({"path": normalize_path(p["path"]), "kind": "file",
                     "bytes": len(data), "text": data, "sha256": _sha(data)},
                    [{"kind": "fs.read", "path": normalize_path(p["path"])}])
        if req.capability == "filesystem.write":
            existed = self.fs.write(p["path"], p["content"])
            return ({"path": normalize_path(p["path"]), "overwrote": existed},
                    [{"kind": "fs.write", "path": normalize_path(p["path"]),
                      "bytes": len(p["content"])}])
        if req.capability == "apps.launch":
            return ({"app": p["app"], "pid": 4242},
                    [{"kind": "process.spawn", "app": p["app"]}])
        if req.capability == "system.info":
            return ({"os": "Windows 11 24H2", "engine": self._identity.engine,
                     "cores": 16}, [])
        if req.capability == "process.inspect":
            return ({"processes": list(self.processes)}, [])
        if req.capability == "system.admin_task":
            return ({"action": p.get("action"), "performed": True},
                    [{"kind": "admin.action", "action": p.get("action")}])
        raise NotImplementedError(req.capability)


class LegacyHost(Host):
    """Windows 98-shaped engine: fewer capabilities, different path habits."""

    def __init__(self, fs: dict[str, str], **kw: Any) -> None:
        self.fs = _VirtualFS(fs)
        self.launched: list[str] = []
        identity = HostIdentity(
            host_id=kw.pop("host_id", "win98-retrobox"),
            display_name=kw.pop("display_name", "RetroBox (Windows 98 SE)"),
            os_family="windows", os_release="98-se",
            engine="dos-bridge/0.1",
        )
        super().__init__(
            identity,
            # No process family, no admin task: this engine does not implement them.
            capabilities=[FS_READ, FS_WRITE, APPS_LAUNCH, SYSTEM_INFO],
            **kw,
        )

    def run(self, req: ExecutionRequest) -> tuple[dict, list[dict]]:
        p = req.params
        if req.capability == "filesystem.read":
            if self.fs.isdir(p["path"]):
                entries = self.fs.listdir(p["path"])
                return ({"path": normalize_path(p["path"]).upper().replace("/", "\\"),
                         "kind": "directory", "entries": entries,
                         "count": len(entries), "order": "modified_desc"},
                        [{"kind": "fs.list", "path": normalize_path(p["path"])}])
            data = self.fs.read(p["path"])
            # Legacy engine reports paths the way the OS would print them.
            return ({"path": normalize_path(p["path"]).upper().replace("/", "\\"),
                     "kind": "file", "bytes": len(data), "text": data,
                     "sha256": _sha(data)},
                    [{"kind": "fs.read", "path": normalize_path(p["path"])}])
        if req.capability == "filesystem.write":
            existed = self.fs.write(p["path"], p["content"])
            return ({"path": normalize_path(p["path"]).upper().replace("/", "\\"),
                     "overwrote": existed},
                    [{"kind": "fs.write", "path": normalize_path(p["path"]),
                      "bytes": len(p["content"])}])
        if req.capability == "apps.launch":
            self.launched.append(p["app"])
            return ({"app": p["app"], "pid": None, "note": "no pid table on this engine"},
                    [{"kind": "process.spawn", "app": p["app"]}])
        if req.capability == "system.info":
            return ({"os": "Windows 98 SE", "engine": self._identity.engine,
                     "cores": 1}, [])
        raise NotImplementedError(req.capability)
