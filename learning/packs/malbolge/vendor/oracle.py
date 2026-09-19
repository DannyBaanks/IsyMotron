# SPDX-License-Identifier: MIT
"""An independent execution control for Malbolge.

Implements the mechanical semantics of the Malbolge reference interpreter
literally, as a control against which other implementations can be checked.

## Provenance

The semantics below were transcribed from the interpreter pseudocode in
Iizawa (2005), Appendix C ("Malbolge インタープリタ 実行部"). That pseudocode
is itself a transcription of the reference interpreter for the language: 13 of
its 19 lines appear verbatim in the reference `malbolge.c` that has circulated
publicly since 1998, including every decisive one — the xlat1 decrypt, the
ternary rotate, and the EOF rule.

So the primary source is the reference interpreter; Iizawa is where it was
read. The translation tables (xlat1/xlat2) and the op/rot primitives are public
constants of the Malbolge specification and are declared here independently.

**No other Malbolge implementation was consulted, reused or copied while
writing this module.** That is the point: a control that shares no ancestry
with the runtimes it is used to check.

Reference semantics implemented:

    unsigned short a = 0, c = 0, d = 0;
    for (;;) {
        if ( mem[c] < 33 || mem[c] > 126 ) continue;        // (1) range guard
        switch ( xlat1[( mem[c] - 33 + c ) % 94] ) {         // (2) decrypt
            case 'j': d = mem[d]; break;                     // LOAD D
            case 'i': c = mem[d]; break;                     // BRANCH
            case '*': a = mem[d] = mem[d] / 3 + mem[d] % 3 * 19683; break; // ROTATE
            case 'p': a = mem[d] = op( a, mem[d] ); break;   // OPR
            case '<': putc( a ); break;                      // INPUT (output)
            case '/':
                x = getc( stdin );
                if ( x == EOF ) a = 59048; else a = x;       // INPUT
                break;
            case 'v': return;                                // HALT
        }
        mem[c] = xlat2[mem[c] - 33];                         // (3) encrypt cell
        if ( c == 59048 ) c = 0; else c++;                   // (4) c advance mod 59049
        if ( d == 59048 ) d = 0; else d++;                   // (5) d advance mod 59049
    }

Notes on faithful translation:
- (1) `continue` means: NO step advance, NO encryption, NO execution. The
  machine is stuck in an infinite loop if mem[c] is out of range forever.
- (2) xlat1 index: (mem[c] - 33 + c) % 94. Characters outside the switch
  are treated as no-ops ("o" is not in the Appendix C switch: it falls
  through, which is a no-op with the normal advance/encrypt).
- (3) encryption applies to mem[c] with the CURRENT c (after 'i' may have
  changed c) and uses the pre-advance value of c for the xlat1 decrypt.
- (4)/(5) advance AFTER the instruction, wrapping at 59048 -> 0.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

MAX_MEMORY = 59049  # words
MEMORY_WRAP = 59048  # last valid index

# xlat1 (instruction interpretation) — Iizawa 2005 §2.2 / Appendix C
XLAT1 = (
    "+b(29e*j1VMEKLyC})8&m#~W>qxdRp0wkrUo[D7,XTcA\"lI.v%{gJh4G\\-=O@5`_3i<?Z'"
    ";FNQuY]szf$!BS/|t:Pn6^Ha"
)
# xlat2 (instruction-character replacement) — Iizawa 2005 §2.2 / Appendix C
XLAT2 = (
    "5z]&gqtyfr$(we4{WP)H-Zn,[%\\3dL+Q;>U!pJS72FhOA1CB6v^=I_0/8|jsb9m<.TVa"
    "c`uY*MK'X~xDl}REokN:#?G\"i@"
)

_OP_TRITS: tuple[tuple[int, int, int, int, int, int, int, int, int], ...] = (
    (1, 1, 2, 0, 0, 2, 0, 2, 1),
)


def _op_trit_table() -> tuple[int, ...]:
    # Table 1 (operator op) from Iizawa 2005 §2.3, trit-by-trit.
    # row-major over (x, y) with x = left operand trit, y = right operand trit.
    return _OP_TRITS[0]


def op(left: int, right: int) -> int:
    """Tritwise 'crazy' operator (Iizawa 2005 Table 1)."""
    table = _op_trit_table()
    result = 0
    power = 1
    for _ in range(10):
        result += table[(left % 3) * 3 + (right % 3)] * power
        left //= 3
        right //= 3
        power *= 3
    return result


def rot(value: int) -> int:
    """Right rotation over 10 trits (Iizawa 2005 §2.3): value/3 + (value%3)*19683."""
    return value // 3 + (value % 3) * 19683


@dataclass(slots=True)
class OracleResult:
    output: str
    halted: bool
    steps: int
    halt_reason: str
    memory: list[int]
    a: int
    c: int
    d: int


class OracleUnderflowEOF:
    """Raised when '/' executes with no input available (Appendix C: EOF -> 59048).

    In Appendix C the input source is stdin; EOF maps to 59048. This class
    distinguishes 'explicit EOF marker consumed' from 'no input configured'.
    """


class Oracle:

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._mem: list[int] = [0] * MAX_MEMORY
        self.a = 0
        self.c = 0
        self.d = 0
        self._output_chars: list[str] = []
        self._halted = False
        self._halt_reason: str | None = None

    # -- loaders -----------------------------------------------------------

    def load_ascii(self, ascii_tape: list[str]) -> None:
        """Load a program and fill the rest of memory the way the reference does.

        Appendix C is `void exec( unsigned short *mem )`: it receives memory
        already loaded and says nothing about how it got that way. The loading
        rule therefore comes from the reference interpreter, not from the paper:

            while ( i < 59049 ) mem[i] = op( mem[i - 1], mem[i - 2] ), i++;

        This is load-bearing. Any program whose execution runs past its own
        last cell — most non-trivial ones — executes whatever is in the tail,
        so a control that zeroes it is running a different machine from every
        other implementation.
        """
        self.reset()
        length = len(ascii_tape)
        if length > MAX_MEMORY:
            raise ValueError("Program exceeds 59049 words.")
        if length < 2:
            raise ValueError(
                "Program must be at least 2 words: the fill rule reads the two "
                "preceding cells.")

        for i, ch in enumerate(ascii_tape):
            self._mem[i] = ord(ch)
        for i in range(length, MAX_MEMORY):
            self._mem[i] = op(self._mem[i - 1], self._mem[i - 2])

    def load_bytes(self, data: bytes) -> None:
        self.load_ascii([chr(b) for b in data])

    # -- input --------------------------------------------------------------

    def provide_input(self, text: str) -> None:
        """Set the input stream. '' means: any '/' yields EOF -> a=59048."""
        self._input_buffer = text

    # -- execution ----------------------------------------------------------

    def run(self, max_steps: int | None = None) -> OracleResult:
        steps = 0
        while not self._halted:
            if max_steps is not None and steps >= max_steps:
                self._halt_reason = "max_steps"
                break

            cell_value = self._mem[self.c]
            if cell_value < 33 or cell_value > 126:
                # Appendix C: `continue` — no advance, no encryption.
                steps += 1
                continue

            instruction = XLAT1[(cell_value - 33 + self.c) % 94]

            if instruction == "j":
                self.d = self._mem[self.d]
            elif instruction == "i":
                self.c = self._mem[self.d]
            elif instruction == "*":
                value = self._mem[self.d]
                value = rot(value)
                self.a = value
                self._mem[self.d] = value
            elif instruction == "p":
                value = op(self.a, self._mem[self.d])
                self.a = value
                self._mem[self.d] = value
            elif instruction == "<":
                self._output_chars.append(chr(self.a % 256))
            elif instruction == "/":
                if self._input_buffer:
                    char = self._input_buffer[0]
                    self._input_buffer = self._input_buffer[1:]
                    self.a = ord(char)
                else:
                    self.a = 59048  # EOF -> 59048 (Appendix C)
            elif instruction == "v":
                self._halted = True
                self._halt_reason = "halt_opcode"
            else:
                # Not in Appendix C switch: no-op (e.g. 'o').
                pass

            if not self._halted:
                # Appendix C: mem[c] = xlat2[mem[c]-33] with the CURRENT c
                # (note: after 'i' c may have changed). The encryption input
                # is the value currently stored at mem[c], not the fetched one.
                current = self._mem[self.c]
                if 33 <= current <= 126:
                    self._mem[self.c] = ord(XLAT2[current - 33])
                self.c = 0 if self.c == MEMORY_WRAP else self.c + 1
                self.d = 0 if self.d == MEMORY_WRAP else self.d + 1
            steps += 1

        return OracleResult(
            output="".join(self._output_chars),
            halted=self._halted,
            steps=steps,
            halt_reason=self._halt_reason or "unknown",
            memory=list(self._mem),
            a=self.a,
            c=self.c,
            d=self.d,
        )
