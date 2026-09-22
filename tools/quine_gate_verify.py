"""Verify a Quine Gate evidence bundle offline.

    python tools/quine_gate_verify.py <bundle-dir> [--key KEY]
                                      [--genesis SHA] [--head SHA]

Prints a JSON report with one status per property and exits 0 only when every
required property is PASS. The signing key, if any, comes from --key or
ISYMOTRON_RECEIPT_KEY; it is never read from the bundle. The genesis and HEAD
anchors MUST be passed in from outside -- a bundle cannot anchor itself.
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

from isymotron.bundle import verify_bundle  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a Quine Gate bundle")
    parser.add_argument("bundle", help="directory containing receipt/claim/...")
    parser.add_argument("--key", default=None,
                        help="receipt signing key (else ISYMOTRON_RECEIPT_KEY)")
    parser.add_argument("--genesis", default=None,
                        help="externally published genesis sha (not read from the bundle)")
    parser.add_argument("--head", default=None,
                        help="externally published HEAD sha (not read from the bundle)")
    args = parser.parse_args(argv)

    report = verify_bundle(args.bundle, key=args.key,
                           anchored_genesis=args.genesis,
                           anchored_head=args.head)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
