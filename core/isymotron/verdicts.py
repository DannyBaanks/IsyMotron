"""Closed vocabularies. Every verdict a surface can render is declared here.

Rule inherited from ISyCo: the `else` branch of a preregistered verdict never
falls into the permissive class. Unmapped -> DENY for authority, UNKNOWN for
evidence.
"""
from __future__ import annotations

from enum import Enum


class Decision(str, Enum):
    """Authority plane. Produced only by the policy engine, never by a model."""

    ALLOW = "ALLOW"
    DENY = "DENY"


class DenyReason(str, Enum):
    """Why authority was refused. Rendered verbatim by every client surface."""

    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"  # host does not implement it
    CAPABILITY_NOT_GRANTED = "CAPABILITY_NOT_GRANTED"  # implemented, not granted here
    OUT_OF_SCOPE = "OUT_OF_SCOPE"                      # inside capability, outside scope
    EXCESS_AUTHORITY = "EXCESS_AUTHORITY"              # asks for more than manifest declares
    LEASE_MISSING = "LEASE_MISSING"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    LEASE_REVOKED = "LEASE_REVOKED"
    LEASE_MISMATCH = "LEASE_MISMATCH"                  # lease is for another cap/host/subject
    MALFORMED_REQUEST = "MALFORMED_REQUEST"
    UNVERIFIED_VERSION = "UNVERIFIED_VERSION"          # activity artifact changed
    REVERIFY_REQUIRED = "REVERIFY_REQUIRED"


class Evidence(str, Enum):
    """ISyCo evidence vocabulary. Applies to claims, not to authority."""

    DEMONSTRATED = "DEMONSTRATED"
    INFERRED = "INFERRED"
    NOT_DEMONSTRATED = "NOT_DEMONSTRATED"
    DESTROYED = "DESTROYED"
    UNKNOWN = "UNKNOWN"


class DoctorVerdict(str, Enum):
    """Sandbox verification plane. Deliberately has no SAFE member."""

    PASS_FOR_SCOPE = "PASS_FOR_SCOPE"
    DENY = "DENY"
    UNKNOWN = "UNKNOWN"
