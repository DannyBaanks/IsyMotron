# Quine Gate demo run — 2026-09-22T07:30:03Z

Status: `DEMONSTRATED`, scoped to
the sealed-receipt/re-derivation gate on the simulated demo host.

Every step below ran in-process against the real `Enforcer`; nothing was
inspected by eye or accepted on the model's word.

## Environment

| Fact | Value |
|---|---|
| Date (UTC) | 2026-09-22T07:30:03Z |
| Host | Linux 7.0.0-31-generic |
| Python | 3.12.3 |
| Repository commit at run time | `bc3e7ef` |
| Signing key | `absent: receipts are unkeyed (integrity only)` |

## Exact command

```bash
python3 tools/quine_gate_demo.py --out evidence/QUINE_GATE
```

## Result per step

| Step | Expected | Observed |
|---|---|---|
| 1. legit_receipt | `PASS` | yes |
| 2. mutated_receipt | `REJECT` | yes |
| 3. fork | `CONFLICT` | yes |
| 4. rollback | `CONFLICT` | yes |
| 5. reproduce_chain | `PASS` | yes |

Receipt in the bundle: `rcpt_5aa6b04295bd48f2` —
`DENY`
(OUT_OF_SCOPE),
re-derivable because `sha256:e9434b4118da4908…` names its claim.

## Anchors (the trust root is the commit that records them)

A bundle cannot anchor itself. Verify this package with the values below,
taken from this committed file:

```bash
python3 tools/quine_gate_verify.py evidence/QUINE_GATE \
    --genesis sha256:79a67df39398cd387fcd7aae2b240de0b86c2baffe385d161fa2f80492710967 \
    --head sha256:6e2e04dd6492c3b820df09ac51e62434909259d44f2857ece60d903152df2430
```

- genesis: `sha256:79a67df39398cd387fcd7aae2b240de0b86c2baffe385d161fa2f80492710967`
- HEAD: `sha256:6e2e04dd6492c3b820df09ac51e62434909259d44f2857ece60d903152df2430`

To rotate the demo: re-run the generator, commit the result, and (optional but
stronger) publish the new HEAD with `git tag evidence-head-<n>`.

## Not demonstrated

- That the run *occurred* on any particular machine: reproduction proves
  validity, not occurrence.
- Host attestation (TPM/TEE/measured boot): out of scope by design.
- The *effect* of an ALLOW (a real file read): the gate re-derives the
  decision; it does not replay the filesystem.
