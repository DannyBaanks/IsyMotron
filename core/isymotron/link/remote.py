"""Shared sealed-call client for the link subsystem (CLI + console).

One implementation, two callers (tools/link_cli.py, console/server.py),
so the wire behavior cannot drift between surfaces.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from . import envelope, identity, pairing


class LinkCallError(Exception):
    pass


def post_json(url: str, payload: dict, timeout_s: float = 15.0) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read() or b"{}")
        except ValueError:
            body = {"ok": False, "code": f"http_{exc.code}"}
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {"ok": False, "code": "unreachable", "error": str(exc)}


def resolve_peer(directory: Path, query: str) -> dict:
    peer = pairing.find_peer(query, identity.load_peers(directory))
    if peer is None:
        raise LinkCallError(f"oficina no emparejada: {query!r}")
    if not peer.get("addresses"):
        raise LinkCallError(f"{query!r} no tiene direccion conocida")
    return peer


def sealed_call(directory: Path, query: str, payload: dict) -> dict:
    """Seal op to a paired office, try its addresses, return result body."""
    own = identity.load_identity(directory)
    peer = resolve_peer(directory, query)
    env = envelope.seal(own, peer, payload)
    last: dict = {"ok": False, "code": "unreachable"}
    for address in peer.get("addresses", []):
        status, body = post_json(f"http://{address}/link/v1/call", {"env": env})
        if status == 200 and body.get("ok"):
            return body
        last = body
    raise LinkCallError(f"sin respuesta de {peer.get('name')}: {last}")
