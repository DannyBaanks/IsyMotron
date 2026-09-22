"""Quine Gate live demo — the judge-facing sequence.

    python tools/quine_gate_demo.py [--out evidence/QUINE_GATE]

Runs the five steps a judge asks for, each with its expected verdict:

  1. legitimate receipt          -> PASS   (re-derived, not trusted)
  2. DENY->ALLOW, re-sealed     -> REJECT (re-derivation catches it)
  3. fork from the same parent   -> CONFLICT
  4. rollback to an older state -> CONFLICT
  5. anchored chain + bundle    -> PASS

Then writes a sealed demo package into --out: receipt.json, claim.json,
chain.json, RUN.md and a hashes.json manifest over all four. The genesis and
HEAD anchors are printed (and recorded in RUN.md); a bundle cannot anchor
itself, so the trust root is the git commit that records them.

Exits 0 only if every step produced its expected verdict. A JSON footer after
the `=== DEMO_RESULT_JSON ===` marker is machine-readable (used by the tests).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import platform
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "core"), os.path.join(ROOT, "hosts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from isymotron.bundle import verify_bundle                     # noqa: E402
from isymotron.canon import digest                             # noqa: E402
from isymotron.chain import make_state                          # noqa: E402
from isymotron.contracts import ExecutionRequest, PolicyDecision  # noqa: E402
from isymotron.evidence import sha256_file                     # noqa: E402
from isymotron.genealogy import (                              # noqa: E402
    Genealogy,
    Transition,
    verify_genealogy,
)
from isymotron.seal import resolve_key                         # noqa: E402
from isymotron.verdicts import Decision                        # noqa: E402
from isymotron.verify import verify_receipt                    # noqa: E402
from simulator.engines import ModernHost                        # noqa: E402

SUBJECT = "mobile:demo-phone"
HOST_ID = "win11-demo"
IN_SCOPE = "C:/Users/demo/Photos/shot.png"
OUT_OF_SCOPE = "C:/Users/demo/Secrets/keys.txt"
ARTIFACTS = ("receipt.json", "claim.json", "chain.json", "RUN.md")


def _rule(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 62 - len(title)))


def _build_host() -> ModernHost:
    """The same neutral fixtures as tools/m0_demo.py: no real paths, no PII."""
    return ModernHost(
        fs={IN_SCOPE: "PNGDATA", OUT_OF_SCOPE: "hunter2",
            "C:/Users/demo/NemoInbox/.keep": ""},
        granted=["filesystem.read"],
        grant_scopes={"filesystem.read": {"roots": ["C:/Users/demo/Photos"]}},
        host_id=HOST_ID,
        display_name="Demo (Windows 11)",
    )


def _scenario(host: ModernHost, path: str):
    """One real execution through the contract: lease, request, receipt, claim."""
    lease, _ = host.request_lease(SUBJECT, "filesystem.read", 300)
    request = ExecutionRequest.make(HOST_ID, SUBJECT, "filesystem.read",
                                    {"path": path}, lease_id=lease.lease_id)
    receipt = host.execute_capability(request)
    return receipt, host.claim_bundle(receipt.receipt_id)


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:  # pragma: no cover - cosmetic
        return "unknown"


def _run_md(out: Path, receipt, steps: dict, anchors: dict) -> str:
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    verdict_rows = "\n".join(
        f"| {i+1}. {name} | `{expected}` | {'yes' if ok else 'NO'} |"
        for i, (name, ok, expected) in enumerate(steps))
    return f"""# Quine Gate demo run — {stamp}

Status: `{'DEMONSTRATED' if all(ok for _, ok, _ in steps) else 'FAILED'}`, scoped to
the sealed-receipt/re-derivation gate on the simulated demo host.

Every step below ran in-process against the real `Enforcer`; nothing was
inspected by eye or accepted on the model's word.

## Environment

| Fact | Value |
|---|---|
| Date (UTC) | {stamp} |
| Host | {platform.system()} {platform.release()} |
| Python | {platform.python_version()} |
| Repository commit at run time | `{_git_commit()}` |
| Signing key | `{'present (ISYMOTRON_RECEIPT_KEY)' if resolve_key() else 'absent: receipts are unkeyed (integrity only)'}` |

## Exact command

```bash
python3 tools/quine_gate_demo.py --out evidence/QUINE_GATE
```

## Result per step

| Step | Expected | Observed |
|---|---|---|
{verdict_rows}

Receipt in the bundle: `{receipt.receipt_id}` —
`{receipt.decision.decision.value}`
({receipt.decision.reason.value if receipt.decision.reason else 'no reason'}),
re-derivable because `{receipt.claim_digest[:23]}…` names its claim.

## Anchors (the trust root is the commit that records them)

A bundle cannot anchor itself. Verify this package with the values below,
taken from this committed file:

```bash
python3 tools/quine_gate_verify.py evidence/QUINE_GATE \\
    --genesis {anchors['genesis']} \\
    --head {anchors['head']}
```

- genesis: `{anchors['genesis']}`
- HEAD: `{anchors['head']}`

To rotate the demo: re-run the generator, commit the result, and (optional but
stronger) publish the new HEAD with `git tag evidence-head-<n>`.

## Not demonstrated

- That the run *occurred* on any particular machine: reproduction proves
  validity, not occurrence.
