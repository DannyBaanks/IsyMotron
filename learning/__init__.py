"""The learning seam: teach, exercise, verify, receipt.

IsyMotron core never learns a language's semantics. A *pack* does: it holds
lesson content, a verifier composed of real tooling, and the provenance of
that tooling. This seam holds the flow — explain, ask, receive an answer,
call the pack's verifier, seal a receipt — and nothing else.

Two invariants, both structural:

- the model is never part of a verdict. A verdict exists when the pack's
  tooling produced it, or it does not exist (UNAVAILABLE is an outcome,
  never a fallback to "the model said it was right");
- the receipt is sealed with the same canonical digest machinery as every
  other IsyMotron receipt (``isymotron.canon.digest``), so a lesson receipt
  is tamper-evident the same way a host receipt is.

The open channel (companion-event-v1 inbox lines) is the projection surface:
a pack may announce its lesson and the machine's verdict there, so the
desktop pet can say it. The projection is write-only speech — it can never
produce a receipt, and a receipt can never be read back from it.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field, fields, replace
from typing import Any, Callable, Mapping, Protocol, Sequence

# Bootstrap the import paths exactly the way conftest.py does for the test
# suite, so `import learning` works from anywhere in the repository (the
# seam reuses the canonical digest machinery from core).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "core"), os.path.join(_ROOT, "hosts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from isymotron.canon import digest
from isymotron.contracts import new_receipt_id

RECEIPT_CONTRACT = "learning-receipt-v1"

PASS = "PASS"
FAIL = "FAIL"
INVALID = "INVALID"
UNAVAILABLE = "UNAVAILABLE"
VERDICTS = frozenset({PASS, FAIL, INVALID, UNAVAILABLE})

# A verdict is machine-produced or it is not a verdict. This constant exists
# so a receipt can carry the distinction explicitly (compose requirement:
# "model said it was right" must be distinguishable from "tooling verified").
VERDICT_SOURCE = "machine"


@dataclass(frozen=True)
class Exercise:
    """One question with a machine-checkable answer spec.

    ``target`` is opaque to the seam — the pack's verifier owns its meaning.
    ``expected`` is the human-readable semantics that ends up in the receipt.
    """

    exercise_id: str
    prompt: str
    target: Mapping[str, Any]
    expected: Mapping[str, Any]


@dataclass(frozen=True)
class Lesson:
    lesson_id: str
    pack: str
    title: str
    agent: str
    explanation: Sequence[str]
    worked_examples: Sequence[str]
    exercises: Sequence[Exercise]

    def exercise(self, key: str) -> Exercise:
        """Find an exercise by id-prefix or by its 1-based position."""
        if key.isdigit():
            index = int(key) - 1
            if 0 <= index < len(self.exercises):
                return self.exercises[index]
        for exercise in self.exercises:
            if exercise.exercise_id.startswith(key):
                return exercise
        raise KeyError(f"no such exercise: {key}")


@dataclass(frozen=True)
class VerifyResult:
    """What the pack's tooling observed. Never produced by a model."""

    verdict: str
    observed: Mapping[str, Any]
    verified_by: Sequence[str]
    provenance: Sequence[str]
    execution: Mapping[str, Any] | None = None
    notes: Sequence[str] = ()


class Verifier(Protocol):
    def verify(self, exercise: Exercise, answer: str) -> VerifyResult: ...


class ToolingUnavailable(RuntimeError):
    """The pack's tooling could not be loaded. An outcome, never a PASS."""


