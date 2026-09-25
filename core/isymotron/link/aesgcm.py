"""AES-128 + GCM + HKDF-SHA256. Stdlib only (no cipher in stdlib).

Why hand-rolled: the shipped executable must stay self-contained
(same doctrine as seal.py and link/curve.py) and the Dockerfile test
image carries no third-party crypto. Correctness is falsifiable, not
asserted: tests/test_link_server.py carries vectors confirmed against
the `cryptography` package (OpenSSL bindings) on 2026-09-25, and the
stdlib-only AST gate covers this module too.

Scope: 128-bit keys, 96-bit IVs, the link-envelope use case. Not a
general crypto library — do not grow it into one.
"""

from __future__ import annotations

import hashlib
import hmac
import os

_SBOX = (
    0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76,
    0xCA, 0x82, 0xC9, 0x7D, 0xFA, 0x59, 0x47, 0xF0, 0xAD, 0xD4, 0xA2, 0xAF, 0x9C, 0xA4, 0x72, 0xC0,
    0xB7, 0xFD, 0x93, 0x26, 0x36, 0x3F, 0xF7, 0xCC, 0x34, 0xA5, 0xE5, 0xF1, 0x71, 0xD8, 0x31, 0x15,
    0x04, 0xC7, 0x23, 0xC3, 0x18, 0x96, 0x05, 0x9A, 0x07, 0x12, 0x80, 0xE2, 0xEB, 0x27, 0xB2, 0x75,
    0x09, 0x83, 0x2C, 0x1A, 0x1B, 0x6E, 0x5A, 0xA0, 0x52, 0x3B, 0xD6, 0xB3, 0x29, 0xE3, 0x2F, 0x84,
    0x53, 0xD1, 0x00, 0xED, 0x20, 0xFC, 0xB1, 0x5B, 0x6A, 0xCB, 0xBE, 0x39, 0x4A, 0x4C, 0x58, 0xCF,
    0xD0, 0xEF, 0xAA, 0xFB, 0x43, 0x4D, 0x33, 0x85, 0x45, 0xF9, 0x02, 0x7F, 0x50, 0x3C, 0x9F, 0xA8,
    0x51, 0xA3, 0x40, 0x8F, 0x92, 0x9D, 0x38, 0xF5, 0xBC, 0xB6, 0xDA, 0x21, 0x10, 0xFF, 0xF3, 0xD2,
    0xCD, 0x0C, 0x13, 0xEC, 0x5F, 0x97, 0x44, 0x17, 0xC4, 0xA7, 0x7E, 0x3D, 0x64, 0x5D, 0x19, 0x73,
    0x60, 0x81, 0x4F, 0xDC, 0x22, 0x2A, 0x90, 0x88, 0x46, 0xEE, 0xB8, 0x14, 0xDE, 0x5E, 0x0B, 0xDB,
    0xE0, 0x32, 0x3A, 0x0A, 0x49, 0x06, 0x24, 0x5C, 0xC2, 0xD3, 0xAC, 0x62, 0x91, 0x95, 0xE4, 0x79,
    0xE7, 0xC8, 0x37, 0x6D, 0x8D, 0xD5, 0x4E, 0xA9, 0x6C, 0x56, 0xF4, 0xEA, 0x65, 0x7A, 0xAE, 0x08,
    0xBA, 0x78, 0x25, 0x2E, 0x1C, 0xA6, 0xB4, 0xC6, 0xE8, 0xDD, 0x74, 0x1F, 0x4B, 0xBD, 0x8B, 0x8A,
    0x70, 0x3E, 0xB5, 0x66, 0x48, 0x03, 0xF6, 0x0E, 0x61, 0x35, 0x57, 0xB9, 0x86, 0xC1, 0x1D, 0x9E,
    0xE1, 0xF8, 0x98, 0x11, 0x69, 0xD9, 0x8E, 0x94, 0x9B, 0x1E, 0x87, 0xE9, 0xCE, 0x55, 0x28, 0xDF,
    0x8C, 0xA1, 0x89, 0x0D, 0xBF, 0xE6, 0x42, 0x68, 0x41, 0x99, 0x2D, 0x0F, 0xB0, 0x54, 0xBB, 0x16,
)

_RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


