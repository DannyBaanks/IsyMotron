# Evidence ledger

ISyCo vocabulary. A claim carries exactly one label, and the label is a
statement about *this repository right now*, not about the design's potential.

| Label | Meaning |
|---|---|
| `DEMONSTRATED` | Reproducible execution supports it, inside a declared scope |
| `INFERRED` | Reasonable from demonstrated evidence, not directly tested |
| `NOT_DEMONSTRATED` | Desired and plausible; evidence not yet sufficient |
| `DESTROYED` | A specific hypothesis failed a test or an ablation |
| `UNKNOWN` | The instrument cannot currently establish the answer |

There is no `SAFE`. There is no default-pass. An unmeasured claim is
`NOT_DEMONSTRATED`, never "probably fine".

---

## Target claims from the roadmap (section 39)

| Claim | Status | Basis |
|---|---|---|
| **A** — one plan orchestrates across heterogeneous hosts under one contract | `NOT_DEMONSTRATED` | Cross-host execution works (`test_cross_device_transfer_produces_two_receipts`), but no planner exists. The claim is about a *plan*, and there is none. |
| **B** — a host denies an action outside local scope even if the model asks | `NOT_DEMONSTRATED` | The denial is now `DEMONSTRATED` **on real hardware** (`evidence/M1/02_real_read_denied.json`, plus a real junction escape). The "even if the model asks" half still has no model to ask it. |
| **C** — Doctor detects an undeclared side effect and blocks promotion | `NOT_DEMONSTRATED` | No Doctor. |
| **D** — a changed artifact invalidates prior verification | `NOT_DEMONSTRATED` | No marketplace, no artifact records. |
| **E** — a publicly accepted activity can still be denied locally | `NOT_DEMONSTRATED` | No marketplace. The mechanism that would enforce it (local grant beats everything) is `DEMONSTRATED` in isolation. |
| **F** — two Windows generations serve the same contract via different engines | `NOT_DEMONSTRATED` | One **real** engine (`nt-real/0.1`, Windows build 10.0.26200) and two simulated ones now serve the contract. One real machine is not two generations. |
| **G** — a verified activity reuses a fast path without repeating verification | `NOT_DEMONSTRATED` | No verification path of either speed. |
| **H** — measured model provider continuity under load | `NOT_DEMONSTRATED` | No model calls at all. |
| **I** — Windows 98 participates and launches an app from a mobile workflow | `NOT_DEMONSTRATED` | A simulated `dos-bridge/0.1` launches a simulated `DOOM.EXE`. That is a test fixture, not a Windows 98 machine. |

Still nine `NOT_DEMONSTRATED` after M1. B and F moved — their basis lines now
cite real hardware instead of a simulator — but neither crossed the line, and
nudging a label because progress *feels* like it should is exactly the failure
this ledger exists to prevent. B needs a model to do the asking. F needs a
second real Windows generation.

---

## What *is* demonstrated

**M0 scope:** in-process Python, simulated engines, no real filesystem, no
network, no model. Every row below is a passing test in `tests/test_m0_gate.py`.

| # | Claim | Test |
|---|---|---|
| 1 | describe -> lease -> request -> sealed receipt completes end to end | `test_gate_describe_request_receipt_roundtrip` |
| 2 | Both engines expose all 8 contract operations | `test_all_eight_operations_exist_on_every_host` |
| 3 | An out-of-scope path is denied and still receipted, with no payload | `test_outside_scope_is_denied_and_still_receipted` |
| 4 | A sibling prefix is not inside a root (`/Photos2` vs `/Photos`) | `test_sibling_prefix_is_not_inside_root` |
| 5 | `..` traversal is resolved before the scope comparison | `test_dotdot_traversal_is_denied` |
| 6 | Backslash and case variations do not bypass scope | `test_backslashes_do_not_bypass_scope` |
| 7 | No lease is a hard deny | `test_no_lease_is_a_hard_deny` |
| 8 | An ungranted capability is absent from the agent's view | `test_ungranted_capability_is_absent_not_forbidden` |
| 9 | A capability an engine lacks denies with `CAPABILITY_UNAVAILABLE` | `test_capability_the_host_does_not_implement` |
| 10 | `requires_admin` denies without an admin grant | `test_admin_capability_denied_without_admin_grant` |
| 11 | An expired lease is denied | `test_expired_lease_is_denied` |
| 12 | A revoked lease is denied | `test_revoked_lease_is_denied` |
| 13 | A caller asking for wider scope receives the narrow one | `test_lease_cannot_be_widened_by_the_caller` |
| 14 | The host caps lease TTL | `test_lease_ttl_is_capped_by_the_host` |
| 15 | An undeclared parameter is rejected | `test_undeclared_param_is_rejected` |
| 16 | A read-only family rejects a mutating parameter | `test_read_only_family_rejects_mutation` |
| 17 | A capability family with no scope checker falls to DENY, not ALLOW | `test_unmapped_capability_family_falls_to_deny` |
| 18 | Two unlike engines serve one contract and declare the same effect shape | `test_same_workflow_on_two_unlike_engines` |
| 19 | A cross-device transfer yields two verifiable receipts | `test_cross_device_transfer_produces_two_receipts` |
| 20 | A tampered receipt fails its seal | `test_receipt_seal_detects_tampering` |
| 21 | Identical intents digest identically; ids differ | `test_request_digest_is_stable_across_identical_intents` |
| 22 | An engine error yields ALLOW + `UNKNOWN`, never ALLOW + `DEMONSTRATED` | `test_error_inside_the_engine_is_unknown_not_allow` |
| 23 | No verdict vocabulary contains `SAFE` | `test_no_verdict_vocabulary_contains_safe` |

