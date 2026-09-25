"""Link identity: Ed25519+X25519 keypairs, office fingerprint, peer registry.

Port of Munder Link `loadIdentity`/`publicCard`/peers (lib-link.cjs),
same file shapes so a future bridge can read both. Differences are
deliberate and documented: protocol string (separate trust domain),
state dir (XDG), office name prefix (isytron-).

M1 only: no network, no envelopes (those are M2).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import socket
import time
from pathlib import Path

from . import curve

PROTOCOL = "isymotron-link@1"


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "state"
    )
    return Path(base) / "isymotron" / "link"


def _files(directory: Path) -> dict[str, Path]:
    return {
        "identity": directory / "identity.json",
        "peers": directory / "peers.json",
        "pending": directory / "pending.json",
    }


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _write_private(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass


def _read_json(path: Path, fallback):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return fallback


def office_id_of(sign_pub_raw: bytes) -> str:
    return hashlib.sha256(sign_pub_raw).hexdigest()[:16]


def pretty_fingerprint(office_id: str) -> str:
    return " ".join(office_id[i : i + 4] for i in range(0, len(office_id), 4))


def default_name() -> str:
    host = socket.gethostname().lower()
    clean = "".join(c if c.isalnum() or c == "-" else "-" for c in host)[:24]
    return f"isytron-{clean or 'office'}"


def load_identity(directory: Path | None = None, name: str | None = None) -> dict:
    """Create once (0600), return afterwards. Never logs secrets."""
    directory = directory or state_dir()
    path = _files(directory)["identity"]
    existing = _read_json(path, None)
    if existing and existing.get("sign") and existing.get("box"):
        if name and existing.get("name") != name:
            existing["name"] = name
            _write_private(path, existing)
        return existing
    sign_seed, sign_pub = curve.ed25519_keygen()
    box_priv, box_pub = curve.x25519_keygen()
    identity = {
        "protocol": PROTOCOL,
        "name": name or default_name(),
        "office_id": office_id_of(sign_pub),
        "sign": {"x": _b64(sign_pub), "d": _b64(sign_seed)},
        "box": {"x": _b64(box_pub), "d": _b64(box_priv)},
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _write_private(path, identity)
    return identity


def public_card(identity: dict, extra: dict | None = None) -> dict:
    """What anyone may learn about us: no secrets, no session contents."""
    card = {
        "protocol": PROTOCOL,
        "office_id": identity["office_id"],
        "name": identity["name"],
        "sign_pub": identity["sign"]["x"],
        "box_pub": identity["box"]["x"],
    }
    if extra:
        card.update(extra)
    return card


def load_peers(directory: Path | None = None) -> dict:
    directory = directory or state_dir()
    peers = _read_json(_files(directory)["peers"], {})
    return peers if isinstance(peers, dict) else {}


def save_peers(peers: dict, directory: Path | None = None) -> None:
    directory = directory or state_dir()
    _write_private(_files(directory)["peers"], peers)


def load_pending(directory: Path | None = None) -> dict:
    """Pending requests; expired ones are pruned on read, never trusted."""
    directory = directory or state_dir()
    now = time.time()
    all_pending = _read_json(_files(directory)["pending"], {})
    if not isinstance(all_pending, dict):
        return {}
    return {k: p for k, p in all_pending.items() if p.get("expires_at", 0) > now}


def save_pending(pending: dict, directory: Path | None = None) -> None:
    directory = directory or state_dir()
    _write_private(_files(directory)["pending"], pending)


def platform_name() -> str:
    return platform.node()
