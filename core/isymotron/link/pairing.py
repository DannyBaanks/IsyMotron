"""Pairing ceremony: 6-digit code, both humans compare, keys get pinned.

Port of Munder Link pairing (lib-link.cjs): SAS derived from both
signing keys and both nonces (sorted, so a MITM cannot make both
screens agree), pending TTL 10 min, max 5 pending, accept-by-code,
trust preserves the first paired_at, forget is one-sided.

M1 only: the transport half (POST /link/v1/pair over HTTP) arrives in
M2. These functions operate on cards and nonces directly so the
ceremony logic is testable without a network.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from . import identity as link_identity

PROTOCOL = link_identity.PROTOCOL
PENDING_TTL_S = 600
MAX_PENDING = 5


def short_code(sign_pub_a: str, sign_pub_b: str, nonce_a: str, nonce_b: str) -> str:
    """6-digit code both humans compare. Order-independent by construction."""
    keys = sorted([sign_pub_a, sign_pub_b])
    nonces = sorted([nonce_a, nonce_b])
    digest = hashlib.sha256(
        "|".join([PROTOCOL, *keys, *nonces]).encode("utf-8")
    ).digest()
    return str(int.from_bytes(digest[:4], "big") % 1_000_000).zfill(6)


def fresh_nonce() -> str:
    return link_identity._b64(os.urandom(16))


def propose(
    local_identity: dict,
    peer_card: dict,
    peer_nonce: str,
    directory: Path | None = None,
) -> dict:
    """Asking side, step 1: record pending + return the code to compare."""
    directory = directory or link_identity.state_dir()
    pending = link_identity.load_pending(directory)
    if len(pending) >= MAX_PENDING:
        raise ValueError(f"too many pending pairings (max {MAX_PENDING})")
    office_id = str(peer_card["office_id"])
    nonce_local = fresh_nonce()
    # The peer nonce arrives with the /pair response on the wire (M2);
    # offline it is supplied explicitly so the ceremony stays testable.
    code = short_code(
        local_identity["sign"]["x"], str(peer_card["sign_pub"]),
        nonce_local, peer_nonce,
    )
    entry = {
        "office_id": office_id,
        "name": str(peer_card.get("name", office_id)),
        "sign_pub": str(peer_card["sign_pub"]),
        "box_pub": str(peer_card["box_pub"]),
        "addresses": list(peer_card.get("addresses", [])),
        "nonce_local": nonce_local,
        "nonce_peer": peer_nonce,
        "code": code,
        "expires_at": time.time() + PENDING_TTL_S,
    }
    pending[office_id] = entry
    link_identity.save_pending(pending, directory)
    return {"peer": {k: entry[k] for k in ("office_id", "name")}, "code": entry["code"]}


def accept(code: str, directory: Path | None = None) -> dict | None:
    """Asked side, step 2: a human typed the code from the other screen."""
    directory = directory or link_identity.state_dir()
    pending = link_identity.load_pending(directory)
    wanted = str(code).strip()
    hit = next((p for p in pending.values() if p.get("code") == wanted), None)
    if hit is None:
        return None
    del pending[hit["office_id"]]
    link_identity.save_pending(pending, directory)
    return trust_peer(hit, directory)


def trust_peer(peer: dict, directory: Path | None = None) -> dict:
    """Pin a peer. First paired_at wins; addresses accumulate."""
    directory = directory or link_identity.state_dir()
    peers = link_identity.load_peers(directory)
    office_id = str(peer["office_id"])
    prev = peers.get(office_id, {})
    prev_addresses = prev.get("addresses", []) if isinstance(prev, dict) else []
    peers[office_id] = {
        "office_id": office_id,
        "name": str(peer.get("name", office_id)),
        "sign_pub": str(peer["sign_pub"]),
        "box_pub": str(peer["box_pub"]),
        "addresses": sorted(
            set(list(peer.get("addresses", [])) + list(prev_addresses))
        ),
        "paired_at": prev.get("paired_at") if isinstance(prev, dict) and prev.get("paired_at") else time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        ),
    }
    link_identity.save_peers(peers, directory)
    return peers[office_id]


def forget(query: str, directory: Path | None = None) -> dict | None:
    """One-sided: we drop our trust; the peer still knows us until it forgets."""
    directory = directory or link_identity.state_dir()
    peers = link_identity.load_peers(directory)
    found = find_peer(query, peers)
    if found is None:
        return None
    del peers[found["office_id"]]
    link_identity.save_peers(peers, directory)
    return found


def find_peer(query: str, peers: dict) -> dict | None:
    """Exact office id/name (minus isytron- prefix) or one unambiguous fragment."""
    text = str(query).lower().strip()
    if not text:
        return None
    items = list(peers.values())
    short = lambda p: str(p.get("name", "")).lower().removeprefix("isytron-")
    exact = next(
        (
            p
            for p in items
            if p.get("office_id") == text
            or str(p.get("name", "")).lower() == text
            or short(p) == text
        ),
        None,
    )
    if exact is not None:
        return exact
    matches = [
        p
        for p in items
        if str(p.get("office_id", "")).startswith(text)
        or text in str(p.get("name", "")).lower()
    ]
    return matches[0] if len(matches) == 1 else None
