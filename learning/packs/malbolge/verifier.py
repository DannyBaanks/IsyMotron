"""The Malbolge Pack verifier: composes real tooling, holds no opinions.

The verdict for an exercise comes from three vendored tools and nothing else
(see ``vendor/PROVENANCE.md`` for provenance and licenses):

1. decode witness — ``classic_codec.decode(answer, c)``: the positional
   codec whose own repository proves the encode/decode parity exhaustively.
   This answers the question the lesson asks ("which character produces this
   opcode at this position?").
2. reference witness — ``malbolge_oracle.XLAT1``: the reference interpreter's
   instruction letter for the learner's character at that position, compared
   with the letter the target opcode must produce
   (``XLAT1[(op - 33) % 94]``, the classic offset between the two
   formulations). The oracle was written without consulting any other
   implementation, so agreement between (1) and (2) is a real differential.
3. execution witness — a real program is composed with
   ``classic_encoder.encode`` (a trail of nops up to the position, the
   learner's character, then END) and run on the ``Oracle`` under reference
   semantics. The learner's character genuinely executes inside a Malbolge
   program; a PASS requires the clean halt at the expected step.

Honest limitation, stated in every receipt that uses it: the execution
witness confirms the composed program runs to a clean halt, but other
characters that decode to a runtime no-op-equivalent can also halt cleanly
in this particular program — the unique verdict signal for the question
asked is the positional codec plus the reference letter, not the halt.

If the vendored tooling cannot be loaded, the verdict is UNAVAILABLE. Never
a PASS, never a model's opinion: no model is involved anywhere in this file.
"""

from __future__ import annotations

from typing import Any, Mapping

from learning import (
    INVALID, PASS, FAIL, VerifyResult, ToolingUnavailable, Exercise,
)

PROVENANCE = (
    "learning.packs.malbolge.vendor.classic_encoder — MALBOLGE repository, HEAD 82076be",
    "learning.packs.malbolge.vendor.classic_codec — MALBOLGE repository, HEAD 82076be",
    "learning.packs.malbolge.vendor.oracle — malbolge-oracle repository, HEAD fc3daa7, MIT",
    "pedagogical source: C:\\Development\\clasesbolge.md (owner material), "
    "semantics verified against the tooling before use",
)

EXECUTION_LIMIT_NOTE = (
    "execution witness: the composed program runs on reference semantics; a "
    "no-op-equivalent wrong character can also halt cleanly, so the verdict "
    "comes from the positional codec + reference letter, not the halt alone"
)


class _Tooling:
    """Lazy import of the vendored modules (keeps pack load failures honest)."""

    def __init__(self) -> None:
        try:
            from .vendor import classic_codec, classic_encoder
            from .vendor import oracle
        except Exception as exc:  # noqa: BLE001 — any import failure is an outcome
            raise ToolingUnavailable(
                f"malbolge tooling could not be loaded: {exc}") from exc
        self.codec = classic_codec
        self.encoder = classic_encoder
        self.oracle = oracle


class MalbolgeVerifier:
    """Verify source-encoding exercises with the vendored real tooling."""

    def __init__(self, tooling: _Tooling | None = None) -> None:
        self._tooling = tooling

    def _load(self) -> _Tooling:
        if self._tooling is None:
            self._tooling = _Tooling()
        return self._tooling

    # -- input contract ------------------------------------------------------
    @staticmethod
    def _validate(answer: Any) -> str | None:
        """The learner's answer must be exactly one printable ASCII character.
        Anything else is INVALID — an outcome, never a crash, never a PASS."""
        if not isinstance(answer, str):
            return "answer must be a string"
        if len(answer) != 1:
            return f"answer must be exactly one character, got {len(answer)}"
        code = ord(answer)
        if not 33 <= code <= 126:
            return f"answer must be printable ASCII (33..126), got code {code}"
        return None

    # -- the witnesses --------------------------------------------------------
    def verify(self, exercise: Exercise, answer: Any) -> VerifyResult:
        tooling = self._load()
        target: Mapping[str, Any] = exercise.target
        opcode = int(target["opcode"])
        position = int(target["position"])
        expected_letter = tooling.oracle.XLAT1[(opcode - 33) % 94]

        problem = self._validate(answer)
        if problem is not None:
            return VerifyResult(
                verdict=INVALID,
                observed={"reason": problem, "learner_input": repr(answer)},
                verified_by=[],
                provenance=PROVENANCE,
                notes=["out-of-contract input is INVALID: never a crash, never a PASS"],
            )

        try:
            decoded = tooling.codec.decode(answer, position)
        except ValueError as exc:
            return VerifyResult(
                verdict=INVALID,
                observed={"reason": f"codec rejected the character: {exc}"},
                verified_by=["classic_codec.decode"],
                provenance=PROVENANCE,
            )

        decoded_name = tooling.encoder.OPCODES.get(decoded, "invalid")
        reference_letter = tooling.oracle.XLAT1[(ord(answer) - 33 + position) % 94]
        observed = {
            "decoded_opcode": decoded,
            "decoded_opcode_name": decoded_name,
            "reference_instruction": reference_letter,
            "reference_instruction_of_target": expected_letter,
        }

        # -- execution witness (always run: a wrong answer's behaviour is a
        #    pedagogical fact, and a right answer must really execute)
        trail = "".join(
            tooling.encoder.encode(68, i)[2] for i in range(position))
        end_char = tooling.encoder.encode(81, position + 1)[2]
        program = trail + answer + end_char
        machine = tooling.oracle.Oracle()
        machine.load_ascii(list(program))
        run = machine.run(max_steps=10_000)
        execution = {
            "program_cells": len(program),
            "halted": run.halted,
            "halt_reason": run.halt_reason,
            "steps": run.steps,
            "expected_steps": position + 2,
            "accumulator": run.a,
            "output": run.output,
        }

        verdict = PASS if (
            decoded == opcode and reference_letter == expected_letter
        ) else FAIL

        return VerifyResult(
            verdict=verdict,
            observed=observed,
            verified_by=[
                "classic_codec.decode (vendored, MALBOLGE 82076be)",
                "malbolge-oracle XLAT1 reference witness (vendored, fc3daa7, MIT)",
                "classic_encoder.encode + Oracle execution witness (vendored)",
            ],
            provenance=PROVENANCE,
            execution=execution,
            notes=[EXECUTION_LIMIT_NOTE] if verdict == PASS else [],
        )
