# Avatar bridge — handoff (2026-09-18)

Context for whoever continues the avatar track. **The operational document
is `docs/AVATAR_ROADMAP.md`**; frozen rules are in `docs/AVATAR_CONTRACT.md`.
This file explains what was going on and why.

## Objective

Make Companion (`C:\Development\ISyCo Git\Companion`, Danny's MIT desktop-pet
project) **the avatar of IsyMotron**, built into the same `.exe`, for the
Nebius × NVIDIA hackathon speech. Not a second product, not a dependency: the
useful parts are extracted and adapted.

Three pieces were identified; this track covers the first two and prepares
the third:

1. the avatar shows what IsyMotron decides (plans, verdicts, host events);
2. other TUIs (OpenCode, OpenISy, Claude Code hooks) can move the avatar;
3. *(later, own spec)* other TUIs **act through** IsyMotron — leases,
   enforcer, receipts — e.g. IsyMotron exposed as an MCP server.

## Product thesis, as it applies here

*"New behaviour may be learned. New authority may not be learned silently."*
The avatar is the first part of IsyMotron that makes authority **visible**
instead of only refusing things (the weakness `docs/ROADMAP_DELTA.md` names).
Its demo beat: a random local process writes `"ALLOW ✅"` to the avatar inbox;
the pet shows it as *"script-x: ALLOW ✅"* in a third-party frame, while the
real host verdict appears with host badge and receipt id. **Talking grants
nothing.**

## Decisions closed (by Danny, this session)

| Decision | Choice |
|---|---|
| TUIs: move the avatar, or act through IsyMotron? | **Both** (act-through is a later spec) |
| Where the avatar renders | **Floating desktop window + inside the web console** (phone sees it too) |
| What the no-AI user gets | **Avatar + TUIs + manual host actions** (no reminders) |
| Modes | Detected, not configured: no key → `avatar` mode; key → `agent` mode |
| Architecture | **Option A: two trust channels, one avatar** |

### Why Option A

Any local process can append to a JSONL inbox. If the inbox could draw a
verdict, **any process could make the pet say "allowed"** — an avatar that
certifies permissions and can be forged is a phishing surface, placed at the
centre of a product whose thesis is authority. So: an **authority** channel
written only by the IsyMotron process and served over the session token, and
an **open** `companion-event-v1` channel for everyone else, always rendered
as attributed third-party speech. The channel is stamped by the reader from
the source, never read from the payload (contract R1).

### Why not B / C

- **B — one inbox for everything (pure Companion model):** simplest and fully
  compatible, but the pet would lie convincingly (the spoof above succeeds).
- **C — Companion as a separate app, IsyMotron as a producer:** rejected by
  Danny (wants one product); also two installs for judges.

## What exists (verified 2026-09-18)

**IsyMotron** (`C:\Development\ISyCo Git\ISyMotron`, branch `master`, no
remote; last commits `d610dd3` logical resources, `f38e0dc` M5 exe):

- 151 tests pass (`python -m pytest -q`, ~30 s, Python 3.10, stdlib only).
- `console/server.py`: HTTP console; `/api/state`, `/api/events` (awareness),
  `/api/plan`, `/api/run`, `/api/execute`, `/api/grant|revoke` (loopback
  only); session token via header/query; tiers `local` vs `lan`.
- `console/__main__.py`: `--port --lan --no-browser --grants --demo-host
  --url-file`.
- `build_exe.py`: PyInstaller one-file (7.2 MB) with a self-check smoke test;
  **excludes `tkinter` at line 154** — must change for the desktop avatar.
- `core/isymotron/resources.py` (new today): logical names `hostfs://<id>`
  and app ids; the planner and receipts speak only logical names. The avatar
  must too (R6).
- Providers: NVIDIA NIM and **Nebius verified live today**; switch with
  `ISYMOTRON_PROVIDER=nebius` + `NEBIUS_API_KEY`. Without a key, `/api/plan`
  returns 503 and everything else works — the no-AI mode already half-exists.

