"""Learn one pack lesson from the terminal.

    py -m learning malbolge                    interactive lesson
    py -m learning malbolge --exercise 1 --answer 3 --json
    isymotron learn malbolge --exercise 1 --answer 3

Exit codes carry the machine verdict:
    0 PASS   1 FAIL   2 INVALID   3 UNAVAILABLE   4 pack/lesson not found

The model is never asked, and nothing here can turn a model's opinion into a
verdict: the verifier's tooling produces one or the receipt says UNAVAILABLE.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _bootstrap_paths() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for sub in ("", "core", "hosts"):
        p = os.path.join(root, sub) if sub else root
        if p not in sys.path:
            sys.path.insert(0, p)


_bootstrap_paths()

from learning import (  # noqa: E402
    INVALID, PASS, FAIL, UNAVAILABLE, Lesson, Verifier,
    dump_receipt, project_line, verify_exercise,
)

EXIT_CODES = {PASS: 0, FAIL: 1, INVALID: 2, UNAVAILABLE: 3}

# The pack registry. Explicit, not magic: a pack joins when it is named here
# and nothing else imports it. Adding a future Python/Rust/Zig pack is adding
# one entry + one directory under learning/packs/ — the seam stays generic.
PACKS = {
    "malbolge": lambda: __import__(
        "learning.packs.malbolge", fromlist=["lesson", "verifier"]),
    "malbolge-advanced": lambda: __import__(
        "learning.packs.malbolge.advanced", fromlist=["lesson", "verifier"]),
}


def load_pack(pack_id: str) -> tuple[Lesson, Verifier]:
    if pack_id not in PACKS:
        raise KeyError(pack_id)
    module = PACKS[pack_id]()
    return module.lesson(), module.verifier()


def _print_receipt_lines(receipt) -> None:
    if "opcode" not in receipt.expected:
        print(f"  expected: {receipt.expected}")
        print(f"  observed: {receipt.observed}")
        if receipt.execution is not None:
            print(f"  execution: {receipt.execution}")
        for note in receipt.notes:
            print(f"  note: {note}")
        print(f"  VERDICT: {receipt.verdict}   (verdict_source: {receipt.verdict_source}; "
              f"receipt {receipt.receipt_id}; seal {'ok' if receipt.verify() else 'BROKEN'})")
        return
    print(f"  expected: opcode {receipt.expected.get('opcode')}"
          f" ({receipt.expected.get('opcode_name')})"
          f" — reference instruction {receipt.expected.get('reference_instruction')!r}")
    observed = receipt.observed
    if receipt.verdict == INVALID:
        print(f"  observed: {observed.get('reason', observed)}")
    else:
        print(f"  observed: opcode {observed.get('decoded_opcode')}"
              f" ({observed.get('decoded_opcode_name')})"
              f" — reference instruction {observed.get('reference_instruction')!r}")
    if receipt.execution is not None:
        ex = receipt.execution
        print(f"  execution: {ex.get('program_cells')}-cell program, "
              f"halted={ex.get('halted')} reason={ex.get('halt_reason')} "
              f"steps={ex.get('steps')} (expected {ex.get('expected_steps')})")
    for note in receipt.notes:
        print(f"  note: {note}")
    print(f"  VERDICT: {receipt.verdict}   (verdict_source: {receipt.verdict_source}; "
          f"receipt {receipt.receipt_id}; seal {'ok' if receipt.verify() else 'BROKEN'})")


def run(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="isymotron learn", description="one verifiable lesson")
    parser.add_argument("pack", help="a learning pack, e.g. malbolge")
    parser.add_argument("--exercise", help="exercise id-prefix or 1-based position")
    parser.add_argument("--answer", help="the learner's answer (scripted mode)")
    parser.add_argument("--all", action="store_true", help="run every exercise")
    parser.add_argument("--json", action="store_true",
                        help="print the receipt as JSON")
    parser.add_argument("--save", metavar="DIR",
                        help="write each receipt as JSON under DIR")
    parser.add_argument("--inbox", default=None,
                        help="project the lesson to this companion inbox "
                             "(default: the avatar inbox resolution)")
    parser.add_argument("--no-project", action="store_true",
                        help="do not announce through the pet")
    args = parser.parse_args(argv)

    try:
        lesson, verifier = load_pack(args.pack)
    except KeyError:
        print(f"no such learning pack: {args.pack!r} "
              f"(available: {', '.join(sorted(PACKS))})")
        return 4

    inbox = args.inbox
    if inbox is None and not args.no_project:
        from avatar.inbox import resolve_inbox_path
        inbox = str(resolve_inbox_path())

    print(f"\n  {lesson.agent} · {lesson.title}\n  {'-' * 60}\n")
    for line in lesson.explanation:
        print(f"  {line}" if line else "")
    print()
    for line in lesson.worked_examples:
        print(f"  worked example: {line}")
    print()

    if args.inbox:
        project_line(args.inbox, lesson,
                     f"{lesson.title} — prove the encoding, I will verify.")

    if args.exercise and not args.answer and not args.json:
        print(f"  --exercise needs --answer (scripted mode) or drop --exercise "
              f"to answer interactively.")
        return 2

    to_run = list(lesson.exercises) if args.all else (
        [lesson.exercise(args.exercise)] if args.exercise else [lesson.exercises[0]])

    worst = 0
    save_dir = Path(args.save) if args.save else None
    for index, exercise in enumerate(to_run, 1):
        print(f"  Exercise {index} ({exercise.exercise_id})")
        print(f"  {exercise.prompt}")
        answer = args.answer if (args.exercise and not args.all) else None
        if answer is None:
            try:
                answer = input("  your answer (one character): ").strip()
            except EOFError:
                answer = ""
        else:
            print(f"  your answer: {answer}")
        receipt = verify_exercise(lesson, verifier, exercise, answer)
        _print_receipt_lines(receipt)
        if args.inbox:
            project_line(args.inbox, lesson,
                         f"{exercise.exercise_id}: {receipt.verdict} — "
                         f"{receipt.observed.get('decoded_opcode_name', 'invalid')}"
                         f" decoded from {answer!r}. Receipt {receipt.receipt_id}.")
        print()
        if args.json:
            print(json.dumps(receipt.to_dict(), indent=2, ensure_ascii=False))
        if save_dir is not None:
            dump_receipt(receipt, save_dir / f"{receipt.receipt_id}.json")
        worst = max(worst, EXIT_CODES.get(receipt.verdict, 3))
    return worst


if __name__ == "__main__":
    raise SystemExit(run())
