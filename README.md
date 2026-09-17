# IsyMotron

> One AI, many hosts, one capability fabric.
> Any machine, only the authority you grant.

IsyMotron is a personal AI capability fabric: a model can compose capabilities
that the user has explicitly granted across their own phones and computers,
while every grant, refusal and effect is enforced and recorded by machinery the
model does not control.

**Status: M0 — contract freeze.** The authority grammar exists and is tested.
No model is wired in yet, deliberately. See [`docs/EVIDENCE.md`](docs/EVIDENCE.md)
for what is demonstrated and what is not.

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
| M0 acceptance gate, 23 tests | `tests/test_m0_gate.py` | 23 passed |
| Sealed receipts from a real run | `evidence/M0/` | 7 receipts |

Not started: real Windows host, Nemotron roles, the Doctor, the sandbox, the
marketplace, the identity seam, the mobile app.

## Run it

```
python -m pytest tests/ -q      # 23 passed in 0.37s
python tools/m0_demo.py         # prints the walkthrough, writes evidence/M0/
```

No dependencies beyond the standard library and `pytest`.

Spanish walkthrough, command by command, with the real output:
[`docs/GUIA.es.md`](docs/GUIA.es.md).

## The five rules the code actually enforces

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

## Layout

```
core/isymotron/   L0. Contract, policy, verdicts, canonical digests.
hosts/simulator/  Two engines that serve the same contract differently.
relay/            Transport. Holds no policy and cannot execute.
clients/          Fake mobile surface.
tests/            The M0 acceptance gate.
tools/            m0_demo.py
evidence/         Receipts produced by real runs, not by hand.
docs/             Thesis, architecture, evidence ledger, prior art, Spanish guide.
```

## Documents

- [`docs/PRODUCT_THESIS.md`](docs/PRODUCT_THESIS.md) — what this is and what it is not
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the contract and the L0/L1 boundary
- [`docs/EVIDENCE.md`](docs/EVIDENCE.md) — every claim, with its current status
- [`docs/PRIOR_ART_ISYCO.md`](docs/PRIOR_ART_ISYCO.md) — what ISyCo already solved
- [`docs/ROADMAP_DELTA.md`](docs/ROADMAP_DELTA.md) — where this repo departs from the roadmap, and why
- [`docs/GUIA.es.md`](docs/GUIA.es.md) — guía en español

## License

MIT. See [`LICENSE`](LICENSE).
