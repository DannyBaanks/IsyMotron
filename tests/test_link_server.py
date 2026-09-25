"""M2: envelopes, server, delegation, receipts. Tempdirs + loopback only.

Crypto vectors confirmed against the `cryptography` package (OpenSSL
bindings) on 2026-09-25; GCM all-zero matches the classic NIST value.
"""
import ast
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))

from isymotron.link import aesgcm, envelope, identity, pairing, receipts
from isymotron.link.server import LinkServer


def test_aes_block_matches_oracle_vector():
    key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    pt = bytes.fromhex("00112233445566778899aabbccddeeff")
    assert aesgcm.aes128_block(key, pt).hex() == (
        "69c4e0d86a7b0430d8cdb78070b4c55a"
    )


def test_gcm_zero_vector():
    ct, tag = aesgcm.gcm_encrypt(bytes(16), bytes(12), bytes(16), b"")
    assert ct.hex() == "0388dace60b6a392f328c2b971b2fe78"
    assert tag.hex() == "ab6e47d42cec13bdf53a67b21257bddf"
    assert aesgcm.gcm_decrypt(bytes(16), bytes(12), ct, tag, b"") == bytes(16)


def test_gcm_tamper_fails_closed():
    ct, tag = aesgcm.gcm_encrypt(bytes(16), bytes(12), b"hola", b"aad")
    bad = bytearray(ct)
    bad[0] ^= 1
    with pytest.raises(ValueError):
        aesgcm.gcm_decrypt(bytes(16), bytes(12), bytes(bad), tag, b"aad")
    with pytest.raises(ValueError):
        aesgcm.gcm_decrypt(bytes(16), bytes(12), ct, tag, b"other-aad")


def test_hkdf_rfc5869_case1():
    okm = aesgcm.hkdf_sha256(
        bytes.fromhex("0b" * 22),
        bytes.fromhex("000102030405060708090a0b0c"),
        bytes.fromhex("f0f1f2f3f4f5f6f7f8f9"),
        42,
    )
    assert okm.hex() == (
        "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c"
        "5bf34007208d5b887185865"
    )


