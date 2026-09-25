"""M1: link identity + pairing. No network, tempdirs only.

Curve vectors below are cross-checked against OpenSSL 3.0 (independent
implementation) on 2026-09-25: openssl-derived pubkey/signature for the
fixed seed, X25519 shared secret both directions. Triple agreement was
observed (openssl->mine verify, mine->openssl verify, byte-identical
deterministic signatures). Hand-transcribed RFC strings are deliberately
NOT used: a 31-byte typo once failed here and blamed the code.
"""
import ast
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))

from isymotron.link import curve, identity, pairing

SEED = bytes.fromhex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
OPENSSL_PUB = bytes.fromhex(
    "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8"
)
# Deterministic RFC 8032 signature of b"hola" under SEED, byte-identical
# between this module and `openssl pkeyutl -sign` (verified both ways).
OPENSSL_SIG = bytes.fromhex(
    "cc1de3c7a09ba81951b32a5c55048654e50e4c033ada9394afd6d889695ca6b"
    "de4a32a4df9828141a75379c44393e62062706b2f91f45b5270a786cf4af9ca0f"
)
OPENSSL_MSG = b"hola"


def test_ed25519_matches_openssl_vector():
    _, pub = curve.ed25519_keygen(SEED)
    assert pub == OPENSSL_PUB
    assert curve.ed25519_verify(OPENSSL_PUB, OPENSSL_MSG, OPENSSL_SIG)


def test_ed25519_keygen_matches_openssl():
    _, pub = curve.ed25519_keygen(SEED)
    assert pub == OPENSSL_PUB


def test_ed25519_sign_verify_roundtrip():
    _, pub = curve.ed25519_keygen(SEED)
    sig = curve.ed25519_sign(SEED, b"m1")
    assert curve.ed25519_verify(pub, b"m1", sig)
    assert not curve.ed25519_verify(pub, b"m2", sig)
    bad = bytearray(sig)
    bad[0] ^= 1
    assert not curve.ed25519_verify(pub, b"m1", bytes(bad))


def test_ed25519_rejects_garbage():
    _, pub = curve.ed25519_keygen(SEED)
    assert not curve.ed25519_verify(pub, b"m1", b"\x00" * 64)
    assert not curve.ed25519_verify(b"\x00" * 32, b"m1", curve.ed25519_sign(SEED, b"m1"))


def test_x25519_shared_is_symmetric():
    a_priv, a_pub = curve.x25519_keygen()
    b_priv, b_pub = curve.x25519_keygen()
    assert curve.x25519_shared(a_priv, b_pub) == curve.x25519_shared(b_priv, a_pub)


def test_x25519_matches_openssl_vector():
    # Fixed keys; shared secret confirmed byte-identical via
    # `openssl pkeyutl -derive` on 2026-09-25.
    a_priv = bytes.fromhex("11" * 32)
    b_pub = bytes.fromhex(
        "0faa684ed28867b97f4a6a2dee5df8ce974e76b7018e3f22a1c4cf2678570f20"
    )
    assert curve.x25519_shared(a_priv, b_pub).hex() == (
        "9e004098efc091d4ec2663b4e9f5cfd4d7064571690b4bea97ab146ab9f35056"
    )


def test_office_id_is_key_fingerprint():
    _, pub = curve.ed25519_keygen(SEED)
    office = identity.office_id_of(pub)
    assert len(office) == 16 and all(c in "0123456789abcdef" for c in office)
    assert identity.pretty_fingerprint(office) == " ".join(
        office[i : i + 4] for i in range(0, 16, 4)
    )