- Host attestation (TPM/TEE/measured boot): out of scope by design.
- The *effect* of an ALLOW (a real file read): the gate re-derives the
  decision; it does not replay the filesystem.
"""


def run_demo(out: Path) -> dict:
    key = resolve_key()
    host = _build_host()
    steps: list[tuple[str, bool, str]] = []

    # -- 1. legitimate DENY receipt, accepted because it re-derives ---------
    _rule("1. legitimate receipt (out-of-scope read -> DENY)")
    deny_receipt, deny_claim = _scenario(host, OUT_OF_SCOPE)
    legit = verify_receipt(deny_receipt, deny_claim, key)
    print(f"  decision : {deny_receipt.decision.decision.value}"
          f" ({deny_receipt.decision.reason.value if deny_receipt.decision.reason else '?'})")
    print(f"  rederive : {legit.status} — {legit.reason}")
    steps.append(("legit_receipt", legit.passed, "PASS"))

    # -- 2. the M0 attack: DENY -> ALLOW, re-sealed, still rejected ---------
    _rule("2. mutate DENY -> ALLOW and re-seal the receipt")
    forged = replace(deny_receipt, decision=PolicyDecision(Decision.ALLOW)).sealed(key=key)
    caught = verify_receipt(forged, deny_claim, key)
    print(f"  forged seal self-consistent : {forged.verify(key)}")
    print(f"  verifier                   : {caught.status} — {caught.reason}")
    steps.append(("mutated_receipt", not caught.passed, "REJECT"))

    # -- 3/4/5. the state genealogy under anchored GENESIS + HEAD ------------
    _rule("3-5. genealogy S0 -> S1(allow) -> S2(deny), anchored")
    ledger = Genealogy()
    ledger.start(Transition.genesis(label="S0"))
    allow_receipt, _ = _scenario(host, IN_SCOPE)
    ledger.append(ledger.head, Transition.from_receipt(allow_receipt, label="S1"))
    ledger.append(ledger.head, Transition.from_receipt(deny_receipt, label="S2"))
    states = ledger.states()
    print(f"  chain    : {' -> '.join(s['transition']['label'] for s in states)}")
    print(f"  parent linkage : "
          f"{all(states[i + 1]['parent'] == states[i]['sha'] for i in range(len(states) - 1))}")

    fork_tip = make_state(states[1]["sha"], Transition(
        kind="execute", label="S2-forged", operation="filesystem.write",
        output_digest=digest({"wrote": "stolen"})).to_dict())
    fork = verify_genealogy([states[0], states[1], fork_tip],
                            anchored_genesis=ledger.genesis, anchored_head=ledger.head)
    print(f"  fork     : {fork.status} — {fork.reason}")
    steps.append(("fork", fork.status == "CONFLICT", "CONFLICT"))

    rollback = verify_genealogy([states[0], states[1]],
                                anchored_genesis=ledger.genesis, anchored_head=ledger.head)
    print(f"  rollback : {rollback.status} — {rollback.reason}")
    steps.append(("rollback", rollback.status == "CONFLICT", "CONFLICT"))

    ok_chain = verify_genealogy(states, anchored_genesis=ledger.genesis,
                                 anchored_head=ledger.head)
    print(f"  legit    : {ok_chain.status} — {ok_chain.reason}")
    steps.append(("reproduce_chain", ok_chain.passed, "PASS"))

    # -- 6. write the sealed package and verify it from disk -----------------
    _rule(f"6. write + verify the bundle on disk ({out})")
    out.mkdir(parents=True, exist_ok=True)
    (out / "receipt.json").write_text(json.dumps(deny_receipt.to_dict(), indent=2) + "\n",
                                      encoding="utf-8")
    (out / "claim.json").write_text(json.dumps(deny_claim.to_dict(), indent=2) + "\n",
                                    encoding="utf-8")
    (out / "chain.json").write_text(json.dumps(states, indent=2) + "\n", encoding="utf-8")
    anchors = {"genesis": ledger.genesis, "head": ledger.head}
    (out / "RUN.md").write_text(_run_md(out, deny_receipt, steps, anchors), encoding="utf-8")
    manifest = {"algorithm": "SHA-256",
                "artifacts": {name: sha256_file(out / name) for name in ARTIFACTS}}
    (out / "hashes.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    report = verify_bundle(out, key=key, anchored_genesis=anchors["genesis"],
                           anchored_head=anchors["head"])
    for name, prop in sorted(report.properties.items()):
        print(f"  {name:<20} {prop['status']}")
    steps.append(("bundle_on_disk", report.passed, "PASS"))

    all_ok = all(ok for _, ok, _ in steps)
    print(f"\n  all steps as expected : {all_ok}")

    return {
        "genesis": anchors["genesis"],
        "head": anchors["head"],
        "out": out.as_posix(),
        "steps": {name: ok for name, ok, _ in steps},
        "expected": {name: exp for name, _, exp in steps},
        "all_expected": all_ok,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Quine Gate live demo")
    parser.add_argument("--out", default=os.path.join(ROOT, "evidence", "QUINE_GATE"),
                        help="where to write the sealed demo package")
    args = parser.parse_args(argv)

    result = run_demo(Path(args.out))
    print("\n=== DEMO_RESULT_JSON ===")
    print(json.dumps(result, indent=2))
    return 0 if result["all_expected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
