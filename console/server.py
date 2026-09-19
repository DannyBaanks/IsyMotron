"""The IsyMotron console — a local web surface over the existing contract.

This is a *new attack surface*, so it is built like one.

Two authority tiers, enforced by which interface the request arrived on:

    loopback (127.0.0.1)   the human is sitting at this machine.
                           May grant, revoke, execute, plan.

    LAN (--lan)            something else on the network, typically a phone.
                           May read, execute and plan. **May not grant or
                           revoke.**

That second line is invariant 2.7 made concrete: a remote surface can use the
authority a human granted at the keyboard, and can never widen it. A phone that
could grant itself `filesystem.read C:/` would undo the entire product.

The console adds no capability of its own. Every action below goes through the
same `Enforcer`, produces the same sealed receipt, and is refused by the same
grant file as `tools/host_cli.py`.
"""
from __future__ import annotations

import http.server
import json
import mimetypes
import os
import secrets
import socket
import threading
import time
import urllib.parse
from typing import Any, Callable

from avatar.model import AvatarBus
from isymotron.attribution import Attribution
from isymotron.awareness import HostAwarenessEngine
from isymotron.resources import fs_roots, to_uri
from isymotron.verdicts import Decision
from relay.loopback import LoopbackRelay

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

#: The avatar pack root (AV4). Files under it are served ONLY through the
#: exact-name allowlist built below; a directory walk here would be the same
#: leak class as the static one above.
PACK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "avatar", "packs")
PACK_MIME = {".gif": "image/gif", ".json": "application/json",
             ".txt": "text/plain", ".png": "image/png"}

PACK_SERVABLE: dict = {}


def _load_pack_servable() -> None:
    if not os.path.isdir(PACK_DIR):
        return
    for root, _dirs, files in os.walk(PACK_DIR):
        for fn in sorted(files):
            ext = os.path.splitext(fn)[1].lower()
            if ext not in PACK_MIME:
                continue
            rel = os.path.relpath(os.path.join(root, fn), PACK_DIR).replace("\\", "/")
            PACK_SERVABLE["avatar/packs/" + rel] = PACK_MIME[ext]


_load_pack_servable()

#: Served files, by exact name. An allowlist rather than a directory walk:
#: this process has a grant file and a receipt store next to it, and a static
#: handler that resolves paths is the classic way to leak them.
SERVABLE = {
    "index.html": "text/html; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "avatar.js": "text/javascript; charset=utf-8",
    "favicon.svg": "image/svg+xml",
}

#: Awareness event types that become avatar `host` events (contract §3.1:
#: suspend / network change). PROCESS_STARTED etc. are noise to a pet.
HOST_EVENT_KINDS = {
    "HOST_SUSPEND_REQUESTED", "HOST_RESUMED",
    "NETWORK_UP", "NETWORK_DOWN", "NETWORK_CHANGED",
}


def avatar_token_path() -> str:
    """Where the read-only avatar token lives (AV3).

    Overridable for tests via ISYMOTRON_AVATAR_TOKEN_PATH; the product path is
    %LOCALAPPDATA%\\IsyMotron\\session\\avatar.token. Never argv, never a URL
    printed to the console (R5).
    """
    override = os.environ.get("ISYMOTRON_AVATAR_TOKEN_PATH")
    if override:
        return override
    local = os.environ.get("LOCALAPPDATA") or ""
    return os.path.join(local, "IsyMotron", "session", "avatar.token")


def write_avatar_token(token: str, path: str | None = None) -> str:
    path = path or avatar_token_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(token)
    return path


