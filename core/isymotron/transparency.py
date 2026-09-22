"""Append-only transparency log for published Quine Gate heads (M9, minimal).

Why this exists: a hash chain cannot choose between two divergent histories —
both recompute cleanly, and each side looks valid to itself. A transparency
log is ONE shared sequence: entry N names exactly one head. Two logs that
disagree at any shared sequence number are a CONFLICT either side can detect
without trusting the other, and a log presented as current that is only an
older prefix of the published one is detected as STALE (a rollback).

Honest boundary: this detects forks *between compared logs*. It cannot detect
the sole holder of a log silently truncating its tail — that is what the
external checkpoint is for: the git commit (or tag) that carries this file.
The log does not replace the anchor; it batches the anchors so they can be
compared.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .chain import CONFLICT, NOT_VERIFIABLE, PASS, REJECT

#: A presented log that is only an older prefix of the published one.
STALE = "STALE"


class TransparencyError(Exception):
    """The log could not be read; the caller must treat it as NOT_VERIFIABLE."""


@dataclass(frozen=True)
class LogEntry:
    """One published head. `seq` is the only thing that orders entries."""

    seq: int
    genesis: str
    head: str
    commit: str = ""
    timestamp: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "genesis": self.genesis,
            "head": self.head,
            "commit": self.commit,
            "timestamp": self.timestamp,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LogEntry":
        try:
            return cls(
                seq=int(data["seq"]),
                genesis=str(data["genesis"]),
                head=str(data["head"]),
                commit=str(data.get("commit", "")),
                timestamp=str(data.get("timestamp", "")),
                note=str(data.get("note", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise TransparencyError(f"malformed log entry: {exc}") from exc


@dataclass(frozen=True)
class LogVerification:
    passed: bool
    status: str
    reason: str
    length: int

    def to_dict(self) -> dict:
        return {"passed": self.passed, "status": self.status,
                "reason": self.reason, "length": self.length}


def load_log(path: str | Path) -> list[LogEntry]:
    """Strict load: a missing file is an empty log; a malformed line is an
    error, never a silent skip."""
    target = Path(path)
    if not target.is_file():
        return []
    entries: list[LogEntry] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(LogEntry.from_dict(json.loads(line)))
        except json.JSONDecodeError as exc:
            raise TransparencyError(f"unparseable log line: {exc}") from exc
    return entries


def append_entry(path: str | Path, *, genesis: str, head: str,
                 commit: str = "", note: str = "",
                 timestamp: str | None = None) -> LogEntry:
    """Append the next published head. Sequence numbers are never reused
    within one log: seq is the current length, so a rewritten history shifts
    every following entry and becomes detectable on comparison."""
    entries = load_log(path)  # raises on a malformed existing log: fail closed
    entry = LogEntry(
        seq=len(entries),
        genesis=genesis,
        head=head,
        commit=commit,
        timestamp=timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        note=note,
    )
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry.to_dict()) + "\n")
    return entry


def verify_log(entries: list[LogEntry]) -> LogVerification:
    """Internal consistency: sequence numbers must be exactly 0..n-1."""
    if not entries:
        return LogVerification(False, NOT_VERIFIABLE, "log is empty", 0)
    for index, entry in enumerate(entries):
        if entry.seq != index:
            return LogVerification(False, REJECT,
                                   f"entry {index} carries seq {entry.seq}; "
                                   "the log was rewritten or spliced", len(entries))
    return LogVerification(True, PASS, "sequence is 0..n-1 without gaps or dups",
                           len(entries))


def verify_log_file(path: str | Path) -> LogVerification:
    try:
        return verify_log(load_log(path))
    except TransparencyError as exc:
        return LogVerification(False, NOT_VERIFIABLE, str(exc), 0)


def conflicts_between(local: list[LogEntry],
                      other: list[LogEntry]) -> LogVerification:
    """Compare two logs. Same sequence number with a different head is a
    fork nobody can talk their way out of; a strict prefix is a rollback."""
    if not local or not other:
        return LogVerification(False, NOT_VERIFIABLE,
                               "a log to compare is empty", max(len(local), len(other)))
    for a, b in zip(local, other):
        if a.seq != b.seq:
            return LogVerification(False, REJECT,
                                   f"misaligned logs at seq {a.seq}/{b.seq}",
                                   min(len(local), len(other)))
        if a.head != b.head or a.genesis != b.genesis:
            return LogVerification(
                False, CONFLICT,
                f"fork at seq {a.seq}: head {a.head[:23]}… vs {b.head[:23]}…",
                min(len(local), len(other)))
    if len(other) < len(local):
        return LogVerification(False, STALE,
                                f"the presented log stops at seq {len(other) - 1}; "
                                f"the published log continues to {len(local) - 1}",
                                len(other))
    return LogVerification(True, PASS, "logs agree on every shared sequence",
                           min(len(local), len(other)))