@dataclass
class LessonReceipt:
    """Sealed record of one evaluated exercise.

    Reuses the canonical digest + receipt-id machinery; the payload is
    lesson-shaped, not host-shaped — a lesson PASS is a correctness fact
    about source encoding, never an authority ALLOW (that conflation is the
    one thing this receipt must make impossible to do by accident).
    """

    receipt_id: str
    lesson_id: str
    exercise_id: str
    learner_input: str
    verdict: str
    expected: Mapping[str, Any]
    observed: Mapping[str, Any]
    execution: Mapping[str, Any] | None
    verified_by: Sequence[str]
    provenance: Sequence[str]
    notes: Sequence[str]
    verdict_source: str
    started_at: float
    ended_at: float
    seal: str = ""

    def payload(self) -> dict:
        return {
            "contract": RECEIPT_CONTRACT,
            "receipt_id": self.receipt_id,
            "lesson_id": self.lesson_id,
            "exercise_id": self.exercise_id,
            "learner_input": self.learner_input,
            "verdict": self.verdict,
            "verdict_source": self.verdict_source,
            "expected": dict(self.expected),
            "observed": dict(self.observed),
            "execution": dict(self.execution) if self.execution is not None else None,
            "verified_by": list(self.verified_by),
            "provenance": list(self.provenance),
            "notes": list(self.notes),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }

    def sealed(self) -> "LessonReceipt":
        return replace(self, seal=digest(self.payload()))

    def verify(self) -> bool:
        return bool(self.seal) and self.seal == digest(self.payload())

    def to_dict(self) -> dict:
        data = self.payload()
        data["seal"] = self.seal
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LessonReceipt":
        """Round-trip a receipt from its JSON. Unknown keys are dropped; a
        tampered value still fails its own seal at ``verify()``."""
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


def verify_exercise(lesson: Lesson, verifier: Verifier, exercise: Exercise,
                    answer: str, *, now_fn: Callable[[], float] | None = None) -> LessonReceipt:
    """Run one exercise through the pack's verifier and seal the outcome.

    If the verifier cannot load its tooling, the receipt says UNAVAILABLE —
    it never falls back to any model's opinion.
    """
    clock = now_fn or time.time
    started = clock()
    result: VerifyResult
    try:
        result = verifier.verify(exercise, answer)
        if result.verdict not in VERDICTS:
            raise ToolingUnavailable(
                f"verifier returned an unknown verdict: {result.verdict!r}")
    except ToolingUnavailable as exc:
        result = VerifyResult(
            verdict=UNAVAILABLE,
            observed={"reason": str(exc)},
            verified_by=[],
            provenance=[],
            notes=["no tooling, no verdict — an unavailable verifier never produces PASS"],
        )
    receipt = LessonReceipt(
        receipt_id=new_receipt_id(),
        lesson_id=lesson.lesson_id,
        exercise_id=exercise.exercise_id,
        learner_input=answer,
        verdict=result.verdict,
        expected=dict(exercise.expected),
        observed=dict(result.observed),
        execution=dict(result.execution) if result.execution is not None else None,
        verified_by=list(result.verified_by),
        provenance=list(result.provenance),
        notes=list(result.notes),
        verdict_source=VERDICT_SOURCE,
        started_at=started,
        ended_at=clock(),
    )
    return receipt.sealed()


def project_line(inbox_path, lesson: Lesson, text: str, *,
                 now_fn: Callable[[], float] | None = None,
                 event_id: str | None = None) -> bool:
    """Append one companion-event-v1 `say` line — the cat speaks.

    Pure third-party speech on the open channel: it can announce a verdict
    that already happened, it can never produce or alter one. Failures to
    write are swallowed (the lesson does not depend on the pet being up).
    """
    from pathlib import Path

    path = Path(inbox_path)
    event = {
        "id": event_id or f"learn-{uuid.uuid4().hex[:12]}",
        "agent": lesson.agent,
        "type": "say",
        "text": text,
        "created_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime((now_fn or time.time)())),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def dump_receipt(receipt: LessonReceipt, path) -> None:
    """Write one receipt as JSON, per the evidence conventions."""
    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt.to_dict(), indent=2, ensure_ascii=False),
                      encoding="utf-8")


__all__ = [
    "PASS", "FAIL", "INVALID", "UNAVAILABLE", "VERDICTS", "VERDICT_SOURCE",
    "Exercise", "Lesson", "LessonReceipt", "VerifyResult", "Verifier",
    "ToolingUnavailable", "verify_exercise", "project_line", "dump_receipt",
    "RECEIPT_CONTRACT",
]
