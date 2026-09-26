"""Local model providers (Ollama, llama.cpp) through the same seam.

A stub HTTP server speaks the OpenAI-compatible surface both servers expose
(`/v1/chat/completions`, `/v1/models`), so this suite proves the protocol and
the configuration without a model. What a real Llama plans is a live run, not
this file (docs/PROVIDERS.md).
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agents.planner import PlanRejected, Planner
from agents.provider import Provider, ProviderError
from simulator.engines import LegacyHost, ModernHost


class _Stub(BaseHTTPRequestHandler):
    """Records what it was sent; answers with whatever the test queued."""
    requests: list = []
    reply: str = "{}"

    def log_message(self, *a):
        pass

    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        _Stub.requests.append({"path": self.path, "headers": dict(self.headers)})
        self._send({"object": "list", "data": [{"id": "llama3.1:8b"}, {"id": "qwen2.5:0.5b"}]})

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(n))
        _Stub.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
        self._send({"model": body["model"], "choices": [
            {"message": {"role": "assistant", "content": _Stub.reply}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}})


@pytest.fixture
def stub(monkeypatch):
    for var in ("ISYMOTRON_PROVIDER", "ISYMOTRON_MODEL", "ISYMOTRON_BASE_URL",
                "OLLAMA_HOST", "OLLAMA_API_KEY", "LLAMACPP_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    _Stub.requests = []
    srv = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture
def world():
    modern = ModernHost(fs={"C:/Photos/a.png": "AAA"}, granted=["filesystem.read"],
                        grant_scopes={"filesystem.read": {"roots": ["C:/Photos"]}})
    legacy = LegacyHost(fs={"C:/NEMO/INBOX/.keep": ""}, granted=["filesystem.write"],
                        grant_scopes={"filesystem.write": {"roots": ["C:/NEMO/INBOX"]}})
    return [modern.describe(), legacy.describe()]


# -- configuration -------------------------------------------------------------

def test_ollama_needs_no_key_and_has_local_defaults(stub):
    p = Provider(name="ollama")
    assert p.configured() and not p.api_key
    assert p.base_url == "http://127.0.0.1:11434/v1"
    assert p.model == "llama3.1:8b"
    assert p.describe()["key_required"] is False


def test_llamacpp_preset(stub):
    p = Provider(name="llamacpp")
    assert p.configured()
    assert p.base_url == "http://127.0.0.1:8080/v1"


@pytest.mark.parametrize("value,expected", [
    ("127.0.0.1:11500", "http://127.0.0.1:11500/v1"),
    ("http://10.0.0.5:11434/", "http://10.0.0.5:11434/v1"),
])
def test_ollama_host_is_honoured(stub, monkeypatch, value, expected):
    monkeypatch.setenv("OLLAMA_HOST", value)
    assert Provider(name="ollama").base_url == expected


def test_explicit_base_url_beats_ollama_host(stub, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "10.0.0.5:11434")
    assert Provider(name="ollama", base_url=stub + "/v1").base_url == stub + "/v1"


def test_hosted_presets_still_require_a_key(stub):
    p = Provider(name="nebius", api_key="")
    assert not p.configured()
    with pytest.raises(ProviderError, match="NEBIUS_API_KEY"):
        p.complete([{"role": "user", "content": "hi"}])


def test_a_key_never_travels_over_plain_http_off_this_machine(stub):
    with pytest.raises(ProviderError, match="plain http"):
        Provider(name="ollama", base_url="http://10.0.0.5:11434/v1", api_key="secret")
    # https anywhere, or http on loopback, is fine
    Provider(name="ollama", base_url="https://ollama.example/v1", api_key="secret")
    Provider(name="ollama", base_url="http://localhost:11434/v1", api_key="secret")
    # no key: nothing to leak, a LAN Ollama is allowed
    Provider(name="ollama", base_url="http://10.0.0.5:11434/v1")


# -- the wire ------------------------------------------------------------------

def test_no_key_means_no_authorization_header(stub):
    p = Provider(name="ollama", base_url=stub + "/v1")
    c = p.complete([{"role": "user", "content": "hi"}])
    assert c.provider == "ollama" and c.model == "llama3.1:8b"
    sent = _Stub.requests[-1]
    assert sent["path"] == "/v1/chat/completions"
    assert "Authorization" not in sent["headers"]


def test_a_set_key_is_sent_to_a_loopback_server(stub):
    Provider(name="llamacpp", base_url=stub + "/v1", api_key="k-123").complete(
        [{"role": "user", "content": "hi"}])
    assert _Stub.requests[-1]["headers"]["Authorization"] == "Bearer k-123"


def test_models_lists_what_the_local_server_serves(stub):
    assert "llama3.1:8b" in Provider(name="ollama", base_url=stub + "/v1").models()


def test_json_mode_only_where_the_preset_declares_it(stub):
    Provider(name="ollama", base_url=stub + "/v1").complete(
        [{"role": "user", "content": "x"}], json_object=True)
    assert _Stub.requests[-1]["body"]["response_format"] == {"type": "json_object"}
    Provider(name="nebius", base_url=stub + "/v1", api_key="k").complete(
        [{"role": "user", "content": "x"}], json_object=True)
    assert "response_format" not in _Stub.requests[-1]["body"], \
        "hosted presets are unchanged: the prompt alone asks for JSON"


def test_a_stopped_local_server_says_how_to_start_it(stub):
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                                   # nothing listens here now
    import time
    from agents.provider import LocalServerDown
    p = Provider(name="ollama", base_url=f"http://127.0.0.1:{port}/v1")
    t0 = time.time()
    with pytest.raises(LocalServerDown) as e:
        p.complete([{"role": "user", "content": "hi"}])
    assert time.time() - t0 < 5, "a stopped local server fails fast, no 90 s backoff"
    assert e.value.attempts == 1 and e.value.transport
    assert "ollama serve" in str(e.value)


# -- the planner over a local model: authority is unchanged ---------------------

def test_planner_over_ollama_plans_in_json_mode(stub, world):
    _Stub.reply = json.dumps({"understood": "list photos", "refused": None, "steps": [
        {"host": "win11-victus", "capability": "filesystem.read",
         "params": {"path": "hostfs://photos"}, "why": "list"}]})
    plan = Planner(Provider(name="ollama", base_url=stub + "/v1")).plan("list my photos", world)
    assert [s.capability for s in plan.steps] == ["filesystem.read"]
    assert _Stub.requests[-1]["body"]["response_format"] == {"type": "json_object"}


def test_a_small_model_inventing_a_capability_is_refused(stub, world):
    """A weaker model yields more refusals, never more reach."""
    _Stub.reply = json.dumps({"understood": "x", "refused": None, "steps": [
        {"host": "win11-victus", "capability": "shell.exec",
         "params": {"cmd": "rm -rf /"}, "why": "helpful"}]})
    with pytest.raises(PlanRejected) as e:
        Planner(Provider(name="ollama", base_url=stub + "/v1")).plan("clean up", world)
    assert e.value.reason == "UNKNOWN_CAPABILITY"


def test_the_catalogue_sent_to_a_local_model_has_no_physical_path(stub, world):
    _Stub.reply = json.dumps({"understood": "", "refused": "nothing to do", "steps": []})
    Planner(Provider(name="ollama", base_url=stub + "/v1")).plan("hi", world)
    sent = json.dumps(_Stub.requests[-1]["body"])
    assert "C:/Photos" not in sent and "hostfs://photos" in sent
