"""Link receipts: append-only JSONL plus evidence-manifest writer.

Every delegated task leaves `link_delegated` on the sender side and
`link_received` on the receiver side, same shape Munder keeps. The
evidence manifest writer emits the exact {algorithm, artifacts} shape
that `isymotron evidence verify` checks.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


def append_receipt(directory: Path, kind: str, record: dict) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    entry = {
        "kind": kind,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **record,
    }
    path = directory / "receipts.jsonl"
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_receipts(directory: Path, kind: str | None = None) -> list[dict]:
    path = directory / "receipts.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if kind is None or entry.get("kind") == kind:
            out.append(entry)
    return out


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_hashes_manifest(evidence_dir: Path, files: list[str]) -> Path:
    """Write hashes.json for the given files (relative names, sorted)."""
    artifacts = {}
    for name in sorted(files):
        target = evidence_dir / name
        if not target.is_file():
            raise ValueError(f"evidence artifact missing: {name}")
        artifacts[name] = sha256_file(target)
    manifest = {"algorithm": "SHA-256", "artifacts": artifacts}
    path = evidence_dir / "hashes.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path
