# Tool Profiles — evidence run

Status: DEMONSTRATED on host authority paths (pytest 571 pass; physical mobile = NOT_DEMONSTRATED).

## Environment

- Host: Linux (DannyISyCo desktop), grants file `~/.config/isymotron/grants.json`
- Repo HEAD (see current git) on branch `claude/exciting-lamport-84gclk`
- Tests: `python3 -m pytest -q` → 571 passed, 15 skipped
- Mobile tests: `cd mobile && npm test` → 75 passed
- e2e:gus PASS; pairing e2e PASS (includes GUS ISYMOTRON delegate step)

## Full

- full + legal capability → ALLOW, receipt with tool_profile=full
- full + unknown capability → DENY CAPABILITY_UNAVAILABLE
- full + hard-bound violation → DENY (fs path outside scope)
- receipts `link_task_*` carry `tool_profile: "full"`

## Security

- request → permission request on the shared queue → approve → ALLOW → done (`link_task_done`)
- deny → `denied` (`link_task_denied`, `human_denied`)
- no response → timeout → `denied` (`request_timeout`)
- The phone must be the human approving; no phone client in this run — physical mobile = NOT_DEMONSTRATED.

## Custom

- default-enabled capability → ALLOW
- disabled + `--no-prompts` → DENY CAPABILITY_NOT_GRANTED
- disabled + `--allow-prompts` → NEEDS_APPROVAL → approval → ALLOW
- inertia: no grants file → inert host, catalogue empty

## Guard clauses (legacy)

- Grants with no `tool_profile` → `security` (least-privilege default)
- Unknown profile string → inert (no authority)

## Authority invariants (still true in every profile)

- Model cannot mint grants, widen scope, extend TTL beyond max, mint unknown capabilities, bypass the manifest, or forge receipts.
- `full` never skips the enforcer or the scope checkers; it only skips the per-capability prompt.
- Protocol surface unchanged: MODEL PROPOSES → HOST DECIDES → EXECUTION/DENY → RECEIPT.
