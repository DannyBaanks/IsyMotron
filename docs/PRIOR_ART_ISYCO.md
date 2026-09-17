# Prior art inside ISyCo

Before writing a line of this repo, `C:\Development\ISyCo` and
`C:\Development\ISyCo Git` were searched for the pieces the roadmap describes.
A surprising amount of the hard part already exists and has been exercised.

Everything below was verified by reading the files on **2026-09-17**, except
where a row is marked as coming from an earlier verified session.

---

## 1. Sentinel — the policy decision point already exists

`ISyCo/bridge_core/contracts/foundation/sentinel/sentinel.iesy`, verbatim:

```
1. Sentinel SOLO evalúa Systembilities.
   - Nunca ejecuta acciones.
   - Nunca modifica el ExecutionContext.
...
5. Si el conjunto de Systembilities está vacío,
   Sentinel debe devolver DENY (fail-closed).

Final Principle:
    "Sentinel no decide. Solo combina veredictos."
```

That is PEP/PDP separation and fail-closed, written down before IsyMotron
existed. The eight Systembilities are `WorkspaceBoundary`, `AuthorityChain`,
`CoreIntegrity`, `HookIsolation`, `CapabilityIsolation`, `ExecutionIntegrity`,
`RuntimeContract`, `PatternLinter`.

**What IsyMotron's `Enforcer` shares with it:** deny-by-default, a verdict type
that only the enforcer can produce, and the rule that an empty grant set is a
refusal rather than a wildcard.

**What it does not share:** IsyMotron's enforcer is per-request and
scope-parameterized (paths, allowlists, leases). Sentinel evaluates
Systembilities over an execution context. They answer different questions;
they agree about failure.

**The lesson to carry over, not the code.** From an earlier verified session:
Sentinel's problem was never that it did not work — it was *coverage*
(some execution paths routed around it) and a flag that stayed off for months
because nobody knew what would break. Measured across 81 capabilities: 70
ALLOW, 11 DENY, 0 ERROR. IsyMotron should not repeat that: the enforcer is on
the only path to execution from day one, and there is no flag.

## 2. The 8-operation contract shape is not a coincidence

`ISyCo/bridge_core/capabilities/cap.agent_bridge/handshake.py` implements an
async agent mailbox whose core is exactly eight verbs — verified by reading the
source today: `status`, `hello`, `peek`, `recv`, `summary`, `claim`, `send`,
`release`, `goodbye`.

IsyMotron's eight (`identify`, `describe`, `list_capabilities`,
`request_lease`, `validate_lease`, `execute_capability`, `return_receipt`,
`health`) are a different eight, for a different purpose. What transfers is the
discipline: a surface small enough to reimplement on an unlike substrate, and a
`claim`/`release` lease pattern that ISyCo already ran in anger.

That lease pattern also came with a scar worth inheriting. From an earlier
verified session on the bridge: a lease entry was found with a *topic* stored
in the holder field, because `claim` never validated the holder against the
agent registry. IsyMotron's `Lease` binds `(host, subject, capability, scope)`
and `Enforcer` re-checks all four at use time — `test_expired_lease_is_denied`
and the `LEASE_MISMATCH` branch exist because of that bug.

## 3. Capabilities as first-class directories

`ISyCo/bridge_core/capabilities/` holds **38 `cap.*` directories** (85 entries
total including templates and runtime folders). Each is a declared capability
with its own manifest and executor. The mental model IsyMotron needs —
capability as a named, versioned, individually-grantable unit — is already the
house style, not a new idea to sell.

## 4. OpencodeNative — the iOS boundary research is done

`ISyCo Git/OpencodeNative` (1.7 MB, MIT, CI on GitHub Actions) is a native
Swift agent runtime for iOS built to answer one question: can the OpenCode TUI
run on iOS? Its verdict: `BLOCKED` — no PTY/TTY, no spawn/exec, no Bun.

For IsyMotron this is worth more than the code. It is a **capability matrix for
iOS that was produced by hitting the wall**, which is exactly what
`describe()` on an iOS host has to return. The roadmap's reuse path
(`OpenCodeRuntimeContract` -> `NemoHostContract`) is real, with one caveat: take
the demonstrated boundaries, not the OpenCode-specific coupling.

## 5. The read gateway already solved "expose a tree, read-only, deny by default"

ISyCo has a read-only HTTP gateway over the repo with its own deny-by-default
path policy. Two findings from that work apply directly here:

- **Measure the protected surface, do not assume it.** When the denylist was
  measured against the real tree, it protected **17 files out of 111,091**.
  It was not wrong; it was narrow, and nobody had counted.
- **An execution plane can be a wider bypass than the read plane it sits
  beside.** A proposed exec-broker mounted the whole repo read-only and let the
  model choose the entrypoint, which reached every file the read gateway
  denied.

IsyMotron's equivalent risk is the Doctor's sandbox. When it is built, the
first thing to measure is not whether it catches an undeclared write — it is
what the sandbox can *read*, and where its artifacts land.

---

## What this means for the build

| Roadmap piece | Prior art | Action |
|---|---|---|
| Deterministic policy engine | Sentinel (contract + measured) | Reuse the discipline; write a new enforcer — different question |
| Lease / claim / release | Agent bridge (ran for months) | Reuse the shape **and the bug list** |
| Capability as a unit | 38 `cap.*` dirs | Reuse the model outright |
| iOS host capability matrix | OpencodeNative | Reuse the findings, not the coupling |
| Sandbox / Doctor | read gateway + exec-broker post-mortem | Reuse the *method*: measure the surface, do not argue about it |
| Receipts | causal ledger, evidence dirs | Look before building |
| Marketplace | nothing comparable | Genuinely new — and therefore the riskiest item on the roadmap |

The honest summary: of the roadmap's fourteen subsystems, roughly four have
real precedent in ISyCo, one (the marketplace) has none, and the rest are
between. That ratio is the argument for the sequencing in
`docs/ROADMAP_DELTA.md`.
