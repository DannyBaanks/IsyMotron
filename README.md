# IsyMotron

> One AI, many hosts, one capability fabric.
> Any machine, only the authority you grant.

IsyMotron is a personal AI capability fabric: a model can compose capabilities
that the user has explicitly granted across their own phones and computers,
while every grant, refusal and effect is enforced and recorded by machinery the
model does not control.

**Status: M3 — Nemotron plans, the host still decides.** The authority grammar
runs on a real Windows machine, and a real Nemotron plan orchestrates work
across two unlike hosts — while a host refuses a step the model asked for.
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
| Provider seam — NVIDIA / Nebius, one env var apart | `agents/provider.py` | working |
| Planner role — intent to a validated plan | `agents/planner.py` | working |
| Executor — resolves `$from`, stops at the first DENY | `agents/executor.py` | working |
| M0 acceptance gate | `tests/test_m0_gate.py` | 23 passed |
| M1 real-hardware gate | `tests/test_win11_real.py` | 17 passed |
| M3 planner gate (offline) | `tests/test_planner.py` | 29 passed |
| M3 live gate (real Nemotron) | `tests/test_live_model.py` | 5 passed |
| Sealed receipts from real runs | `evidence/M0/`, `M1/`, `M3/` | 12 receipts + probe |

Not started: the Doctor, the sandbox, the marketplace, the identity seam, the
mobile surface, a legacy Windows host.

## Run it

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

Spanish walkthrough, command by command, with the real output:
[`docs/GUIA.es.md`](docs/GUIA.es.md).

## The eight rules the code actually enforces

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

## Layout

```
core/isymotron/   L0. Contract, policy, verdicts, canonical digests.
agents/           L1. Provider seam, planner, executor. The only model code.
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
- [`docs/PRIOR_ART_ISYCO.md`](docs/PRIOR_ART_ISYCO.md) — what ISyCo already solved
- [`docs/ROADMAP_DELTA.md`](docs/ROADMAP_DELTA.md) — where this repo departs from the roadmap, and why
- [`docs/GUIA.es.md`](docs/GUIA.es.md) — guía en español

## License

MIT. See [`LICENSE`](LICENSE).
