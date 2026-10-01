"""Regression tests for Link audit findings (2026-10-01)."""

from concurrent.futures import ThreadPoolExecutor
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))

from isymotron.link import envelope, identity, pairing
import isymotron.link.server as link_server
from isymotron.link.server import LinkState


def _paired(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    ident_a = identity.load_identity(dir_a, name="isytron-a")
    ident_b = identity.load_identity(dir_b, name="isytron-b")
    pairing.trust_peer(identity.public_card(ident_a), dir_b)
    return ident_a, ident_b, identity.load_peers(dir_b)


def test_expired_nonce_entries_are_pruned(tmp_path):
    ident_a, ident_b, peers_b = _paired(tmp_path)
    seen: dict[str, float] = {}

    for i, moment in enumerate((1000.0, 1001.0, 1002.0)):
        env = envelope.seal(
            ident_a,
            identity.public_card(ident_b),
            {"i": i},
            now=moment,
        )
        envelope.open_envelope(ident_b, peers_b, env, seen, now=moment)

    fresh = envelope.seal(
        ident_a,
        identity.public_card(ident_b),
        {"i": "fresh"},
        now=2000.0,
    )
    envelope.open_envelope(ident_b, peers_b, fresh, seen, now=2000.0)

    assert list(seen) == [fresh["nonce"]]


def test_concurrent_task_messages_do_not_overwrite_each_other(tmp_path, monkeypatch):
    state = LinkState(tmp_path / "office")
    peer = {"office_id": "peer"}
    state.inbox_append(
        {
            "task_id": "task-1",
            "from": peer["office_id"],
            "title": "audit",
            "body": "",
            "context": [],
            "status": "queued",
        }
    )

    workers = 8
    ready_to_rewrite = threading.Barrier(workers)
    original_rewrite = link_server._rewrite_inbox

    def synchronized_rewrite(state_arg, entries):
        # Force the old read -> modify -> rewrite implementation to let every
        # request read the same snapshot before any one of them rewrites it.
        ready_to_rewrite.wait(timeout=5)
        original_rewrite(state_arg, entries)

    monkeypatch.setattr(link_server, "_rewrite_inbox", synchronized_rewrite)

    def send_message(i: int) -> None:
        link_server._dispatch(
            state,
            peer,
            {"op": "message", "task_id": "task-1", "text": f"m{i}"},
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(send_message, i) for i in range(workers)]
        for future in futures:
            future.result(timeout=10)

    task = state.inbox()[0]
    texts = [item["text"] for item in task["context"]]
    assert sorted(texts) == [f"m{i}" for i in range(workers)]