def _expand_key(key: bytes) -> list[list[int]]:
    words = [list(key[i : i + 4]) for i in range(0, 16, 4)]
    for i in range(4, 44):
        temp = words[i - 1][:]
        if i % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [_SBOX[b] for b in temp]
            temp[0] ^= _RCON[i // 4 - 1]
        words.append([(a ^ b) & 0xFF for a, b in zip(words[i - 4], temp)])
    return [words[4 * r : 4 * r + 4] for r in range(11)]


def _add_round_key(state: list[int], schedule: list[list[int]], rnd: int) -> list[int]:
    key = [b for word in schedule[rnd] for b in word]
    return [(s ^ k) & 0xFF for s, k in zip(state, key)]


def _xtime(value: int) -> int:
    return ((value << 1) ^ 0x11B) & 0xFF if value & 0x80 else (value << 1) & 0xFF


def _mix_column(col: list[int]) -> list[int]:
    a = col[:]
    return [
        (_xtime(a[0]) ^ (a[1] ^ _xtime(a[1])) ^ a[2] ^ a[3]) & 0xFF,
        (a[0] ^ _xtime(a[1]) ^ (a[2] ^ _xtime(a[2])) ^ a[3]) & 0xFF,
        (a[0] ^ a[1] ^ _xtime(a[2]) ^ (a[3] ^ _xtime(a[3]))) & 0xFF,
        ((a[0] ^ _xtime(a[0])) ^ a[1] ^ a[2] ^ _xtime(a[3])) & 0xFF,
    ]


def aes128_block(key: bytes, block16: bytes) -> bytes:
    """One raw AES-128 encryption (no mode). FIPS-197 Appendix B checked."""
    if len(key) != 16 or len(block16) != 16:
        raise ValueError("AES-128 needs 16-byte key and block")
    schedule = _expand_key(key)
    state = _add_round_key(list(block16), schedule, 0)
    for rnd in range(1, 10):
        state = [_SBOX[b] for b in state]
        state = [
            state[0], state[5], state[10], state[15],
            state[4], state[9], state[14], state[3],
            state[8], state[13], state[2], state[7],
            state[12], state[1], state[6], state[11],
        ]
        for col in range(4):
            mixed = _mix_column(state[4 * col : 4 * col + 4])
            state[4 * col : 4 * col + 4] = mixed
        state = _add_round_key(state, schedule, rnd)
    state = [_SBOX[b] for b in state]
    state = [
        state[0], state[5], state[10], state[15],
        state[4], state[9], state[14], state[3],
        state[8], state[13], state[2], state[7],
        state[12], state[1], state[6], state[11],
    ]
    return bytes(_add_round_key(state, schedule, 10))


def _gf_mult(x: int, y: int) -> int:
    """NIST SP 800-38D Algorithm 1: X por MSB, V desplazado a la derecha."""
    reduce = 0xE1000000000000000000000000000000
    result, running = 0, y
    for bit in range(127, -1, -1):
        if (x >> bit) & 1:
            result ^= running
        low = running & 1
        running >>= 1
        if low:
            running ^= reduce
    return result


def _ghash(subkey: int, aad: bytes, ciphertext: bytes) -> int:
    data = aad + b"\x00" * (-len(aad) % 16)
    data += ciphertext + b"\x00" * (-len(ciphertext) % 16)
    data += (len(aad) * 8).to_bytes(8, "big") + (len(ciphertext) * 8).to_bytes(8, "big")
    state = 0
    for offset in range(0, len(data), 16):
        state = _gf_mult(state ^ int.from_bytes(data[offset : offset + 16], "big"), subkey)
    return state


def gcm_encrypt(key: bytes, iv12: bytes, plaintext: bytes, aad: bytes = b"") -> tuple[bytes, bytes]:
    """Return (ciphertext, tag16). 96-bit IVs only (the link use case)."""
    if len(key) != 16 or len(iv12) != 12:
        raise ValueError("GCM here needs a 16-byte key and 12-byte IV")
    subkey = int.from_bytes(aes128_block(key, b"\x00" * 16), "big")
    counter = int.from_bytes(iv12 + b"\x00\x00\x00\x01", "big")
    keystream = b""
    while len(keystream) < len(plaintext):
        counter += 1
        keystream += aes128_block(key, counter.to_bytes(16, "big"))
    ciphertext = bytes(p ^ k for p, k in zip(plaintext, keystream))
    tag_full = (
        _ghash(subkey, aad, ciphertext)
        ^ int.from_bytes(aes128_block(key, iv12 + b"\x00\x00\x00\x01"), "big")
    )
    return (ciphertext, tag_full.to_bytes(16, "big"))


def gcm_decrypt(key: bytes, iv12: bytes, ciphertext: bytes, tag16: bytes, aad: bytes = b"") -> bytes:
    """Return plaintext or raise ValueError (auth failure is not data)."""
    if len(tag16) != 16:
        raise ValueError("GCM tag must be 16 bytes")
    subkey = int.from_bytes(aes128_block(key, b"\x00" * 16), "big")
    expected = (
        _ghash(subkey, aad, ciphertext)
        ^ int.from_bytes(aes128_block(key, iv12 + b"\x00\x00\x00\x01"), "big")
    ).to_bytes(16, "big")
    if not hmac.compare_digest(expected, tag16):
        raise ValueError("GCM authentication failed")
    counter = int.from_bytes(iv12 + b"\x00\x00\x00\x01", "big")
    keystream = b""
    while len(keystream) < len(ciphertext):
        counter += 1
        keystream += aes128_block(key, counter.to_bytes(16, "big"))
    return bytes(c ^ k for c, k in zip(ciphertext, keystream))


def hkdf_sha256(secret: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    """RFC 5869 extract+expand (SHA-256)."""
    if not salt:
        salt = b"\x00" * 32
    pseudo = hmac.new(salt, secret, hashlib.sha256).digest()
    output, block, counter = b"", b"", 1
    while len(output) < length:
        block = hmac.new(pseudo, block + info + bytes([counter]), hashlib.sha256).digest()
        output += block
        counter += 1
    return output[:length]


def random_iv12() -> bytes:
    return os.urandom(12)
