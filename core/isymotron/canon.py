"""Canonical JSON + digests.

One serialization rule for the whole system, so that a digest computed on a
phone, on a relay and on a Windows 98 host is the same digest.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no spaces, UTF-8, no NaN."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(obj: Any) -> str:
    """sha256 of the canonical form, prefixed so it is never mistaken for a hex blob."""
    return "sha256:" + hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()
