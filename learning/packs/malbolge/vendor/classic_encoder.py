"""Manual Malbolge Classic character encoder.

Given the desired decoded opcode and the current c value, calculate the source
ASCII character using the Classic inverse:

    r = (opcode - c) mod 94
    ascii = r if r >= 33 else r + 94

This is deliberately only the character encoder. It does not simulate c/d,
the crazy transform, rotation, or post-execution memory mutation.
"""
from __future__ import annotations

import argparse

OPCODES = {
    4: "jmp",
    5: "out",
    23: "in",
    39: "rot",
    40: "movd",
    62: "opr",
    68: "nop",
    81: "end",
}
OPCODE_BY_NAME = {name: opcode for opcode, name in OPCODES.items()}


def encode(opcode: int, c: int) -> tuple[int, int, str]:
    """Return (residue, ascii, source_character)."""
    if not 0 <= opcode <= 93:
        raise ValueError("opcode must be in 0..93")
    residue = (opcode - c) % 94
    ascii_code = residue if residue >= 33 else residue + 94
    return residue, ascii_code, chr(ascii_code)


def describe(opcode: int, c: int) -> str:
    residue, ascii_code, char = encode(opcode, c)
    name = OPCODES.get(opcode, "unknown")
    return (f"c={c} opcode={opcode} ({name}) r={residue} "
            f"ASCII={ascii_code} char={char!r}")


def encode_program(program: str, start_c: int = 0) -> tuple[str, list[str]]:
    """Encode comma-separated opcode names/numbers and return source + trace."""
    source: list[str] = []
    trace: list[str] = []
    tokens = [token.strip() for token in program.split(",") if token.strip()]
    if not tokens:
        raise ValueError("program must contain at least one opcode")
    for offset, token in enumerate(tokens):
        try:
            opcode = OPCODE_BY_NAME[token.lower()] if not token.isdigit() else int(token)
        except KeyError as exc:
            raise ValueError(f"unknown opcode: {token}") from exc
        c = start_c + offset
        residue, ascii_code, char = encode(opcode, c)
        source.append(char)
        trace.append(f"c={c} opcode={opcode} r={residue} ASCII={ascii_code} char={char!r}")
    return "".join(source), trace


def main() -> int:
    parser = argparse.ArgumentParser(description="Encode one Malbolge Classic character")
    parser.add_argument("opcode", type=int, nargs="?", help="decoded opcode, 0..93")
    parser.add_argument("c", type=int, nargs="?", help="current c value")
    parser.add_argument("--table", action="store_true", help="show known opcodes for c")
    parser.add_argument("--program", help="encode comma-separated opcode names/numbers")
    parser.add_argument("--start-c", type=int, default=0, help="c for the first program opcode")
    parser.add_argument("--c-range", nargs=2, type=int, metavar=("START", "END"),
                        help="show one opcode across an inclusive c range")
    args = parser.parse_args()

    if args.program is not None:
        source, trace = encode_program(args.program, args.start_c)
        print(f"source={source!r}")
        for line in trace:
            print(line)
        return 0

    if args.table:
        if args.c is None:
            parser.error("--table requires c")
        for opcode, name in OPCODES.items():
            print(describe(opcode, args.c))
        return 0
    if args.c_range is not None:
        if args.opcode is None:
            parser.error("--c-range requires opcode")
        start, end = args.c_range
        for c in range(start, end + 1):
            print(describe(args.opcode, c))
        return 0
    if args.opcode is None or args.c is None:
        parser.error("provide opcode and c, or use --table/--c-range")
    print(describe(args.opcode, args.c))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
