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

## Owner dogfood — same machine, real provider + real file

Comando base:
```bash
set -a; source ~/.config/isymotron/keys.env; set +a
export XDG_STATE_HOME=/tmp/isymotron_dogfood/state
ISYMOTRON_PROVIDER=nvidia python3 tools/link_task_runner.py --grants /tmp/isymotron_dogfood/grants.json --once
```
Task seed (inbox de `/tmp/isymotron_dogfood/state/isymotron/link/`):
```json
{"title": "lee la foto", "body": "lee /home/danny/isymotron-dogfood/photo-demo.png", "status": "queued"}
```
`~/isymotron-dogfood/photo-demo.png` interna al grants scope `/home/danny/isymotron-dogfood`.

Observado:

| Perfil | Tarea | Observado |
|---|---|---|
| full | task-dog1 | `done`: Nemotron propuso `filesystem.read`, ALLOW, `tool_profile: "full"` en receipt (`rcpt_b5ec460508c04c5a`, seal_ok=true), 140614 bytes, sha256 colocado en el result. |
| security | task-dog2 | `denied`, `detail: request_timeout`, `link_task_denied` con `tool_profile: "security"`. Pending request permaneció hasta expirar. |
| security | task-dog3 | A probada con scope `{"roots":["hostfs:/isymotron-dogfood"]}` de un item stale → retry → `DENY OUT_OF_SCOPE` (seal_ok=true). Demostrando que la bounds validation se aplica también tras aprobación (before fix `_derive_scope`). |
| security | task-dog4 | Approved explícita con scope declarado `{"roots":["/home/danny/isymotron-dogfood"]}` → `done` con `tool_profile: "security"`, `link_task_done` + `link_permission_decided(approved, lease_id=lease_442f…)`, mount timestamp. |

Receipts de estos runs viven en `/tmp/isymotron_dogfood/state/isymotron/link/receipts.jsonl` — no forman parte del state real del teléfono; el grano se movió con XDG_STATE_HOME override. Lifecycle of evidence: seed → NEEDS_APPROVAL-path → permission-decided → done/denied → ledger.