class ConsoleState:
    """Everything the console can see. Assembled once, read many times."""

    def __init__(self, relay: LoopbackRelay, awareness: HostAwarenessEngine | None,
                 grants_path: str, provider_factory: Callable[[], Any] | None = None,
                 subject: str = "console:local") -> None:
        self.relay = relay
        self.awareness = awareness
        self.grants_path = grants_path
        self.provider_factory = provider_factory
        self.subject = subject
        self.receipts: list[dict] = []
        self.token = secrets.token_urlsafe(24)
        # The avatar is a representation, never an authority
        # (docs/AVATAR_CONTRACT.md). It gets a second token: read-only in
        # effect, refused on every POST (R5).
        self.avatar = AvatarBus()
        self.avatar_token = secrets.token_urlsafe(24)
        self._lock = threading.Lock()
        self._emitted_awareness: set[str] = set()
        # AV6: the mode is a fact of configuration, never of authority (R7).
        # One `mode` event at start, with the provider label when there is one.
        provider_label = "none"
        if provider_factory is not None:
            try:
                provider_label = provider_factory().label
            except Exception:
                provider_label = "unknown"
        self.avatar.publish_authority("mode", state="idle", provider=provider_label)

    # -- reads --------------------------------------------------------------
    def snapshot(self) -> dict:
        hosts = []
        for ident in self.relay.hosts():
            desc = self.relay.describe(ident["host_id"])
            granted = set(desc["granted"])
            hosts.append({
                "identity": desc["identity"],
                "granted": desc["granted"],
                "scopes": self._scopes_for(ident["host_id"]),
                "health": self.relay.health(ident["host_id"]),
                "capabilities": [
                    {**c, "state": "GRANTED" if c["id"] in granted else "AVAILABLE"}
                    for c in desc["capabilities"]
                ],
            })
        return {
            "hosts": hosts,
            "awareness": self._awareness_block(),
            "receipts": self.receipts[-40:],
        }

    def _scopes_for(self, host_id: str) -> dict:
        """The granted scopes, so the UI can show what a grant actually covers.

        Read from the live host rather than the file: what is enforced is what
        the host holds, and showing the file instead would quietly disagree
        after a grant that has not been reloaded.
        """
        host = self.relay._host(host_id)
        return {k: dict(v) for k, v in getattr(host, "_grant_scopes", {}).items()}

    def _awareness_block(self) -> dict | None:
        if self.awareness is None:
            return None
        snap = self.awareness.snapshot()
        for event in self.awareness.recent_events(limit=12):
            if event.event_id in self._emitted_awareness:
                continue
            if event.event_type not in HOST_EVENT_KINDS:
                continue
            self._emitted_awareness.add(event.event_id)
            self.avatar.publish_authority(
                "host", host_id=event.host_id, awareness_event=event.event_id,
                event_type=event.event_type.value, state="waiting",
                text=f"host report: {event.event_type.value} on {event.host_id}")
        return {
            "snapshot": snap.to_dict(),
            "health": self.awareness.health(),
            "events": [e.to_dict() for e in self.awareness.recent_events(limit=12)],
        }

    # -- avatar producers (the authority channel) ---------------------------
    def _logical_detail(self, host_id: str, capability: str, params: Any) -> str:
        """R6: authority details are logical. A path param resolves to its
        granted hostfs:// name; anything that does not resolve stays unnamed.
        A physical path never reaches a renderer."""
        if not isinstance(params, dict):
            return capability
        path = params.get("path")
        if isinstance(path, str):
            scope = self._scopes_for(host_id).get(capability, {})
            uri = to_uri(path, fs_roots(scope))
            if uri:
                return f"{capability} on {uri}"
        return capability

    def _verdict_event(self, host_id: str, capability: str, decision: dict,
                       receipt_id, seal_ok, params: Any = None) -> None:
        """One verdict visual, straight from a real receipt. Only code that
        held an ExecutionReceipt calls this -- never an inbox line (R1/R2)."""
        outcome = decision.get("decision")
        reason = decision.get("reason")
        allowed = outcome == "ALLOW"
        detail = self._logical_detail(host_id, capability, params)
        self.avatar.publish_authority(
            "verdict",
            host_id=host_id,
            capability=capability,
            decision=outcome,
            reason=reason,
            detail=detail,
            receipt_id=receipt_id,
            seal_ok=seal_ok,
            state="success" if allowed else "error",
            text=(f"The host allowed: {detail}" if allowed else
                  f"The host refused: {detail}" + (f" ({reason})" if reason else "")),
        )

    # -- writes -------------------------------------------------------------
    def execute(self, host_id: str, capability: str, params: dict) -> dict:
        with self._lock:
            lease, decision = self.relay.request_lease(
                host_id, self.subject, capability, 300.0)
            if lease is None:
                entry = {
                    "host": host_id, "capability": capability,
                    "decision": decision.to_dict(), "result": {},
                    "receipt_id": None, "seal_ok": None,
                }
                self.receipts.append(entry)
                self._verdict_event(host_id, capability, decision.to_dict(),
                                    None, None, params)
                return entry

            from isymotron.contracts import ExecutionRequest
            req = ExecutionRequest.make(host_id, self.subject, capability,
                                        params, lease.lease_id)
            rcpt = self.relay.execute(req)
            entry = {
                "host": host_id,
                "capability": capability,
                "params": params,
                "decision": rcpt.decision.to_dict(),
                "result": rcpt.result,
                "evidence": rcpt.evidence.value,
                "receipt_id": rcpt.receipt_id,
                "seal": rcpt.seal,
                "seal_ok": rcpt.verify(),
                "wall": rcpt.ended_at,
            }
            self.receipts.append(entry)
            self._verdict_event(host_id, capability, rcpt.decision.to_dict(),
                                rcpt.receipt_id, entry["seal_ok"], params)
            return entry


