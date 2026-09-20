"""Malbolge curriculum levels L3-L6, composed from the vendored oracle."""
from __future__ import annotations

from typing import Any, Mapping

from learning import FAIL, PASS, UNAVAILABLE, Exercise, Lesson, VerifyResult
from .vendor import classic_codec, classic_encoder, oracle
from .vendor import secondary
import hashlib
import json
from pathlib import Path

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
    Exercise("malbolge-l7-roundtrip", "Does opcode/source roundtrip preserve the canonical program? Answer yes or no.", {"kind": "roundtrip"}, {"level": "L7", "roundtrip": True}),
    Exercise("malbolge-l8-differential", "Do the primary oracle and an independent runner agree on Hello World!? Answer consistent or divergent.", {"kind": "differential"}, {"level": "L8", "result": "CONSISTENT"}),
    Exercise("malbolge-l9-existing", "What output does the published canonical Malbolge program produce?", {"kind": "existing"}, {"level": "L9", "output": "Hello World!"}),
    Exercise("malbolge-l10-quine", "Enter the recorded Lutter quine step count.", {"kind": "quine"}, {"level": "L10", "steps": 69547437, "scope": "EVIDENCE_ONLY"}),
    Exercise("malbolge-l11-lisp", "Can the MalbolgeLISP forensic image run in this pack? Answer yes or no.", {"kind": "unavailable", "level": "L11"}, {"level": "L11", "status": "NOT_DEMONSTRATED"}),
    Exercise("malbolge-l12-free", "Can MalbolgeFree run in the classic oracle? Answer yes or no.", {"kind": "unavailable", "level": "L12"}, {"level": "L12", "status": "NOT_DEMONSTRATED"}),
    Exercise("malbolge-l13-episodic", "Does a sealed output survive a one-bit tamper check? Answer yes or no.", {"kind": "episodic"}, {"level": "L13", "tamper_rejected": True}),
)

LESSON = Lesson(
    "malbolge-semantics-3-to-6",
    "malbolge",
    "Malbolge lessons L3-L13 — semantics, differential, quine and extensions",
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
        if kind == "roundtrip":
            source = HELLO_WORLD
            decoded = classic_codec.disassemble(source)
            rebuilt = classic_codec.assemble([item.opcode for item in decoded])
            return self._result(answer.strip().lower() == "yes", {"cells": len(source), "preserved": rebuilt == source}, "codec-roundtrip")
        if kind == "differential":
            primary = oracle.Oracle(); primary.load_ascii(list(HELLO_WORLD)); a = primary.run(max_steps=100)
            status, steps, output = secondary.run(HELLO_WORLD, max_steps=100)
            observed = {"primary": {"output": a.output, "steps": a.steps}, "secondary": {"output": output.decode(), "steps": steps, "status": status}}
            return self._result(answer.strip().upper() == "CONSISTENT", observed, "oracle-vs-independent-runner")
        if kind == "existing":
            machine = oracle.Oracle(); machine.load_ascii(list(HELLO_WORLD)); run = machine.run(max_steps=100)
            return self._result(answer == run.output, {"output": run.output, "steps": run.steps, "fixture": "canonical published Hello World!"}, "published-fixture")
        if kind == "episodic":
            payload = b"Hello World!"
            seal = hashlib.sha256(payload).hexdigest()
            tampered = b"I" + payload[1:]
            observed = {"seal": seal, "tamper_rejected": hashlib.sha256(tampered).hexdigest() != seal}
            return self._result(answer.strip().lower() == "yes", observed, "hash-linked-episode")
        if kind == "quine":
            witness_path = Path(__file__).resolve().parents[3] / "evidence" / "MALBOLGE_V0" / "lutter_quine_witness.json"
            witness = json.loads(witness_path.read_text(encoding="utf-8"))
            observed = {
                "steps": witness["steps"],
                "quine": witness["quine"],
                "source_sha256": witness["source_sha256"],
                "scope": witness["evidence_scope"],
            }
            ok = answer.strip() == str(witness["steps"])
            return VerifyResult(
                PASS if ok else FAIL, observed, ["lutter-quine-witness/1"],
                PROVENANCE, execution=None,
                notes=["evidence-only: source artifact is absent; this receipt does not claim re-execution"],
            )
        if kind == "unavailable":
            return VerifyResult(UNAVAILABLE, {"level": exercise.target["level"], "reason": "adapter/artifact not present in IsyMotron"}, [], PROVENANCE, notes=["NOT_DEMONSTRATED: no verdict is issued without the required tooling"])
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
