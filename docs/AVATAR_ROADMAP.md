# Avatar roadmap — operational (track AV)

**This is the operational artifact.** A coder continues from here without the
original conversation. Context and reasoning: `docs/AVATAR_BRIDGE.md`. Frozen
rules: `docs/AVATAR_CONTRACT.md` (cited below as R1–R7).

Track prefix is **AV** because `M0–M5` are IsyMotron's product milestones and
`docs/ROADMAP_DELTA.md` already reserves `M6'`/`M7'`.

## How to work this file

1. Take the first milestone whose status is not `DONE` and whose dependencies
   are `DONE`. Set it `IN_PROGRESS` and commit that one-line change first.
2. Write the tests listed under **Tests** first; watch them fail.
3. Implement the minimum. Run the **whole** suite: `python -m pytest -q`
   from the repo root (baseline at AV0: **151 passed**).
4. Produce the **Evidence**. Set status `DONE`, fill `Result:` with the
   commit hash and test count. One commit per milestone (the **Commit
   boundary** line is the message subject).
5. If a **Failure condition** triggers: revert the milestone's commit(s),
   set `BLOCKED`, write why under `Result:`. Never leave half a milestone in
   `master`.

Global rule for every milestone: **do not modify** `core/isymotron/*`,
`hosts/*`, `agents/planner.py` or the grant file format. The avatar is
outside the authority boundary; if a milestone seems to need a change there,
stop and mark `BLOCKED` — that is an architecture question, not a coding one.

Language: code, docs and UI strings in English; `docs/GUIA.es.md` sections in
Spanish with real executed output (ISyCo `AGENTS.md` § 10b convention).

---

## Status board

| ID | Milestone | Status | Depends on |
|---|---|---|---|
| AV0 | Freeze architecture + contract | **DONE** | — |
| AV1 | Pure avatar model (bus, channels, precedence) | **DONE** | AV0 |
| AV2 | Open channel: inbox reader, companion-event-v1 | **DONE** | AV1 |
| AV3 | Authority channel: producers + `/api/avatar` | **DONE** | AV1 |
| AV4 | Web renderer in the console | **DONE** | AV2, AV3 |
| AV5 | Desktop renderer (Companion window, adapted) | **DONE** | AV2, AV3 |
| AV6 | No-AI mode ("avatar" mode) | **DONE** | AV3 |
| AV7 | AI mode ("agent" mode) | **DONE** | AV6 |
| AV8 | Adversarial suite | **DONE** | AV4, AV5 |
| AV9 | Demo path, packaging, docs | NOT_STARTED | AV7, AV8 |

---

## AV0 — Freeze architecture + contract

- **Status:** DONE
- **Objective:** freeze the two trust channels before any code exists.
- **Scope:** `docs/AVATAR_CONTRACT.md`, `docs/AVATAR_ROADMAP.md`,
  `docs/AVATAR_BRIDGE.md`. No code.
- **Acceptance:** authority-only fields listed (R1, R2); third-party
  rendering rule (R3, R4); avatar holds no authority (R5); logical details
  (R6); mode never changes authority (R7); event shapes, precedence,
  staleness/replay rules written.
- **Result:** committed with this file (see `git log -- docs/AVATAR_*`).

---

## AV1 — Pure avatar model

- **Objective:** the security heart, with no I/O and no UI: an `AvatarBus`
  that stamps channels by source, keeps precedence, and renders a `View`.
- **Scope:** new package `avatar/` at repo root (sibling of `console/`,
  `agents/`). Pure Python, stdlib only.
- **Files to create:** `avatar/__init__.py`, `avatar/model.py`,
  `avatar/protocol.py`, `tests/test_avatar_model.py`.
- **Do not touch:** everything outside `avatar/` and `tests/`.
- **Minimal implementation:**
  - `avatar/protocol.py`: port of Companion's `validate_event` and the
    `STATES`/`POSITIONS` sets from
    `C:\Development\ISyCo Git\Companion\src\companion\protocol.py` (58 lines,
    MIT, same author). Keep behaviour identical; add a header naming the source
    commit (`0aae576`).
  - `avatar/model.py`:
    - `AvatarBus.publish_authority(kind, **fields)` — the only way to create an
      authority event; assigns `seq`, `at`, `channel="authority"`.
    - `AvatarBus.publish_open(raw: dict, now)` — validates via protocol,
      **drops** the forbidden fields of R1, applies R4 labelling, staleness and
      replay rules (contract §5), stamps `channel="open"`,
      `agent_verified=False`.
    - `AvatarBus.since(seq) -> list[event]` — ring buffer (200).
    - `AvatarBus.view(now) -> View` — resolves precedence (contract §4):
      `state`, `host_frame` (authority text + verdict slot or None),
      `third_party` (list of framed open bubbles).
