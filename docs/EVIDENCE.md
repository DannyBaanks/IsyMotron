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
| **A** — one plan orchestrates across heterogeneous hosts under one contract | **`DEMONSTRATED`** (scoped) | A real Nemotron plan read a real file on `win11-danny` (`nt-real/0.1`) and wrote it to a second host on a different engine, through a typed `$from` reference, in one plan. Scope: the second host is a fixture, so this is one real machine plus one simulated one. `test_planner_uses_typed_references_for_cross_step_data`. |
| **B** — a host denies an action outside local scope even if the model asks | **`DEMONSTRATED`** | Nemotron planned `apps.launch {"app": "DOOM"}`; the allowlist grants `DOOM.EXE`; the host refused with `OUT_OF_SCOPE` and the plan stopped. No prompt instructed the refusal — it came from the grant file. See FINDINGS.md #6, and `test_a_live_plan_still_meets_the_enforcer`. |
| **C** — Doctor detects an undeclared side effect and blocks promotion | `NOT_DEMONSTRATED` | No Doctor. |
| **D** — a changed artifact invalidates prior verification | `NOT_DEMONSTRATED` | No marketplace, no artifact records. |
| **E** — a publicly accepted activity can still be denied locally | `NOT_DEMONSTRATED` | No marketplace. The mechanism that would enforce it (local grant beats everything) is `DEMONSTRATED` in isolation. |
| **F** — two Windows generations serve the same contract via different engines | `NOT_DEMONSTRATED` | One **real** engine (`nt-real/0.1`, Windows build 10.0.26200) and two simulated ones now serve the contract. One real machine is not two generations. |
| **G** — a verified activity reuses a fast path without repeating verification | `NOT_DEMONSTRATED` | No verification path of either speed. |
| **H** — measured model provider continuity under load | `NOT_DEMONSTRATED` (now measurable) | Spot numbers only, no workload. Round trip 0.75–6.16 s (median 1.56 s over 12); a two-host plan 4.6–22.4 s. **One HTTP 503 in 12 calls** — real, but n=12 is not a rate. A second run that looked like throttling was the laptop being closed mid-measurement, not the provider (FINDINGS.md #7b). Also: `nemotron-nano-3-30b-a3b` is listed by `/models` and returns 404 on invocation — listed is not servable. |
| **I** — Windows 98 participates and launches an app from a mobile workflow | `NOT_DEMONSTRATED` | A simulated `dos-bridge/0.1` launches a simulated `DOOM.EXE`. That is a test fixture, not a Windows 98 machine. |

**Two claims crossed on 2026-09-17: A and B.** Both are scoped, and the scope
is written into the basis line rather than left implied. Seven remain.

Still nine `NOT_DEMONSTRATED` after M1. B and F moved — their basis lines
cited real hardware instead of a simulator — but neither crossed at that point,
and nudging a label because progress *feels* like it should is exactly the
failure this ledger exists to prevent. B crossed later the same day, when a
real model actually did the asking and was refused. F still needs a second real
Windows generation and has not moved.

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

**M3 scope:** the planner and executor. Offline tests use a scripted provider
and are deterministic; live tests hit real Nemotron and skip without a key.

| # | Claim | Test |
|---|---|---|
| 40 | The catalogue omits ungranted capabilities entirely | `test_catalogue_omits_ungranted_capabilities` |
| 41 | The catalogue declares each capability's result fields | `test_catalogue_declares_result_fields` |
| 42 | Both engines agree on result field names | `test_both_engines_agree_on_result_field_names` |
| 43 | A hallucinated capability is rejected | `test_hallucinated_capability_is_rejected` |
| 44 | A real-but-ungranted capability is rejected identically | `test_ungranted_but_real_capability_is_rejected_the_same_way` |
| 45 | An unknown host is rejected | `test_unknown_host_is_rejected` |
| 46 | An undeclared param is rejected | `test_undeclared_param_is_rejected` |
| 47 | A forward reference is rejected | `test_forward_reference_is_rejected` |
| 48 | A reference to an undeclared result field is rejected | `test_reference_to_an_undeclared_result_field_is_rejected` |
| 49 | Truncation is not reported as bad JSON | `test_truncation_is_not_reported_as_bad_json` |
| 50 | JSON inside a fence is accepted | `test_json_inside_a_fence_is_accepted` |
| 51 | An empty plan **with a reason** is a refusal, not a failure | `test_empty_plan_with_a_reason_is_a_refusal_not_a_failure` |
| 52 | An empty plan without a reason is its own class | `test_empty_plan_without_a_reason_is_its_own_class` |
| 53 | The executor resolves a `$from` reference across hosts | `test_executor_resolves_a_reference_across_hosts` |
| 54 | The executor stops at the first DENY and runs nothing after | `test_executor_stops_at_the_first_deny` |
| 55 | **A validated plan still carries no authority** | `test_a_plan_carries_no_authority` |
| 56 | A prose placeholder is refused before it reaches a host | `test_prose_placeholder_is_refused_before_it_reaches_a_host` |
| 57 | The placeholder detector, six cases | `test_placeholder_detector` |
| 58 | Provider presets differ only in base_url, not model id | `test_provider_presets_differ_only_in_door` |
| 59 | An unknown provider is refused | `test_unknown_provider_is_refused` |
| 60 | A missing key is refused before any request leaves | `test_missing_key_is_refused_before_any_request` |

Live (real Nemotron, `tests/test_live_model.py`, 5 passed in 14.58s):

| # | Claim | Test |
|---|---|---|
| L1 | The provider reaches a real endpoint | `test_provider_reaches_the_endpoint` |
| L2 | An undersized budget truncates rather than shortens | `test_an_undersized_budget_truncates_rather_than_shortens` |
| L3 | The planner refuses rather than inventing a capability | `test_planner_refuses_instead_of_inventing_a_capability` |
| L4 | The planner uses typed references, not prose | `test_planner_uses_typed_references_for_cross_step_data` |
| L5 | A live plan still meets the enforcer | `test_a_live_plan_still_meets_the_enforcer` |

Reproduce:

```
python -m pytest -q                        # 69 passed in 2.41s
python -m pytest tests/test_live_model.py  # 5 passed in 14.58s  (needs a key)
python tools/nemotron_check.py             # the M3 probe, writes evidence/M3/
```

Sealed receipts from real runs:

- `evidence/M0/` — 7 receipts, simulated hosts, 4 ALLOW / 3 DENY, 7/7 seals verified
- `evidence/M1/` — 5 receipts from the **real** `win11-danny` host, including a
  real read of a real file and a real `OUT_OF_SCOPE` refusal
- `evidence/M3/` — the provider probe, with measured latencies and the
  adversarial verdict

Eight findings came out of first contact with real hardware and a real model,
and six changed the architecture: `docs/FINDINGS.md`. Three were bugs in our own
verdict or attribution logic, which is the category worth watching — in each
case the defence worked and the *record* of the defence was wrong.

**M4 scope:** host awareness and attribution (`tests/test_awareness.py`,
21 passed). Deterministic: proving a suspend is attributed correctly never
requires closing a laptop.

| # | Claim | Test |
|---|---|---|
| 61 | A quiet host never changes its epochs | `test_a_quiet_host_never_changes_epoch` |
| 62 | A suspend advances `power_epoch` and records the measured gap | `test_a_suspend_advances_power_epoch_and_records_the_gap` |
| 63 | **Wall time advances through a suspend; awake time does not** | `test_wall_time_advances_through_a_suspend_but_awake_time_does_not` |
| 64 | Millisecond bias drift is not a suspend | `test_sub_threshold_noise_is_not_a_suspend` |
| 65 | **No mechanism means UNKNOWN, never ACTIVE** | `test_no_mechanism_means_unknown_not_active` |
| 66 | A missing measurement is `None`, not zero | `test_elapsed_awake_is_none_without_an_unbiased_clock` |
| 67 | A network change advances `network_epoch` | `test_network_change_advances_network_epoch` |
| 68 | A reboot changes `boot_id` | `test_reboot_changes_boot_id` |
| A | Provider 429 with the host awake → `PROVIDER_ERROR`, countable | `test_case_A_provider_error_with_the_host_awake` |
| B | **Suspend mid-request → `HOST_SUSPENDED`, `provider_fault=False`** | `test_case_B_suspend_mid_request_is_not_a_provider_error` |
| C | Network loss without suspend → `HOST_NETWORK_LOSS`, not `HOST_SUSPENDED` | `test_case_C_network_loss_without_suspend` |
| D | Deadline exceeded with the host awake → `DEADLINE_EXCEEDED` | `test_case_D_deadline_exceeded_with_the_host_awake` |
| E | Insufficient evidence → `UNKNOWN`, not a guess | `test_case_E_insufficient_evidence_is_unknown` |
| F | A suspended measurement is excluded from provider stats, visibly | `test_case_F_a_suspended_measurement_is_excluded_from_provider_stats` |
| G | A process restart is detected → `PROCESS_INTERRUPTED` | `test_case_G_process_restart_is_detected` |
| H | **A model cannot manufacture a host event** | `test_case_H_a_model_cannot_manufacture_a_host_event` |
| 69 | Reliability says plainly when it cannot tell | `test_reliability_says_so_when_it_cannot_tell` |
| 70 | Awareness exposes no verb that could allow, execute or grant | `test_awareness_grants_nothing` |

One claim of its own, and it is the reason the engine exists:

> **An agent cannot reliably distinguish provider latency from local host
> suspension without host evidence.** — `DEMONSTRATED` (2026-09-17). On this
> machine `time.monotonic()` *is* `GetTickCount64()`, so both of Python's
> clocks advance through suspend; a 793 s sleep and a 793 s call are identical
> from inside the process. Corroborated by the Windows event log at 795 s.
> See `docs/FINDINGS.md` #7, #8 and `docs/HOST_AWARENESS.md`.

Platform status: Windows `DEMONSTRATED`; Linux `NOT_DEMONSTRATED` (documented
seam, reports UNKNOWN); macOS `NOT_DEMONSTRATED` (no hardware, no stub);
pre-suspend notification `NOT_DEMONSTRATED` (no message pump, never claimed).

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
