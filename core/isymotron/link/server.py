"""Link server: HTTP envelopes + UDP discovery + delegation inbox.

M2 scope. Beside the relay, never inside it: the LoopbackRelay contract
is untouched. Default ports 47931/tcp + 47932/udp (M0 choice; free and
clear of pet 8760 and Munder defaults). Tests bind ephemeral ports.

Routes:
  GET  /link/v1/status            public card + paired/inbox counts
  POST /link/v1/pair              {card..., nonce, port} -> {peer, code}
  POST /link/v1/call              {env} sealed op: ping|delegate|message|cancel|task
                                  -> {ok, ...result, renv}: the same result sealed back to
                                     the caller and bound to its request nonce ("re"), so a
                                     client can trust a reply only if this office signed it
UDP :47932 answers the ISYMO-LINK?v1 probe with our card (discovery).

Delegation lands in state_dir/inbox.jsonl (queued); the human (or M3
`link tarea`) reads it from there. Receipts go to receipts.jsonl on
both sides of every delegation.
"""

from __future__ import annotations

import json
import ipaddress
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import envelope, identity, pairing, permissions

PROBE = "ISYMO-LINK?v1"
DEFAULT_TCP_PORT = 47931
DEFAULT_UDP_PORT = 47932


class LinkError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def _task_id() -> str:
    return f"task-{int(time.time() * 1000)}-{os.urandom(2).hex()}"


class LinkState:
    """Per-process link runtime: identity, nonces, inbox. No sockets."""

    def __init__(self, directory: Path | None = None, permission_host=None):
        self.directory = directory or identity.state_dir()
        self.identity = identity.load_identity(self.directory)
        self.seen_nonces: dict[str, float] = {}
        self.nonce_lock = threading.Lock()
        self.inbox_lock = threading.RLock()
        self.permissions = (
            permissions.PermissionQueue(self.directory, permission_host)
            if permission_host is not None else None
        )
        # Session window: every sealed inbound call refreshes it. The phone
        # can show "sesión activa hasta HH:MM" without keeping a socket
        # alive; the PC stays the sole authority of when it is valid.
        self.session_expires_at: float = 0.0

    def inbox_path(self) -> Path:
        return self.directory / "inbox.jsonl"

    def _read_inbox_unlocked(self) -> list[dict]:
        try:
            lines = self.inbox_path().read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def inbox(self) -> list[dict]:
        with self.inbox_lock:
            return self._read_inbox_unlocked()

    def _rewrite_inbox_unlocked(self, entries: list[dict]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with open(self.inbox_path(), "w", encoding="utf-8", newline="\n") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def inbox_update(self, task_id: str, office_id: str, mutate) -> dict | None:
        """Read, mutate and rewrite one owned task under one process-local lock."""
        with self.inbox_lock:
            entries = self._read_inbox_unlocked()
            hit = next(
                (
                    entry
                    for entry in entries
                    if entry.get("task_id") == task_id and entry.get("from") == office_id
                ),
                None,
            )
            if hit is None:
                return None
            mutate(hit)
            self._rewrite_inbox_unlocked(entries)
            return hit

    def inbox_append(self, entry: dict) -> dict:
        with self.inbox_lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entry}
            with open(self.inbox_path(), "a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            return record


def handle_pair(state: LinkState, body: dict, remote_addr: str = "") -> dict:
    for field in ("office_id", "name", "sign_pub", "box_pub", "nonce"):
        if not body.get(field):
            raise LinkError("bad_card", f"pair needs {field}", 400)
    if body.get("protocol", identity.PROTOCOL) != identity.PROTOCOL:
        raise LinkError("bad_protocol", "foreign link protocol", 400)
    try:
        claimed = envelope.digest_public_card_fingerprint(str(body["sign_pub"]))
    except Exception:
        raise LinkError("bad_identity", "unreadable signing key", 400) from None
    if claimed != str(body["office_id"]):
        raise LinkError("bad_identity", "office_id does not match its key", 400)
    if str(body["office_id"]) == state.identity["office_id"]:
        raise LinkError("self", "cannot pair with yourself", 400)
    pending = identity.load_pending(state.directory)
    office_id = str(body["office_id"])
    if office_id not in pending and len(pending) >= pairing.MAX_PENDING:
        raise LinkError("busy", "too many pending pairings", 429)
    server_nonce = pairing.fresh_nonce()
    code = pairing.short_code(
        state.identity["sign"]["x"], str(body["sign_pub"]),
        server_nonce, str(body["nonce"]),
    )
    try:
        port = int(body.get("port", 0) or 0)
    except (TypeError, ValueError):
        port = 0
    host = (remote_addr or "").split("%")[0]
    entry = {
        "office_id": office_id,
        "name": str(body.get("name", "desconocida"))[:64],
        "sign_pub": str(body["sign_pub"]),
        "box_pub": str(body["box_pub"]),
        "addresses": [f"{host}:{port}"] if host and port else [],
        "code": code,
        "expires_at": time.time() + pairing.PENDING_TTL_S,
    }
    pending[office_id] = entry
    identity.save_pending(pending, state.directory)
    return {
        "peer": identity.public_card(state.identity),
        "nonce": server_nonce,
        "expires_at": entry["expires_at"],
    }


def _require_arg(body: dict, name: str) -> str:
    value = body.get(name)
    if not value:
        raise LinkError("bad_call", f"op needs {name}", 400)
    return str(value)


def handle_call(state: LinkState, env: dict) -> dict:
    return handle_call_with_peer(state, env)[0]


def handle_call_with_peer(state: LinkState, env: dict) -> tuple[dict, dict]:
    peers = identity.load_peers(state.directory)
    try:
        with state.nonce_lock:
            peer, payload = envelope.open_envelope(
                state.identity, peers, env, state.seen_nonces
            )
    except envelope.EnvelopeError as exc:
        raise LinkError("rejected", str(exc), 403) from exc
    result = _dispatch(state, peer, payload)
    if isinstance(result, dict):
        result.setdefault("session_until", _session_until_iso(state))
    return (result, peer)


SESSION_TTL_S = 4 * 3600


def _session_until_iso(state: LinkState) -> str | None:
    if state.session_expires_at <= 0:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(state.session_expires_at))


