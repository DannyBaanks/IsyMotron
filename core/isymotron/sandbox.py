"""Small, observable Python activity sandbox for Doctor V0.

This is a provider seam, not an OS security boundary. It runs an activity in
an isolated temporary working directory, records mutating audit events, and
blocks writes/process/network attempts outside that directory. A later host
provider can replace it without changing :mod:`isymotron.doctor`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .doctor import ActivityManifest, DoctorReport, ObservedEffect, examine


_RUNNER = r'''
import builtins, json, os, runpy, socket, sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
script = Path(sys.argv[2]).resolve()
trace_path = Path(sys.argv[3]).resolve()
events = []

def target(value):
    try:
        path = Path(os.fspath(value)).resolve()
    except (TypeError, ValueError, OSError):
        return "hostfs://<unresolved>"
    try:
        relative = path.relative_to(root)
    except ValueError:
        return "hostfs://" + str(path)
    return "activity://" + relative.as_posix()

def effect(kind, value, mutation=True):
    item = {"kind": kind, "target": target(value), "mutation": mutation}
    events.append(item)
    return item

def audit(event, args):
    if event == "open":
        path = args[0] if args else "<unknown>"
        mode = args[1] if len(args) > 1 and isinstance(args[1], str) else "r"
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            item = effect("filesystem.write", path)
            if item["target"].startswith("hostfs://"):
                raise PermissionError("sandbox blocked write outside activity root")
    elif event in {"os.mkdir", "os.remove", "os.rename", "os.replace", "os.rmdir"}:
        path = args[0] if args else "<unknown>"
        item = effect("filesystem.write", path)
        if item["target"].startswith("hostfs://"):
            raise PermissionError("sandbox blocked filesystem mutation outside activity root")
    elif event in {"subprocess.Popen", "os.system", "os.posix_spawn"}:
        events.append({"kind": "process.spawn", "target": "hostfs://process", "mutation": True})
        raise PermissionError("sandbox blocked process creation")
    elif event in {"socket.connect", "socket.bind", "socket.getaddrinfo"}:
        events.append({"kind": "network.connect", "target": "hostfs://network", "mutation": True})
        raise PermissionError("sandbox blocked network access")

sys.addaudithook(audit)
try:
    runpy.run_path(str(script), run_name="__main__")
finally:
    trace_path.write_text(json.dumps(events, sort_keys=True), encoding="utf-8")
'''


@dataclass(frozen=True)
class SandboxResult:
    """Process result plus the Doctor's sealed scoped report."""

    exit_code: int | None
    timed_out: bool
    stdout: str
    stderr: str
    effects: tuple[ObservedEffect, ...]
    report: DoctorReport


class PythonSandbox:
    """Run one Python activity with a temporary root and audit tracing."""

    def __init__(self, timeout_s: float = 5.0):
        self.timeout_s = timeout_s

    def run(self, manifest: ActivityManifest, script: str | os.PathLike[str]) -> SandboxResult:
        script_path = Path(script).resolve()
        if not script_path.is_file():
            raise FileNotFoundError(script_path)

        with tempfile.TemporaryDirectory(prefix="isymotron-sandbox-") as directory:
            root = Path(directory).resolve()
            trace_path = root / ".isymotron-trace.json"
            command = [
                sys.executable, "-c", _RUNNER,
                str(root), str(script_path), str(trace_path),
            ]
            try:
                completed = subprocess.run(
                    command, cwd=root, capture_output=True, text=True,
                    timeout=self.timeout_s, check=False,
                    env={"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"},
                )
                timed_out = False
                exit_code = completed.returncode
                stdout, stderr = completed.stdout, completed.stderr
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                exit_code = None
                stdout = _text(exc.stdout)
                stderr = _text(exc.stderr)

            raw_events: list[dict[str, Any]] = []
            if trace_path.exists():
                raw_events = json.loads(trace_path.read_text(encoding="utf-8"))
            effects = tuple(ObservedEffect(**event) for event in raw_events)
            report = examine(manifest, effects)
            return SandboxResult(exit_code, timed_out, stdout, stderr, effects, report)


def _text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