**Companion** (`C:\Development\ISyCo Git\Companion`, commit `0aae576`,
1.0.0, MIT):

| Module | Lines | Use |
|---|---|---|
| `src/companion/protocol.py` | 58 | **port** (validator, STATES, POSITIONS) |
| `src/companion/pack.py` | 60 | **port** (manifest + path-escape check) |
| `src/companion/window.py` | 480 | **adapt** (Tk transparent window; strip menus that act) |
| `src/companion/queue.py`, `runtime.py` | 46, 161 | reference only (partial-line rule, priority/TTL ideas) |
| `src/companion/scheduled.py`, `adapters/pomodoro.py` | 243, 41 | **not taken** (reminders out of scope) |
| `src/companion/doctor.py` | 87 | not taken — it is a self-diagnostic, **not** the M12 capability Doctor |
| `integrations/opencode-plugin.ts`, `openisy-tui-plugin.ts` | 53, 47 | unchanged; they write `$COMPANION_ROOT/inbox.jsonl` |
| `packs/malbolge-cat` | 417 KB | **copy** (6 states) |
| `packs/tabby-shinji-cat` | 2.0 MB | optional |

Companion's suite: 82 pass, 1 fails here only because `tomllib` needs Python
≥ 3.11 (`config.py`, not taken).

## What does not exist

Everything in AV1–AV9: no `avatar/` package, no `/api/avatar`, no read-only
token tier, no inbox reader, no renderer, no mode field, no adversarial
tests.

## Invariants — do not break

1. Avatar ≠ authority.
2. External text ≠ trusted verdict.
3. Model ≠ authority.
4. Capability ≠ implementation.
5. Surface exposes intent; engine owns authority.
6. AI may add cognition but never silently gain permissions.
7. No API key must not cripple the non-AI product.
8. OpenCode/OpenISy compatibility stays an optional, open integration path.
9. Trusted authority visuals carry provenance unavailable to inbox writers.
10. No layer may grant or certify its own authority expansion.

Plus the existing IsyMotron ones: deny-by-default, receipts for DENY too, LAN
cannot grant, no physical path to a model provider.

## State at end of session

- AV0 **DONE** (these three docs). AV1–AV9 **NOT_STARTED**. No avatar code
  written — deliberately, to leave `master` whole.
- Working tree clean after the docs commit.
- Other open items (not this track): Devpost deadline unconfirmed; `evidence/M1/`
  receipts contain real paths — scrub before any remote; Nebius key sits in
  plain text at `C:\Development\nebiustoken.txt` (outside the repo — never
  commit, never print; load with `tr -d '\r\n\t '` into `NEBIUS_API_KEY`).

## Known commands

```
python -m pytest -q                                  # 151 passed
python -m console --demo-host                        # console + simulated Win98 host
ISYMOTRON_PROVIDER=nebius python tools/nemotron_check.py
python build_exe.py                                  # dist/IsyMotron.exe + smoke test
python tools/host_cli.py do filesystem.read --path hostfs://demo
```

Gotcha: to stop a background console, filter by process **name** too
(`Name='python.exe'`) — filtering only on `--port 8771` also matched and killed
the calling shell once.

## Open questions / risks

- **Tk inside the exe:** size and PyInstaller Tk data files (AV5 failure
  condition at > 20 MB).
- **Tk needs the main thread:** the pet runs as a subprocess of the same exe,
  not a thread of the HTTP server.
- **Hackathon rules:** Companion is prior work; declare it in Devpost (AV9).
- **Third-party identity:** `agent_verified` is always false in v1; signed
  producers are future work, and needed before piece 3 (act-through).
- **Piece 3 (TUIs act through IsyMotron)** needs its own spec; it will reuse
  the authority channel but adds a new executing surface — treat it like the
  LAN tier (can use grants, can never widen them).
