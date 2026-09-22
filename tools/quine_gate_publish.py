"""Publish a Quine Gate head to the append-only transparency log.

    python3 tools/quine_gate_publish.py --genesis <sha> --head <sha> \
        [--commit <sha>] [--note "..."] [--log evidence/QUINE_GATE/HEADS.jsonl]

Appends one entry with the next sequence number and verifies the whole log.
Exit 0 only if the log still verifies after the append.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from isymotron.transparency import (  # noqa: E402
    TransparencyError,
    append_entry,
    verify_log,
    verify_log_file,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish a Quine Gate head")
    parser.add_argument("--genesis", required=True, help="anchored genesis sha")
    parser.add_argument("--head", required=True, help="published HEAD sha")
    parser.add_argument("--commit", default="",
                        help="commit that records the anchored evidence")
    parser.add_argument("--note", default="", help="free-form remark")
    parser.add_argument("--log", default=os.path.join(
        ROOT, "evidence", "QUINE_GATE", "HEADS.jsonl"))
    args = parser.parse_args(argv)

    try:
        before = verify_log_file(args.log)
        entry = append_entry(args.log, genesis=args.genesis, head=args.head,
                             commit=args.commit, note=args.note)
        after = verify_log_file(args.log)
    except TransparencyError as exc:
        print(f"REFUSED: the existing log does not read cleanly: {exc}")
        return 1

    print(json.dumps({
        "log": os.path.relpath(args.log, ROOT),
        "was": before.to_dict(),
        "appended": entry.to_dict(),
        "now": after.to_dict(),
    }, indent=2, ensure_ascii=False))
    if not after.passed:
        print("REFUSED: the log does not verify after the append")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
