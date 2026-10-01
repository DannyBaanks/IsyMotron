"""Regression tests for Link concurrency and bounded replay state."""

from concurrent.futures import ThreadPoolExecutor
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))

from isymotron.link import envelope, identity, pairing
from isymotron.link.server import LinkState, _dispatch


def _paired(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    ident_a = identity.load_identity(dir_a, name="isytron-a")
    ident_b = identity.load_identity(dir_b, name="isytron-b")
    pairing.trust_peer(identity.public_card(ident_a), dir_b)
    return ident_a, ident_b, dir_b


def test_replay_cache_discards_expired_nonces(tmp_path):
    ident_a, ident_b, dir_b = _paired(tmp_path)
    seen = {"expired-a": 10.0, "expired-b": 20.0}
    env = envelope.seal(
        ident_a, identity.public_card(ident_b), {"op": "ping"}, now=100.0,
    )

    envelope.open_envelope(
        ident_b, identity.load_peers(dir_b), env, seen, now=100.0,
    )

    assert set(seen) == {env["nonce"]}


def test_concurrent_messages_do_not_overwrite_each_other(tmp_path):
    state = LinkState(tmp_path / "office")
    peer = {"office_id": "peer-a"}
    state.inbox_append(
        {
            "task_id": "task-1",
            "from": peer["office_id"],
            "title": "parallel",
            "body": "",
            "context": [],
            "status": "queued",
        }
    )
    barrier = threading.Barrier(16)

    def send(index):
        barrier.wait()
        _dispatch(
            state,
            peer,
            {"op": "message", "task_id": "task-1", "text": f"m{index}"},
        )

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(send, range(16)))

    context = state.inbox()[0]["context"]
    assert len(context) == 16
    assert {item["text"] for item in context} == {f"m{i}" for i in range(16)}
