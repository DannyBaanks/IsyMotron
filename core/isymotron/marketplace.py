"""Git-backed activity registry (the roadmap's marketplace replacement).

Git distributes source and evidence; it does not distribute trust.  An
installation is pinned to one commit, verifies the activity tree digest, runs
the local sandbox/Doctor, and records the scoped report beside the installed
source.  No remote is contacted by this module.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .doctor import ActivityManifest, DoctorReport
from .sandbox import PythonSandbox


CONTRACT = "git-activity-registry/v0"


def tree_digest(root: str | Path, *, exclude: Iterable[str] = ("activity.json",)) -> str:
    """Digest relative paths and bytes in stable order."""
    base = Path(root).resolve()
    excluded = {Path(item).as_posix() for item in exclude}
    hasher = hashlib.sha256()
    files = sorted(path for path in base.rglob("*") if path.is_file())
    for path in files:
        relative = path.relative_to(base).as_posix()
        if relative in excluded or relative.startswith(".git/"):
            continue
        data = path.read_bytes()
        hasher.update(relative.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(str(len(data)).encode("ascii"))
        hasher.update(b"\0")
        hasher.update(data)
    return "sha256:" + hasher.hexdigest()


@dataclass(frozen=True)
class ActivityRecord:
    activity_id: str
    version: str
    entrypoint: str
    declared_effects: tuple[dict[str, Any], ...]
    tree_digest: str

    @classmethod
    def read(cls, path: Path) -> "ActivityRecord":
        data = json.loads(path.read_text(encoding="utf-8"))
        required = {"activity_id", "version", "entrypoint", "declared_effects", "tree_digest"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"activity.json missing fields: {sorted(missing)}")
        return cls(
            activity_id=str(data["activity_id"]),
            version=str(data["version"]),
            entrypoint=str(data["entrypoint"]),
            declared_effects=tuple(dict(effect) for effect in data["declared_effects"]),
            tree_digest=str(data["tree_digest"]),
        )


@dataclass(frozen=True)
class Installation:
    commit: str
    path: Path
    record: ActivityRecord
    report: DoctorReport


class GitActivityRegistry:
    """Install one immutable activity snapshot from a local Git repository."""

    def __init__(self, sandbox: PythonSandbox | None = None):
        self.sandbox = sandbox or PythonSandbox()

    def install(self, repository: str | Path, commit: str, destination: str | Path) -> Installation:
        repository = Path(repository).resolve()
        destination = Path(destination).resolve()
        resolved = self._git(repository, "rev-parse", f"{commit}^{{commit}}").strip()
        if destination.exists() and any(destination.iterdir()):
            raise FileExistsError(f"destination is not empty: {destination}")
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as archive:
            archive_path = Path(archive.name)
        try:
            self._git(repository, "archive", "--format=tar", resolved, stdout_path=archive_path)
            with tarfile.open(archive_path) as bundle:
                bundle.extractall(destination, filter="data")
        finally:
            archive_path.unlink(missing_ok=True)

        record = ActivityRecord.read(destination / "activity.json")
        actual_digest = tree_digest(destination)
        if actual_digest != record.tree_digest:
            raise ValueError(f"tree digest mismatch: expected {record.tree_digest}, got {actual_digest}")
        entrypoint = destination / record.entrypoint
        if not entrypoint.is_file():
            raise ValueError(f"entrypoint is not a file: {record.entrypoint}")
        manifest = ActivityManifest(record.activity_id, record.version, record.declared_effects)
        result = self.sandbox.run(manifest, entrypoint)
        report_path = destination / "doctor-report.json"
        report_path.write_text(json.dumps(report_payload(result.report), indent=2) + "\n", encoding="utf-8")
        return Installation(resolved, destination, record, result.report)

    @staticmethod
    def _git(repository: Path, *args: str, stdout_path: Path | None = None) -> str:
        if stdout_path is None:
            return subprocess.check_output(["git", "-C", str(repository), *args], text=True)
        with stdout_path.open("wb") as output:
            subprocess.run(["git", "-C", str(repository), *args], stdout=output, check=True)
        return ""


def report_payload(report: DoctorReport) -> dict[str, Any]:
    payload = report.payload()
    payload["seal"] = report.seal
    payload["contract"] = CONTRACT + "+" + payload["contract"]
    return payload
