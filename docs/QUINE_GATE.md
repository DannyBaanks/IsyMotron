# Quine Gate — evidence that reproduces itself

A receipt is an *affirmation*; the authority is the reproduction. Before the
Quine Gate, a receipt's seal was an unkeyed digest — honest about integrity,
but anyone could edit a `DENY` into an `ALLOW` and recompute it. The Quine Gate
closes that by making every authority-bearing receipt **re-derivable**: the
verifier re-runs the real `Enforcer` over the inputs the receipt claims, and
compares. A forged decision stops being about seals and becomes a mismatch
against recomputed policy.

The name is an internal analogy, not a literal quine: a claim earns authority
when the artifact that produced it can derive it again.

## Architecture

```text
        GENESIS  (externally anchored: the git commit / tag that records it)
           |
      TRANSITION  (kind, operation, input digests, policy digest,
           |       artifact digest, output digest — all inside the hash)
         STATE     sha = H(parent ‖ transition)
           |
      TRANSITION → STATE → … → HEAD   (externally anchored, same root)
           |
        RECEIPT   v1: request/policy/capability/result digests + claim_digest
           |
       REPRODUCE  Enforcer.decide(claim) at the pinned decision instant
           |
        VERDICT   one status per property — never a global "secure"
```

Rule, enforced at **write** time: *no state without a verified parent*
(`Genealogy.append` refuses anything that is not the current head, and leaves
the ledger unchanged).

## The pieces

| Piece | Path |
|---|---|
| Canonical JSON + digests | `core/isymotron/canon.py` |
| Receipt v1 (provenance + `from_dict`) | `core/isymotron/contracts.py` |
| Keyed sealing (`unkeyed` / `hmac-sha256`) | `core/isymotron/seal.py` |
| Claim bundle + re-derivation | `core/isymotron/verify.py` |
| Anchored chain (GENESIS + HEAD) | `core/isymotron/chain.py` |
| Genealogy ledger (state transitions) | `core/isymotron/genealogy.py` |
| Evidence manifest verification | `core/isymotron/evidence.py` |
| Bundle report (per property) | `core/isymotron/bundle.py` |
| Host wiring (emits v1, stores claims) | `core/isymotron/host.py` |
| CLI: verify a bundle offline | `tools/quine_gate_verify.py` |
| CLI: live demo, writes sealed evidence | `tools/quine_gate_demo.py` |
| Sealed demo package | `evidence/QUINE_GATE/` |

## Commands

```bash
# the live sequence: legit → PASS, mutate → REJECT, fork/rollback → CONFLICT
python3 tools/quine_gate_demo.py

# verify the sealed package offline, property by property
python3 tools/quine_gate_verify.py evidence/QUINE_GATE \
    --genesis <sha from evidence/QUINE_GATE/RUN.md> \
    --head    <sha from evidence/QUINE_GATE/RUN.md>

# the gates
python3 -m pytest tests/test_quine_gate_rederivation.py tests/test_quine_gate_chain.py \
    tests/test_quine_gate_genealogy.py tests/test_quine_gate_matrix.py -q
```

## Anchors are external

A bundle cannot anchor itself: an `anchors.json` that travels with the chain it
anchors would be rewritten together with it (`verify_bundle` never reads it).
The genesis and HEAD values must come from outside — in this repository the
trust root is **git**, which is already an append-only log:

1. Run the demo; it writes the package plus `RUN.md` with the genesis/HEAD.
2. Commit it. The commit *is* the anchor.
3. Optional, stronger: `git tag evidence-head-<n> && git push origin evidence-head-<n>`.

Releases add a second, independent anchor: CI publishes a Sigstore-backed
build attestation for `IsyMotron.exe` (`actions/attest-build-provenance`), so
the shipped binary's provenance does not depend on any key in this repo.

## Sealing

| Scheme | Meaning | Limit |
|---|---|---|
| `unkeyed` | `sha256(canonical(payload))` — legacy v0, integrity only | anyone can recompute it |
| `hmac-sha256` | HMAC over the payload with `ISYMOTRON_RECEIPT_KEY` | symmetric: a key holder can forge; integrity, not non-repudiation |

The key is resolved from the environment or passed explicitly; it never lives
in the repository or in a public artifact (`.gitignore` blocks `*.key`,
`*.pem`, `.receipt-key`). Without a key the receipt is sealed `unkeyed` and
the report says so instead of pretending.

## Threat matrix (each row is a test)

| Attack | Expected | Gate |
|---|---|---|
| A. mutate `DENY→ALLOW` | REJECT | `tests/test_quine_gate_adversarial.py`, `..._matrix.py` |
| B. re-seal with recomputed hash | REJECT | `tests/test_quine_gate_adversarial.py` |
| C. fork from the same parent | CONFLICT | `tests/test_quine_gate_chain.py`, `..._matrix.py` |
| D. rollback to an older state | CONFLICT | `tests/test_quine_gate_chain.py` |
| E. changed input | REJECT | `tests/test_quine_gate_rederivation.py`, `..._matrix.py` |
| F. changed policy | REJECT | `tests/test_quine_gate_rederivation.py` |
| G. changed artifact byte | REJECT | `tests/test_evidence_manifest.py` |
| H. reproduction mismatch of the *effect* | **NOT_VERIFIABLE — declared** | `tests/test_quine_gate_matrix.py` |
| I. missing anchor | NOT_VERIFIABLE | `tests/test_quine_gate_chain.py` |
| J. wrong anchor | REJECT | `tests/test_quine_gate_chain.py` |

Genesis-only anchoring is refused (`NOT_VERIFIABLE`): the measured failure mode
was that it accepts both forks and rollbacks.

## What this does NOT demonstrate

- **Occurrence.** Reproduction proves the decision is a function of the
  anchored inputs. It does not prove a run happened on a given host at a given
  time. The bundle reports `occurrence: NOT_DEMONSTRATED`.
- **Host attestation.** No TPM/TEE/measured boot. A hostile host can lie about
  itself; that boundary needs remote attestation and is out of scope.
  Reported as `host_attestation: ABSENT`.
- **Effect replay.** The gate re-derives the *decision*, not the filesystem
  write. Attack H is open and declared, not hidden.
- **Engine overrides.** When the engine refuses *after* an enforcer ALLOW
  (junctions, case-fold collisions), the decision depends on OS state the
  verifier does not have: such receipts carry `claim_digest: null` and claim
  nothing. No claim beats a false claim.
