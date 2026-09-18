"""Drive the real Windows host from the command line.

    python tools/host_cli.py status
    python tools/host_cli.py grant filesystem.read --root "C:/Users/me/Pictures"
    python tools/host_cli.py grant apps.launch --app notepad.exe
    python tools/host_cli.py revoke filesystem.write
    python tools/host_cli.py do filesystem.read --path "C:/Users/me/Pictures"
    python tools/host_cli.py do system.info

This is the human sitting at the machine. It is the only thing that can widen
authority, and it writes to the grant file, never to a lease.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "core"), os.path.join(ROOT, "hosts")):
    sys.path.insert(0, p)

from isymotron.verdicts import Decision                 # noqa: E402
from relay.loopback import LoopbackRelay                # noqa: E402
from clients.fake_mobile import FakeMobile              # noqa: E402
from windows.grants import DEFAULT_PATH, Grants         # noqa: E402
from windows.win11 import CAPABILITIES, Win11Host       # noqa: E402

EVIDENCE = os.path.join(ROOT, "evidence", "M1")


def cmd_status(args) -> int:
    host = Win11Host(Grants.load(args.grants))
    d = host.describe()
    print(f"host      {d.identity.host_id}  ({d.identity.display_name})")
    print(f"engine    {d.identity.engine}   contract {d.identity.contract}")
    print(f"grants    {host.grants.source}")
    print(f"admin     {'GRANTED' if host.grants.admin_granted else 'not granted'}")
    print(f"lease cap {host.grants.max_lease_ttl_s:.0f}s")
    print()
    print(f"{'capability':22s} {'state':12s} scope")
    for cap in d.capabilities:
        state = "GRANTED" if cap.id in d.granted else "-"
        scope = host.grants.scopes.get(cap.id, {}) if cap.id in d.granted else {}
        print(f"{cap.id:22s} {state:12s} {json.dumps(scope) if scope else ''}")
    if not d.granted:
        print("\nNothing is granted. The host is inert: every request returns DENY.")
    return 0


def cmd_grant(args) -> int:
    g = Grants.load(args.grants)
    if g.source.startswith("<inert:"):
        g = Grants(host_id=g.host_id, display_name=g.display_name, granted=[], scopes={})

    known = {c.id for c in CAPABILITIES}
    if args.capability not in known:
        print(f"unknown capability {args.capability!r}; this engine has: "
              + ", ".join(sorted(known)))
        return 2

    scope = dict(g.scopes.get(args.capability, {}))
    if args.root:
        roots = list(dict.fromkeys(scope.get("roots", []) + [r.replace("\\", "/") for r in args.root]))
        scope["roots"] = roots
    if args.app:
        apps = list(dict.fromkeys(scope.get("allowlist", []) + list(args.app)))
        scope["allowlist"] = apps

    if args.capability not in g.granted:
        g.granted.append(args.capability)
    g.scopes[args.capability] = scope
    path = g.save(args.grants)
    print(f"granted {args.capability} -> {json.dumps(scope) if scope else '{} (empty scope = still denies)'}")
    print(f"written to {path}")
    return 0


def cmd_revoke(args) -> int:
    g = Grants.load(args.grants)
    if args.capability not in g.granted:
        print(f"{args.capability} was not granted")
        return 0
    g.granted.remove(args.capability)
    g.scopes.pop(args.capability, None)
    g.save(args.grants)
    print(f"revoked {args.capability}")
    return 0


def cmd_do(args) -> int:
    host = Win11Host(Grants.load(args.grants))
    relay = LoopbackRelay()
    relay.attach(host)
    phone = FakeMobile(relay, args.subject)

    lease = phone.approve(host.identify().host_id, args.capability, ttl_s=args.ttl)
    if lease is None:
        print(f"[DENY] the host refused to issue a lease for {args.capability}")
        print("       run: python tools/host_cli.py status")
        return 1

    params = {}
    if args.path:
        params["path"] = args.path
    if args.content is not None:
        params["content"] = args.content
    if args.app:
        params["app"] = args.app

    rcpt = phone.act(host.identify().host_id, args.capability, **params)
    _show(rcpt)

    if args.save:
        os.makedirs(EVIDENCE, exist_ok=True)
        out = os.path.join(EVIDENCE, f"{args.save}.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(rcpt.to_dict(), fh, indent=2, ensure_ascii=False)
        print(f"       receipt -> {os.path.relpath(out, ROOT)}")
    return 0 if rcpt.decision.decision is Decision.ALLOW else 1


def _show(rcpt) -> None:
    d = rcpt.decision
    head = "ALLOW" if d.decision is Decision.ALLOW else f"DENY {d.reason.value}"
    print(f"[{head}] {rcpt.capability} on {rcpt.host.host_id}")
    if d.detail:
        print(f"       {d.detail}")
    if rcpt.result:
        body = json.dumps(rcpt.result, ensure_ascii=False)
        print(f"       {body[:400]}{'...' if len(body) > 400 else ''}")
    print(f"       evidence={rcpt.evidence.value}  seal_ok={rcpt.verify()}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="host_cli", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grants", default=DEFAULT_PATH, help=f"grant file (default: {DEFAULT_PATH})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="show identity and what is granted").set_defaults(fn=cmd_status)

    g = sub.add_parser("grant", help="grant a capability (this is the local human)")
    g.add_argument("capability")
    g.add_argument("--root", action="append", help="add a filesystem root (repeatable)")
    g.add_argument("--app", action="append", help="add an app to the allowlist (repeatable)")
    g.set_defaults(fn=cmd_grant)

    r = sub.add_parser("revoke", help="revoke a capability")
    r.add_argument("capability")
    r.set_defaults(fn=cmd_revoke)

    d = sub.add_parser("do", help="take a lease and execute one capability")
    d.add_argument("capability")
    d.add_argument("--path")
    d.add_argument("--content")
    d.add_argument("--app")
    d.add_argument("--ttl", type=float, default=120.0)
    d.add_argument("--subject", default="cli:local")
    d.add_argument("--save", help="write the receipt to evidence/M1/<name>.json")
    d.set_defaults(fn=cmd_do)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
