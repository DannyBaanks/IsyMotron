"""M2: permission queue integration in the task runner (security profile)."""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for sub in ("", "core", "hosts", "agents"):
    p = str(REPO / sub) if sub else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

from agents.provider import ScriptedProvider
from relay.loopback import LoopbackRelay
from simulator.engines import ModernHost

import tools.link_task_runner as runner
from isymotron.link.permissions import PermissionQueue


def _security_relay():
    relay = LoopbackRelay()
    relay.attach(ModernHost(
        fs={"C:/Photos/a.png": "AAA"},
        granted=["filesystem.read"],
        grant_scopes={"filesystem.read": {"roots": ["C:/Photos"]}},
        tool_profile="security",
    ))
    return relay


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    sd = tmp_path / "link"
    sd.mkdir()
    monkeypatch.setattr(runner.link_identity, "state_dir", lambda: sd)
    return sd


def _queue(sd, cap="filesystem.read"):
    inbox = sd / "inbox.jsonl"
    inbox.write_text(json.dumps({
        "ts": "2026-10-06T20:00:00Z", "task_id": "task-m2", "from": "office-a",
        "title": "lee la foto", "body": "por favor lee la foto",
        "context": [], "status": "queued",
    }) + "\n", encoding="utf-8")


def _decide(state_dir, request_id, verdict):
    # The server-side queue fakes the phone's approval decision; grants are
    # file-backed on the same caps, so the mint path narrows via file scopes.
    host = ModernHost(
        fs={}, granted=["filesystem.read"],
        grant_scopes={"filesystem.read": {"roots": ["C:/Photos"]}},
        tool_profile="security",
    )
    q = PermissionQueue(state_dir, host)
    return q.decide(request_id, verdict, "office-phone-test")


def test_security_request_approve_then_done(state_dir):
    _queue(state_dir)
    reply = json.dumps({"understood": "read", "steps": [
        {"host": "win11-victus", "capability": "filesystem.read",
         "params": {"path": "C:/Photos/a.png"}, "why": "read"}],
        "refused": None})
    result_holder = {}

    def run():
        n = runner.process_inbox(_security_relay(), lambda: ScriptedProvider([reply, reply]),
                                 approvals_timeout_s=6.0)
        result_holder["n"] = n

    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(1.0)
    reqs = [json.loads(l) for l in (state_dir / "permission_requests.jsonl").read_text().splitlines()]
    assert reqs[-1]["status"] == "pending"
    got_it = _decide(state_dir, reqs[-1]["request_id"], "approve")
    assert got_it["status"] == "approved"
    t.join(timeout=10)
    entry = json.loads((state_dir / "inbox.jsonl").read_text().strip().splitlines()[-1])
    assert entry["status"] == "done"
    receipts = [json.loads(l) for l in (state_dir / "receipts.jsonl").read_text().splitlines()]
    kinds = [r["kind"] for r in receipts]
    assert "link_task_done" in kinds and "link_permission_decided" in kinds
    assert entry["tool_profile"] == "security"


def test_security_denial_marks_denied(state_dir):
    _queue(state_dir)
    reply = json.dumps({"understood": "read", "steps": [
        {"host": "win11-victus", "capability": "filesystem.read",
         "params": {"path": "C:/Photos/a.png"}}], "refused": None})
    holder = {}

    def run():
        holder["n"] = runner.process_inbox(_security_relay(), lambda: ScriptedProvider([reply, reply]),
                                           approvals_timeout_s=6.0)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(1.0)
    reqs = [json.loads(l) for l in (state_dir / "permission_requests.jsonl").read_text().splitlines()]
    _decide(state_dir, reqs[-1]["request_id"], "deny")
    t.join(timeout=10)
    entry = json.loads((state_dir / "inbox.jsonl").read_text().strip().splitlines()[-1])
    assert entry["status"] == "denied"
    assert entry["tool_profile"] == "security"


def test_security_timeout_denies(state_dir):
    _queue(state_dir)
    reply = json.dumps({"understood": "read", "steps": [
        {"host": "win11-victus", "capability": "filesystem.read",
         "params": {"path": "C:/Photos/a.png"}}], "refused": None})
    runner.process_inbox(_security_relay(), lambda: ScriptedProvider([reply, reply]),
                         approvals_timeout_s=1.0)
    entry = json.loads((state_dir / "inbox.jsonl").read_text().strip().splitlines()[-1])
    assert entry["status"] == "denied"
    receipts = [json.loads(l) for l in (state_dir / "receipts.jsonl").read_text().splitlines()]
    kinds = [r["kind"] for r in receipts]
    assert "link_task_denied" in kinds
