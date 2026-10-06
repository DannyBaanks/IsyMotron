#!/usr/bin/env python3
"""Link task runner: the PC turns Link tasks into executed proof.

Tasks from a phone land in the Link inbox (``state_dir/inbox.jsonl``) with
``status: queued``. This runner claims each queued task, asks the configured
provider/planner for a plan over the real host contract, executes it through
the local authority (grants + Enforcer, same path as the console), and writes
the outcome back: ``done`` / ``denied`` / ``rejected`` / ``failed`` plus
receipt ids. The phone later observes the transition with the ``task`` op.

Nothing here bypasses the Enforcer: the planner proposes, the host decides.

Usage:
    python3 tools/link_task_runner.py --once          # drain the inbox once
    python3 tools/link_task_runner.py --watch 2       # poll every 2 seconds
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for sub in ("", "core", "hosts", "agents"):
    p = str(ROOT / sub) if sub else str(ROOT)
    if p not in sys.path:
        sys.path.insert(0, p)

from isymotron.link import identity as link_identity  # noqa: E402
from agents.executor import Executor  # noqa: E402
from agents.planner import Planner, PlanRejected  # noqa: E402
from agents.provider import Provider, ProviderError  # noqa: E402
from relay.loopback import LoopbackRelay  # noqa: E402

SUBJECT = "link:mobile"


def _inbox_path() -> Path:
    return link_identity.state_dir() / "inbox.jsonl"


def _receipts_path() -> Path:
    return link_identity.state_dir() / "receipts.jsonl"


def load_inbox() -> list[dict]:
    path = _inbox_path()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def save_inbox(entries: list[dict]) -> None:
    path = _inbox_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")
    tmp.replace(path)


def append_receipt(entry: dict) -> None:
    path = _receipts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def build_relay(grants_path: str | None):
    """Attach the real host exactly like the console does."""
    relay = LoopbackRelay()
    try:
        import native
        from windows.grants import DEFAULT_PATH, Grants

        relay.attach(native.real_host(Grants.load(grants_path or DEFAULT_PATH)))
    except Exception:
        # No real host on this machine: fall back is explicit and loud.
        print("link-task-runner: NOT_DEMONSTRATED: no real host backend; "
              "tasks will be rejected, not executed", flush=True)
    return relay


def run_task(relay, provider: Provider, task: dict) -> dict:
    intent = (str(task.get("title", "")) + "\n" + str(task.get("body", ""))).strip()
    if not intent:
        return {"status": "failed", "detail": "empty intent"}
    descs = [relay._host(h["host_id"]).describe() for h in relay.hosts()]
    try:
        plan = Planner(provider).plan(intent, descs, max_tokens=2000)
    except PlanRejected as exc:
        return {"status": "rejected", "detail": exc.detail or exc.reason}
    except ProviderError as exc:
        attribution = exc.outcome.attribution.value if exc.outcome else "UNKNOWN"
        return {"status": "failed", "detail": str(exc), "attribution": attribution}
    if plan.is_refusal() or not plan.steps:
        return {"status": "rejected", "detail": plan.refused or "the planner returned no steps"}

    execution = Executor(relay, f"{SUBJECT}:{task.get('from', '')}").run(plan)
    if execution.stop_reason and "NEEDS_APPROVAL" in execution.stop_reason:
        cap = None
        import re as _re
        m = _re.search(r"host refused a lease for (\S+): NEEDS_APPROVAL", execution.stop_reason)
        if m:
            cap = m.group(1)
        outcome = {"status": "needs_approval", "capability": cap}
        # derive a narrow approval scope from the step's params where possible
        params = {}
        if cap is not None:
            for s in plan.steps:
                if s.capability == cap:
                    params = dict(s.params)
                    break
        if cap and cap.startswith("filesystem.") and params.get("path"):
            from pathlib import PurePath
            outcome["derived_scope"] = {"roots": [str(PurePath(str(params["path"])).parent)]}
        elif cap == "apps.launch" and params.get("app"):
            from pathlib import PurePath
            outcome["derived_scope"] = {"allowlist": [PurePath(str(params["app"])).name]}
        else:
            outcome["derived_scope"] = {}
        outcome["params"] = params
        return outcome
    receipts = []
    denied = None
    for step in execution.steps:
        r = step.receipt
        receipts.append({
            "host": step.request.host_id,
            "capability": step.request.capability,
            "params": dict(step.request.params),
            "decision": r.decision.to_dict(),
            "receipt_id": r.receipt_id,
            "seal_ok": r.verify(),
        })
        if not step.allowed and denied is None:
            denied = r.decision.reason.value if r.decision.reason else "DENY"
    if denied is not None:
        return {"status": "denied", "detail": denied, "receipts": receipts}
    if execution.completed and receipts:
        summary = ""
        for step in execution.steps:
            result = step.receipt.result
            if isinstance(result, dict):
                summary = json.dumps(result, ensure_ascii=False)[:400]
            else:
                summary = str(result)[:400]
            if summary:
                break
        return {"status": "done", "result": summary, "receipts": receipts}
    return {
        "status": "failed",
        "detail": execution.stop_reason or "no steps executed",
        "receipts": receipts,
    }


def process_inbox(relay, provider_factory, limit: int | None = None, approvals_timeout_s: float = 60.0) -> int:
    entries = load_inbox()
    changed = False
    processed = 0
    for entry in entries:
        if entry.get("status") != "queued":
            continue
        entry["status"] = "running"
        save_inbox(entries)
        try:
            provider = provider_factory()
        except ProviderError as exc:
            entry.update({"status": "failed", "detail": str(exc)})
            append_receipt({
                "kind": "link_task_failed",
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "task_id": entry.get("task_id"),
                "detail": str(exc),
            })
        else:
            outcome, request_id = _run_with_approval_flow(relay, provider, entry, approvals_timeout_s)
            if request_id:
                entry["permission_request_id"] = request_id
            entry.update(outcome)
            profile = "unknown"
            try:
                first = relay.hosts()[0]
                profile = getattr(relay._host(first["host_id"]), "tool_profile", "unknown")
            except Exception:
                pass
            entry["tool_profile"] = profile
            append_receipt({
                "kind": f"link_task_{outcome['status']}",
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "task_id": entry.get("task_id"),
                "from": entry.get("from"),
                "receipts": outcome.get("receipts", []),
                "detail": outcome.get("detail"),
                "tool_profile": profile,
            })
        changed = True
        processed += 1
        if limit is not None and processed >= limit:
            break
    if changed:
        save_inbox(entries)
    return processed


def _permission_queue(relay):
    """Queue bound to the shared state dir (the Link server reads the same file)."""
    from isymotron.link.permissions import PermissionQueue
    from isymotron.link import identity as _ident

    first = relay.hosts()[0]
    host = relay._host(first["host_id"])
    return PermissionQueue(_ident.state_dir(), host)


def _derive_scope(cap: str | None, params: dict) -> dict:
    if cap and cap.startswith("filesystem.") and params.get("path"):
        from pathlib import PurePath
        return {"roots": [str(PurePath(str(params["path"])).parent)]}
    if cap == "apps.launch" and params.get("app"):
        from pathlib import PurePath
        return {"allowlist": [PurePath(str(params["app"])).name]}
    return {}


def _approval_outcome(queue, request_id, timeout_s):
    deadline = time.time() + max(float(timeout_s), 0.0)
    while time.time() < deadline:
        item = queue.local_status(request_id)
        if item is None:
            return "denied", "lost_request"
        if item["status"] == "approved":
            return "approved", item
        if item["status"] in ("denied", "expired"):
            return "denied", item.get("decision_reason", item["status"])
        time.sleep(min(0.5, max(deadline - time.time(), 0.0)))
    # mark expired locally so the phone's view and the ledger agree
    return "denied", "request_timeout"


def _run_with_approval_flow(relay, provider, task, approvals_timeout_s: float):
    outcome = run_task(relay, provider, task)
    if outcome.get("status") != "needs_approval":
        return outcome, None
    cap = outcome.get("capability")
    subject = f"{SUBJECT}:{task.get('from', '')}"
    try:
        queue = _permission_queue(relay)
    except Exception:
        return {"status": "failed", "detail": "no permission queue available"}, None
    # dedupe: reuse a pending request for the same subject+capability
    existing = None
    for item in queue.pending() + [
        e for it in queue._latest().values() for e in [it] if it.get("status") == "pending"
    ]:
        if item.get("subject") == subject and item.get("capability") == cap:
            existing = item
            break
    if existing is not None:
        request_id = existing["request_id"]
    else:
        scope = outcome.get("derived_scope") or _derive_scope(cap, outcome.get("params") or {})
        item = queue.submit({
            "subject": subject,
            "capability": cap,
            "scope": scope,
            "ttl_s": 120.0,
            "reason": f"{task.get('title', '')}: {task.get('body', '')}"[:280],
        })
        request_id = item["request_id"]
    # Persist the pending state so the phone/CLI sees the wait, not "queued".
    task["status"] = "pending_permission"
    task["permission_request_id"] = request_id
    try:
        _entries = load_inbox()
        for _e in _entries:
            if _e.get("task_id") == task.get("task_id"):
                _e.update({"status": "pending_permission", "permission_request_id": request_id})
        save_inbox(_entries)
    except Exception:
        pass
    decision, detail = _approval_outcome(queue, request_id, approvals_timeout_s)
    if decision == "approved":
        # The shared queue recorded the approval. The runner's own host gets
        # the exact same bound injected so the retry can lease it.
        scope = detail.get("scope") or {} if isinstance(detail, dict) else {}
        ttl = (detail.get("ttl_s") if isinstance(detail, dict) else None) or 120.0
        try:
            first = relay.hosts()[0]
            relay._host(first["host_id"]).record_external_approval(
                subject, cap, scope, ttl
            )
        except Exception:
            pass
        outcome = run_task(relay, provider, task)
        if isinstance(outcome, dict):
            outcome["permission_request_id"] = request_id
        return outcome, request_id
    return {"status": "denied", "detail": str(detail)}, request_id


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="process all queued tasks once")
    parser.add_argument("--watch", type=float, default=0.0, metavar="SECONDS",
                        help="poll the inbox every SECONDS")
    parser.add_argument("--grants", default=None, help="grants.json path")
    args = parser.parse_args(argv)

    def provider_factory() -> Provider:
        return Provider()

    relay = build_relay(args.grants)
    if not args.watch:
        n = process_inbox(relay, provider_factory)
        print(f"link-task-runner: processed {n} task(s)")
        return 0
    print(f"link-task-runner: watching every {args.watch}s")
    while True:
        process_inbox(relay, provider_factory)
        time.sleep(args.watch)


if __name__ == "__main__":
    raise SystemExit(main())