def sealed_reply(state: LinkState, peer: dict, env: dict, result: dict) -> dict:
    """The result sealed back to the caller, bound to the request nonce."""
    return envelope.seal(state.identity, peer, {"re": str(env.get("nonce", "")), **result})


def _dispatch(state: LinkState, peer: dict, payload: dict) -> dict:
    op = payload.get("op")
    state.session_expires_at = time.time() + SESSION_TTL_S
    if op == "ping":
        profile = None
        if state.permissions is not None:
            profile = getattr(state.permissions.host, "tool_profile", None)
        return {"ok": True, "pong": True, "from": state.identity["office_id"],
                "tool_profile": profile}
    if op == "delegate":
        task_id = _task_id()
        state.inbox_append(
            {
                "task_id": task_id,
                "from": peer["office_id"],
                "title": _require_arg(payload, "title"),
                "body": str(payload.get("body", "")),
                "context": [],
                "status": "queued",
            }
        )
        from . import receipts

        receipts.append_receipt(
            state.directory,
            "link_received",
            {"task_id": task_id, "from": peer["office_id"], "title": payload.get("title", "")},
        )
        return {"ok": True, "task_id": task_id}
    if op == "message":
        task_id = _require_arg(payload, "task_id")
        text = _require_arg(payload, "text")

        def add_message(hit: dict) -> None:
            hit.setdefault("context", []).append(
                {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "text": text}
            )

        if state.inbox_update(task_id, peer["office_id"], add_message) is None:
            raise LinkError("no_such_task", "task is not yours", 404)
        return {"ok": True}
    if op == "cancel":
        task_id = _require_arg(payload, "task_id")

        def mark_cancelled(hit: dict) -> None:
            hit["status"] = "cancelled"

        if state.inbox_update(task_id, peer["office_id"], mark_cancelled) is None:
            raise LinkError("no_such_task", "task is not yours", 404)
        return {"ok": True}
    if op == "task":
        task_id = _require_arg(payload, "task_id")
        hit = next(
            (e for e in state.inbox() if e.get("task_id") == task_id and e.get("from") == peer["office_id"]),
            None,
        )
        if hit is None:
            raise LinkError("no_such_task", "task is not yours", 404)
        return {"ok": True, "task": hit}
    if op == "permissions":
        queue = _permission_queue(state)
        return {"ok": True, "requests": queue.pending()}
    if op == "permission_decide":
        queue = _permission_queue(state)
        request_id = _require_arg(payload, "request_id")
        decision = _require_arg(payload, "decision")
        try:
            return {"ok": True, **queue.decide(request_id, decision, peer["office_id"])}
        except permissions.PermissionQueueError as exc:
            raise LinkError(exc.code, str(exc), exc.status) from exc
    raise LinkError("bad_op", f"unknown op {op!r}", 400)


def _permission_queue(state: LinkState) -> permissions.PermissionQueue:
    if state.permissions is None:
        raise LinkError("permissions_unavailable", "this PC has no active host permission service", 503)
    return state.permissions


