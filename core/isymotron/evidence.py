"""Evidence manifest verification (Quine Gate, milestone M8).

The repository carries ``hashes.json`` manifests (``evidence/LINUX_V0``,
``evidence/M3``) in the shape::

    {"algorithm": "SHA-256", "artifacts": {"<relpath>": "<hex>"}}

Until now nothing in the code read them: they were decorative. This module
turns a manifest into a check a third party can run without the machine that
produced it.

Fail-closed: an unreadable manifest, an unknown algorithm, an empty artifact
set, an unsafe path, a missing file or a digest mismatch is never a PASS.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_ALGORITHM = "SHA-256"
_CHUNK = 1 << 20


@dataclass(frozen=True)
class ArtifactCheck:
    """One artifact entry: what was expected, what is on disk, and whether
    they agree. ``actual`` is None when the file could not be read."""

    path: str
    expected: str
    actual: str | None
    ok: bool

    def to_dict(self) -> dict:
        return {"path": self.path, "expected": self.expected,
                "actual": self.actual, "ok": self.ok}


@dataclass(frozen=True)
class ManifestVerification:
    """Outcome of verifying one manifest. Never claims more than 'these bytes
    match these digests'."""

    manifest: str
    algorithm: str
    passed: bool
    reason: str
    artifacts: tuple[ArtifactCheck, ...]

    def to_dict(self) -> dict:
        return {
            "manifest": self.manifest,
            "algorithm": self.algorithm,
            "passed": self.passed,
            "reason": self.reason,
            "artifacts": [a.to_dict() for a in self.artifacts],
        }


def sha256_file(path: str | Path) -> str:
    """Stream a file through SHA-256 without loading it whole."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _unsafe_relpath(rel: str) -> bool:
    """Absolute paths and any '..' segment would let a manifest point outside
    its own directory. That is a refusal, not a normalisation."""
    if not rel or Path(rel).is_absolute():
        return True
    return ".." in Path(rel).parts


def verify_manifest(manifest_path: str | Path) -> ManifestVerification:
    """Verify every artifact in a ``hashes.json`` against the directory it
    lives in. Returns a structured outcome; never raises on bad input."""
    path = Path(manifest_path)
    shown = path.as_posix()

    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return ManifestVerification(shown, "", False,
                                    f"unreadable manifest: {exc}", ())

    if not isinstance(raw, dict):
        return ManifestVerification(shown, "", False,
                                    "manifest is not a JSON object", ())

    algorithm = raw.get("algorithm")
    if algorithm != SUPPORTED_ALGORITHM:
        return ManifestVerification(shown, str(algorithm), False,
                                    f"unsupported algorithm {algorithm!r}; "
                                    f"only {SUPPORTED_ALGORITHM}", ())

    artifacts = raw.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        return ManifestVerification(shown, algorithm, False,
                                    "empty or malformed artifact set", ())

    base = path.parent
    checks: list[ArtifactCheck] = []
    for rel, expected in sorted(artifacts.items()):
        rel = str(rel)
        expected = str(expected)
        if _unsafe_relpath(rel):
            checks.append(ArtifactCheck(rel, expected, None, False))
            continue
        try:
            actual = sha256_file(base / rel)
        except OSError:
            checks.append(ArtifactCheck(rel, expected, None, False))
            continue
        checks.append(ArtifactCheck(rel, expected, actual, actual == expected))

    passed = all(check.ok for check in checks)
    reason = "all artifacts match" if passed else \
        "artifact mismatch, missing file, or unsafe path"
    return ManifestVerification(shown, algorithm, passed, reason, tuple(checks))