class ConsoleHandler(http.server.BaseHTTPRequestHandler):
    server_version = "IsyMotronConsole/0.1"
    state: ConsoleState
    allow_lan: bool = False

    # -- plumbing -----------------------------------------------------------
    def log_message(self, fmt: str, *args: Any) -> None:
        pass  # the console prints its own, quieter, log

    def _is_loopback(self) -> bool:
        return self.client_address[0] in ("127.0.0.1", "::1", "localhost")

    def _token_kind(self) -> str | None:
        """Which token this request carried: "session" or "avatar".

        Not a security boundary against someone already on this machine -- it
        is the thing that stops another page in the browser, or a stray device
        on the wifi, from driving the host. It is compared in constant time and
        never logged. The avatar token reads the two GET routes and is refused
        on every POST (R5).
        """
        supplied = self.headers.get("X-IsyMotron-Token", "")
        if not supplied:
            q = urllib.parse.urlparse(self.path).query
            supplied = urllib.parse.parse_qs(q).get("t", [""])[0]
        if secrets.compare_digest(supplied, self.state.token):
            return "session"
        if secrets.compare_digest(supplied, self.state.avatar_token):
            return "avatar"
        return None

    def _authorized(self) -> bool:
        return self._token_kind() is not None

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        # This page talks to nothing but itself.
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; "
                         "style-src 'self'; script-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _deny(self, reason: str, code: int = 403) -> None:
        self._json({"error": reason}, code)

    # -- routing ------------------------------------------------------------
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            return self._static("index.html")
        name = path.lstrip("/")
        if name in SERVABLE:
            return self._static(name)
        ctype = PACK_SERVABLE.get(name)
        if ctype is not None:
            return self._pack_static(name, ctype)

        if not path.startswith("/api/"):
            return self._deny("not found", 404)
        if not self._authorized():
            return self._deny("bad or missing session token", 401)

        if path == "/api/state":
            return self._json({
                **self.state.snapshot(),
                "tier": "local" if self._is_loopback() else "lan",
                "can_grant": self._is_loopback(),
                "mode": "agent" if self.state.provider_factory else "avatar",
            })
        if path == "/api/events":
            block = self.state._awareness_block()
            return self._json(block or {"error": "no awareness engine"})
        if path == "/api/avatar":
            q = urllib.parse.parse_qs(parsed.query)
            try:
                since = int(q.get("since", ["0"])[0])
            except ValueError:
                since = 0
            view = self.state.avatar.view(time.time())
            return self._json({
                "events": self.state.avatar.since(since),
                "view": {"state": view.state, "host_frame": view.host_frame,
                         "third_party": view.third_party},
            })
        return self._deny("not found", 404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            return self._deny("not found", 404)
        if not self._authorized():
            return self._deny("bad or missing session token", 401)
        if self._token_kind() == "avatar":
            # R5: the avatar holds no authority and asks for none. Its token
            # reads; it never writes, on any route.
            return self._deny("the avatar token is read-only: the avatar holds "
                              "no authority (R5)", 403)

        length = int(self.headers.get("Content-Length") or 0)
        if length > 1_000_000:
            return self._deny("payload too large", 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._deny("malformed JSON", 400)
        if not isinstance(body, dict):
            return self._deny("body must be an object", 400)

        if path in ("/api/grant", "/api/revoke"):
            if not self._is_loopback():
                # The whole point. A remote surface uses authority; it never
                # widens it.
                return self._deny(
                    "granting requires the local machine: a remote surface may "
                    "use the authority a human granted here, never widen it", 403)
            return self._grant(body, revoke=path.endswith("revoke"))

        if path == "/api/execute":
            host_id = str(body.get("host") or "")
            capability = str(body.get("capability") or "")
            params = body.get("params") or {}
            if not isinstance(params, dict):
                return self._deny("params must be an object", 400)
            return self._json(self.state.execute(host_id, capability, params))

        if path == "/api/plan":
            return self._plan(body)
        if path == "/api/run":
            return self._run(body)
        return self._deny("not found", 404)

    # -- handlers -----------------------------------------------------------
    def _static(self, name: str) -> None:
        ctype = SERVABLE.get(name)
        if ctype is None:
            return self._deny("not found", 404)
        try:
            with open(os.path.join(STATIC, name), "rb") as fh:
                data = fh.read()
        except OSError:
            return self._deny("not found", 404)
        self._send(200, data, ctype)

    def _pack_static(self, name: str, ctype: str) -> None:
        """Serve one pack file, by exact allowlist name only.

        The name came from PACK_SERVABLE, so no traversal can reach this;
        the containment check is belt and braces in case the allowlist is
        ever built from something other than a walk of PACK_DIR.
        """
        rel = name[len("avatar/packs/"):]
        full = os.path.normpath(os.path.join(PACK_DIR, rel))
        base = os.path.normpath(PACK_DIR)
        if not (full == base or full.startswith(base + os.sep)):
            return self._deny("not found", 404)
        try:
            with open(full, "rb") as fh:
                data = fh.read()
        except OSError:
            return self._deny("not found", 404)
        self._send(200, data, ctype)

    def _grant(self, body: dict, revoke: bool) -> None:
        from windows.grants import Grants
        from windows.win11 import CAPABILITIES

        capability = str(body.get("capability") or "")
        known = {c.id for c in CAPABILITIES}
        if capability not in known:
            return self._deny(f"unknown capability {capability!r}", 400)

        g = Grants.load(self.state.grants_path)
        if g.source.startswith("<inert:"):
            g = Grants(host_id=g.host_id, display_name=g.display_name,
                       granted=[], scopes={})

        if revoke:
            if capability in g.granted:
                g.granted.remove(capability)
            g.scopes.pop(capability, None)
        else:
            scope = dict(g.scopes.get(capability, {}))
            roots = [str(r).replace("\\", "/") for r in (body.get("roots") or [])]
            apps = [str(a) for a in (body.get("apps") or [])]
            if roots:
                scope["roots"] = list(dict.fromkeys(scope.get("roots", []) + roots))
            if apps:
                scope["allowlist"] = list(dict.fromkeys(scope.get("allowlist", []) + apps))
            if capability not in g.granted:
                g.granted.append(capability)
            g.scopes[capability] = scope

        g.save(self.state.grants_path)
        self._json({"ok": True, "granted": g.granted, "scopes": g.scopes,
                    "note": "restart the console to re-read grants into the host"})

    def _plan(self, body: dict) -> None:
        if self.state.provider_factory is None:
            return self._deny("no model provider configured: set NVIDIA_NIM_API_KEY "
                              "or NEBIUS_API_KEY and restart the console", 503)
        from agents.planner import PlanRejected, Planner
        from agents.provider import ProviderError

        intent = str(body.get("intent") or "").strip()
        if not intent:
            return self._deny("intent is required", 400)
        descs = [self.state.relay._host(h["host_id"]).describe()
                 for h in self.state.relay.hosts()]
        self.state.avatar.publish_authority(
            "planning", state="thinking", text="the planner is thinking")
        try:
            plan = Planner(self.state.provider_factory()).plan(intent, descs,
                                                               max_tokens=2000)
        except PlanRejected as exc:
            self.state.avatar.publish_authority(
                "planned", state="waiting", text=f"plan refused: {exc.reason}")
            return self._json({"rejected": exc.reason, "detail": exc.detail}, 200)
        except ProviderError as exc:
            attribution = (exc.outcome.attribution.value if exc.outcome
                           else Attribution.UNKNOWN.value)
            self.state.avatar.publish_authority(
                "provider_error", state="error", text=str(exc),
                status=exc.status, attribution=attribution)
            return self._json({"provider_error": str(exc), "status": exc.status,
                               "attribution": attribution}, 200)
        self.state.avatar.publish_authority(
            "planned", state="waiting",
            text=f"plan {plan.verdict()}: {len(plan.steps)} step(s)")
        return self._json({"plan": plan.to_dict(), "verdict": plan.verdict()})

    def _run(self, body: dict) -> None:
        from agents.executor import Executor
        from agents.planner import Planner

        raw = body.get("plan")
        if not isinstance(raw, dict):
            return self._deny("plan is required", 400)
        descs = [self.state.relay._host(h["host_id"]).describe()
                 for h in self.state.relay.hosts()]
        try:
            plan = Planner.parse(json.dumps(raw), descs)
        except Exception as exc:
            return self._deny(f"plan did not revalidate: {exc}", 400)

        for i, step_spec in enumerate(plan.steps, 1):
            self.state.avatar.publish_authority(
                "step", index=i, host_id=step_spec.host,
                capability=step_spec.capability, state="working",
                text=f"step {i}: {step_spec.capability}")
        execution = Executor(self.state.relay, self.state.subject).run(plan)
        for step in execution.steps:
            self.state.receipts.append({
                "host": step.request.host_id,
                "capability": step.request.capability,
                "params": dict(step.request.params),
                "decision": step.receipt.decision.to_dict(),
                "result": step.receipt.result,
                "evidence": step.receipt.evidence.value,
                "receipt_id": step.receipt.receipt_id,
                "seal": step.receipt.seal,
                "seal_ok": step.receipt.verify(),
                "wall": step.receipt.ended_at,
            })
            self.state._verdict_event(
                step.request.host_id, step.request.capability,
                step.receipt.decision.to_dict(), step.receipt.receipt_id,
                step.receipt.verify(), step.request.params)
        return self._json(execution.to_dict())


def lan_address() -> str:
    """This machine's LAN address, without sending anything."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))     # never actually transmits
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def serve(state: ConsoleState, port: int = 8760, lan: bool = False):
    """Return a configured, unstarted server plus the URL to open."""
    handler = type("BoundConsoleHandler", (ConsoleHandler,),
                   {"state": state, "allow_lan": lan})
    host = "0.0.0.0" if lan else "127.0.0.1"
    httpd = http.server.ThreadingHTTPServer((host, port), handler)
    shown = lan_address() if lan else "127.0.0.1"
    return httpd, f"http://{shown}:{port}/?t={state.token}"
