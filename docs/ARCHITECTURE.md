# Architecture — `NemoHostContract/v0`

## The eight operations

A host is anything that implements these eight. The number is a design
constraint, not an accident: it is small enough that a Windows 98 bridge could
plausibly implement all of it, which is the only honest test of whether the
contract is portable.

| # | Operation | Returns | Note |
|---|---|---|---|
| 1 | `identify()` | `HostIdentity` | stable id, OS family, OS release, engine name |
| 2 | `describe()` | `HostDescription` | identity + all capabilities + the granted subset |
| 3 | `list_capabilities()` | `[CapabilityManifest]` | **granted only** — see below |
| 4 | `request_lease()` | `(Lease?, PolicyDecision)` | the host decides the scope |
| 5 | `validate_lease()` | `bool` | |
| 6 | `execute_capability()` | `ExecutionReceipt` | enforces, then runs |
| 7 | `return_receipt()` | `ExecutionReceipt?` | by id |
| 8 | `health()` | `dict` | liveness, live leases, receipt count |

Adding a ninth operation is a version bump, not a feature.

### Why 2 and 3 differ

`describe()` is the **human's** view: it lists everything the engine can do,
including what has not been granted, so a person can decide what to turn on.

`list_capabilities()` is the **agent's** view: ungranted capabilities are not
in it at all. This is invariant 5 in code. A model asked to plan against this
host cannot plan an ungranted action, because the action does not appear in its
world model — it is not told "no", it is told nothing.

```python
def test_ungranted_capability_is_absent_not_forbidden(world):
    assert "system.admin_task" not in [c.id for c in modern.list_capabilities()]
    assert "system.admin_task" in [c.id for c in modern.describe().capabilities]
```

## L0 / L1

**L0 — the trust boundary.** Host identity, the capability registry, the
enforcer, lease issuance, receipt sealing, path normalization. Nothing in L0
imports a model client, performs network I/O, or reads a prompt. `Enforcer` is
a pure function of `(description, lease, request)`.

**L1 — the interpretive plane.** Intent, planning, capability resolution,
recovery, review, explanation. Everything a model does. L1 is a *consumer* of
L0's vocabulary: it may read a `PolicyDecision`, render a `DenyReason`, or
suggest a narrower scope for a human to approve. It cannot construct an
`ALLOW`, mint a `Lease`, or seal a `Receipt`.

The boundary is testable rather than aspirational: `core/isymotron/` has no
third-party imports at all.

```
  L1   intent -> plan -> step               (models live here)
       |                     ^
       | ExecutionRequest    | ExecutionReceipt
       v                     |
 ======================================== the boundary
  L0   Enforcer -> engine -> seal          (no model may live here)
```

## The decision order

`Enforcer.decide` checks in this exact order and returns the **first** failure.
The order is part of the contract, because it controls what a refusal leaks.

1. `MALFORMED_REQUEST` — addressed to another host
2. `CAPABILITY_UNAVAILABLE` — this engine does not implement it
3. `CAPABILITY_NOT_GRANTED` — implemented, not granted here
4. `EXCESS_AUTHORITY` — declares `requires_admin`, admin not granted
5. `LEASE_MISSING` / `LEASE_MISMATCH` / `LEASE_REVOKED` / `LEASE_EXPIRED`
6. `MALFORMED_REQUEST` — parameters the manifest never declared
7. scope check, delegated to the capability family's checker

Checking the grant (3) before the scope (7) is deliberate. If scope were
checked first, a caller could map the shape of a capability's scope by watching
which paths produce `OUT_OF_SCOPE` and which produce something else — on a
capability it does not even hold.

Step 7 has a preregistered else-branch: a capability family with no registered
scope checker returns `CAPABILITY_UNAVAILABLE`, never ALLOW. An unmapped case
is never the permissive case.

## Scope checkers

Scope is capability-specific and is never evaluated by string matching at the
policy layer. Each family registers a checker:

- `filesystem.*` — `roots`, compared on a normalized path
- `apps.*` — `allowlist`, compared case-insensitively
- `process.*` — read-only in V0; `mutate` is `EXCESS_AUTHORITY`
- `system.*` — unparameterized in V0

`normalize_path` gives every Windows generation one path grammar: backslashes
fold to `/`, the drive letter is uppercased, `..` is resolved *before* the
comparison. Containment rejects sibling prefixes, so `C:/Photos2` is not inside
`C:/Photos`. All four of those are tested; the `..` case and the sibling case
are the two that a naive `startswith` gets wrong.

An **empty** grant set is a refusal, not a wildcard. `{"roots": []}` denies
everything. This is the failure mode that turns a policy engine into a
formality, so it has its own branch and its own test.

## Leases

A lease binds `(host, subject, capability, scope)` with a TTL. Three properties
matter:

- **The host issues it.** A client asks; the host decides.
- **Asking for more grants less.** `request_lease(scope=...)` intersects with
  the local grant. Keys the local grant never mentioned are ignored, not added.
- **The host caps the TTL.** `min(requested, host maximum)`; the default
  maximum is 900s.

## Receipts

Every `execute_capability` produces one, including every DENY. A receipt
carries the decision, the timings, the result, the observed effects, an
evidence label, and a seal.

`seal = sha256(canonical(payload))` over sorted-key, separator-fixed JSON, so
the same payload digests identically on a phone, a relay and a legacy host.
Tampering with any field invalidates it.

Two distinct identities:

- `receipt_id` — this event
- `request_digest` — the *intent*, independent of request id and timing, so two
  identical asks digest identically and can be correlated across hosts

A denied receipt carries `result == {}`. The refusal is recorded; the payload
is not.

### Evidence label vs. authority decision

These are separate planes and are deliberately allowed to disagree.

| Situation | `decision` | `evidence` |
|---|---|---|
| allowed, engine succeeded | ALLOW | DEMONSTRATED |
| allowed, engine raised | ALLOW | **UNKNOWN** |
| refused | DENY | DEMONSTRATED (the refusal is) |

An engine failure is not a policy verdict. Collapsing the two is how a broken
capability silently becomes a security claim.

## The relay

`LoopbackRelay` is a dict lookup where a network will later sit. It holds no
policy, issues no leases and cannot execute. That is the entire point: when the
transport becomes a WebSocket, a BLE link or a local socket, nothing above or
below it changes. MCP, if used, is an adapter *over* this contract, never the
contract itself.

## What is not here yet

The sandbox, the marketplace, the identity seam, the agent roles, and any
additional legacy Windows host are not here yet. Doctor V0 now exists as a
pure observation-comparison plane; `docs/EVIDENCE.md` tracks the still-unproven
runtime claim.
