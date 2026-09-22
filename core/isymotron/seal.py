"""Receipt sealing (Quine Gate, milestone M3).

Two schemes, both honest about what they are:

- ``unkeyed``    -- ``sha256(canonical(payload))``. Integrity only. It proves
  the bytes have not changed *since some hash was computed*; it carries no
  authority, because anyone can recompute it. This is the legacy v0 scheme and
  is kept for already-emitted receipts.
- ``hmac-sha256`` -- HMAC over the canonical payload with a secret key. A party
  without the key cannot forge or verify. A party *with* the key can do both:
  this is integrity, not non-repudiation. Public provenance is a different
  property, supplied outside the artifact (CI build attestation), not by this
  module.

The key never lives in the artifact. It is resolved from the
``ISYMOTRON_RECEIPT_KEY`` environment variable or passed explicitly. No
third-party dependency: ``hmac`` and ``hashlib`` are in the standard library,
which keeps the shipped executable self-contained.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

from .canon import canonical, digest

UNKEYED = "unkeyed"
HMAC_SHA256 = "hmac-sha256"
SUPPORTED_KINDS = (UNKEYED, HMAC_SHA256)
_HMAC_PREFIX = "hmac-sha256:"

KEY_ENV = "ISYMOTRON_RECEIPT_KEY"


class SealError(Exception):
    """A seal could not be produced or checked."""


class MissingKey(SealError):
    """An HMAC receipt was asked for without a key."""


class UnsupportedSealKind(SealError):
    """An unknown scheme was requested; fail closed, never fall back."""


def resolve_key(explicit: str | None = None) -> str | None:
    """Explicit key wins; otherwise the environment. Never read from a file in
    the artifact, and never default to a constant."""
    if explicit is not None:
        return explicit
    value = os.environ.get(KEY_ENV)
    return value or None


def seal_payload(payload: Any, *, kind: str = UNKEYED,
                 key: str | None = None) -> str:
    """Produce the seal string for a payload under the requested scheme."""
    if kind == UNKEYED:
        return digest(payload)
    if kind == HMAC_SHA256:
        secret = resolve_key(key)
        if not secret:
            raise MissingKey(
                f"{HMAC_SHA256} requires a key ({KEY_ENV} or explicit)"
            )
        mac = hmac.new(secret.encode("utf-8"),
                       canonical(payload).encode("utf-8"),
                       hashlib.sha256)
        return _HMAC_PREFIX + mac.hexdigest()
    raise UnsupportedSealKind(f"unknown seal kind {kind!r}")


def verify_payload(payload: Any, seal: str, *, kind: str = UNKEYED,
                   key: str | None = None) -> bool:
    """Check a seal. Any doubt is a False, never an exception-driven PASS."""
    if not seal:
        return False
    if kind == UNKEYED:
        return seal == digest(payload)
    if kind == HMAC_SHA256:
        secret = resolve_key(key)
        if not secret:
            return False
        expected = hmac.new(secret.encode("utf-8"),
                            canonical(payload).encode("utf-8"),
                            hashlib.sha256).hexdigest()
        return hmac.compare_digest(seal, _HMAC_PREFIX + expected)
    return False
