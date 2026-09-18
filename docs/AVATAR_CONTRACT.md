# Avatar contract — AV0 (frozen 2026-09-18)

The avatar is a **representation** of IsyMotron. It is never an authority,
never a grant surface, and never evidence. This file freezes the two trust
channels and what each may make the avatar show. Changing anything under
"Frozen" is a contract change: bump to AV-contract v2 and say why in
`docs/FINDINGS.md`.

Companion of: `docs/AVATAR_ROADMAP.md` (operational), `docs/AVATAR_BRIDGE.md`
(context).

---

## 1. Two channels, one avatar

| | **authority** channel | **open** channel |
|---|---|---|
| Who writes | the IsyMotron process only (console server, executor, HostAwareness) | anyone: OpenCode, OpenISy, Claude Code hooks, scripts |
| Transport | in-process `AvatarBus`, served by `GET /api/avatar` behind the session token | `inbox.jsonl`, append-only, `companion-event-v1` unchanged |
| May show a verdict (ALLOW/DENY) | **yes** | **never** |
| May show host badge / host_id / receipt id / seal state | **yes** | **never** |
| May change the animation state | yes, with precedence | yes, only when no authority event is active (see §4) |
| May show text | yes, in the host frame | yes, **always** in the third-party frame, prefixed with its `agent` |
| Persisted across restart | **no** (a stale verdict is never re-shown) | the file persists; the reader starts at end-of-file |

## 2. Frozen rules

**R1 — The channel is assigned by where an event came from, never by what it
says.** The reader stamps `channel`. Any `channel`, `decision`, `receipt_id`,
`seal_ok`, `host_id`, `badge` or `verified` field inside an inbox line is
dropped before rendering. An inbox line cannot become an authority event by
shape, content, agent name or timing.

**R2 — Only the authority channel renders verdict visuals.** The verdict
visuals are: the host badge, the words ALLOW/DENY in the verdict slot, the
receipt id, the seal indicator, and the DENY reason. Renderers draw them only
from events whose `channel == "authority"` as stamped by the server.

**R3 — External text is shown verbatim, framed, never filtered.** A `say` of
`"ALLOW ✅"` from the inbox is rendered as `<agent>: ALLOW ✅` inside the
third-party frame. We do not keyword-filter: filtering is bypassable and would
suggest that unfiltered text is trustworthy. The frame is the defense.

**R4 — Reserved agent names are shown as unverified.** If an inbox `agent`
equals (case-insensitive) `isymotron`, `host`, `system`, `authority`, or any
current `host_id`, the label is rendered `unverified: <agent>`.

**R5 — The avatar holds no authority and asks for none.** No avatar code path
may call `/api/grant`, `/api/revoke`, `/api/execute`, `/api/run` or
`/api/plan`. The desktop avatar's token is read-only in effect: it only reads
`/api/avatar` and `/api/state`. (A read-only token tier is AV3 scope.)

**R6 — Authority details are logical.** Verdict text uses the logical names
from `core/isymotron/resources.py` (`hostfs://demo`, app id `doom`). A physical
path never reaches a renderer (the phone may be watching).

**R7 — Mode never changes authority.** `mode` is `avatar` (no provider
configured) or `agent` (provider configured). Switching mode may enable
planning; it must not change any grant, bound, lease or enforcer decision.

## 3. Event shapes

### 3.1 Authority event (server-produced, served by `/api/avatar`)

```json
{
  "seq": 42,
  "channel": "authority",
  "kind": "verdict",
  "at": "2026-09-18T20:00:00Z",
  "host_id": "win11-danny",
  "capability": "filesystem.write",
  "decision": "DENY",
  "reason": "OUT_OF_SCOPE",
  "detail": "hostfs://demo/hola.txt names no granted resource; granted: ['hostfs://nemoinbox']",
  "receipt_id": "rcpt_81bf729e7dfe47d5",
  "seal_ok": true,
  "state": "error",
  "text": "The host refused: filesystem.write outside hostfs://nemoinbox"
}
```

`kind` is one of:

| kind | produced when | state |
|---|---|---|
| `mode` | console start, provider (un)configured | `idle` |
| `planning` | `/api/plan` starts | `thinking` |
| `planned` | plan returned (`PLANNED` / `REFUSED_WITH_REASON` / rejected) | `waiting` |
| `step` | each executor step starts | `working` |
| `verdict` | each receipt (from `/api/run` or `/api/execute`) | `success` on ALLOW, `error` on DENY |
| `host` | HostAwareness reports suspend / network change | `waiting` |
| `provider_error` | provider failure (attribution included) | `error` |

Only `verdict` carries `decision`, `receipt_id`, `seal_ok`.

### 3.2 Open event (inbox, `companion-event-v1`, unchanged)

Exactly Companion's SPEC (`C:\Development\ISyCo Git\Companion\SPEC.md`):
required `version`, `id`, `agent`, `created_at`, `type`; types `summon`,
`hide`, `say`, `state`, `mood`, `move`, `status`. After validation the reader
emits:

```json
{"seq": 43, "channel": "open", "agent": "opencode", "agent_verified": false,
 "type": "say", "text": "ALLOW ✅", "ttl": 8, "priority": 0}
```

`agent_verified` is always `false` in v1 (there is no way to verify it).

## 4. Precedence (renderers)

1. An active authority `verdict` (its TTL, default 8 s; DENY 12 s).
2. An active authority `host` or `provider_error`.
3. Authority `planning` / `step` / `planned`.
4. Open-channel `state` / `mood` / `say`.
5. `idle`.

Open `say` bubbles still display during 1–3, stacked below the host frame and
visibly third-party; they never replace or restyle it.

## 5. Staleness, replay, malformed

- Open events older than 60 s by `created_at`, or dated more than 60 s in the
  future, are dropped.
- Open event `id`s seen in the last 1000 events are dropped (replay).
- Malformed lines are counted and skipped; they never stop the reader and are
  never shown.
- Authority events live only in memory (ring buffer, 200). After a restart the
  avatar starts from a fresh `mode` event.

## 6. Out of scope for v1

Signed third-party identity (`agent_verified: true`), reminders/timers,
Companion's pack editor, any avatar-initiated action.
