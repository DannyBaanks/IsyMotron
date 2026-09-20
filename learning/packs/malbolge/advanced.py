"""Malbolge curriculum levels L3-L6, composed from the vendored oracle."""
from __future__ import annotations

from typing import Any, Mapping

from learning import FAIL, PASS, Exercise, Lesson, VerifyResult
from .vendor import classic_encoder, oracle

HELLO_WORLD = (
    "(=<`#9]~6ZY32Vx/4Rs+0No-&Jk)\"Fh}|Bcy?`=*z]Kw%oG4UUS0/@-ejc(:'8dc"
)

EXPLANATION = (
    "L3: A, C and D are registers; memory is 59049 trits-packed words.",
    "L4: crazy operation is a tritwise table, not ordinary integer arithmetic.",
    "L5: every executed cell is encrypted after the instruction runs.",
    "L6: these rules compose into executable programs, including Hello World!.",
)

EXERCISES = (
    Exercise(
        "malbolge-l3-registers",
        "At reset, what are the initial A, C and D registers? Answer A,C,D.",
        {"kind": "registers"},
        {"level": "L3", "registers": "0,0,0"},
    ),
    Exercise(
        "malbolge-l4-crazy-op",
        "The oracle's crazy operation is op(1, 2). What decimal value does it return?",
        {"kind": "crazy", "left": 1, "right": 2},
        {"level": "L4", "op": "op(1,2)", "value": 29525},
    ),
    Exercise(
        "malbolge-l5-encryption",
        "Does executing ROT at cell 0 change that cell after the instruction? Answer yes or no.",
        {"kind": "encryption"},
        {"level": "L5", "changed": True, "rotated_cell": 121},
    ),
    Exercise(
        "malbolge-l6-hello-world",
        "What exact output does the canonical 40-step program produce?",
        {"kind": "program"},
        {"level": "L6", "output": "Hello World!", "steps": 40},
    ),
)

LESSON = Lesson(
    "malbolge-semantics-3-to-6",
    "malbolge",
    "Malbolge lessons L3-L6 — registers, crazy op, encryption, programs",
    "malbolge-cat",
    EXPLANATION,
    ("The oracle is the witness: every answer below is checked by execution, not prose.",),
    EXERCISES,
)

PROVENANCE = (
    "learning.packs.malbolge.vendor.oracle — malbolge-oracle repository, HEAD fc3daa7, MIT",
    "learning.packs.malbolge.vendor.classic_encoder — MALBOLGE repository, HEAD 82076be",
)


class AdvancedMalbolgeVerifier:
    def verify(self, exercise: Exercise, answer: str) -> VerifyResult:
        kind = exercise.target["kind"]
        if kind == "registers":
            machine = oracle.Oracle()
            observed = {"a": machine.a, "c": machine.c, "d": machine.d}
            expected = "0,0,0"
            return self._result(answer.strip() == expected, observed, "reset")
        if kind == "crazy":
            value = oracle.op(exercise.target["left"], exercise.target["right"])
            return self._result(answer.strip() == str(value), {"op": value}, "op")
        if kind == "encryption":
            program = classic_encoder.encode(40, 0)[2] + classic_encoder.encode(81, 1)[2]
            machine = oracle.Oracle()
            machine.load_ascii(list(program))
            before = ord(program[0])
            run = machine.run(max_steps=2)
            observed = {"before": before, "after": run.memory[0], "changed": run.memory[0] != before}
            return self._result(answer.strip().lower() == "yes", observed, "encrypt-after-execute")
        if kind == "program":
            machine = oracle.Oracle()
            machine.load_ascii(list(HELLO_WORLD))
            run = machine.run(max_steps=100)
            observed = {"output": run.output, "steps": run.steps, "halted": run.halted}
            return self._result(answer == run.output, observed, "oracle.run")
        return VerifyResult(FAIL, {"reason": f"unknown exercise kind: {kind}"}, PROVENANCE)

    @staticmethod
    def _result(ok: bool, observed: Mapping[str, Any], witness: str) -> VerifyResult:
        return VerifyResult(
            verdict=PASS if ok else FAIL,
            observed=observed,
            verified_by=[f"malbolge-oracle {witness}"],
            provenance=PROVENANCE,
            execution=observed,
        )


def lesson() -> Lesson:
    return LESSON


def verifier() -> AdvancedMalbolgeVerifier:
    return AdvancedMalbolgeVerifier()
