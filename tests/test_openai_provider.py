"""OpenAI's GPT-6 request shape over the normal provider HTTP boundary."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agents.provider import Provider, ProviderError


class _OpenAIStub(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, *_args):
        pass

    def _send(self, payload):
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        type(self).requests.append({"method": "GET", "path": self.path})
        self._send({"data": [{"id": "gpt-6-luna"}, {"id": "gpt-6-astra"}]})

    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(length))
        type(self).requests.append({
            "method": "POST", "path": self.path, "headers": dict(self.headers),
            "body": body,
        })
        self._send({
            "model": body["model"],
            "choices": [{"message": {"role": "assistant", "content": "{}"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2},
        })


@pytest.fixture
def openai_stub(monkeypatch):
    for name in ("ISYMOTRON_PROVIDER", "ISYMOTRON_MODEL", "ISYMOTRON_BASE_URL",
                 "ISYMOTRON_REASONING_EFFORT", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    _OpenAIStub.requests = []
    server = HTTPServer(("127.0.0.1", 0), _OpenAIStub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    thread.join(timeout=2)


def test_openai_uses_gpt6_request_fields_and_bearer_key(openai_stub):
    provider = Provider(name="openai", base_url=openai_stub, api_key="test-secret")

    completion = provider.complete(
        [{"role": "user", "content": "Reply with JSON"}],
        max_tokens=128, temperature=0.1, json_object=True,
    )

    sent = _OpenAIStub.requests[-1]
    assert completion.text == "{}"
    assert sent["path"] == "/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer test-secret"
    assert sent["body"]["model"] == "gpt-6-luna"
    assert sent["body"]["max_completion_tokens"] == 128
    assert sent["body"]["reasoning_effort"] == "medium"
    assert sent["body"]["response_format"] == {"type": "json_object"}
    assert "temperature" not in sent["body"]
    assert "max_tokens" not in sent["body"]


def test_openai_none_reasoning_effort_allows_temperature_and_lists_models(
    openai_stub, monkeypatch,
):
    monkeypatch.setenv("ISYMOTRON_REASONING_EFFORT", "none")
    provider = Provider(name="openai", base_url=openai_stub, api_key="test-secret")

    provider.complete([{"role": "user", "content": "hi"}], temperature=0.35)

    body = _OpenAIStub.requests[-1]["body"]
    assert body["reasoning_effort"] == "none"
    assert body["temperature"] == 0.35
    assert provider.models() == ["gpt-6-astra", "gpt-6-luna"]


def test_openai_rejects_unknown_reasoning_effort(monkeypatch):
    monkeypatch.setenv("ISYMOTRON_REASONING_EFFORT", "turbo")

    with pytest.raises(ProviderError, match="invalid ISYMOTRON_REASONING_EFFORT"):
        Provider(name="openai", api_key="test-secret")
