"""The console is a new attack surface. These are the tests that treat it as one.

The one that matters is `test_lan_cannot_grant`: a phone may use the authority
a human granted at the keyboard and may never widen it. Everything else here
guards the surface itself -- the token, the static allowlist, the body size.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request

import pytest

from console.server import SERVABLE, ConsoleState, serve
from isymotron.awareness import HostAwarenessEngine, TestPowerProvider
from relay.loopback import LoopbackRelay
from simulator.engines import LegacyHost, ModernHost


@pytest.fixture
def console(tmp_path):
    relay = LoopbackRelay()
    relay.attach(ModernHost(
        fs={"C:/Photos/a.png": "AAA", "C:/Secrets/k.txt": "NEVER"},
        granted=["filesystem.read", "system.info"],
        grant_scopes={"filesystem.read": {"roots": ["C:/Photos"]}, "system.info": {}},
    ))
    relay.attach(LegacyHost(
        fs={"C:/NEMO/INBOX/.keep": ""},
        granted=["filesystem.write"],
        grant_scopes={"filesystem.write": {"roots": ["C:/NEMO/INBOX"]}},
    ))
    awareness = HostAwarenessEngine("win11-victus", TestPowerProvider())
    state = ConsoleState(relay, awareness, str(tmp_path / "grants.json"))
    httpd, url = serve(state, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield state, base
    httpd.shutdown()
    httpd.server_close()


def get(base, path, token=None, expect=200):
    url = f"{base}{path}" + (f"?t={token}" if token else "")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            assert r.status == expect
            return json.loads(r.read()) if "json" in r.headers.get("Content-Type", "") else r.read()
    except urllib.error.HTTPError as exc:
        assert exc.code == expect, f"expected {expect}, got {exc.code}"
        return json.loads(exc.read() or b"{}")


def post(base, path, body, token=None, expect=200):
    url = f"{base}{path}" + (f"?t={token}" if token else "")
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            assert r.status == expect
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        assert exc.code == expect, f"expected {expect}, got {exc.code}"
        return json.loads(exc.read() or b"{}")


# -- the token --------------------------------------------------------------

def test_api_without_a_token_is_refused(console):
    _, base = console
    assert "error" in get(base, "/api/state", expect=401)


def test_api_with_a_wrong_token_is_refused(console):
    _, base = console
    assert "error" in get(base, "/api/state", token="nope", expect=401)


def test_a_near_miss_token_is_refused(console):
    state, base = console
    get(base, "/api/state", token=state.token[:-1], expect=401)
    get(base, "/api/state", token=state.token + "x", expect=401)


def test_post_without_a_token_is_refused(console):
    _, base = console
    post(base, "/api/execute", {"host": "win11-victus",
                                "capability": "system.info", "params": {}},
         expect=401)


# -- the static surface -----------------------------------------------------

def test_only_allowlisted_files_are_served(console):
    _, base = console
    for name in SERVABLE:
        get(base, "/" + name)
    for forbidden in ("/server.py", "/__main__.py", "/static/app.js",
                      "/grants.json", "/..%2fserver.py", "/./server.py"):
        get(base, forbidden, expect=404)


def test_the_index_needs_no_token(console):
    """The page loads; the data behind it does not. The token lives in the URL
    the console printed, so a page opened without one simply shows nothing."""
    _, base = console
    body = get(base, "/")
    assert b"ISY" in body


# -- authority tiers --------------------------------------------------------

def test_loopback_is_the_local_tier(console):
    state, base = console
    s = get(base, "/api/state", token=state.token)
    assert s["tier"] == "local"
    assert s["can_grant"] is True


def test_lan_cannot_grant(console, monkeypatch):
    """The invariant, in one test.

    A remote surface may read, plan and execute. It may not widen authority.
    Simulated by telling the handler its peer is not loopback, because the
    alternative is asking a test to come from another machine.
    """
    from console import server as srv
    state, base = console
    monkeypatch.setattr(srv.ConsoleHandler, "_is_loopback", lambda self: False)

    s = get(base, "/api/state", token=state.token)
    assert s["tier"] == "lan"
    assert s["can_grant"] is False

    for path in ("/api/grant", "/api/revoke"):
        r = post(base, path, {"capability": "filesystem.read",
                              "roots": ["C:/"]}, token=state.token, expect=403)
        assert "never widen it" in r["error"]

    # ...but it can still use what was granted.
    r = post(base, "/api/execute",
             {"host": "win11-victus", "capability": "system.info", "params": {}},
             token=state.token)
    assert r["decision"]["decision"] == "ALLOW"


def test_lan_grant_does_not_touch_the_grant_file(console, monkeypatch, tmp_path):
    from console import server as srv
    state, base = console
    monkeypatch.setattr(srv.ConsoleHandler, "_is_loopback", lambda self: False)
    post(base, "/api/grant", {"capability": "filesystem.read", "roots": ["C:/"]},
         token=state.token, expect=403)
    assert not os.path.exists(state.grants_path), \
        "a refused grant must not create or write the grant file"


# -- execution goes through the enforcer ------------------------------------

def test_in_scope_execute_returns_a_sealed_receipt(console):
    state, base = console
    r = post(base, "/api/execute",
             {"host": "win11-victus", "capability": "filesystem.read",
              "params": {"path": "C:/Photos/a.png"}}, token=state.token)
    assert r["decision"]["decision"] == "ALLOW"
    assert r["result"]["text"] == "AAA"
    assert r["seal_ok"] is True


def test_out_of_scope_execute_is_denied_with_no_payload(console):
    state, base = console
    r = post(base, "/api/execute",
             {"host": "win11-victus", "capability": "filesystem.read",
              "params": {"path": "C:/Secrets/k.txt"}}, token=state.token)
    assert r["decision"]["decision"] == "DENY"
    assert r["decision"]["reason"] == "OUT_OF_SCOPE"
    assert r["result"] == {}
    assert "NEVER" not in json.dumps(r)


def test_ungranted_capability_through_the_console_is_denied(console):
    state, base = console
    r = post(base, "/api/execute",
             {"host": "win11-victus", "capability": "process.inspect",
              "params": {}}, token=state.token)
    assert r["decision"]["decision"] == "DENY"


def test_every_console_action_lands_in_the_ledger(console):
    state, base = console
    before = len(get(base, "/api/state", token=state.token)["receipts"])
    post(base, "/api/execute",
         {"host": "win11-victus", "capability": "system.info", "params": {}},
         token=state.token)
    post(base, "/api/execute",
         {"host": "win11-victus", "capability": "filesystem.read",
          "params": {"path": "C:/Secrets/k.txt"}}, token=state.token)
    after = get(base, "/api/state", token=state.token)["receipts"]
    assert len(after) == before + 2, "a refusal is recorded like anything else"
    assert after[-1]["decision"]["decision"] == "DENY"


# -- malformed input --------------------------------------------------------

def test_malformed_json_is_refused(console):
    state, base = console
    req = urllib.request.Request(
        f"{base}/api/execute?t={state.token}", data=b"{not json",
        headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 400


def test_params_must_be_an_object(console):
    state, base = console
    post(base, "/api/execute",
         {"host": "win11-victus", "capability": "system.info", "params": "all"},
         token=state.token, expect=400)


def test_plan_without_a_provider_is_503_not_a_guess(console):
    state, base = console
    r = post(base, "/api/plan", {"intent": "do something"},
             token=state.token, expect=503)
    assert "provider" in r["error"]


# -- the state block --------------------------------------------------------

def test_state_reports_scopes_and_awareness(console):
    state, base = console
    s = get(base, "/api/state", token=state.token)
    host = next(h for h in s["hosts"] if h["identity"]["host_id"] == "win11-victus")
    assert host["scopes"]["filesystem.read"]["roots"] == ["C:/Photos"]
    assert s["awareness"]["snapshot"]["power_epoch"] == 0
    granted = {c["id"]: c["state"] for c in host["capabilities"]}
    assert granted["filesystem.read"] == "GRANTED"
    assert granted["process.inspect"] == "AVAILABLE"


def test_the_avatar_token_reads_the_state(console):
    """R5's read side: the avatar token reads /api/state and /api/avatar,
    and its writes are refused (asserted in test_avatar_authority.py)."""
    state, base = console
    s = get(base, "/api/state", token=state.avatar_token)
    assert s["tier"] == "local"


# -- no-key world (AV6): no key is a complete product, not a crippled one ---

def test_no_key_everything_but_plan_works(console):
    state, base = console
    s = get(base, "/api/state", token=state.token)
    assert s["mode"] == "avatar"
    r = post(base, "/api/execute",
             {"host": "win11-victus", "capability": "system.info", "params": {}},
             token=state.token)
    assert r["decision"]["decision"] == "ALLOW"
    post(base, "/api/grant", {"capability": "filesystem.read",
                              "roots": ["C:/Photos"]}, token=state.token)
    post(base, "/api/revoke", {"capability": "filesystem.read"},
         token=state.token)
    get(base, "/api/avatar", token=state.avatar_token)
    r = post(base, "/api/plan", {"intent": "do something"},
             token=state.token, expect=503)
    assert "NEBIUS_API_KEY" in r["error"]


def test_plan_is_503_without_provider(console):
    state, base = console
    r = post(base, "/api/plan", {"intent": "do something"},
             token=state.token, expect=503)
    assert "no model provider configured" in r["error"]


def test_mode_event_at_start(console):
    state, _ = console
    events = state.avatar.since(0)
    assert events[0]["kind"] == "mode"
    assert events[0]["channel"] == "authority"
    assert events[0]["state"] == "idle"
    assert events[0]["provider"] == "none"
