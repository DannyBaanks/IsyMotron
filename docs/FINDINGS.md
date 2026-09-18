# Findings

Things the code taught us that the design did not. Each one is dated, has a
regression test, and stays here even after it is fixed — a fixed bug that
leaves no record gets reintroduced.

---

## Finding 1 — a junction defeats a lexical scope check, and the receipt lied about it

**Found:** 2026-09-17, first contact between the contract and a real filesystem.
**Status:** fixed, two regression tests.

### What happened

M0's scope check was lexical: normalize the path, resolve `..`, compare against
the granted roots. Twenty-three tests passed, including `..` traversal,
backslashes, case folding and sibling prefixes.

On a real NTFS volume, a **directory junction** inside a granted root points
anywhere, and its path is lexically flawless:

```
C:/.../granted/escape/loot.txt      <- every character is inside the root
C:/.../granted/escape  -->  C:/.../secret     (mklink /J, no admin needed)
```

Measured, before the fix:

```
1) Enforcer lexico : {'decision': 'ALLOW', 'reason': None, 'detail': ''}
```

The enforcer said ALLOW. The string was never wrong; the *filesystem* was.

This is the exact class of failure `docs/EVIDENCE.md` warned that simulation
erases by construction — the simulated `_VirtualFS` had no links because
nothing in a Python dict can point outside itself. The warning was written
before the bug was found, which is the only reason we went looking.

### The second bug, which was worse

The engine *did* catch it. `Win11Host._resolve_inside` resolves the path with
`os.path.realpath` and re-checks containment, so no bytes leaked. But it raised
a plain exception, and `Host.execute_capability` had exactly one handler for
"the engine raised":

```python
except Exception as exc:          # engine failure is not a policy verdict
    result = {"error": type(exc).__name__, "message": str(exc)}
    evidence = Evidence.UNKNOWN
```

So the receipt read:

```
2) host completo   : {'decision': 'ALLOW', ...}
   evidence        : UNKNOWN
   result          : {"error": "ScopeEscape", "message": "... resolves outside ..."}
```

**`decision: ALLOW`.** An attempted scope escape was recorded in the ledger as
an allowed action with an unknown outcome. Anyone auditing receipts — a human,
a reviewer model, a metric — would count it on the wrong side. The defence
worked and the record of the defence was wrong, which is the more dangerous
half: a blocked attack that logs as permitted teaches you nothing the next time.

Root cause: `ALLOW` and `DENY` were treated as something only the `Enforcer`
could produce, so the engine had no vocabulary for refusing. Everything it
could say came out as a failure.

### The fix

`ScopeViolation` now lives in L0 (`core/isymotron/host.py`) and carries a
`DenyReason`. `execute_capability` catches it *before* the generic handler and
overrides the enforcer's verdict:

```python
except ScopeViolation as exc:
    decision = PolicyDecision(Decision.DENY, exc.reason, exc.detail)
    result, effects = {}, []
    evidence = Evidence.DEMONSTRATED
```

After:

```
junction  DENY | OUT_OF_SCOPE | evidence= DEMONSTRATED
          result: {}
          seal ok: True
legitimo  ALLOW | -            | evidence= DEMONSTRATED
```

### What this changes about the architecture

Enforcement is **two-stage, and both stages can say DENY**:

| Stage | Sees | Catches | Cannot catch |
|---|---|---|---|
| `Enforcer` (L0, pure) | the request as written | undeclared params, missing/expired leases, ungranted capabilities, lexical escapes | anything the OS resolves |
| the engine | the resolved path | junctions, symlinks, 8.3 names, mount points | a path that does not exist yet — it resolves the nearest existing ancestor instead |

Neither is sufficient. The lexical check cannot see the filesystem; the
resolving check cannot resolve what has not been created. Both run on every
filesystem call.

The general rule, now a contract term: **an engine may refuse on authority
grounds, and that refusal outranks the enforcer's ALLOW.** A refusal is a
refusal wherever it is discovered, it carries no payload, and it is
`DEMONSTRATED`, never `UNKNOWN`.

### Regression tests

- `test_junction_inside_a_granted_root_is_denied` — asserts the enforcer alone
  *is* fooled (so the test fails if someone "simplifies" the two stages into
  one), then asserts the host as a whole is not.
- `test_junction_write_is_denied_too` — and the file does not appear in the
  target directory.
- `test_write_to_a_nonexistent_path_outside_scope_is_denied` — the
  nearest-ancestor resolution.

Both junction tests **ran** on this machine, they did not skip:

