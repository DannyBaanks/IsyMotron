"""AV3 tests: the authority channel.

Only the IsyMotron process produces verdict visuals, over an authenticated
transport, with a second token the avatar can read with and never write with
(R5). Verdict text is logical (R6): a physical path never reaches a renderer.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from agents.provider import ScriptedProvider
from console.server import ConsoleState, serve
from isymotron.awareness import HostAwarenessEngine, TestPowerProvider
from relay.loopback import LoopbackRelay
from simulator.engines import LegacyHost, ModernHost


def build_console(tmp_path, provider_factory=None):
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
    state = ConsoleState(relay, awareness, str(tmp_path / "grants.json"),
                         provider_factory=provider_factory)
    httpd, _ = serve(state, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    return state, base, httpd


@pytest.fixture
def console(tmp_path):
    state, base, httpd = build_console(tmp_path)
    yield state, base
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def scripted_console(tmp_path):
    reply = json.dumps({
        "understood": "report system info",
        "steps": [{"host": "win11-victus", "capability": "system.info",
                   "params": {}, "why": "report"}],
        "refused": None,
    })
    state, base, httpd = build_console(tmp_path, lambda: ScriptedProvider([reply]))
    yield state, base
    httpd.shutdown()
    httpd.server_close()


def get(base, path, token=None, expect=200):
    sep = "&" if "?" in path else "?"
    url = f"{base}{path}" + (f"{sep}t={token}" if token else "")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            assert r.status == expect
            return json.loads(r.read()) if "json" in r.headers.get("Content-Type", "") else r.read()
    except urllib.error.HTTPError as exc:
        assert exc.code == expect, f"expected {expect}, got {exc.code}"
        return json.loads(exc.read() or b"{}")


def post(base, path, body, token=None, expect=200):
    sep = "&" if "?" in path else "?"
    url = f"{base}{path}" + (f"{sep}t={token}" if token else "")
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


def avatar(base, state, since=0):
    r = get(base, f"/api/avatar?since={since}", token=state.token)
    return r["events"], r["view"]


def verdicts(events):
    return [e for e in events if e.get("kind") == "verdict"]


# -- the endpoint and its tokens ---------------------------------------------

def test_avatar_endpoint_requires_a_token(console):
    state, base = console
    assert "error" in get(base, "/api/avatar", expect=401)
    assert "error" in get(base, "/api/avatar", token="nope", expect=401)
    r = get(base, "/api/avatar", token=state.token)
    assert "events" in r and "view" in r
    r = get(base, "/api/avatar", token=state.avatar_token)
    assert "events" in r and "view" in r


def test_avatar_token_cannot_post_anything(console):
    state, base = console
    bodies = {
        "/api/grant": {"capability": "filesystem.read", "roots": ["C:/"]},
        "/api/revoke": {"capability": "filesystem.read"},
        "/api/execute": {"host": "win11-victus", "capability": "system.info",
                         "params": {}},
        "/api/plan": {"intent": "do something"},
        "/api/run": {"plan": {}},
    }
    for path, body in bodies.items():
        r = post(base, path, body, token=state.avatar_token, expect=403)
        assert "read-only" in r["error"]
    # the read side still works with the avatar token (R5)
    get(base, "/api/state", token=state.avatar_token)
    get(base, "/api/avatar", token=state.avatar_token)


# -- verdicts come from real receipts -----------------------------------------

def test_deny_verdict_carries_receipt_and_seal(console):
    state, base = console
    r = post(base, "/api/execute",
             {"host": "win11-victus", "capability": "filesystem.read",
              "params": {"path": "C:/Secrets/k.txt"}}, token=state.token)
    assert r["decision"]["decision"] == "DENY"
    events, _ = avatar(base, state)
    vs = verdicts(events)
    assert len(vs) == 1
    v = vs[0]
    assert v["channel"] == "authority"
    assert v["decision"] == "DENY"
    assert v["reason"] == "OUT_OF_SCOPE"
    assert v["receipt_id"] == r["receipt_id"]
    assert v["seal_ok"] == r["seal_ok"]
    assert v["state"] == "error"
    assert v["host_id"] == "win11-victus"


def test_verdict_detail_is_logical(console):
    state, base = console
    post(base, "/api/execute",
         {"host": "win11-victus", "capability": "filesystem.read",
          "params": {"path": "C:/Secrets/k.txt"}}, token=state.token)
    events, _ = avatar(base, state)
    v = verdicts(events)[-1]
    dump = json.dumps(v, ensure_ascii=False)
    assert "\\" not in dump, "a physical path never reaches a renderer (R6)"
    assert "C:/" not in dump


def test_run_emits_one_verdict_per_receipt(console):
    state, base = console
    plan = {
        "understood": "read the same photo twice",
        "steps": [
            {"host": "win11-victus", "capability": "filesystem.read",
             "params": {"path": "C:/Photos/a.png"}, "why": "read"},
            {"host": "win11-victus", "capability": "filesystem.read",
             "params": {"path": "C:/Photos/a.png"}, "why": "read again"},
        ],
        "refused": None,
    }
    r = post(base, "/api/run", {"plan": plan}, token=state.token)
    assert r["completed"] is True
    assert len(r["steps"]) == 2
    events, _ = avatar(base, state)
    vs = verdicts(events)
    assert len(vs) == 2, "one verdict per receipt, not per request"
    for step, v in zip(r["steps"], vs):
        assert v["decision"] == "ALLOW"
        assert v["receipt_id"] == step["receipt_id"]
        assert v["capability"] == step["capability"]
        assert v["state"] == "success"


# -- the planning producers ----------------------------------------------------

def test_plan_emits_planning_then_planned(scripted_console):
    state, base = scripted_console
    r = post(base, "/api/plan", {"intent": "report system info"},
             token=state.token)
    assert r["verdict"] == "PLANNED"
    events, view = avatar(base, state)
    planning = [e for e in events if e.get("kind") == "planning"]
    planned = [e for e in events if e.get("kind") == "planned"]
    assert len(planning) == 1 and len(planned) == 1
    assert planning[0]["seq"] < planned[0]["seq"]
    assert planning[0]["channel"] == "authority"
    assert planning[0]["state"] == "thinking"
    assert planned[0]["state"] == "waiting"
    assert view["state"] == "waiting"
