r"""Malbolge Pack — lesson 1: source encoding (the vertical slice).

The pedagogical source is the owner's educational material
(`C:\Development\clasesbolge.md`, 2026-09-19). Every number in the lesson was
verified against executable tooling before being written here:

- the opcode table below is byte-identical to the vendored
  ``classic_encoder.OPCODES`` (MALBOLGE repository, HEAD ``82076be``), which
  the vendored ``malbolge-oracle`` independently agrees with: for every
  opcode, ``XLAT1[(op - 33) % 94]`` is the reference instruction letter with
  the meaning named here (verified 2026-09-19 for all eight);
- ``encode(68, 17) == '3'`` (the worked example and exercise 1) was executed
  with the vendored encoder and cross-checked against the oracle's XLAT1
  (reference letter ``'o'`` — a no-op in the reference switch).

The lesson text is deliberately small: what the learner needs to *derive*
the answer, not a dump of the source material.
"""

from __future__ import annotations

from learning import Exercise, Lesson

EXPLANATION = (
    "Classic Malbolge stores one printable ASCII character (33..126) per",
    "memory cell. At load position c, that character decodes to a normalized",
    "opcode:  op = (ASCII(char) + c) mod 94.",
    "",
    "The eight classic normalized opcodes:",
    "    4  jmp    5  out    23 in     39 rot",
    "    40 movd   62 opr    68 nop    81 end",
    "",
    "To WRITE a chosen instruction at position c, invert the decode:",
    "    r = (op - c) mod 94",
    "    ASCII = r   when 33 <= r <= 93",
    "    ASCII = r + 94   when 0 <= r <= 32     (fold into the printable range)",
    "    source character = chr(ASCII)",
)

WORKED_EXAMPLES = (
    "nop at position 3:  r = (68 - 3) mod 94 = 65 -> ASCII 65 -> 'A'.",
    "nop at position 17: r = (68 - 17) mod 94 = 51 -> ASCII 51 -> '3'.",
)

EXERCISES = (
    Exercise(
        exercise_id="malbolge-nop-17",
        prompt="The cat wants NOP at position 17. "
               "Which single printable character produces it?",
        target={"opcode": 68, "position": 17},
        expected={"opcode": 68, "opcode_name": "nop",
                  "reference_instruction": "o"},
    ),
    Exercise(
        exercise_id="malbolge-out-0",
        prompt="OUT at position 0. Which single printable character produces it?",
        target={"opcode": 5, "position": 0},
        expected={"opcode": 5, "opcode_name": "out",
                  "reference_instruction": "<"},
    ),
    Exercise(
        exercise_id="malbolge-end-2",
        prompt="END at position 2. Which single printable character produces it?",
        target={"opcode": 81, "position": 2},
        expected={"opcode": 81, "opcode_name": "end",
                  "reference_instruction": "v"},
    ),
)

LESSON = Lesson(
    lesson_id="malbolge-source-encoding-1",
    pack="malbolge",
    title="Malbolge lesson 1 — source encoding: from opcode to character",
    agent="malbolge-cat",
    explanation=EXPLANATION,
    worked_examples=WORKED_EXAMPLES,
    exercises=EXERCISES,
)
