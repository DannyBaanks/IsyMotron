"""Link task runner: queued task -> planner -> host enforcer -> done/denied/receipt."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for sub in ("", "core", "hosts", "agents"):
    p = str(ROOT / sub) if sub else str(ROOT)
    if p not in sys.path:
        sys.path.insert(0, p)

from agents.provider import ScriptedProvider
from relay.loopback import LoopbackRelay
from simulator.engines import ModernHost

import tools.link_task_runner as runner  # noqa: E402


def _host_relay():
    relay = LoopbackRelay()
    relay.attach(ModernHost(
        fs={"C:/Photos/a.png": "AAA"},
        granted=["filesystem.read", "system.info"],
        grant_scopes={"filesystem.read": {"roots": ["C:/Photos"]}, "system.info": {}},
    ))
    return relay


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    sd = tmp_path / "link"
    sd.mkdir()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(runner.link_identity, "state_dir", lambda: sd)
    return sd


def _queue(sd, title="lee la foto", body="léeme la foto del inbox"):
    inbox = sd / "inbox.jsonl"
    inbox.write_text(json.dumps({
        "ts": "2026-10-06T20:00:00Z", "task_id": "task-1", "from": "office-a",
        "title": title, "body": body, "context": [], "status": "queued",
    }) + "\n", encoding="utf-8")


def test_queued_task_becomes_done_with_receipt(state_dir):
    _queue(state_dir)
    reply = json.dumps({"understood": "info", "steps": [
        {"host": "win11-victus", "capability": "system.info",
         "params": {}, "why": "report"}], "refused": None})
    n = runner.process_inbox(_host_relay(), lambda: ScriptedProvider([reply]))
    assert n == 1
    entry = json.loads((state_dir / "inbox.jsonl").read_text().strip())
    assert entry["status"] == "done"
    assert entry["receipts"], "expected receipt ids in the task entry"
    receipts = [json.loads(l) for l in (state_dir / "receipts.jsonl").read_text().splitlines()]
    assert receipts[0]["kind"] == "link_task_done"
    assert receipts[0]["task_id"] == "task-1"


def test_hallucinated_capability_is_rejected_not_executed(state_dir):
    _queue(state_dir)
    reply = json.dumps({"understood": "x", "steps": [
        {"host": "win11-victus", "capability": "calendar.nuke",
         "params": {}, "why": "x"}], "refused": None})
    runner.process_inbox(_host_relay(), lambda: ScriptedProvider([reply]))
    entry = json.loads((state_dir / "inbox.jsonl").read_text().strip())
    assert entry["status"] == "rejected"
    detail = entry.get("detail", "")
    assert "calendar.nuke" in detail or "UNKNOWN_CAPABILITY" in detail


def test_out_of_scope_task_is_denied(state_dir):
    _queue(state_dir, title="lee esto", body="lee un secreto")
    reply = json.dumps({"understood": "read", "steps": [
        {"host": "win11-victus", "capability": "filesystem.read",
         "params": {"path": "C:/Secrets/k.txt"}, "why": "read"}], "refused": None})
    runner.process_inbox(_host_relay(), lambda: ScriptedProvider([reply]))
    entry = json.loads((state_dir / "inbox.jsonl").read_text().strip())
    assert entry["status"] == "denied"
    receipts = [json.loads(l) for l in (state_dir / "receipts.jsonl").read_text().splitlines()]
    assert receipts[0]["kind"] == "link_task_denied"


def test_provider_failure_marks_failed_loudly(state_dir):
    from agents.provider import ProviderError

    _queue(state_dir)

    def factory():
        raise ProviderError("no key configured")

    runner.process_inbox(_host_relay(), factory)
    entry = json.loads((state_dir / "inbox.jsonl").read_text().strip())
    assert entry["status"] == "failed"
    assert "no key configured" in entry["detail"]
