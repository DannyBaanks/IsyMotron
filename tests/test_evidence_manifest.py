"""Quine Gate — M8: the evidence manifests are actually verified.

`evidence/LINUX_V0/hashes.json` and `evidence/M3/hashes.json` existed in the
right shape but nothing in the code read them. This gate proves the new
verifier accepts the real manifests and refuses every failure mode:

- a mutated byte;
- a missing artifact;
- an unknown algorithm;
- an empty artifact set;
- a path that tries to escape the manifest's directory.

A PASS here means only "these bytes match these digests", nothing more.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from isymotron.evidence import sha256_file, verify_manifest

REPO = Path(__file__).resolve().parent.parent
REAL_MANIFESTS = [
    REPO / "evidence" / "LINUX_V0" / "hashes.json",
    REPO / "evidence" / "M3" / "hashes.json",
    REPO / "evidence" / "M0" / "hashes.json",
    REPO / "evidence" / "QUINE_GATE" / "hashes.json",
]


def _write_manifest(tmp_path: Path, artifacts: dict, algorithm: str = "SHA-256") -> Path:
    target = tmp_path / "hashes.json"
    target.write_text(
        json.dumps({"algorithm": algorithm, "artifacts": artifacts}),
        encoding="utf-8",
    )
    return target


@pytest.mark.parametrize("manifest", REAL_MANIFESTS, ids=lambda p: p.parent.name)
def test_real_manifests_verify(manifest):
    assert manifest.is_file(), f"expected manifest on disk: {manifest}"
    result = verify_manifest(manifest)
    assert result.passed, result.to_dict()
    assert result.reason == "all artifacts match"


def test_mutated_byte_fails(tmp_path):
    artifact = tmp_path / "run.txt"
    artifact.write_bytes(b"original bytes")
    manifest = _write_manifest(tmp_path, {"run.txt": sha256_file(artifact)})

    assert verify_manifest(manifest).passed

    artifact.write_bytes(b"original byteZ")  # one byte differs
    result = verify_manifest(manifest)
    assert not result.passed
    assert result.artifacts[0].actual is not None


def test_missing_artifact_fails(tmp_path):
    artifact = tmp_path / "gone.txt"
    artifact.write_bytes(b"here now")
    manifest = _write_manifest(tmp_path, {"gone.txt": sha256_file(artifact)})
    artifact.unlink()

    result = verify_manifest(manifest)
    assert not result.passed
    assert result.artifacts[0].actual is None


def test_unknown_algorithm_fails(tmp_path):
    artifact = tmp_path / "a.txt"
    artifact.write_bytes(b"x")
    manifest = _write_manifest(tmp_path, {"a.txt": sha256_file(artifact)},
                               algorithm="MD5")

    result = verify_manifest(manifest)
    assert not result.passed
    assert "unsupported algorithm" in result.reason


def test_empty_artifact_set_fails(tmp_path):
    manifest = _write_manifest(tmp_path, {})
    result = verify_manifest(manifest)
    assert not result.passed
    assert "empty" in result.reason


def test_unreadable_manifest_fails(tmp_path):
    broken = tmp_path / "hashes.json"
    broken.write_text("{not json", encoding="utf-8")

    result = verify_manifest(broken)
    assert not result.passed
    assert "unreadable" in result.reason


def test_path_traversal_is_refused(tmp_path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_bytes(b"do not read me")
    try:
        manifest = _write_manifest(tmp_path, {"../outside-secret.txt": sha256_file(outside)})
        result = verify_manifest(manifest)
        assert not result.passed, "a manifest must not reach outside its directory"
        assert result.artifacts[0].actual is None
    finally:
        outside.unlink(missing_ok=True)


def test_absolute_path_is_refused(tmp_path):
    artifact = tmp_path / "a.txt"
    artifact.write_bytes(b"x")
    manifest = _write_manifest(tmp_path, {str(artifact): sha256_file(artifact)})

    result = verify_manifest(manifest)
    assert not result.passed
    assert result.artifacts[0].actual is None
