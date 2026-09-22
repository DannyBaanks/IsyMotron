# isymotron — one command for the whole product

Every action in this repository is reachable from one command. The verb table
in `tools/isymotron_cli.py` is the **single source of truth**: the help is
generated from it, and a test fails if an entrypoint exists that no verb
reaches (`tests/test_isymotron_cli.py`). The previous CLI kept its verbs in two
places and documented the consequence itself: *"keep the two lists in sync or
the CLI rots"*.

## Usage

```bash
isymotron                       # interactive menu when a terminal is attached
isymotron help                  # every command, no menu
isymotron host status           # what this machine is and grants
isymotron keys list             # which keys are stored (fingerprints, never values)
isymotron evidence verify evidence/M3/hashes.json
isymotron quine demo            # the live Quine Gate sequence
isymotron process verify <pid> --baseline proc.baseline.json
```

With no arguments and **no terminal**, it prints the help and exits: it never
waits for input that is not coming. That rule matters in CI and in pipes.

## Commands

| Verb | What it runs |
|---|---|
| `start` | console + floating pet + browser (adds `--avatar`) |
| `console` | the local web console (`--lan --demo-host --port N ...`) |
| `pet` | only the floating desktop pet |
| `test` | the acceptance suite (default `-q`) |
| `build` | rebuild `IsyMotron.exe` (smoke test included) |
| `spoof` | append the hostile demo lines to an inbox |
| `host` | `status \| grant \| revoke \| do` — the local human, via `tools/host_cli.py` |
| `demo` | the M0 walkthrough (writes `evidence/M0/`) |
| `learn` | a verified lesson from a learning pack (Malbolge) |
| `install` | print the command that makes `isymotron` reachable from a new shell |
| `where` | print the repository this CLI belongs to |
| `help` | the help |
| `keys` | `list \| set <NAME> \| unset <NAME> \| check [--live]` |
| `quine` | `demo \| verify \| publish` — the Quine Gate |
| `process` | `observe \| store \| verify` — the Process Verifier (exit 0/1/2) |
| `evidence` | `verify <manifest.json>` — the `hashes.json` checker |
| `nemotron` | probe the provider seam (`--provider nebius\|nvidia`, `--models`) |
| `host-watch` | watch host awareness over time (`--seconds`, `--tick`, `--probe`) |

Flags after a verb are forwarded **verbatim** to the command that implements
it. The top-level dispatch parses no flags, so there is no `--` separator to
remember.

## Keys

`isymotron keys` manages the four values the product reads: `NEBIUS_API_KEY`,
`NVIDIA_NIM_API_KEY`, `ISYMOTRON_RECEIPT_KEY` (secrets) and
`ISYMOTRON_PROVIDER` (configuration: `nvidia` or `nebius`).

```bash
isymotron keys set NEBIUS_API_KEY     # hidden prompt, or one line from stdin
isymotron keys list                   # set/missing + sha256[:12], never the value
isymotron keys check                  # presence and format; no network
isymotron keys check --live           # delegates to the provider probe (network)
isymotron keys unset NEBIUS_API_KEY
```

- The store lives **outside the repository** (`~/.config/isymotron/keys.env`
  on POSIX, `%APPDATA%\isymotron\keys.env` on Windows), mode `0600` where the
  platform has modes, written atomically. Writing inside the repository is
  refused.
- A secret is never printed, never passed through `argv`, and never read from
  a file the CLI itself wrote into the tree. `list` shows a fingerprint.
- Every child process the CLI runs receives the stored keys in its
  environment, so a stored key works without exporting anything.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | the command succeeded (or the help was printed) |
| 1 | the command ran and the answer is negative (`DENY`, a manifest mismatch) |
| 2 | the command could not run: usage error, unknown command, missing file, `ERROR` verdict |

The exit code of a pass-through verb is the child's exit code, unchanged.

## No authority of its own

The CLI is a pass-through, and that is on purpose: it never widens a grant,
never writes a grant and never mints a receipt. Granting goes through
`isymotron host grant` (which is `tools/host_cli.py`, the local human's
surface) or the loopback console. Everything that produced evidence was
produced by the same code the CLI calls.

## Entrypoints

| Platform | How `isymotron` resolves |
|---|---|
| Windows | `isymotron.ps1` — delegates everything except `install` (which needs PowerShell to set the user PATH) |
| Linux / macOS | `tools/isymotron` — a six-line shim that execs `python3 tools/isymotron_cli.py` |

The shims hold no logic; the verb table stays in one file. The POSIX shim is
deliberately **not** at the repository root: on a case-insensitive filesystem a
root file named `isymotron` would collide with the `IsyMotron/` directory.

## Not demonstrated

- `doctor` and `marketplace` have no CLI entrypoint yet; they are libraries.
  They are excluded **with a reason** in `tools/isymotron_cli.py` so the gap is
  on the record rather than silent.
- The interactive menu's Windows backend (`msvcrt`) is exercised by CI only
  implicitly; the arrow-key loop is covered by pty tests on Linux.
