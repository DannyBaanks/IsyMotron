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
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .doctor import ActivityManifest, DoctorReport
from .canon import digest
from .sandbox import PythonSandbox
from .verdicts import DoctorVerdict, Evidence


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
    manifest_digest: str

    @classmethod
    def read(cls, path: Path) -> "ActivityRecord":
        data = json.loads(path.read_text(encoding="utf-8"))
        required = {"activity_id", "version", "entrypoint", "declared_effects", "tree_digest", "manifest_digest"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"activity.json missing fields: {sorted(missing)}")
        return cls(
            activity_id=str(data["activity_id"]),
            version=str(data["version"]),
            entrypoint=str(data["entrypoint"]),
            declared_effects=tuple(dict(effect) for effect in data["declared_effects"]),
            tree_digest=str(data["tree_digest"]),
            manifest_digest=str(data["manifest_digest"]),
        )


@dataclass(frozen=True)
class Installation:
    commit: str
    path: Path
    record: ActivityRecord
    report: DoctorReport


def _verification_key(record: ActivityRecord) -> str:
    """A key fully pinned by content: identical digests mean identical bits."""
    return f"{record.tree_digest}|{record.manifest_digest}"


class GitActivityRegistry:
    """Install one immutable activity snapshot from a local Git repository."""

    def __init__(self, sandbox: PythonSandbox | None = None,
                 cache_path: str | Path | None = None):
        self.sandbox = sandbox or PythonSandbox()
        # Verification cache: digest-pinned Doctor reports, so a bit-identical
        # activity reuses a sealed verdict instead of re-running the sandbox.
        # Scope: the cache is a local file; a writer able to forge it already
        # has the disk.  Reused reports are marked so the audit trail shows
        # which installs were re-verified and which were replayed.
        self.cache_path = Path(cache_path).resolve() if cache_path else None

    def install(self, repository: str | Path, commit: str, destination: str | Path,
                *, reuse: bool = True) -> Installation:
        repository = Path(repository).resolve()
        destination = Path(destination).resolve()
        resolved = self._git(repository, "rev-parse", f"{commit}^{{commit}}").strip()
        if destination.exists():
            raise FileExistsError(f"destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent))
        published = False
        try:
            with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as archive:
                archive_path = Path(archive.name)
            try:
                self._git(repository, "archive", "--format=tar", resolved, stdout_path=archive_path)
                with tarfile.open(archive_path) as bundle:
                    bundle.extractall(staging, filter="data")
            finally:
                archive_path.unlink(missing_ok=True)

            record = ActivityRecord.read(staging / "activity.json")
            actual_digest = tree_digest(staging)
            if actual_digest != record.tree_digest:
                raise ValueError(f"tree digest mismatch: expected {record.tree_digest}, got {actual_digest}")
            if manifest_digest(record) != record.manifest_digest:
                raise ValueError("manifest digest mismatch")
            entrypoint = staging / record.entrypoint
            if not entrypoint.is_file():
                raise ValueError(f"entrypoint is not a file: {record.entrypoint}")
            manifest = ActivityManifest(record.activity_id, record.version, record.declared_effects)
            cached = self._lookup_cache(record) if reuse else None
            if cached is not None:
                report_obj = doctor_report_from_payload(cached)
            else:
                report_obj = self.sandbox.run(manifest, entrypoint).report
                self._store_cache(record, report_obj)
            report_path = staging / "doctor-report.json"
            payload = report_payload(report_obj)
            payload.update({"git_commit": resolved, "source_tree_digest": record.tree_digest,
                            "manifest_digest": record.manifest_digest,
                            "verification": "reused" if cached is not None else "sandbox"})
            report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            try:
                staging.replace(destination)
            except FileExistsError as exc:
                raise FileExistsError(f"destination was published concurrently: {destination}") from exc
            published = True
            return Installation(resolved, destination, record, report_obj)
        finally:
            if not published:
                shutil.rmtree(staging, ignore_errors=True)

    def _cache_file(self) -> Path | None:
        return self.cache_path

    def _load_cache(self) -> dict[str, Any]:
        if self.cache_path is None or not self.cache_path.is_file():
            return {}
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return dict(data.get("entries", {})) if isinstance(data, dict) else {}

    def _lookup_cache(self, record: ActivityRecord) -> dict[str, Any] | None:
        """Return a cached sealed Doctor report for bit-identical content.

        Only a PASS_FOR_SCOPE verdict whose seal re-derives is reused; anything
        else (missing, tampered, denied) falls back to a full sandbox run, so
        a poisoned cache buys a rewrite, never a verdict.
        """
        entry = self._load_cache().get(_verification_key(record))
        if not isinstance(entry, dict):
            return None
        try:
            report = doctor_report_from_payload(entry["report"])
        except (KeyError, TypeError, ValueError):
            return None
        if report.verdict is not DoctorVerdict.PASS_FOR_SCOPE or not report.verify():
            return None
        return entry["report"]

    def _store_cache(self, record: ActivityRecord, report: DoctorReport) -> None:
        if self.cache_path is None or report.verdict is not DoctorVerdict.PASS_FOR_SCOPE:
            return
        entries = self._load_cache()
        payload = report_payload(report)
        payload.pop("contract", None)
        entries[_verification_key(record)] = {"report": payload,
                                              "contract": CONTRACT}
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
        tmp.write_text(json.dumps({"entries": entries}, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        tmp.replace(self.cache_path)

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


def doctor_report_from_payload(payload: Mapping[str, Any]) -> DoctorReport:
    """Rebuild a sealed DoctorReport from a stored payload (see report_payload)."""
    data = {k: v for k, v in payload.items()
            if k not in {"contract", "git_commit", "source_tree_digest",
                         "manifest_digest", "verification"}}
    return DoctorReport(
        activity_id=str(data["activity_id"]),
        activity_version=str(data["activity_version"]),
        activity_digest=str(data["activity_digest"]),
        verdict=DoctorVerdict(data["verdict"]),
        evidence=Evidence(data["evidence"]),
        declared_effects=tuple(dict(x) for x in data["declared_effects"]),
        observed_effects=tuple(dict(x) for x in data["observed_effects"]),
        undeclared_effects=tuple(dict(x) for x in data["undeclared_effects"]),
        seal=str(data["seal"]),
    )


def manifest_digest(record: ActivityRecord) -> str:
    """Digest manifest claims while excluding only derived digest fields."""
    return digest({
        "activity_id": record.activity_id,
        "version": record.version,
        "entrypoint": record.entrypoint,
        "declared_effects": [dict(effect) for effect in record.declared_effects],
    })
