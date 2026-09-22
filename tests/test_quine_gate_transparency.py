"""Quine Gate — M9 minimal: the transparency log.

A chain alone cannot choose between two divergent histories. This gate proves
the log does the two things the plan asks of it: conflict detection (same
sequence number, different head) and rollback detection (a presented log that
is only an older prefix). And it fails closed: empty or malformed is
NOT_VERIFIABLE, never a wildcard.
"""
from __future__ import annotations

import json

import pytest

from isymotron.transparency import (
    CONFLICT,
    NOT_VERIFIABLE,
    PASS,
    REJECT,
    STALE,
    TransparencyError,
    LogEntry,
    append_entry,
    conflicts_between,
    load_log,
    verify_log,
    verify_log_file,
)


def _entry(seq: int, head: str, genesis: str = "sha256:" + "a" * 64) -> LogEntry:
    return LogEntry(seq=seq, genesis=genesis, head=head)


def test_append_assigns_monotonic_sequence_numbers(tmp_path):
    log = tmp_path / "HEADS.jsonl"
    first = append_entry(log, genesis="sha256:" + "a" * 64, head="sha256:" + "1" * 64)
    second = append_entry(log, genesis="sha256:" + "a" * 64, head="sha256:" + "2" * 64)
    assert (first.seq, second.seq) == (0, 1)
    assert [e.seq for e in load_log(log)] == [0, 1]
    assert verify_log_file(log).passed


def test_verify_log_rejects_a_spliced_sequence(tmp_path):
    log = tmp_path / "HEADS.jsonl"
    append_entry(log, genesis="sha256:" + "a" * 64, head="sha256:" + "1" * 64)
    lines = log.read_text(encoding="utf-8").splitlines()
    duplicate = json.loads(lines[0])
    duplicate["head"] = "sha256:" + "f" * 64
    log.write_text("\n".join(lines + [json.dumps(duplicate)]) + "\n", encoding="utf-8")

    result = verify_log(load_log(log))
    assert not result.passed and result.status == REJECT
    assert "rewritten or spliced" in result.reason


def test_malformed_log_is_not_verifiable(tmp_path):
    log = tmp_path / "HEADS.jsonl"
    log.write_text("this is not json\n", encoding="utf-8")
    result = verify_log_file(log)
    assert not result.passed and result.status == NOT_VERIFIABLE


def test_empty_log_is_not_verifiable(tmp_path):
    result = verify_log_file(tmp_path / "missing.jsonl")
    assert not result.passed and result.status == NOT_VERIFIABLE


def test_fork_at_a_shared_sequence_is_conflict():
    local = [_entry(0, "sha256:" + "1" * 64), _entry(1, "sha256:" + "2" * 64)]
    forked = [_entry(0, "sha256:" + "1" * 64), _entry(1, "sha256:" + "e" * 64)]
    result = conflicts_between(local, forked)
    assert not result.passed and result.status == CONFLICT
    assert "fork at seq 1" in result.reason


def test_different_genesis_is_conflict():
    local = [_entry(0, "sha256:" + "1" * 64, genesis="sha256:" + "a" * 64)]
    other = [_entry(0, "sha256:" + "1" * 64, genesis="sha256:" + "b" * 64)]
    result = conflicts_between(local, other)
    assert not result.passed and result.status == CONFLICT


def test_presented_older_prefix_is_stale_rollback():
    local = [_entry(0, "sha256:" + "1" * 64), _entry(1, "sha256:" + "2" * 64),
             _entry(2, "sha256:" + "3" * 64)]
    older = [_entry(0, "sha256:" + "1" * 64), _entry(1, "sha256:" + "2" * 64)]
    result = conflicts_between(local, older)
    assert not result.passed and result.status == STALE
    assert "stops at seq 1" in result.reason


def test_agreeing_log_extending_forward_is_pass():
    """A presented log that agrees and continues past mine is not a conflict:
    they are simply ahead. (The mirrored direction is the STALE case above.)"""
    mine = [_entry(0, "sha256:" + "1" * 64)]
    ahead = [_entry(0, "sha256:" + "1" * 64), _entry(1, "sha256:" + "2" * 64)]
    result = conflicts_between(mine, ahead)
    assert result.passed and result.status == PASS


def test_malformed_entry_raises_instead_of_skipping():
    with pytest.raises(TransparencyError):
        LogEntry.from_dict({"seq": "not-a-number", "head": "x"})


def test_sequence_numbers_never_reuse_within_one_log(tmp_path):
    """The property that makes a rewritten history detectable on comparison."""
    log = tmp_path / "HEADS.jsonl"
    for i in range(5):
        append_entry(log, genesis="sha256:" + "a" * 64,
                     head=f"sha256:{i:0>63x}")
    entries = load_log(log)
    assert [e.seq for e in entries] == list(range(5))
    # deleting a middle entry shifts nothing silently: the gap is visible
    lines = log.read_text(encoding="utf-8").splitlines()
    del lines[2]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert verify_log(load_log(log)).status == REJECT
