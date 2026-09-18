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
