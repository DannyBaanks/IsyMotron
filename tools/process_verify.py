"""Verify that a process is the instance that was authorized.

    python3 tools/process_verify.py observe <pid>
    python3 tools/process_verify.py store   <pid> --baseline FILE
    python3 tools/process_verify.py verify  <pid> --baseline FILE

Exit codes: 0 PASS, 1 DENY, 2 ERROR / unsupported platform.

Read-only: this never signals, ptrace-attaches or modifies the process. The
baseline is a sealed file; the key comes from --key or ISYMOTRON_RECEIPT_KEY
and is never stored with it.
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

from isymotron.process import (  # noqa: E402
    DENY,
    ERROR,
    PASS,
    ProcessError,
    load_baseline,
    observe,
    save_baseline,
    verify,
)

EXIT = {PASS: 0, DENY: 1, ERROR: 2}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process identity verifier")
    parser.add_argument("command", choices=("observe", "store", "verify"))
    parser.add_argument("pid", type=int)
    parser.add_argument("--baseline", help="sealed baseline file (store/verify)")
    parser.add_argument("--key", default=None,
                        help="seal key (else ISYMOTRON_RECEIPT_KEY)")
    args = parser.parse_args(argv)

    if args.command in ("store", "verify") and not args.baseline:
        parser.error(f"{args.command} requires --baseline")
    if args.command == "verify" and not os.path.isfile(args.baseline):
        print(json.dumps({"status": ERROR, "reason": "NO_BASELINE",
                          "detail": args.baseline}))
        return EXIT[ERROR]

    try:
        if args.command == "observe":
            identity = observe(args.pid)
            print(json.dumps(identity.to_dict(), indent=2, ensure_ascii=False))
            return EXIT[PASS]

        if args.command == "store":
            identity = observe(args.pid)
            save_baseline(args.baseline, identity, key=args.key)
            print(json.dumps({"stored": args.baseline, "strength": identity.strength,
                              "fingerprint": identity.fingerprint}, indent=2))
            return EXIT[PASS]

        baseline = load_baseline(args.baseline, key=args.key)
        verdict = verify(args.pid, baseline)
        print(json.dumps(verdict.to_dict(), indent=2, ensure_ascii=False))
        return EXIT[verdict.status]
    except ProcessError as exc:
        print(json.dumps({"status": ERROR, "reason": exc.reason,
                          "detail": exc.detail}, ensure_ascii=False))
        return EXIT[ERROR]


if __name__ == "__main__":
    raise SystemExit(main())
