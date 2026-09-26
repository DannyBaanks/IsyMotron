"""Claim H instrument: provider continuity as measured numbers.

The workload drives `agents/provider.py` against a stub server whose delays
and failures are scripted, so the statistics are exercised without a model
and without the network.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import provider_load  # noqa: E402
from agents.provider import Provider  # noqa: E402


class _Scripted(BaseHTTPRequestHandler):
    # script: per-request tuples (delay_s, status); repeats the last entry
    script: list[tuple[float, int]] = []
    seen: int = 0

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        self.rfile.read(n)
        delay, status = _Scripted.script[min(_Scripted.seen, len(_Scripted.script) - 1)]
        _Scripted.seen += 1
        if delay:
            time.sleep(delay)
        if status != 200:
            self.send_response(status)
            self.send_header("content-length", "2")
            self.end_headers()
            self.wfile.write(b"{}")
            return
        body = json.dumps({"model": "stub/0", "choices": [
            {"message": {"role": "assistant", "content": "OK"},
             "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 1}}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def stub(monkeypatch):
    for var in ("ISYMOTRON_PROVIDER", "ISYMOTRON_MODEL", "ISYMOTRON_BASE_URL",
                "OLLAMA_HOST"):
        monkeypatch.delenv(var, raising=False)
    _Scripted.seen = 0
    srv = HTTPServer(("127.0.0.1", 0), _Scripted)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


def _provider_at(url: str) -> Provider:
    p = Provider(name="llamacpp", model="stub/0")
    p.base_url = url
    return p


def test_clean_run_reports_zeros_and_quantiles(stub):
    _Scripted.script = [(0.01, 200)] * 6
    p = _provider_at(stub)
    workload = provider_load.run_workload(p, calls=6, interval_s=0, sleep=lambda s: None)
    s = provider_load.summarize(workload["samples"])
    assert s["calls"] == 6 and s["ok"] == 6 and s["errors"] == 0
    assert s["error_rate"] == 0.0
    assert s["latency_s"]["min"] >= 0.01
    assert s["latency_s"]["median"] <= s["latency_s"]["p95"] <= s["latency_s"]["max"]


def test_failures_are_counted_with_n_and_status(stub):
    # One persistent 400 (non-retryable) among successes.
    _Scripted.script = [(0, 200), (0, 400), (0, 400), (0, 400), (0, 400), (0, 200)]
    p = _provider_at(stub)
    workload = provider_load.run_workload(p, calls=2, interval_s=0, sleep=lambda s: None)
    s = provider_load.summarize(workload["samples"])
    assert s["calls"] == 2 and s["ok"] == 1 and s["errors"] == 1
    assert s["error_rate"] == 0.5
    assert s["error_statuses"] == ["400"]


def test_a_transient_503_is_a_slower_success_not_an_error(stub):
    # 503 once, then 200: the seam's retry hides it; the report must be
    # honest that errors are post-retry. Latency absorbs the backoff.
    _Scripted.script = [(0, 503), (0, 200)]
    p = _provider_at(stub)
    workload = provider_load.run_workload(p, calls=1, interval_s=0, sleep=lambda s: None)
    s = provider_load.summarize(workload["samples"])
    assert s["ok"] == 1 and s["errors"] == 0
    assert _Scripted.seen == 2, "the retry happened, the report counts the final outcome"


def test_report_writes_json_with_scope_and_n(stub, tmp_path):
    _Scripted.script = [(0, 200)] * 3
    p = _provider_at(stub)
    workload = provider_load.run_workload(p, calls=3, interval_s=0, sleep=lambda s: None)

    class Args:
        calls = 3
        interval = 0.0

    out = tmp_path / "nested" / "run.json"
    rep = provider_load.report(p, workload, Args())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep), encoding="utf-8")

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["contract"] == "provider-load/v0"
    assert data["summary"]["calls"] == 3
    assert "post-retry" in data["scope"]
    assert len(data["samples"]) == 3


def test_main_reports_and_returns_exit_code(stub, tmp_path, monkeypatch, capsys):
    _Scripted.script = [(0, 200)] * 4
    monkeypatch.setenv("ISYMOTRON_BASE_URL", stub)
    out = tmp_path / "run.json"
    rc = provider_load.main(["--provider", "llamacpp", "--model", "stub/0",
                             "--calls", "4", "--interval", "0", "--json", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["summary"]["calls"] == 4
    assert "measured" in capsys.readouterr().out


def test_main_fails_with_errors(stub, monkeypatch):
    _Scripted.script = [(0, 400)] * 10
    # no server at all: connect error is also a measured failure
    rc = provider_load.main(["--provider", "llamacpp", "--model", "stub/0",
                             "--calls", "2", "--interval", "0"])
    assert rc == 1