```
tests\test_win11_real.py ..                                              [100%]
2 passed, 14 deselected in 0.48s
```

### Still open

Not yet tested, and therefore `UNKNOWN`, not "fine":

- Network paths (`\\server\share`) and device paths (`\\?\C:\`, `\\.\PhysicalDrive0`).
- NTFS alternate data streams (`file.txt:hidden`).
- A junction created *between* the enforcer's check and the engine's read
  (TOCTOU). The window is small and single-process today; it stops being small
  when the relay is a network service.
- Case-folding on a volume mounted case-sensitive.

---

## Finding 2 — a grant file that fails to parse must mean *no* authority

**Found:** 2026-09-17, while writing `Grants.load`.
**Status:** designed in from the start, test `test_unparseable_grant_file_yields_an_inert_host`.

Not a bug that shipped — a bug that was one line away. `Grants.load` wraps
`json.load` in a `try`, and the tempting `except` body is `return Grants()`
with default fields. Defaults mean "nothing configured", and in most systems
nothing configured means nothing restricted.

Here it must mean the opposite: a grant file we cannot read yields a host with
**zero** granted capabilities, which still identifies, describes and reports
healthy, and denies everything.

This is the same shape as a bug already on record elsewhere in ISyCo: a BOM in
a JSON file made a lease registry unparseable, the handler silently returned
the default, and the default read as *"there are no leases"* — which would have
permitted claims on topics that were already held. Same line of code, same
`except`, opposite meaning intended.

Hence `Grants.save` writes `utf-8`, never `utf-8-sig`, and `Grants.load` reads
`utf-8-sig` so it tolerates a BOM someone else introduced. Tolerant reader,
strict writer, and a failure that fails closed.

---

## Finding 3 — an under-budgeted reasoning model returns thinking, not a short answer

**Found:** 2026-09-17, first Nemotron calls.
**Status:** detected and reported distinctly, two tests.

`nvidia/nemotron-3-super-120b-a12b` returns its chain of thought in a separate
`reasoning_content` field. That is the well-behaved case. The trap is what
happens when `max_tokens` runs out before the thinking ends.

Measured on the same prompt (`"Reply with exactly: OK"`):

| max_tokens | finish_reason | out | `content` |
|---|---|---|---|
| 16 | `length` | 16 | `'The user says: "Reply with exactly: OK". So '` |
| 48 | `stop` | 23 | `'OK'` |
| 120 | `stop` | 15 | `'OK'` |
| 400 | `stop` | 26 | `'OK'` |

Under-budgeting does not shorten the answer. **It replaces the answer with
thinking.** A planner asking for strict JSON gets fluent prose back and every
symptom points at the prompt: "the model ignores the format instruction", "it
explains instead of answering", "it is bad at JSON". None of that is true, and
changing the prompt cannot fix it.

The first cross-host plan we asked for hit exactly this at 900 tokens. The
same request succeeded at 1600, using 831 output tokens and 2,681 characters of
reasoning.

**Fix.** `Completion.truncated` reads `finish_reason == "length"`, and
`Planner.parse` raises `TRUNCATED` instead of `NOT_JSON` when it applies. The
two have opposite remedies — raise the budget, versus change the prompt — so
collapsing them costs an afternoon of debugging the wrong thing.

**Operational rule:** budget output tokens for reasoning plus answer, and treat
`finish_reason == "length"` as a hard error, never as a parseable reply. Our
plan budget is 2000.

---

## Finding 4 — the planner refused a legitimate request, and it was right

**Found:** 2026-09-17, first real planner run.
**Status:** capability improved; the model's objection was correct.

Asked to *"copy my most recent photo from the Victus to the RetroBox's inbox
and then open DOOM there"*, Nemotron returned zero steps and this reason:

> Cannot identify the most recent photo because no capability to list files
> with timestamps or sort by date.

That was true. `filesystem.read` returned bare names on a directory. Nothing in
the catalogue could answer *"most recent"*, so no correct plan existed.

Two things came out of it.

**The product gap.** Directory listings now carry `bytes` and `modified` per
entry, sorted newest first, with `"order": "modified_desc"`, on both the real
engine and the fixture. One UTC, second-resolution, string-sortable time
grammar for every host generation.

**Our own verdict bug.** The probe scored this as `FAIL (no steps)`. It was the
behaviour we designed for — an empty plan *with a stated reason* is a correct
refusal — and a two-class verdict had no way to say so. `Plan.verdict()` now
returns one of three: `PLANNED`, `REFUSED_WITH_REASON`, `EMPTY_NO_REASON`. Only
the last is a failure.

This is the recurring shape: the `else` branch of a preregistered verdict must
never land in the wrong class, and the way to find out is to test every class
before trusting the score. Our first correct refusal was scored as a bug.

**Worth keeping in view:** the planner functions as a reviewer of the
capability design. It found a real gap in the catalogue faster than we did, by
being unable to do its job.

---

## Finding 5 — two engines returned the same value under different names

**Found:** 2026-09-17, first plan executed against the real Windows host.
**Status:** fixed; `returns` is now part of the manifest, two regression tests.

Nemotron planned a correct three-step transfer from the real `win11-danny` host
to the legacy fixture, and the executor stopped at step 3:

```
step 3.content needs field 'content' of step 2,
which returned ['bytes', 'kind', 'path', 'sha256', 'text']
```

`filesystem.read` returned file contents as `content` on the simulator and as
`text` on the real host. Same capability id, same version, same declared
params, **incompatible results.**

The model could not have got this right. The catalogue advertised each
capability's `params` and never its result shape, so every `$from` reference
was a guess with no way to check it.

Invariant 2.1 says *"capability != implementation; the contract is stable, the
backend is local."* We had been treating only the *input* side as contract. The
output side was left to whoever wrote the engine, and two engines drifted
within a day.

**Fix.** `CapabilityManifest.returns` declares the keys a successful result
carries. The catalogue shows it to the planner, `Planner.parse` rejects a
reference to a field the source capability does not declare
(`UNKNOWN_RESULT_FIELD`), and both engines were aligned on the real host's
names — the real one is ground truth, the fixture follows.

It failed closed: nothing was written with wrong data, and the error named the
fields that did exist. But it would have failed *in the demo*, on the flagship
cross-device transfer, where the symptom is a file arriving empty.

**The general rule, now a contract term:** a capability's result shape is part
of its contract. An engine that returns a different key is not an
implementation detail, it is a different capability.

---

## Finding 6 — a plan is a proposal, demonstrated by a model that got it wrong

**Found:** 2026-09-17.
**Status:** no fix needed; this is the product working.

The first fully successful cross-device run from the real Windows host ended
like this:

```
paso 1: win11-danny    :: filesystem.read  {"path": ".../Demo/nota.txt"}
paso 2: win98-retrobox :: filesystem.write {"content": {"$from": {"step": 1, "field": "text"}}}
paso 3: win98-retrobox :: apps.launch      {"app": "DOOM"}

completed = False | stop: step 3 denied: OUT_OF_SCOPE
```

Steps 1 and 2 worked: real text from a real disk landed on the other host
through a typed reference. Step 3 asked to launch `DOOM`. The allowlist grants
`DOOM.EXE`. The host refused.

The model was not malicious and not even really wrong — it was *approximate*,
which is what models are. The allowlist does not do approximate. No prompt
instructed this, no reviewer model weighed in, and the plan validated cleanly
before execution: the refusal came from the grant file on the machine.

That is roadmap Target Claim B — *a host can deny an action outside locally
granted scope even if the model requests it* — with an actual model actually
requesting it. Recorded in `docs/EVIDENCE.md`.

---

## Finding 7 — the provider fails in two unrelated ways, and only one of them is the provider

**Found:** 2026-09-17.
**Status:** fixed; deadline, transport retry and pacing added.

Two separate failures turned up while measuring the inference path, and it
matters a great deal that they are not the same failure.

### 7a — a real provider error, measured

Twelve back-to-back calls to NVIDIA NIM, all identical:

```
   0:   2.53s  stop        6:   1.36s  stop
   1:   1.43s  stop        7:   0.75s  stop
   2: ERROR status=503     8:   0.86s  stop
      "Service temporarily overloaded"
   3:   1.56s  stop        9:   6.16s  stop
   4:   2.54s  stop       10:   1.97s  length
   5:   1.57s  stop       11:   0.96s  length

ok=11 err=1   min 0.75s  median 1.56s  max 6.16s
```

**One HTTP 503 in twelve**, with healthy calls on both sides of it. No warning,
no pattern. At that rate a three-minute live demo making a handful of calls has
a meaningful chance of hitting one, and an unretried 503 in front of judges
looks exactly like a broken product.

Sample size twelve. That is a spot measurement, not a rate, and
`docs/EVIDENCE.md` records Target Claim H as `NOT_DEMONSTRATED` accordingly.

### 7b — a failure we nearly misattributed

A follow-up run of 25 calls produced something far worse: 7 successes, then one
request that hung for **793 seconds** despite `timeout=120`, then eighteen
consecutive failures with `status=None`. A minute later the same endpoint
answered in 0.89 s.

The draft of this finding said "sustained bursts trigger throttling that
manifests as dropped connections." That was wrong. **The laptop had been closed
and carried out of the house mid-run.** There was no throttling and no provider
fault; the network simply went away underneath an open socket.

It is worth recording the near-miss, not just the correction. Every number was
real, the reasoning was plausible, and the conclusion was false — because the
one variable that explained it was not visible from inside the process. This is
the failure mode the whole evidence discipline exists to catch, and it caught
it only because a human said what had actually happened.

### Corroboration, found afterwards

The Windows System log, read without elevation, holds the answer that was
sitting on the machine the whole time:

```
21:51:44  Kernel-Power 506  entering modern standby
22:04:59  Kernel-Power 507  exiting modern standby
```

**795 seconds.** The hung request measured **793.32 s**. Two independent
sources agreeing within two seconds, both saying the machine was asleep.

The evidence existed and nothing was reading it. That is what `docs/HOST_AWARENESS.md`
and finding #8 are about.

### What survives, and what it changed

7b is not evidence about NVIDIA. It is excellent evidence about **us**, and the
fixes stand on their own:

- **`urllib`'s `timeout` is not a deadline.** It applies per socket operation.
  A socket that stops producing data without closing never trips it, which is
  how a 120-second timeout permitted a 793-second call. `DEADLINE_S` (90 s,
  `ISYMOTRON_DEADLINE_S`) is a wall clock across all attempts. A demo machine
  that sleeps, or a hotel wifi that drops, is not an exotic scenario.
- **A status-less transport error is retryable.** It was classified otherwise,
  which is backwards for the commonest case there is: a network that comes
  back. `ProviderError.transport` now marks it, and it retries with backoff.
- **Pacing.** `MIN_INTERVAL_S` keeps a floor of 250 ms between calls. Cheap
  insurance against our own bursts, whatever they do or do not trigger.

Retries remain purely a *transport* decision. A host that said DENY is never
asked twice.

### Still open

- Whether NVIDIA NIM throttles at all, and at what rate. `UNKNOWN` — the run
  that looked like throttling was not.
- The real 503 rate over a realistic workload. Twelve calls is not a rate.
- Nebius Token Factory's behaviour on both counts: entirely unmeasured.

---

## Finding 8 — Python's clocks cannot see a Windows suspend, and a second one can

**Found:** 2026-09-17, building the fix for #7b.
**Status:** fixed; `HostAwarenessEngine`, 21 tests, `docs/HOST_AWARENESS.md`.

The obvious defence against #7b is to compare a wall clock with a monotonic
clock: if wall advances much more than monotonic, the machine slept.

**On Windows that detects nothing.** Measured here:

```
GetTickCount64      42365.203 s
time.monotonic()    42365.203 s     <- the same counter
```

Python's `time.monotonic()` *is* `GetTickCount64()`, and both it and
`time.time()` advance through suspend. The standard trick fails silently on the
platform we ship on first.

There is a third counter that does not:

```
GetTickCount64                42365.203 s  (11.77 h)   includes sleep
QueryUnbiasedInterruptTime    35038.317 s  ( 9.73 h)   excludes sleep
-------------------------------------------------------------------
difference = suspend bias      7326.886 s  ( 2.04 h)   time spent asleep
```

The difference is monotonically non-decreasing, and any increase between two
readings is exactly the time slept in between. Across a two-second awake
interval it moved **2.2 ms**, so noise is milliseconds and a suspend is
seconds. Two `ctypes` calls: no admin, no message pump, no thread, no polling.

Both `QueryInterruptTime` and the `*Precise` variants turned out **not to be
exported from `kernel32`** on this build (they live in `KernelBase.dll`), which
is the kind of thing only a call discovers. `QueryUnbiasedInterruptTime` is in
`kernel32` and is all that is needed.

**What this changed.** Every provider call now takes a host snapshot before and
after and compares epochs, and `attribute()` checks host continuity *before* it
looks at the error — because a transport failure during a suspend is a suspend.
`HOST_SUSPENDED` is never `PROVIDER_ERROR`, and a host-interrupted call is
excluded from `fault_rate` explicitly rather than silently.

The general lesson, and the reason this is architecture rather than a prompt:
**a model asked to explain a 793-second call had no mechanism that could have
known.** The answer was available on the machine, in a counter nothing was
reading. Adding "remember that laptops sleep" to a prompt would have produced a
plausible guess in place of a measurement.
