# IsyMotron

> One AI, many hosts, one capability fabric.
> Any machine, only the authority you grant.

IsyMotron is a personal AI capability fabric: a model can compose capabilities
that the user has explicitly granted across their own phones and computers,
while every grant, refusal and effect is enforced and recorded by machinery the
model does not control.

**Status: M5 + the avatar track (AV0–AV9).** The authority grammar runs on a
real Windows machine, a real Nemotron plan orchestrates work across two unlike
hosts while a host refuses a step the model asked for, and all of it ships as a
single 12 MB binary with a console you can open on your phone — plus a floating
desktop pet that shows what the host decided, and can be talked about, but
never talked into anything.
See [`docs/EVIDENCE.md`](docs/EVIDENCE.md) for what is demonstrated and what is
not, and [`docs/FINDINGS.md`](docs/FINDINGS.md) for the six things first contact
taught us that the design did not.

---

## What exists right now

| Piece | Where | State |
|---|---|---|
| `NemoHostContract/v0` — 8 operations | `core/isymotron/host.py` | frozen |
| Capability / Lease / Request / Receipt types | `core/isymotron/contracts.py` | frozen |
| L0 authority enforcer, deny-by-default | `core/isymotron/policy.py` | working |
| Closed verdict vocabularies | `core/isymotron/verdicts.py` | frozen |
| Two simulated hosts, two unlike engines | `hosts/simulator/engines.py` | working |
| Loopback relay | `relay/loopback.py` | working |
| Fake mobile client | `clients/fake_mobile.py` | working |
| **Real Windows host** — NTFS, processes, app launch | `hosts/windows/win11.py` | working |
| Local grant file — the local authority, deny-by-default | `hosts/windows/grants.py` | working |
| Host CLI — grant, revoke, execute | `tools/host_cli.py` | working |
| **Console** — local web UI, dark/green, phone-ready | `console/` | working |
| **`IsyMotron.exe`** — one file, no runtime dependencies | `build_exe.py` | 12 MB |
| **Avatar model** — two trust channels, precedence, no I/O | `avatar/model.py` | working |
| **Open channel** — inbox reader, companion-event-v1 | `avatar/inbox.py` | working |
| **Authority channel** — producers + `/api/avatar`, read-only avatar token | `console/server.py` | working |
| **Web avatar** — host frame + third-party bubbles, no innerHTML | `console/static/avatar.js` | working |
| **Desktop pet** — transparent Tk window, `--avatar` | `avatar/window.py` | working |
| **Avatar pack** — Malbolge Cat, copied from Companion (see Credits) | `avatar/packs/` | shipped |
| Avatar adversarial gate — talking grants nothing | `tests/test_avatar_adversarial.py` | 10 passed |
| **HostAwarenessEngine** — deterministic suspend/network facts | `core/isymotron/awareness.py` | working |
| Attribution — `HOST_SUSPENDED` is never `PROVIDER_ERROR` | `core/isymotron/attribution.py` | working |
| Windows power provider — clock bias, no message pump | `hosts/windows/power.py` | working |
| Provider seam — NVIDIA / Nebius, one env var apart | `agents/provider.py` | working |
| Planner role — intent to a validated plan | `agents/planner.py` | working |
| Executor — resolves `$from`, stops at the first DENY | `agents/executor.py` | working |
| M0 acceptance gate | `tests/test_m0_gate.py` | 23 passed |
| M1 real-hardware gate | `tests/test_win11_real.py` | 17 passed |
| M3 planner gate (offline) | `tests/test_planner.py` | 29 passed |
| M3 live gate (real Nemotron) | `tests/test_live_model.py` | 5 passed |
| M4 host awareness gate | `tests/test_awareness.py` | 21 passed |
| M5 console surface gate | `tests/test_console.py` | 17 passed |
| Sealed receipts from real runs | `evidence/M0/`, `M1/`, `M3/` | 12 receipts + probe |

Not started: the Doctor, the sandbox, the marketplace, the identity seam, a
legacy Windows host.

**Windows 7 and earlier are out of product scope.** Not because the contract
could not reach them — the whole point of an 8-operation surface is that it
could — but because legal copies of those releases are not obtainable to test
on, and an untested host would have to be labelled `NOT_DEMONSTRATED` anyway.
Roadmap invariant 2.13: unsupported != impossible.

## Run it

Build the binary (PyInstaller is a build-time dependency only):

```
python build_exe.py            # dist/IsyMotron.exe, 12 MB, self-smoke-tested
IsyMotron.exe                  # opens the console on localhost
IsyMotron.exe --lan            # also reachable from your phone
IsyMotron.exe --avatar         # ...plus the floating desktop pet
```

Or from source:

```
python -m pytest -q             # 39 passed in 1.33s
python tools/m0_demo.py         # simulated walkthrough, writes evidence/M0/
python tools/host_cli.py status # what THIS machine is, and what it grants
```

Make your own machine a host (it boots inert until you do):

```
python tools/host_cli.py grant filesystem.read --root "C:/Users/you/Pictures"
python tools/host_cli.py do filesystem.read --path "C:/Users/you/Pictures"
python tools/host_cli.py do filesystem.read --path "C:/Users/you/Documents"   # DENY
```

Wire up a model (either provider — the model id string is the same on both):