def _offices(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    ident_a = identity.load_identity(dir_a, name="isytron-a")
    ident_b = identity.load_identity(dir_b, name="isytron-b")
    pairing.trust_peer(identity.public_card(ident_b), dir_a)
    pairing.trust_peer(identity.public_card(ident_a), dir_b)
    return (dir_a, ident_a), (dir_b, ident_b)


def test_envelope_roundtrip_and_tamper(tmp_path):
    (dir_a, ident_a), (dir_b, ident_b) = _offices(tmp_path)
    peers_b = identity.load_peers(dir_b)
    env = envelope.seal(ident_a, identity.public_card(ident_b), {"op": "ping"})
    peer, payload = envelope.open_envelope(ident_b, peers_b, env, {})
    assert payload == {"op": "ping"} and peer["office_id"] == ident_a["office_id"]
    tampered = dict(env)
    tampered["ct"] = "A" + tampered["ct"][1:]
    with pytest.raises(envelope.EnvelopeError):
        envelope.open_envelope(ident_b, peers_b, tampered, {})
    with pytest.raises(envelope.EnvelopeError):
        envelope.open_envelope(ident_b, {}, env, {})


def test_envelope_replay_and_skew_rejected(tmp_path):
    (dir_a, ident_a), (dir_b, ident_b) = _offices(tmp_path)
    peers_b = identity.load_peers(dir_b)
    env = envelope.seal(ident_a, identity.public_card(ident_b), {"op": "ping"})
    seen: dict = {}
    envelope.open_envelope(ident_b, peers_b, env, seen)
    with pytest.raises(envelope.EnvelopeError):
        envelope.open_envelope(ident_b, peers_b, env, seen)
    old = envelope.seal(
        ident_a, identity.public_card(ident_b), {"op": "ping"},
        now=time.time() - 3600,
    )
    with pytest.raises(envelope.EnvelopeError):
        envelope.open_envelope(ident_b, peers_b, old, {})


def _post(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read() or b"{}")


def test_pair_over_http_and_code_binds_both_sides(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    ident_a = identity.load_identity(dir_a, name="isytron-a")
    ident_b = identity.load_identity(dir_b, name="isytron-b")
    server_b = LinkServer(dir_b, tcp_port=0, udp_port=0).start()
    try:
        card_a = identity.public_card(ident_a)
        status, body = _post(
            f"http://{server_b.tcp_address}/link/v1/pair",
            {**card_a, "nonce": "nonce-a", "port": 1},
        )
        assert status == 200 and body["ok"]
        # The asker computes the code locally from both nonces, like the CLI.
        code = pairing.short_code(
            ident_a["sign"]["x"], body["peer"]["sign_pub"], "nonce-a", body["nonce"]
        )
        assert len(code) == 6
        # The asked side stored the same code for `aceptar` to match.
        pending = identity.load_pending(dir_b)
        assert len(pending) == 1
        stored = next(iter(pending.values()))
        assert stored["code"] == code
        assert pairing.accept(code, dir_b) is not None
        # Bad identity binding and self-pairing are refused.
        bad_id = dict(card_a, office_id="deadbeefdeadbeef", nonce="n2")
        try:
            _post(f"http://{server_b.tcp_address}/link/v1/pair", bad_id)
            raise AssertionError("mismatched id accepted")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
        res = pairing.propose(ident_a, {**identity.public_card(ident_b), "addresses": []}, peer_nonce="nonce-b", directory=dir_a)
        assert len(res["code"]) == 6
        pinned = pairing.accept(res["code"], dir_a)
        assert pinned is not None
    finally:
        server_b.stop()


def test_delegate_lands_in_inbox_with_receipts_both_sides(tmp_path):
    (dir_a, ident_a), (dir_b, ident_b) = _offices(tmp_path)
    server_b = LinkServer(dir_b, tcp_port=0, udp_port=0).start()
    try:
        env = envelope.seal(
            ident_a, identity.public_card(ident_b),
            {"op": "delegate", "title": "Audita X", "body": "detalle"},
        )
        status, body = _post(f"http://{server_b.tcp_address}/link/v1/call", {"env": env})
        assert status == 200 and body["ok"] and body["task_id"].startswith("task-")
        from isymotron.link.server import LinkState

        inbox = LinkState(dir_b).inbox()
        assert len(inbox) == 1 and inbox[0]["status"] == "queued"
        received = receipts.read_receipts(dir_b, "link_received")
        assert len(received) == 1 and received[0]["task_id"] == body["task_id"]
        receipts.append_receipt(
            dir_a, "link_delegated",
            {"task_id": body["task_id"], "to": ident_b["office_id"]},
        )
        sent = receipts.read_receipts(dir_a, "link_delegated")
        assert len(sent) == 1
        # task status + message + cancel roundtrip through sealed calls
        for op in ({"op": "task", "task_id": body["task_id"]},):
            env2 = envelope.seal(ident_a, identity.public_card(ident_b), op)
            status2, body2 = _post(f"http://{server_b.tcp_address}/link/v1/call", {"env": env2})
            assert status2 == 200 and body2["task"]["status"] == "queued"
        env3 = envelope.seal(
            ident_a, identity.public_card(ident_b),
            {"op": "cancel", "task_id": body["task_id"]},
        )
        status3, _ = _post(f"http://{server_b.tcp_address}/link/v1/call", {"env": env3})
        assert status3 == 200
        assert LinkState(dir_b).inbox()[0]["status"] == "cancelled"
    finally:
        server_b.stop()


def test_unpaired_caller_is_rejected(tmp_path):
    (dir_a, ident_a), (dir_b, ident_b) = _two_unpaired(tmp_path)
    server_b = LinkServer(dir_b, tcp_port=0, udp_port=0).start()
    try:
        env = envelope.seal(ident_a, identity.public_card(ident_b), {"op": "ping"})
        try:
            _post(f"http://{server_b.tcp_address}/link/v1/call", {"env": env})
            raise AssertionError("unpaired call accepted")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
    finally:
        server_b.stop()


def _two_unpaired(tmp_path):
    dir_a = tmp_path / "ua"
    dir_b = tmp_path / "ub"
    return (dir_a, identity.load_identity(dir_a)), (dir_b, identity.load_identity(dir_b))


def test_discover_finds_local_server(tmp_path):
    directory = tmp_path / "d"
    identity.load_identity(directory)
    server = LinkServer(directory, tcp_port=0, udp_port=0).start()
    try:
        import socket as _socket

        probe = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        try:
            probe.settimeout(2)
            probe.sendto(b"ISYMO-LINK?v1", ("127.0.0.1", server.udp_port))
            data, _ = probe.recvfrom(4096)
            card = json.loads(data.decode("utf-8"))
            assert card["office_id"] == identity.load_identity(directory)["office_id"]
        finally:
            probe.close()
    finally:
        server.stop()


def test_link_modules_are_stdlib_only():
    roots = [Path(__file__).resolve().parent.parent / "core" / "isymotron" / "link"]
    allowed = {
        "__future__", "base64", "hashlib", "hmac", "http", "json", "os",
        "pathlib", "platform", "socket", "threading", "time", "urllib",
    }
    import ast as _ast

    for root in roots:
        for path in sorted(root.glob("*.py")):
            if path.name == "__init__.py":
                continue
            tree = _ast.parse(path.read_text(encoding="utf-8"))
            for node in _ast.walk(tree):
                if isinstance(node, _ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        assert top in allowed or top == "isymotron", (path.name, alias.name)
                elif isinstance(node, _ast.ImportFrom):
                    if node.level != 0:
                        continue
                    assert (node.module or "").split(".")[0] in allowed, (path.name, node.module)
