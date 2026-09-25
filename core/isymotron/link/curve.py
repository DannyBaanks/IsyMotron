"""Pure-python Ed25519 + X25519. Stdlib only (hashlib, os).

No third-party dependency on purpose: the shipped executable stays
self-contained (same doctrine as core/isymotron/seal.py).

Correctness is falsifiable, not asserted: tests/test_link_identity.py
checks this module against RFC 8032 section 7 vectors (Ed25519) and
RFC 7748 section 6.1 vectors (X25519). If those fail, this module is
wrong — fix it, do not relax the vectors.
"""

from __future__ import annotations

import hashlib
import os

# ---------------------------------------------------------------- Ed25519

_Q = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493


def _inv(value: int) -> int:
    return pow(value, _Q - 2, _Q)


_D = (-121665 * _inv(121666)) % _Q
_SQRT_M1 = pow(2, (_Q - 1) // 4, _Q)


def _edwards_add(p1: tuple[int, int, int, int], p2: tuple[int, int, int, int]):
    """Complete addition (Hisilop-Wong-Carter-Dawson), works for doubling."""
    x1, y1, t1, z1 = p1
    x2, y2, t2, z2 = p2
    a = ((y1 - x1) * (y2 - x2)) % _Q
    b = ((y1 + x1) * (y2 + x2)) % _Q
    c = (t1 * 2 * _D * t2) % _Q
    d = (z1 * 2 * z2) % _Q
    e = (b - a) % _Q
    f = (d - c) % _Q
    g = (d + c) % _Q
    h = (b + a) % _Q
    return ((e * f) % _Q, (g * h) % _Q, (e * h) % _Q, (f * g) % _Q)


def _edwards_mult(point: tuple[int, int, int, int], scalar: int):
    result = (0, 1, 0, 1)
    addend = point
    while scalar > 0:
        if scalar & 1:
            result = _edwards_add(result, addend)
        addend = _edwards_add(addend, addend)
        scalar >>= 1
    return result


def _decode_point(data: bytes) -> tuple[int, int, int, int] | None:
    if len(data) != 32:
        return None
    bits = int.from_bytes(data, "little")
    sign = (bits >> 255) & 1
    y = bits & ((1 << 255) - 1)
    if y >= _Q:
        return None
    x2 = ((y * y - 1) * _inv((_D * y * y + 1) % _Q)) % _Q
    x = pow(x2, (_Q + 3) // 8, _Q)
    if (x * x - x2) % _Q != 0:
        x = (x * _SQRT_M1) % _Q
    if (x * x - x2) % _Q != 0:
        return None
    if (x & 1) != sign:
        x = _Q - x
    return (x, y, (x * y) % _Q, 1)


def _encode_point(point: tuple[int, int, int, int]) -> bytes:
    x, y, _, z = point
    inv_z = _inv(z)
    x = (x * inv_z) % _Q
    y = (y * inv_z) % _Q
    bits = (y & ((1 << 255) - 1)) | ((x & 1) << 255)
    return bits.to_bytes(32, "little")


_BASE_BYTES = bytes.fromhex(
    "5866666666666666666666666666666666666666666666666666666666666666"
)
_BASE = _decode_point(_BASE_BYTES)
assert _BASE is not None


def _clamp(digest32: bytes) -> int:
    value = bytearray(digest32)
    value[0] &= 248
    value[31] &= 63
    value[31] |= 64
    return int.from_bytes(bytes(value), "little")


def ed25519_keygen(seed: bytes | None = None) -> tuple[bytes, bytes]:
    """Return (private_seed_32, public_key_32)."""
    seed = seed if seed is not None else os.urandom(32)
    if len(seed) != 32:
        raise ValueError("Ed25519 seed must be 32 bytes")
    hashed = hashlib.sha512(seed).digest()
    secret = _clamp(hashed[:32])
    public = _encode_point(_edwards_mult(_BASE, secret))
    return (seed, public)


def ed25519_sign(seed: bytes, message: bytes) -> bytes:
    hashed = hashlib.sha512(seed).digest()
    secret, prefix = _clamp(hashed[:32]), hashed[32:]
    nonce = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _L
    commitment = _encode_point(_edwards_mult(_BASE, nonce))
    public = _encode_point(_edwards_mult(_BASE, secret))
    challenge = (
        int.from_bytes(hashlib.sha512(commitment + public + message).digest(), "little")
        % _L
    )
    scalar = (nonce + challenge * secret) % _L
    return commitment + scalar.to_bytes(32, "little")


def ed25519_verify(public: bytes, message: bytes, signature: bytes) -> bool:
    if len(signature) != 64 or len(public) != 32:
        return False
    commitment, scalar_bytes = signature[:32], signature[32:]
    scalar = int.from_bytes(scalar_bytes, "little")
    if scalar >= _L:
        return False
    point_r = _decode_point(commitment)
    point_a = _decode_point(public)
    if point_r is None or point_a is None:
        return False
    challenge = (
        int.from_bytes(hashlib.sha512(commitment + public + message).digest(), "little")
        % _L
    )
    left = _edwards_mult(_BASE, scalar)
    right = _edwards_add(point_r, _edwards_mult(point_a, challenge))
    return _encode_point(left) == _encode_point(right)


# ---------------------------------------------------------------- X25519


def _x25519_clamp(digest32: bytes) -> int:
    value = bytearray(digest32)
    value[0] &= 248
    value[31] &= 127
    value[31] |= 64
    return int.from_bytes(bytes(value), "little")


def _x25519_ladder(scalar: int, point_u: int) -> int:
    x1, x2, z2, x3, z3 = point_u, 1, 0, point_u, 1
    swap = 0
    for bit in range(254, -1, -1):
        bit_choice = (scalar >> bit) & 1
        swap ^= bit_choice
        if swap:
            x2, x3 = x3, x2
            z2, z3 = z3, z2
        swap = bit_choice
        a = (x2 + z2) % _Q
        aa = (a * a) % _Q
        b = (x2 - z2) % _Q
        bb = (b * b) % _Q
        e = (aa - bb) % _Q
        c = (x3 + z3) % _Q
        d = (x3 - z3) % _Q
        da = (d * a) % _Q
        cb = (c * b) % _Q
        x3 = ((da + cb) % _Q) ** 2 % _Q
        z3 = (x1 * (((da - cb) % _Q) ** 2 % _Q)) % _Q
        x2 = (aa * bb) % _Q
        z2 = (e * ((aa + 121665 * e) % _Q)) % _Q
    if swap:
        x2, x3 = x3, x2
        z2, z3 = z3, z2
    return (x2 * _inv(z2)) % _Q


def x25519_keygen() -> tuple[bytes, bytes]:
    """Return (private_32, public_32)."""
    private = os.urandom(32)
    public = _x25519_ladder(_x25519_clamp(private), 9).to_bytes(32, "little")
    return (private, public)


def x25519_shared(private: bytes, peer_public: bytes) -> bytes:
    """Diffie-Hellman shared secret (32 bytes)."""
    if len(private) != 32 or len(peer_public) != 32:
        raise ValueError("X25519 keys must be 32 bytes")
    peer_u = int.from_bytes(peer_public, "little")
    return _x25519_ladder(_x25519_clamp(private), peer_u).to_bytes(32, "little")
