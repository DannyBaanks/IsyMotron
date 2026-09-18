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
import urllib.parse
from typing import Any, Callable

from isymotron.attribution import Attribution
from isymotron.awareness import HostAwarenessEngine
from isymotron.verdicts import Decision
from relay.loopback import LoopbackRelay

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

#: Served files, by exact name. An allowlist rather than a directory walk:
#: this process has a grant file and a receipt store next to it, and a static
#: handler that resolves paths is the classic way to leak them.
SERVABLE = {
    "index.html": "text/html; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "favicon.svg": "image/svg+xml",
}


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
        self._lock = threading.Lock()

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
        return {
            "snapshot": snap.to_dict(),
            "health": self.awareness.health(),
            "events": [e.to_dict() for e in self.awareness.recent_events(limit=12)],
        }

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

    def _authorized(self) -> bool:
        """The session token, from a header or the query string.

        Not a security boundary against someone already on this machine -- it
        is the thing that stops another page in the browser, or a stray device
        on the wifi, from driving the host. It is compared in constant time and
        never logged.
        """
        supplied = self.headers.get("X-IsyMotron-Token", "")
        if not supplied:
            q = urllib.parse.urlparse(self.path).query
            supplied = urllib.parse.parse_qs(q).get("t", [""])[0]
        return secrets.compare_digest(supplied, self.state.token)

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

        if not path.startswith("/api/"):
            return self._deny("not found", 404)
        if not self._authorized():
            return self._deny("bad or missing session token", 401)

        if path == "/api/state":
            return self._json({
                **self.state.snapshot(),
                "tier": "local" if self._is_loopback() else "lan",
                "can_grant": self._is_loopback(),
            })
        if path == "/api/events":
            block = self.state._awareness_block()
            return self._json(block or {"error": "no awareness engine"})
        return self._deny("not found", 404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            return self._deny("not found", 404)
        if not self._authorized():
            return self._deny("bad or missing session token", 401)

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
            return self._deny("no model provider configured", 503)
        from agents.planner import PlanRejected, Planner
        from agents.provider import ProviderError

        intent = str(body.get("intent") or "").strip()
        if not intent:
            return self._deny("intent is required", 400)
        descs = [self.state.relay._host(h["host_id"]).describe()
                 for h in self.state.relay.hosts()]
        try:
            plan = Planner(self.state.provider_factory()).plan(intent, descs,
                                                               max_tokens=2000)
        except PlanRejected as exc:
            return self._json({"rejected": exc.reason, "detail": exc.detail}, 200)
        except ProviderError as exc:
            attribution = (exc.outcome.attribution.value if exc.outcome
                           else Attribution.UNKNOWN.value)
            return self._json({"provider_error": str(exc), "status": exc.status,
                               "attribution": attribution}, 200)
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
