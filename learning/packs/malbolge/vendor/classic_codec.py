"""Bidirectional positional codec for Malbolge Classic source.

This is a static assembler/disassembler. It exactly inverts the load-time
equation at each source position. Runtime jumps and self-encryption require a
trace decompiler and are deliberately outside this codec's claim.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

# VENDORED (see PROVENANCE.md beside this file): the only adaptation from the
# source at MALBOLGE HEAD 82076be is this import — sibling module, package-relative.
from .classic_encoder import OPCODES, encode

MEMORY_SIZE = 3 ** 10
NAME_TO_OPCODE = {name: opcode for opcode, name in OPCODES.items()}


@dataclass(frozen=True)
class Instruction:
    position: int
    character: str
    ascii: int
    opcode: int
    name: str
    valid: bool


def decode(character: str, position: int) -> int:
    """Decode one printable source character at its actual load position."""
    if len(character) != 1 or not 33 <= ord(character) <= 126:
        raise ValueError("character must be one printable ASCII byte (33..126)")
    return (ord(character) + position) % 94


def assemble(opcodes: list[int]) -> str:
    if len(opcodes) > MEMORY_SIZE:
        raise ValueError(f"program exceeds Classic memory ({MEMORY_SIZE} cells)")
    return "".join(encode(opcode, position)[2]
                   for position, opcode in enumerate(opcodes))


def disassemble(source: str) -> list[Instruction]:
    chars = [char for char in source if not char.isspace()]
    if len(chars) > MEMORY_SIZE:
        raise ValueError(f"program exceeds Classic memory ({MEMORY_SIZE} cells)")
    result = []
    for position, character in enumerate(chars):
        opcode = decode(character, position)
        result.append(Instruction(
            position=position,
            character=character,
            ascii=ord(character),
            opcode=opcode,
            name=OPCODES.get(opcode, "invalid"),
            valid=opcode in OPCODES,
        ))
    return result


def parse_plan(text: str) -> list[int]:
    tokens = text.replace(",", " ").split()
    result = []
    for token in tokens:
        lowered = token.lower()
        if lowered in NAME_TO_OPCODE:
            result.append(NAME_TO_OPCODE[lowered])
        else:
            result.append(int(token))
    return result


def parity() -> tuple[int, list[str]]:
    """Exhaustively prove decode(encode(op, c), c) for valid ops/all cells."""
    checked = 0
    problems = []
    for position in range(MEMORY_SIZE):
        for opcode in OPCODES:
            _, _, character = encode(opcode, position)
            decoded = decode(character, position)
            checked += 1
            if decoded != opcode:
                problems.append(
                    f"c={position} opcode={opcode} char={character!r} got={decoded}")
    return checked, problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Malbolge Classic bidirectional codec")
    commands = parser.add_subparsers(dest="command", required=True)
    asm = commands.add_parser("assemble")
    asm.add_argument("plan", help="comma/space-separated names or opcodes")
    dis = commands.add_parser("disassemble")
    dis.add_argument("source", help="source text, or a file with --file")
    dis.add_argument("--file", action="store_true")
    commands.add_parser("parity")
    args = parser.parse_args()

    if args.command == "assemble":
        plan = parse_plan(args.plan)
        print(assemble(plan))
        return 0
    if args.command == "disassemble":
        source = (Path(args.source).read_text(encoding="latin-1")
                  if args.file else args.source)
        for instruction in disassemble(source):
            print(f"{instruction.position:5d}  {instruction.character!r:4} "
                  f"ASCII={instruction.ascii:3d}  op={instruction.opcode:2d} "
                  f"{instruction.name}")
        return 0 if all(item.valid for item in disassemble(source)) else 1
    checked, problems = parity()
    if problems:
        print(f"PARITY FAIL: {len(problems)} / {checked}")
        print(problems[0])
        return 1
    print(f"PARITY PASS: {checked} positional instruction pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