- **Acceptance criteria:**
  - no public API creates an authority event from a dict that came from the
    open channel;
  - an open event carrying `channel: "authority"`, `decision`, `receipt_id`,
    `seal_ok`, `host_id`, `badge`, `verified` produces a view with
    `host_frame is None`;
  - precedence and TTL behave per contract §4 under a fake clock.
- **Tests required:** `test_open_event_cannot_set_channel`,
  `test_forbidden_fields_are_dropped`, `test_reserved_agent_is_unverified`,
  `test_stale_and_future_events_are_dropped`, `test_replayed_id_is_dropped`,
  `test_malformed_is_counted_not_raised`,
  `test_verdict_outranks_open_state`, `test_open_say_stays_framed_under_verdict`,
  `test_deny_ttl_longer_than_allow`, `test_protocol_matches_companion_cases`
  (copy the `validate_event` / `ProtocolError` cases from Companion's `tests/test_companion.py`).
- **Evidence:** test count; no new dependency (`git diff --stat` shows only
  `avatar/` and `tests/`).
- **Failure conditions:** any need to import from `console/` or
  `core/isymotron/policy.py` into `avatar/model.py` → design error, stop.
- **Commit boundary:** `AV1: avatar model -- the channel is where it came from, not what it says`
- **Result:** `f79a37e`; 161 passed (151 baseline + 10 new), `py -m pytest -q`;
  `git diff --stat` vs baseline shows only `avatar/` (protocol port from
  Companion `0aae576`, model) and `tests/test_avatar_model.py`; no new
  dependency; the 10 required tests all present and passing.

---

## AV2 — Open channel: inbox reader

- **Objective:** existing Companion producers work unchanged against
  IsyMotron.
- **Files to create:** `avatar/inbox.py`, `tests/test_avatar_inbox.py`.
- **Do not touch:** `avatar/model.py` semantics (bug fixes only, with a test).
- **Minimal implementation:**
  - inbox path: `$ISYMOTRON_AVATAR_INBOX`, else
    `$COMPANION_ROOT/inbox.jsonl` (so the OpenCode/OpenISy plugins in
    `C:\Development\ISyCo Git\Companion\integrations\*.ts` work by setting one
    env var), else `%LOCALAPPDATA%\IsyMotron\avatar\inbox.jsonl`.
  - `InboxTail`: starts at **end of file**, reads only complete lines (a final
    line without `\n` waits — same rule as Companion's runtime), survives
    truncation/rotation (size < offset → reset to 0), feeds
    `AvatarBus.publish_open`.
  - polled from the console process (a daemon thread, 250 ms). No watcher
    libraries.
- **Acceptance:** a line appended by a separate process appears in
  `bus.since()` within 1 s as `channel="open"`; a partial line is not read
  until completed; backlog present at startup is not replayed.
- **Tests required:** `test_tail_starts_at_end`, `test_partial_line_waits`,
  `test_truncation_resets`, `test_env_precedence`,
  `test_companion_plugin_line_is_accepted` (use the exact JSON shape emitted
  by `integrations/opencode-plugin.ts`).
- **Evidence:** a real run: append a line with
  `echo {...} >> inbox.jsonl` and show it in `bus.since(0)`; paste output into
  `Result:`.
- **Failure conditions:** reading the whole file on each poll (O(n) growth);
  any path where an inbox line reaches `publish_authority`.
- **Commit boundary:** `AV2: open channel -- companion-event-v1 in, framed as third party`
- **Result:** `659e4b8`; 166 passed (161 + 5 new), `py -m pytest -q`; real run
  (separate `cmd` process, `echo {...} >> inbox.jsonl`, poller daemon 250 ms):
  event in `bus.since(0)` in **0.281 s** as
  `{"seq": 1, "channel": "open", "agent": "opencode", "agent_verified": false,
  "type": "say", "text": "hola desde un proceso aparte", "ttl": 8, "priority": 0}`;
  backlog present at the tail's first sighting was **not** replayed
  (`bus.since(0) == []`, 0 accepted); malformed lines counted, none raised.
  Note: one test initially failed because it wrote the plugin line *before*
  the tail's first sighting — that is backlog by definition (contract §1);
  the test was reordered, the reader semantics did not change.

---

## AV3 — Authority channel

- **Objective:** only the IsyMotron process produces verdict visuals, over an
  authenticated transport.
- **Files to touch:** `console/server.py` (producers + endpoint),
  `console/__main__.py` (create bus, start inbox tail),
  `tests/test_console.py` (extend), new `tests/test_avatar_authority.py`.
- **Do not touch:** `agents/executor.py` return types, `core/*`, `hosts/*`.
  Hook at the console layer, where receipts are already appended
  (`_run`, `execute`, `_plan`, awareness block).
- **Minimal implementation:**
  - `AvatarBus` owned by the console `State`.
  - producers per contract §3.1: `planning`, `planned`, `step`, `verdict`
    (one per receipt, with `receipt_id`, `seal_ok = receipt.verify()`),
    `host`, `provider_error`, `mode`.
  - `GET /api/avatar?since=<seq>` → `{"events": [...], "view": {...}}`,
    behind the existing session token.
  - **read-only avatar token**: a second random token, accepted only by
    `GET /api/avatar` and `GET /api/state`; written to
    `%LOCALAPPDATA%\IsyMotron\session\avatar.token` (never argv, never a URL
    printed to the console). Every POST route rejects it (R5).
- **Acceptance:** a real `/api/run` produces one `verdict` per step with the
  right `decision`; the avatar token gets 403 on every POST; verdict `detail`
  contains no physical path (R6).
- **Tests required:** `test_run_emits_one_verdict_per_receipt`,
  `test_deny_verdict_carries_receipt_and_seal`,
  `test_avatar_token_cannot_post_anything` (grant, revoke, execute, run,
  plan), `test_avatar_endpoint_requires_a_token`,
  `test_verdict_detail_is_logical`, `test_plan_emits_planning_then_planned`.
- **Evidence:** console started with `--demo-host`, one `/api/run`, the
  `/api/avatar` JSON saved to `evidence/AV3/avatar_events.json` (scrub:
  must contain no `C:/Users`).
- **Failure conditions:** any verdict emitted from a code path that did not
  hold a real `ExecutionReceipt`.
- **Commit boundary:** `AV3: authority channel -- verdicts come from receipts, over a token the avatar cannot write with`
- **Result:** `febd2d0`; 173 passed (166 + 7 new), `py -m pytest -q`. Live
  evidence: console started with `--demo-host` (real process, port 8791),
  one `/api/run` of two steps on `win98-retrobox` only -> 2 verdicts, both
  `seal_ok=true`, detail logical (`filesystem.read on
  hostfs://games/DOOM/DOOM.EXE`), scrub PASS (no `C:/Users`, no `\` in
  `evidence/AV3/avatar_events.json`); events by kind: mode 1, step 2,
  verdict 2; `view.host_frame` carries the verdict slot only from authority.
  Note: a first evidence run executed the read on the REAL host
  (`win11-danny`) by mistake in the selection logic of the evidence script
  (read-only, denied OUT_OF_SCOPE with empty result); the script now selects
  `win98-retrobox` explicitly. No unit test used the real host.

---

## AV4 — Web renderer

- **Objective:** the same avatar inside the console (and so on the phone
  with `--lan`).
- **Files to touch:** `console/static/*` (index.html, app js, css),
  `console/server.py` (`SERVABLE` allowlist gains the pack files),
  new `avatar/packs/malbolge-cat/` (copy of Companion's pack, 417 KB, 6 GIFs +
  `manifest.json`) plus `avatar/packs/NOTICE` (MIT, source repo, commit).
- **Do not touch:** CSP (no inline script/style), token handling.
- **Minimal implementation:** poll `/api/avatar?since=`; show the GIF for
  `view.state`; **host frame** (badge = host_id, verdict slot, receipt id,
  seal ✓/✗) only from `view.host_frame`; **third-party bubbles** in a visually
  distinct style with the `agent` label (and `unverified:` per R4). All text
  via `textContent`, never `innerHTML`.
- **Acceptance:** screenshot shows a real DENY in the host frame and an inbox
  `"ALLOW ✅"` in a third-party bubble at the same time; no CSP violations in
  the browser console.
- **Tests required:** `test_pack_files_are_served_by_allowlist_only`,
  `test_no_directory_traversal_into_packs`, `test_static_js_never_uses_innerHTML`
  (grep-style test over the shipped JS).
- **Evidence:** `evidence/AV4/web_avatar.png`.
- **Failure conditions:** any renderer path that styles an open event with
  host-frame classes.
- **Commit boundary:** `AV4: web avatar -- the verdict has a frame no inbox line can reach`
- **Result:** `e034241`; 177 passed (173 + 4 new), `py -m pytest -q`. Live
  acceptance evidence (`evidence/AV4/web_avatar.png`, captured in ONE
  in-page run): `/api/execute` on `win98-retrobox` -> DOM read at +1.6 s:
  gif `error.gif`, host frame VISIBLE with badge `win98-retrobox`,
  verdict `DENY` (class `verdict deny`), receipt `rcpt_0789fb09710b4856`,
  `seal ok`, text `The host refused: filesystem.read (OUT_OF_SCOPE)` — and,
  at the same instant, third-party bubble `{label: "opencode", text:
  "ALLOW ✅"}` verbatim. CSP: 0 errors / 0 warnings in the browser console.
  Notes: (1) `avatar.js` initially 404'd (missing from `SERVABLE`; Chrome
  refused the JSON-typed 404 as a script) — caught live and fixed. (2) The
  DOM verification used a `say` with `ttl: 60` because tool-call latency
  exceeded the plugin's `ttl: 8`; the first screenshot (taken 1.2 s after
  the trigger) captured the ttl-8 moment. (3) The PNG was not visually
  inspected by the coding agent (image input unsupported); the DOM-level
  read in the same run is the executable verification.

---

## AV5 — Desktop renderer

- **Objective:** the floating transparent pet, from the same `.exe`.
- **Files to create/touch:** `avatar/window.py` (adapted from
  `C:\Development\ISyCo Git\Companion\src\companion\window.py`, 480 lines),
  `avatar/pack.py` (from Companion `pack.py`, 60 lines — keeps its
  path-escape check), `console/__main__.py` (`--avatar` flag / subprocess
  launch), `build_exe.py`.
- **Keep from Companion:** transparent Tk window (`-transparentcolor
  magenta`), topmost, drag, positions, opacity, GIF frame animation, text
  fallback when an asset is missing.
- **Remove from Companion's window:** reminders UI, file dialogs, pack
  editing, the manual **State** menu (a user-set `success` animation next to
  a real decision would blur R2), anything that writes files.
- **Transport:** reads `avatar.token` (AV3) and polls
  `http://127.0.0.1:<port>/api/avatar`. No inbox access of its own — the
  server is the single merger, so R1 is enforced in exactly one place.
- **Packaging:** `build_exe.py:154` currently **excludes `tkinter`** — remove
  it from that list, rebuild, and record the new size (was 7.2 MB). The
  build's smoke test must still pass.
- **Acceptance:** `IsyMotron.exe` starts console + floating avatar; DENY in
  the console shows red host frame on the desktop pet; closing the pet does
  not stop the console and vice versa.
- **Tests required:** `test_window_module_imports_without_display` (guarded),
  `test_window_has_no_write_paths` (static: no `open(..., "w")`, no
  `append_jsonl`), `test_avatar_client_uses_read_only_token`.
- **Evidence:** `evidence/AV5/desktop_avatar.png`, exe size before/after.
- **Failure conditions:** exe fails its smoke test; exe > 20 MB (then
  reconsider: tk data files); Tk in the same process as the HTTP server
  (use a subprocess — Tk wants the main thread).
- **Commit boundary:** `AV5: desktop avatar -- Companion's window, minus everything that could act`
- **Result:** `08773da`; 180 passed (177 + 3 new), `py -m pytest -q`; exe
  rebuilt: **6.87 MB -> 12.04 MB** (< 20 MB), smoke test PASS (serves
  /api/state, refuses 401 without token). Live evidence
  (`evidence/AV5/desktop_avatar.png`): `dist\IsyMotron.exe --demo-host
  --avatar` started console + pet subprocess (window "IsyMotron",
  ~228x267); DENY via `/api/execute` on `win98-retrobox`; the view AT
  CAPTURE TIME was `state=error` with host_frame
  `{decision: DENY, receipt_id: rcpt_4b95e9636011422d, seal_ok: true}` —
  the exact view the pet renders (poll 500 ms). Independence, both
  directions: pet closed -> console still serves HTTP 200; console closed ->
  a fresh `--avatar-worker` pet stayed alive. Notes: (1) the AV5 tests were
  written after the implementation — a sequencing deviation from the
  fail-first step, recorded here; (2) the PNG was not visually inspected by
  the agent (no image input); the executable verification is the
  view-at-capture-time plus the window rect; (3) an orphaned smoke-test
  `IsyMotron.exe` (PID 15508, `--port 8799` signature) held the dist file
  and was killed to rebuild; (4) `FindWindow` by title failed during the
  one-file extraction window — the capture script enumerates windows with
  an exact-title match instead.

---

## AV6 — No-AI mode

- **Objective:** without any API key the `.exe` is a complete product:
  avatar + TUIs + host by hand.
- **Files to touch:** `console/server.py` (`/api/state` gains `mode`),
  `console/static/*` (mode indicator, plan box explains how to enable),
  `tests/test_console.py`.
- **Minimal implementation:** `mode = "agent" if provider configured else
  "avatar"`; emit authority `mode` event at start.
- **Acceptance:** with `NVIDIA_NIM_API_KEY` and `NEBIUS_API_KEY` unset:
  grant, revoke, execute, receipts, avatar and inbox all work; `/api/plan`
  returns 503 with a human message; avatar shows avatar mode.
- **Tests required:** `test_no_key_everything_but_plan_works`,
  `test_plan_is_503_without_provider`, `test_mode_event_at_start`.
- **Evidence:** GUIA section run with keys unset.
- **Failure conditions:** any authority path that checks for a provider.
- **Commit boundary:** `AV6: avatar mode -- no key is a complete product, not a crippled one`
- **Result:** `20d0f36`; 183 passed (180 + 3 new), `py -m pytest -q`.
  The `mode` event is now emitted by `ConsoleState` itself (where the
  provider is known), `/api/state` gains `mode`, the 503 carries a human
  message, and the console header shows "avatar mode · no model configured".
  Live no-key run (GUIA §15, real output): keys unset -> `mode: avatar`,
  execute ALLOW + seal, grant/revoke 200, `/api/plan` 503 with the human
  message, avatar events `[mode(none), verdict, say]`, bubble rendered,
  backlog not replayed. Incident during evidence (fixed same day): a
  first evidence run POSTed `/api/grant` against the user's REAL grants file
  (no `--grants` flag) and added `C:/GAMES` to `filesystem.read` roots;
  detected and repaired with `Grants.load/save`; every later run passes
  `--grants <temp>`. Also caught: inbox lines appended before the tail's
  first sighting are backlog by contract §1 — the GUIA documents the trap.

---

## AV7 — AI mode

- **Objective:** a key adds cognition, never permissions (R7).
- **Files to touch:** `console/server.py` (planning events already from AV3;
  here: provider label in `mode` event), tests.
- **Minimal implementation:** provider detection stays in
  `agents/provider.py` (`ISYMOTRON_PROVIDER`, `NVIDIA_NIM_API_KEY`,
  `NEBIUS_API_KEY`); no new config.
- **Acceptance:** `describe()` of every host, the grant file bytes and the
  enforcer's decisions on a fixed request set are **identical** with and
  without a provider configured.
- **Tests required:** `test_provider_changes_no_bounds_or_grants`
  (ScriptedProvider), `test_mode_event_names_provider_label`.
- **Evidence:** one live Nebius run through the console with the avatar
  showing thinking → working → verdicts (screenshot).
- **Failure conditions:** any difference in the equality test above.
- **Commit boundary:** `AV7: agent mode -- a key adds a planner, not a permission`
- **Result:** `e09e1f7`; 185 passed (183 + 2 new), `py -m pytest -q`;
  `test_provider_changes_no_bounds_or_grants` proves R7: same world with a
  ScriptedProvider and without -> `describe()` of every host, the grant file
  bytes, and the enforcer's decisions on a fixed 4-request set are identical
  (the mode event differs only in its provider label and clock stamp).
  Live run (`evidence/AV7/agent_mode.png`, real model, one in-page capture):
  `/api/plan` -> PLANNED by `nvidia/nemotron-3-super-120b-a12b` (NVIDIA NIM,
  8.8 s, attribution OK), 2 steps against `win98-retrobox` only
  (`hostfs://games/DOOM.EXE` + `system.info`); `/api/run` completed; avatar
  event chain `mode -> planning(thinking) -> planned(waiting) ->
  step(working) -> step(working) -> verdict(success) -> verdict(success)`;
  DOM at capture: success.gif, ALLOW, receipt `rcpt_783f8147b9ac4c5b`,
  seal ok. NOT_DEMONSTRATED: the *Nebius-specific* live run — no
  `NEBIUS_API_KEY` on this host; the provider is one env var
  (`ISYMOTRON_PROVIDER=nebius`), and the NIM run above exercised the same
  seam. Note: AV7's implementation (planning events, provider label in the
  mode event) was carried by AV3/AV6; AV7 adds the invariant tests and the
  live evidence. The one test failure during development was the test's own
  equality over the event's `at` timestamp — fixed in the test, not the code.

---

## AV8 — Adversarial suite

- **Objective:** prove R1–R6 against a hostile local writer.
- **Files to create:** `tests/test_avatar_adversarial.py`,
  `tools/avatar_spoof.py` (demo helper that appends the spoof lines).
- **Cases (each: append to inbox, assert on `bus.view()` and on the served
  `/api/avatar` JSON):**
  1. `say "ALLOW ✅"` → third-party bubble, `host_frame` unchanged.
  2. fake DENY: `{"decision": "DENY", ...}` fields → dropped, no verdict.
  3. fake receipt id / `seal_ok: true` → dropped.
  4. fake badge: `agent: "win11-danny"` / `"IsyMotron"` → `unverified:`.
  5. event shaped exactly like an authority event (all §3.1 fields,
     `channel: "authority"`) → rendered as open, fields dropped.
  6. malformed JSON, missing fields, wrong types → counted, not shown.
  7. stale (`created_at` −2 min) and future (+2 min) → dropped.
  8. replay of a previously accepted `id` → dropped.
  9. unknown `type` → rejected by protocol.
  10. flood: 10 000 lines → reader stays bounded, authority verdict still
      displayed with precedence.
- **Acceptance:** all cases pass; `tools/avatar_spoof.py` runs against a live
  console and the web avatar shows the spoof framed next to a real verdict.
- **Evidence:** `evidence/AV8/spoof_contained.png`.
- **Failure conditions:** any case that needs a keyword filter to pass (R3).
- **Commit boundary:** `AV8: adversarial avatar -- talking grants nothing`
- **Result:** `f035959`; 195 passed (185 + 10 new), `py -m pytest -q`. The
  suite found a REAL bug, exactly as designed: `publish_open` dropped R1's
  seven fields but let the rest of the §3.1 authority shape through — a
  forged line carrying `kind: "verdict"` posed as a verdict in the event
  stream and `seq: 999` poisoned a renderer's `since` cursor. Fixed in
  `avatar/model.py` (`SHAPE_FIELDS`: seq/kind/at/capability/reason/detail/
  state join the drop list; `text` stays, it is the open channel's own
  field). Live acceptance (`evidence/AV8/spoof_contained.png`, one in-page
  capture): real DENY visible in the host frame
  (`rcpt_0effaec534e340db`, seal ok, error.gif) while ALL FIVE spoof bubbles
  rendered simultaneously — `opencode: ALLOW ✅` verbatim,
  `opencode: I DENY everything` as a bubble not a verdict,
  forged receipt dropped, `unverified: IsyMotron` (R4), and the
  authority-shaped line as a plain open bubble; `verdicts: 3`, all real.
  `tools/avatar_spoof.py` appends from a separate process (ttl 120: a demo
  runs at human speed). No case needed a keyword filter (R3). The one
  flood-test failure during development was the test's own ordering (the
  verdict's 8 s TTL expired under 80 s of unbatched appends) — fixed in the
  test.

---

## AV9 — Demo path, packaging, docs

- **Objective:** one download, one story.
- **Files to touch:** `README.md`, `docs/GUIA.es.md` (new section, real
  output), `docs/EVIDENCE.md` (claims touched by the avatar), `build_exe.py`.
- **Demo path (must run clean on a fresh Windows user profile):**
  1. start `IsyMotron.exe` with no key → avatar mode, pet floating;
  2. OpenCode/OpenISy plugin (with `COMPANION_ROOT` set) moves the pet;
  3. manual host action in the console → real ALLOW with host frame;
  4. `tools/avatar_spoof.py` → "ALLOW ✅" shown as third party;
  5. an out-of-scope manual action → real DENY with receipt id;
  6. optional: set `NEBIUS_API_KEY` → agent mode, Nemotron plans, pet
     thinks/works, host still decides.
- **Docs:** user doc (no provider jargon) separate from advanced/provider
  doc; provider treated as replaceable infrastructure (NVIDIA ⇄ Nebius is
  one env var). Devpost text must **declare Companion as the author's prior
  MIT work** reused under its license.
- **Acceptance:** the six steps recorded end to end; no second install;
  exe smoke test passes.
- **Commit boundary:** `AV9: demo path -- one exe, avatar first, AI optional`
- **Result:** —
