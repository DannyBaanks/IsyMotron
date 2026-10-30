"""Regression: hostile Content-Length and atomic inbox rewrite (audit 2026-10-30)."""

import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))

from isymotron.link.server import LinkServer, LinkState


def _raw(address, request: bytes) -> bytes:
    host, port = address
    with socket.create_connection((host, port), timeout=3) as conn:
        conn.sendall(request)
        chunks = []
        while True:
            data = conn.recv(4096)
            if not data:
                break
            chunks.append(data)
        return b"".join(chunks)


@pytest.fixture()
def link(tmp_path):
    server = LinkServer(tmp_path, tcp_port=0, udp_port=0).start()
    try:
        yield server
    finally:
        server.stop()


@pytest.mark.parametrize("value", ["-1", "-100"])
def test_link_rejects_negative_content_length(link, value):
    reply = _raw(
        link.http.server_address[:2],
        f"POST /link/v1/call HTTP/1.1\r\nHost: x\r\nContent-Length: {value}\r\n\r\n{{}}".encode(),
    )
    assert b" 400 " in reply.split(b"\r\n", 1)[0]
    assert b"bad_length" in reply


def test_inbox_rewrite_is_atomic(tmp_path):
    state = LinkState(tmp_path)
    state.inbox_append({"task_id": "t1", "from": "o", "status": "queued"})
    state._rewrite_inbox_unlocked([{"task_id": "t2"}])
    assert [e["task_id"] for e in state.inbox()] == ["t2"]
    assert not (tmp_path / "inbox.jsonl.tmp").exists()