**M1 scope:** one real Windows host (`nt-real/0.1`, build 10.0.26200), real
NTFS, real processes, real grant file. Every row below is a passing test in
`tests/test_win11_real.py`.

| # | Claim | Test |
|---|---|---|
| 24 | A host with no grant file boots inert and denies everything | `test_missing_grant_file_yields_an_inert_host` |
| 25 | A grant file that fails to parse yields **no** authority, not unrestricted | `test_unparseable_grant_file_yields_an_inert_host` |
| 26 | A capability granted with an empty scope still denies | `test_a_grant_with_no_scope_still_denies` |
| 27 | Grants round-trip through the file on disk | `test_grant_roundtrips_through_the_file` |
| 28 | **A real NTFS junction inside a granted root is denied** | `test_junction_inside_a_granted_root_is_denied` |
| 29 | ...and a write through one plants nothing in the target | `test_junction_write_is_denied_too` |
| 30 | A real in-scope read returns content and a content hash | `test_real_read_inside_scope` |
| 31 | A real out-of-scope read is denied with no payload | `test_real_read_outside_scope` |
| 32 | A real directory listing works | `test_real_directory_listing` |
| 33 | A real write creates the file and reports `overwrote` | `test_real_write_creates_the_file` |
| 34 | A write to a path that does not exist yet is still scope-checked | `test_write_to_a_nonexistent_path_outside_scope_is_denied` |
| 35 | `..` on a real tree is denied | `test_dotdot_on_a_real_tree` |
| 36 | Real `system.info` reports the real machine | `test_real_system_info` |
| 37 | Real `process.inspect` lists processes and rejects `mutate` | `test_real_process_inspect_is_read_only` |
| 38 | An app off the allowlist is denied | `test_app_not_on_allowlist_is_denied` |
| 39 | All 8 operations exist on the real host | `test_all_eight_operations_on_the_real_host` |

Reproduce:

```
python -m pytest -q
39 passed in 1.33s
```

Sealed receipts from real runs:

- `evidence/M0/` — 7 receipts, simulated hosts, 4 ALLOW / 3 DENY, 7/7 seals verified
- `evidence/M1/` — 5 receipts from the **real** `win11-danny` host, including a
  real read of a real file and a real `OUT_OF_SCOPE` refusal

One finding came out of that first contact and changed the architecture:
`docs/FINDINGS.md` #1. It is the reason claim B's basis line now says "on real
hardware".

---

## What simulation cannot establish

This deserves its own section because it is the trap the whole repo is one step
away from falling into.

`ModernHost` and `LegacyHost` are unlike engines: different path rendering,
different capability sets, one has no process table and no pid. That is enough
to show the **contract does not secretly depend on one engine's habits**, which
is a real and useful result about the contract's shape.

It is not evidence about Windows. The interesting failures of a real legacy
host — that the TLS stack is absent, that the filesystem is case-insensitive in
a way the normalizer assumes but does not verify, that there is no service
manager, that a 64KB payload is not free — are precisely the ones a Python
simulation erases by construction.

So: claim F and claim I stay `NOT_DEMONSTRATED` until a receipt comes off real
hardware. The simulated ones are labelled as fixtures in the code and in the
test names, so no future reader can mistake them for the thing.

**This was not a hypothetical.** The section above was written before the first
real host existed. Within hours of writing it, first contact with NTFS produced
exactly the predicted failure: a directory junction inside a granted root, which
no Python dict can represent, defeated a scope check that twenty-three tests
called correct. See `docs/FINDINGS.md` #1. The prediction is now `DEMONSTRATED`
in the most expensive possible way, which is the cheap way compared to finding
it in a demo.

---

## Language rules for this project

- Never write that an activity is *safe*. Write what was verified, for which
  host, at which artifact hash, under which scope.
- Never report an adjective where a number is available. "Measured over N runs:
  X" beats "reliable".
- A claim with no measurement is `NOT_DEMONSTRATED` in writing, not omitted.
- A hypothesis that failed is `DESTROYED` and stays in the ledger. Deleting a
  refuted claim loses the most expensive thing in the file.