def _loopback(address: str) -> bool:
    try:
        return ipaddress.ip_address(address.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def _rewrite_inbox(state: LinkState, entries: list[dict]) -> None:
    with state.inbox_lock:
        state._rewrite_inbox_unlocked(entries)


class _Handler(BaseHTTPRequestHandler):
    state: LinkState

    def log_message(self, *args) -> None:  # quiet by design
        pass

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        prefix = "/link/v1/local/permissions/"
        if self.path.startswith(prefix):
            if not _loopback(self.client_address[0]):
                self._send(403, {"ok": False, "code": "local_only"})
                return
            try:
                request_id = self.path[len(prefix):]
                request = _permission_queue(self.state).local_status(request_id)
            except LinkError as exc:
                self._send(exc.status, {"ok": False, "code": exc.code, "error": str(exc)})
                return
            if request is None:
                self._send(404, {"ok": False, "code": "no_such_request"})
            else:
                self._send(200, {"ok": True, "request": request})
            return
        if self.path == "/link/v1/status":
            peers = identity.load_peers(self.state.directory)
            queued = sum(1 for e in self.state.inbox() if e.get("status") == "queued")
            self._send(
                200,
                {
                    "office": identity.public_card(self.state.identity),
                    "paired": len(peers),
                    "inbox_queued": queued,
                },
            )
            return
        self._send(404, {"ok": False, "code": "not_found"})

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length > envelope.MAX_BODY_BYTES:
            self._send(413, {"ok": False, "code": "too_large"})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._send(400, {"ok": False, "code": "bad_json"})
            return
        try:
            if self.path == "/link/v1/local/permissions":
                if not _loopback(self.client_address[0]):
                    self._send(403, {"ok": False, "code": "local_only"})
                    return
                request = _permission_queue(self.state).submit(body)
                self._send(201, {"ok": True, "request": request})
            elif self.path == "/link/v1/pair":
                remote = (self.client_address[0] if self.client_address else "")
                self._send(200, {"ok": True, **handle_pair(self.state, body, remote)})
            elif self.path == "/link/v1/call":
                if "env" not in body:
                    raise LinkError("bad_call", "call needs env", 400)
                result, peer = handle_call_with_peer(self.state, body["env"])
                renv = sealed_reply(self.state, peer, body["env"], result)
                self._send(200, {"ok": True, **result, "renv": renv})
            else:
                self._send(404, {"ok": False, "code": "not_found"})
        except LinkError as exc:
            self._send(exc.status, {"ok": False, "code": exc.code, "error": str(exc)})
        except permissions.PermissionQueueError as exc:
            self._send(exc.status, {"ok": False, "code": exc.code, "error": str(exc)})


class LinkServer:
    """HTTP + UDP discovery. start() backgrounds both; stop() ends them."""

    def __init__(
        self,
        directory: Path | None = None,
        tcp_port: int = DEFAULT_TCP_PORT,
        udp_port: int = DEFAULT_UDP_PORT,
        host: str = "127.0.0.1",
        permission_host=None,
    ):
        self.state = LinkState(directory, permission_host=permission_host)
        handler = type("BoundHandler", (_Handler,), {"state": self.state})
        self.http = ThreadingHTTPServer((host, tcp_port), handler)
        self.udp_port = udp_port
        self.host = host
        self._udp_sock: socket.socket | None = None
        self._udp_thread: threading.Thread | None = None
        self._running = False

    @property
    def tcp_address(self) -> str:
        host, port = self.http.server_address[:2]
        return f"{host}:{port}"

    def start(self) -> "LinkServer":
        self._running = True
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.udp_port))
            sock.settimeout(0.5)
            self.udp_port = sock.getsockname()[1]
            self._udp_sock = sock
            self._udp_thread = threading.Thread(target=self._serve_udp, daemon=True)
            self._udp_thread.start()
        except OSError:
            self._udp_sock = None
        return self

    def _serve_udp(self) -> None:
        assert self._udp_sock is not None
        while self._running:
            try:
                data, addr = self._udp_sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                return
            if data.decode("utf-8", "replace").strip() != PROBE:
                continue
            card = identity.public_card(self.state.identity)
            card["port"] = self.http.server_address[1]
            try:
                self._udp_sock.sendto(json.dumps(card).encode("utf-8"), addr)
            except OSError:
                pass

    def stop(self) -> None:
        self._running = False
        self.http.shutdown()
        if self._udp_sock is not None:
            try:
                self._udp_sock.close()
            except OSError:
                pass


def discover(timeout_s: float = 1.0, udp_port: int = DEFAULT_UDP_PORT) -> list[dict]:
    """Broadcast probe; return office cards that answer. Lists only, trusts none."""
    found: list[dict] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout_s)
        sock.sendto(PROBE.encode("utf-8"), ("255.255.255.255", udp_port))
        sock.sendto(PROBE.encode("utf-8"), ("127.0.0.1", udp_port))
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                break
            try:
                card = json.loads(data.decode("utf-8"))
            except ValueError:
                continue
            if isinstance(card, dict) and card.get("office_id"):
                card["seen_at"] = addr[0]
                found.append(card)
    finally:
        sock.close()
    seen: set[str] = set()
    unique = []
    for card in found:
        if card["office_id"] not in seen:
            seen.add(card["office_id"])
            unique.append(card)
    return unique