```
setx NVIDIA_NIM_API_KEY nvapi-...        # or NEBIUS_API_KEY, with
setx ISYMOTRON_PROVIDER nebius           # this
python tools/nemotron_check.py           # eligibility + planner + adversarial
python tools/nemotron_check.py --models  # what the key can actually serve
```

No dependencies beyond the standard library and `pytest`. No SDK.

## The avatar (the part a person sees)

A small transparent cat floats on your desktop and mirrors what the host
decided: a red frame with the verdict, the receipt id and the seal when
something was allowed or refused; a calm animation the rest of the time. It
lives in the console page too, so the phone sees the same pet.

Two channels feed it, and they are not equal:

- what **the host decided** — drawn in the host frame. It can only come from
  the IsyMotron process itself, over a token the avatar can read with and
  never write with;
- what **someone said** — anything appended to the inbox file renders as a
  third-party bubble, labelled with who wrote it, verbatim, never filtered.
  A line that *claims* to be a verdict loses those fields before it exists:
  talking grants nothing, and the frame cannot be talked into.

No model key is needed for any of it — the pet, the inbox, grants and sealed
receipts are the product; a key only adds a planner, never a permission.

See [`docs/AVATAR_CONTRACT.md`](docs/AVATAR_CONTRACT.md) for the frozen rules
(R1–R7) and [`docs/AVATAR_ROADMAP.md`](docs/AVATAR_ROADMAP.md) for how each
one was built and proven.

## Credits

The desktop avatar window, the pack loader and the Malbolge Cat pack are
adapted from **Companion**, the author's own prior MIT-licensed work
(repository `Companion`, commit `0aae576`), copied into this repository and
reused under the terms of the MIT license. The companion-event-v1 inbox
protocol is Companion's transport, unchanged. (Devpost text: declare it.)

Spanish walkthrough, command by command, with the real output:
[`docs/GUIA.es.md`](docs/GUIA.es.md).

## The ten rules the code actually enforces

1. **No capability means no action.** `list_capabilities()` omits ungranted
   capabilities entirely. They are absent from the agent's world, not forbidden
   in it.
2. **Deny-by-default, first reason wins.** The enforcer checks in a fixed
   order and reports the *first* failure, so a caller cannot probe the scope of
   a capability it was never granted.
3. **A model never returns ALLOW.** `Enforcer.decide` is the only thing in the
   system that can, and it is a pure function with no I/O.
4. **A refusal is an outcome.** DENY produces a sealed receipt like anything
   else. Silence is not a result.
5. **Narrowing is safe, widening is impossible.** A client may ask for less
   scope than it was granted; anything outside the local grant is dropped when
   the lease is issued, not when it is used.
6. **Enforcement is two-stage and both stages can refuse.** The enforcer checks
   the request as written; the engine re-checks what the OS actually resolves.
   A junction inside a granted root passes the first and is stopped by the
   second — see [`docs/FINDINGS.md`](docs/FINDINGS.md) #1.
7. **A plan is a proposal.** The planner only ever sees granted capabilities,
   its output is validated against the manifests, and every step is still
   judged by the host. Nemotron asked to launch `DOOM`; the allowlist grants
   `DOOM.EXE`; the host refused. No prompt made that happen.
8. **A capability's result shape is part of its contract.** Two engines
   returned the same value under different names and a plan broke on it —
   `returns` is now declared and cross-step references are checked against it.
9. **A remote surface uses authority; it never widens it.** The console grants
   only from loopback. A phone can read, plan and execute what a human already
   allowed at the keyboard, and `/api/grant` from the network is a 403.
10. **Never ask a model to infer host state the host can report.** A closed
   laptop lid once looked exactly like provider throttling. The machine knows,
   and `time.monotonic()` on Windows does not —
   see [`docs/HOST_AWARENESS.md`](docs/HOST_AWARENESS.md).

## Layout

```
core/isymotron/   L0. Contract, policy, verdicts, canonical digests.
agents/           L1. Provider seam, planner, executor. The only model code.
console/          The web surface and its static files. Holds no authority.
hosts/windows/    The real Windows engine and the local grant file.
hosts/simulator/  Two engines that serve the same contract differently.
relay/            Transport. Holds no policy and cannot execute.
clients/          Fake mobile surface.
tests/            The M0 and M1 acceptance gates.
tools/            m0_demo.py, host_cli.py (real machine), nemotron_check.py.
evidence/         Receipts produced by real runs, not by hand.
docs/             Thesis, architecture, evidence, findings, prior art, Spanish guide.
```

## Documents

- [`docs/PRODUCT_THESIS.md`](docs/PRODUCT_THESIS.md) — what this is and what it is not
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the contract and the L0/L1 boundary
- [`docs/EVIDENCE.md`](docs/EVIDENCE.md) — every claim, with its current status
- [`docs/FINDINGS.md`](docs/FINDINGS.md) — what the code taught us that the design did not
- [`docs/HOST_AWARENESS.md`](docs/HOST_AWARENESS.md) — why a closed laptop looked like provider throttling, and the fix
- [`docs/PRIOR_ART_ISYCO.md`](docs/PRIOR_ART_ISYCO.md) — what ISyCo already solved
- [`docs/ROADMAP_DELTA.md`](docs/ROADMAP_DELTA.md) — where this repo departs from the roadmap, and why
- [`docs/GUIA.es.md`](docs/GUIA.es.md) — guía en español

## License

MIT. See [`LICENSE`](LICENSE).
