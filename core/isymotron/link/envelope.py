"""Sealed envelopes: X25519 DH -> HKDF -> AES-128-GCM + Ed25519 signature.

Mirror of Munder Link seal/open (lib-link.cjs), adapted: AES-128-GCM
(see link/aesgcm.py doctrine), protocol string isymotron-link@1,
HKDF info "... seal" with 16-byte output.

Wire shape (JSON, b64u fields) mirrors Munder so a future bridge can
read both: {v, from, to, ts, nonce, iv, ct, sig} with sig over
"v|from|to|ts|nonce|iv|ct".

Anti-replay lives here as pure checks (skew + unseen nonce set passed
in by the server); transport lives in link/server.py (M2 scope: this
module has no sockets).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time

from . import aesgcm, curve, identity

PROTOCOL = identity.PROTOCOL
MAX_SKEW_S = 120
NONCE_TTL_S = 600
MAX_BODY_BYTES = 256 * 1024


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def shared_key(own_office_id: str, own_box_priv: bytes, peer_box_pub: bytes, peer_office_id: str) -> bytes:
    secret = curve.x25519_shared(own_box_priv, peer_box_pub)
    salt = "|".join(sorted([own_office_id, peer_office_id])).encode("utf-8")
    return aesgcm.hkdf_sha256(secret, salt, f"{PROTOCOL} seal".encode("utf-8"), 16)


def _signed_text(env: dict) -> bytes:
    return "|".join(
        str(env[field]) for field in ("v", "from", "to", "ts", "nonce", "iv", "ct")
    ).encode("utf-8")


def seal(own_identity: dict, peer_card: dict, payload: dict, now: float | None = None) -> dict:
    key = shared_key(
        own_identity["office_id"],
        _unb64(own_identity["box"]["d"]),
        _unb64(str(peer_card["box_pub"])),
        str(peer_card["office_id"]),
    )
    iv = os.urandom(12)
    aad = f"{own_identity['office_id']}>{peer_card['office_id']}".encode("utf-8")
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ct, tag = aesgcm.gcm_encrypt(key, iv, body, aad)
    env = {
        "v": 1,
        "from": own_identity["office_id"],
        "to": str(peer_card["office_id"]),
        "ts": int((now if now is not None else time.time()) * 1000),
        "nonce": _b64(os.urandom(16)),
        "iv": _b64(iv),
        "ct": _b64(ct + tag),
    }
    env["sig"] = _b64(
        _sign_raw(_unb64(own_identity["sign"]["d"]), _signed_text(env))
    )
    return env


def _sign_raw(seed32: bytes, message: bytes) -> bytes:
    return curve.ed25519_sign(seed32, message)


def open_envelope(
    own_identity: dict,
    peers: dict,
    env: dict,
    seen_nonces: dict,
    now: float | None = None,
) -> tuple[dict, dict]:
    """Return (peer, payload) or raise EnvelopeError. Fail-closed, always."""
    moment = now if now is not None else time.time()
    for field in ("v", "from", "to", "ts", "nonce", "iv", "ct", "sig"):
        if field not in env:
            raise EnvelopeError(f"missing field {field}")
    if env["v"] != 1:
        raise EnvelopeError(f"unsupported envelope v{env['v']}")
    peer = peers.get(str(env["from"]))
    if peer is None:
        raise EnvelopeError("unknown office (not paired)")
    if str(env["to"]) != own_identity["office_id"]:
        raise EnvelopeError("envelope not addressed to us")
    try:
        sign_pub = _unb64(str(peer["sign_pub"]))
        signature = _unb64(str(env["sig"]))
    except Exception as exc:
        raise EnvelopeError(f"bad encoding: {exc}") from exc
    if not curve.ed25519_verify(sign_pub, _signed_text(env), signature):
        raise EnvelopeError("bad signature")
    skew = abs(moment - int(env["ts"]) / 1000)
    if skew > MAX_SKEW_S:
        raise EnvelopeError("envelope outside time window")
    nonce = str(env["nonce"])
    expiry = seen_nonces.get(nonce)
    if expiry is not None and expiry > moment:
        raise EnvelopeError("nonce replay")
    seen_nonces[nonce] = moment + NONCE_TTL_S
    key = shared_key(
        own_identity["office_id"],
        _unb64(own_identity["box"]["d"]),
        _unb64(str(peer["box_pub"])),
        str(peer["office_id"]),
    )
    try:
        raw_ct = _unb64(str(env["ct"]))
        iv = _unb64(str(env["iv"]))
        aad = f"{peer['office_id']}>{own_identity['office_id']}".encode("utf-8")
        body = aesgcm.gcm_decrypt(key, iv, raw_ct[:-16], raw_ct[-16:], aad)
        payload = json.loads(body.decode("utf-8"))
    except EnvelopeError:
        raise
    except Exception as exc:
        raise EnvelopeError(f"cannot open: {type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise EnvelopeError("payload must be an object")
    return (peer, payload)


class EnvelopeError(Exception):
    """Any envelope problem. The caller answers 4xx, never trust."""


def digest_public_card_fingerprint(sign_pub_b64u: str) -> str:
    raw = _unb64(sign_pub_b64u)
    return hashlib.sha256(raw).hexdigest()[:16]
