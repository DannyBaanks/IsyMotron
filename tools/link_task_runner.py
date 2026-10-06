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


def process_inbox(relay, provider_factory, limit: int | None = None) -> int:
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
            outcome = run_task(relay, provider, entry)
            entry.update(outcome)
            append_receipt({
                "kind": f"link_task_{outcome['status']}",
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "task_id": entry.get("task_id"),
                "from": entry.get("from"),
                "receipts": outcome.get("receipts", []),
                "detail": outcome.get("detail"),
            })
        changed = True
        processed += 1
        if limit is not None and processed >= limit:
            break
    if changed:
        save_inbox(entries)
    return processed


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