def _two_offices(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    ident_a = identity.load_identity(dir_a, name="isytron-a")
    ident_b = identity.load_identity(dir_b, name="isytron-b")
    return (dir_a, ident_a), (dir_b, ident_b)


def test_identity_created_once_private(tmp_path):
    directory = tmp_path / "link"
    first = identity.load_identity(directory)
    second = identity.load_identity(directory)
    assert first["office_id"] == second["office_id"]
    mode = os.stat(directory / "identity.json").st_mode & 0o777
    if os.name != "nt":
        assert mode == 0o600
    assert "d" not in identity.public_card(first)


def test_pairing_happy_path_and_wrong_code_rejected(tmp_path):
    (dir_a, ident_a), (dir_b, ident_b) = _two_offices(tmp_path)
    card_b = identity.public_card(ident_b)
    result = pairing.propose(ident_a, card_b, peer_nonce="nonce-b", directory=dir_a)
    assert len(result["code"]) == 6 and result["code"].isdigit()
    assert pairing.accept("000000", dir_a) is None
    pinned = pairing.accept(result["code"], dir_a)
    assert pinned is not None and pinned["office_id"] == ident_b["office_id"]
    assert pairing.accept(result["code"], dir_a) is None


def test_pairing_code_is_order_independent_and_binding(tmp_path):
    (dir_a, ident_a), (_dir_b, ident_b) = _two_offices(tmp_path)
    code_ab = pairing.short_code(
        ident_a["sign"]["x"], ident_b["sign"]["x"], "n1", "n2"
    )
    code_ba = pairing.short_code(
        ident_b["sign"]["x"], ident_a["sign"]["x"], "n2", "n1"
    )
    assert code_ab == code_ba
    other = pairing.short_code(
        ident_a["sign"]["x"], ident_b["sign"]["x"], "n1", "OTHER"
    )
    assert other != code_ab


def test_expired_pending_is_pruned(tmp_path):
    (dir_a, ident_a), (_dir_b, ident_b) = _two_offices(tmp_path)
    result = pairing.propose(
        ident_a, identity.public_card(ident_b), peer_nonce="n", directory=dir_a
    )
    pending = identity.load_pending(dir_a)
    key = next(iter(pending))
    pending[key]["expires_at"] = 0
    identity.save_pending(pending, dir_a)
    assert pairing.accept(result["code"], dir_a) is None


def test_repair_keeps_first_paired_at_and_forget(tmp_path):
    (dir_a, ident_a), (_dir_b, ident_b) = _two_offices(tmp_path)
    card = identity.public_card(ident_b)
    first = pairing.accept(
        pairing.propose(ident_a, card, peer_nonce="n", directory=dir_a)["code"],
        dir_a,
    )
    second = pairing.accept(
        pairing.propose(ident_a, card, peer_nonce="n2", directory=dir_a)["code"],
        dir_a,
    )
    assert first is not None and second is not None
    assert second["paired_at"] == first["paired_at"]
    assert pairing.find_peer("isytron-b", identity.load_peers(dir_a)) is not None
    assert pairing.find_peer("b", identity.load_peers(dir_a)) is not None
    assert pairing.find_peer("nope", identity.load_peers(dir_a)) is None
    assert pairing.forget("isytron-b", dir_a) is not None
    assert pairing.find_peer("isytron-b", identity.load_peers(dir_a)) is None


def test_link_modules_are_stdlib_only():
    roots = [
        Path(__file__).resolve().parent.parent / "core" / "isymotron" / "link",
    ]
    allowed_first = {
        "__future__", "base64", "hashlib", "json", "os", "pathlib", "platform",
        "socket", "time",
    }
    for root in roots:
        for path in sorted(root.glob("*.py")):
            if path.name == "__init__.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        assert top in allowed_first or top == "isymotron", (
                            path.name,
                            alias.name,
                        )
                elif isinstance(node, ast.ImportFrom):
                    if node.level != 0:
                        continue
                    assert (node.module or "").split(".")[0] in allowed_first, (
                        path.name,
                        node.module,
                    )


def test_max_pending_is_bounded(tmp_path):
    directory = tmp_path / "link"
    ident = identity.load_identity(directory, name="isytron-a")
    for index in range(pairing.MAX_PENDING):
        card = {"office_id": f"peer{index:02d}", "name": f"p{index}",
                "sign_pub": f"s{index}", "box_pub": f"b{index}"}
        pairing.propose(ident, card, peer_nonce="n", directory=directory)
    with pytest.raises(ValueError):
        pairing.propose(
            ident,
            {"office_id": "toomany", "name": "x", "sign_pub": "s", "box_pub": "b"},
            peer_nonce="n",
            directory=directory,
        )
