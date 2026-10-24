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

from agents.executor import Executor
from agents.planner import Plan, PlanStep
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


def test_concurrent_inbox_append_survives_runner_update(state_dir, monkeypatch):
    _queue(state_dir)

    def fake_run_task(relay, provider, task):
        path = state_dir / "inbox.jsonl"
        with runner.locked(path):
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "ts": "2026-10-23T00:00:00Z", "task_id": "task-2",
                    "from": "office-b", "title": "new", "body": "later",
                    "context": [], "status": "queued",
                }) + "\n")
        return {"status": "done", "receipts": []}

    monkeypatch.setattr(runner, "run_task", fake_run_task)
    runner.process_inbox(_host_relay(), lambda: None)
    entries = [json.loads(line) for line in (state_dir / "inbox.jsonl").read_text().splitlines()]
    assert [e["task_id"] for e in entries] == ["task-1", "task-2"]
    assert entries[0]["status"] == "done"
    assert entries[1]["status"] == "queued"


def test_executor_resume_does_not_reexecute_completed_steps():
    host = ModernHost(
        fs={"C:/Photos/a.png": "AAA"},
        granted=["system.info", "filesystem.read"],
        grant_scopes={
            "system.info": {},
            "filesystem.read": {"roots": ["C:/Photos"]},
        },
        tool_profile="custom",
        custom={"capabilities": ["system.info"], "allow_request_prompts": True},
    )
    relay = LoopbackRelay()
    relay.attach(host)
    subject = "link:mobile:office-a"
    plan = Plan(
        understood="two steps",
        steps=[
            PlanStep(host=host.identify().host_id, capability="system.info", params={}),
            PlanStep(host=host.identify().host_id, capability="filesystem.read",
                     params={"path": "C:/Photos/a.png"}),
        ],
        refused=None,
        plan_id="plan-resume",
    )

    first = Executor(relay, subject).run(plan)
    assert first.stopped_at == 2
    assert "NEEDS_APPROVAL" in first.stop_reason
    assert len(first.steps) == 1
    first_receipt_id = first.steps[0].receipt.receipt_id

    host.record_external_approval(subject, "filesystem.read", {"roots": ["C:/Photos"]}, 120)
    resumed = Executor(relay, subject).run(
        plan,
        start_at=2,
        results={step.index: step.receipt.result for step in first.steps
                 if isinstance(step.receipt.result, dict)},
        done=list(first.steps),
    )
    assert resumed.completed
    assert len(resumed.steps) == 2
    assert resumed.steps[0].receipt.receipt_id == first_receipt_id
