"""M0 walkthrough. Produces the receipts in evidence/M0/.

Run:  python tools/m0_demo.py

Six steps, in the order of roadmap section 31: describe the hosts, take a
narrow lease, do an allowed thing, get refused for an out-of-scope thing, move
a file between two unlike engines, verify every seal.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "core"), os.path.join(ROOT, "hosts")):
    sys.path.insert(0, p)

from clients.fake_mobile import FakeMobile          # noqa: E402
from relay.loopback import LoopbackRelay            # noqa: E402
from simulator.engines import LegacyHost, ModernHost  # noqa: E402

OUT = os.path.join(ROOT, "evidence", "M0")


def rule(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 62 - len(title)))


def show(rcpt) -> None:
    d = rcpt.decision
    mark = "ALLOW" if d.decision.value == "ALLOW" else f"DENY  {d.reason.value}"
    print(f"  [{mark}] {rcpt.capability} on {rcpt.host.host_id}")
    if d.detail:
        print(f"         {d.detail}")
    if rcpt.result:
        print(f"         result: {json.dumps(rcpt.result)[:96]}")
    print(f"         seal ok: {rcpt.verify()}  ({rcpt.seal[:23]}...)")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)

    modern = ModernHost(
        fs={
            "C:/Users/demo/Photos/shot.png": "PNGDATA",
            "C:/Users/demo/Secrets/keys.txt": "hunter2",
            "C:/Users/demo/NemoInbox/.keep": "",
        },
        granted=["filesystem.read", "filesystem.write", "apps.launch",
                 "system.info", "process.inspect"],
        grant_scopes={
            "filesystem.read": {"roots": ["C:/Users/demo/Photos"]},
            "filesystem.write": {"roots": ["C:/Users/demo/NemoInbox"]},
            "apps.launch": {"allowlist": ["notepad.exe"]},
            "system.info": {},
            "process.inspect": {},
        },
        host_id="win11-demo",
        display_name="Demo (Windows 11)",
    )
    legacy = LegacyHost(
        fs={"C:/NEMO/INBOX/.keep": "", "C:/GAMES/DOOM/DOOM.EXE": "MZ"},
        granted=["filesystem.read", "filesystem.write", "apps.launch", "system.info"],
        grant_scopes={
            "filesystem.read": {"roots": ["C:/GAMES"]},
            "filesystem.write": {"roots": ["C:/NEMO/INBOX"]},
            "apps.launch": {"allowlist": ["DOOM.EXE"]},
            "system.info": {},
        },
        host_id="win98-retrobox",
        display_name="RetroBox (Windows 98 SE)",
    )

    relay = LoopbackRelay()
    relay.attach(modern)
    relay.attach(legacy)
    phone = FakeMobile(relay, "mobile:demo-phone")
    receipts = []

    rule("1. describe() - what each device says it is")
    for h in phone.devices():
        d = relay.describe(h["host_id"])
        print(f"  {h['host_id']:16s} {h['os_release']:8s} engine={h['engine']:15s} "
              f"granted={len(d['granted'])}/{len(d['capabilities'])}")

    rule("2. the human approves one narrow lease")
    lease = phone.approve("win11-demo", "filesystem.read",
                          scope={"roots": ["C:/Users/demo/Photos"]}, ttl_s=300)
    print(f"  lease {lease.lease_id}")
    print(f"  capability {lease.capability}  scope {lease.scope}  ttl 300s")

    rule("3. an in-scope read")
    r = phone.act("win11-demo", "filesystem.read",
                  path="C:/Users/demo/Photos/shot.png")
    show(r); receipts.append(("01_read_allow", r))

    rule("4. the same capability, one directory over")
    r = phone.act("win11-demo", "filesystem.read", path="C:/Users/demo/Secrets/keys.txt")
    show(r); receipts.append(("02_read_out_of_scope", r))

    rule("5. a capability this host does not implement")
    r = phone.act("win98-retrobox", "process.inspect")
    show(r); receipts.append(("03_capability_unavailable", r))

    rule("6. cross-device: Win11 -> Win98, two engines, one contract")
    phone.approve("win98-retrobox", "filesystem.write")
    src = phone.act("win11-demo", "filesystem.read",
                    path="C:/Users/demo/Photos/shot.png")
    dst = phone.act("win98-retrobox", "filesystem.write",
                    path="C:/NEMO/INBOX/SHOT.PNG", content=src.result["text"])
    show(src); show(dst)
    receipts.append(("04_transfer_src", src))
    receipts.append(("05_transfer_dst", dst))

    rule("7. launch on the legacy engine")
    phone.approve("win98-retrobox", "apps.launch")
    r = phone.act("win98-retrobox", "apps.launch", app="DOOM.EXE")
    show(r); receipts.append(("06_legacy_launch", r))
    r = phone.act("win98-retrobox", "apps.launch", app="REGEDIT.EXE")
    show(r); receipts.append(("07_legacy_launch_denied", r))

    for name, rcpt in receipts:
        with open(os.path.join(OUT, f"{name}.json"), "w", encoding="utf-8") as fh:
            json.dump(rcpt.to_dict(), fh, indent=2, ensure_ascii=False)

    rule("summary")
    allowed = sum(1 for _, r in receipts if r.decision.decision.value == "ALLOW")
    print(f"  receipts written : {len(receipts)} -> evidence/M0/")
    print(f"  ALLOW / DENY     : {allowed} / {len(receipts) - allowed}")
    print(f"  seals verified   : {sum(1 for _, r in receipts if r.verify())}/{len(receipts)}")
    print(f"  relay hops       : {len(relay.log)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
