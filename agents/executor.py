"""The Executor (L0, despite living next to the agents).

It walks a plan, resolves references between steps, takes a lease per step and
executes. It contains no model call and never decides authority: every step is
still judged by the host's `Enforcer`, and a DENY stops the plan.

The reason this file exists is FINDINGS.md #3. A plan is a flat list, so when
step 2 needs step 1's output the model has nowhere to put that fact and writes
prose into a parameter -- `"content": "<content from previous step>"` -- which
would be sent to the host literally. Resolution has to be a mechanism, not a
convention, and the mechanism has to live below the model.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from isymotron.contracts import ExecutionReceipt, ExecutionRequest
from isymotron.verdicts import Decision

from .planner import Plan, _as_join, _as_reference

# Phrases a model reaches for when the schema gives it nowhere to express a
# data dependency. Sending any of these to a host means silently writing
# garbage, so they are refused at the boundary rather than executed.
PLACEHOLDER_MARKS = ("previous step", "step 1", "step 2", "from step",
                     "paso anterior", "<content", "<result", "<output",
                     "placeholder", "todo:", "tbd")


class UnresolvedReference(Exception):
    """A step depends on something that is not available. The plan stops."""


@dataclass
class ExecutedStep:
    index: int
    request: ExecutionRequest
    receipt: ExecutionReceipt

    @property
    def allowed(self) -> bool:
        return self.receipt.decision.decision is Decision.ALLOW


@dataclass
class Execution:
    plan_id: str
    steps: list[ExecutedStep]
    stopped_at: int | None = None
    stop_reason: str = ""

    @property
    def completed(self) -> bool:
        return self.stopped_at is None

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "completed": self.completed,
            "stopped_at": self.stopped_at,
            "stop_reason": self.stop_reason,
            "steps": [
                {"index": s.index, "capability": s.request.capability,
                 "host": s.request.host_id,
                 "decision": s.receipt.decision.to_dict(),
                 "receipt_id": s.receipt.receipt_id}
                for s in self.steps
            ],
        }


def looks_like_a_placeholder(value: Any) -> str | None:
    """Return the offending mark, or None. Case-insensitive, substring match."""
    if not isinstance(value, str):
        return None
    low = value.lower()
    for mark in PLACEHOLDER_MARKS:
        if mark in low:
            return mark
    return None


class Executor:
    def __init__(self, relay, subject: str, lease_ttl_s: float = 300.0) -> None:
        self.relay = relay
        self.subject = subject
        self.lease_ttl_s = lease_ttl_s

    def run(self, plan: Plan) -> Execution:
        results: dict[int, Mapping[str, Any]] = {}
        done: list[ExecutedStep] = []

        for i, step in enumerate(plan.steps, 1):
            try:
                params = self._resolve(step.params, results, i)
            except UnresolvedReference as exc:
                return Execution(plan.plan_id, done, stopped_at=i, stop_reason=str(exc))

            req = ExecutionRequest.make(step.host, self.subject, step.capability,
                                        params, plan_id=plan.plan_id)
            lease, decision = self.relay.request_lease(
                step.host, self.subject, step.capability, self.lease_ttl_s)
            if lease is None:
                return Execution(
                    plan.plan_id, done, stopped_at=i,
                    stop_reason=f"host refused a lease for {step.capability}: "
                                f"{decision.reason.value if decision.reason else '?'}")

            req = replace(req, lease_id=lease.lease_id)
            receipt = self.relay.execute(req)
            executed = ExecutedStep(i, req, receipt)
            done.append(executed)

            if not executed.allowed:
                reason = receipt.decision.reason
                return Execution(
                    plan.plan_id, done, stopped_at=i,
                    stop_reason=f"step {i} denied: {reason.value if reason else '?'}")

            results[i] = receipt.result

        return Execution(plan.plan_id, done)

    # -- reference resolution ----------------------------------------------
    def _resolve(self, params: Mapping[str, Any], results: Mapping[int, Mapping[str, Any]],
                 current: int) -> dict:
        out: dict[str, Any] = {}
        for key, value in params.items():
            ref = _as_reference(value)
            if ref is not None:
                out[key] = self._lookup(ref, results, current, key)
                continue
            parts = _as_join(value)
            if parts is not None:
                pieces = []
                for part in parts:
                    got = part if isinstance(part, str) else \
                        self._lookup(_as_reference(part), results, current, key)
                    if isinstance(got, bool) or not isinstance(got, (str, int, float)):
                        raise UnresolvedReference(
                            f"step {current}.{key} joins a {type(got).__name__}, "
                            "not a string")
                    pieces.append(str(got))
                out[key] = "".join(pieces)
                continue

            mark = looks_like_a_placeholder(value)
            if mark is not None:
                # The model tried to express a dependency in prose. Executing
                # this would write the placeholder text to a real file.
                raise UnresolvedReference(
                    f"step {current}.{key} looks like an unresolved placeholder "
                    f"({mark!r}); use {{\"$from\": {{...}}}} instead")
            out[key] = value
        return out

    @staticmethod
    def _lookup(ref, results: Mapping[int, Mapping[str, Any]], current: int, key: str) -> Any:
        src, field_name = ref
        if src not in results:
            raise UnresolvedReference(
                f"step {current}.{key} needs step {src}, which did not run")
        if field_name not in results[src]:
            raise UnresolvedReference(
                f"step {current}.{key} needs field {field_name!r} of step "
                f"{src}, which returned {sorted(results[src])}")
        return results[src][field_name]
