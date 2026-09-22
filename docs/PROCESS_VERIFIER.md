# Process Verifier

The Volume Verifier establishes the identity of a *volume*: normalized
observations → fingerprint → strength tier → verdict, with a sealed store of
known-good identities. This is that pattern applied to a **running process**:
"is the process I am looking at the instance that was authorized, with the
artifact that was authorized?"

Same discipline: evidence before narrative, read-only, no tier invented.

## What it does

- **Instance identity.** `pid` + the `/proc/<pid>` inode + `starttime` name one
  process instance. A reused pid is caught as `INSTANCE_MISMATCH`.
- **Artifact drift.** The executable is hashed through `/proc/<pid>/exe`, which
  keeps working after the file is unlinked. A binary deleted or replaced under
  a live process is caught (`ARTIFACT_DELETED` / `ARTIFACT_DRIFT`), and
  `execve` is caught as a changed image with an unchanged instance.
- **Strength tiers.** `STANDARD` when the instance fields are readable and the
  executable could be hashed; `WEAK` otherwise. There is **no STRONG tier**.
- **Sealed baselines.** A baseline is written atomically and sealed with the
  same machinery as the Quine Gate (`unkeyed`, or `hmac-sha256` with
  `ISYMOTRON_RECEIPT_KEY`). The key is never stored next to it.

## What it does NOT do

- **It does not verify integrity of the running image.** `exe_sha256` hashes the
  *file*, not the mapped memory. A self-modifying or injected process keeps a
  clean file hash. (When `execve` replaces the image, the hash *does* change —
  that is a different event.)
- **It does not prove benign behaviour.** A malicious process has a perfectly
  verifiable identity.
- **It is not independent of the kernel.** `ps` and `/proc` are the same layer,
  so corroboration here is single-layer. The Volume Verifier can cross-check
  filesystem metadata against raw sectors; a process verifier running in the
  same kernel cannot. An independent observer (hypervisor introspection,
  TPM/measured boot) is a separate frontier, deliberately out of scope.
- **It does not resist a hostile kernel or root.** The observer is below the
  observed only up to the OS boundary.

## Identity model

| Observation | Role |
|---|---|
| `pid` | instance (weak alone: reused) |
| `/proc/<pid>` inode | instance handle |
| `starttime` (stat field 22) | instance handle, survives `execve` |
| `exe_link`, `exe_deleted` | artifact provenance; visible deletion |
| `exe_sha256` (via `/proc/<pid>/exe`) | artifact identity (the **file**) |
| `uid`, `cmdline` | configuration identity |

`fingerprint = sha256(canonical(observations))`. Dropping the instance fields
makes two identical commands collide — which is exactly what shows those fields
carry instance identity (measured, scenario I2).

## Reason codes and exit codes

| Status | Reason | Meaning |
|---|---|---|
| `PASS` | — | same instance, same artifact |
| `DENY` | `INSTANCE_MISMATCH` | the pid now names a different instance |
| `DENY` | `ARTIFACT_DELETED` | the executable was unlinked under the live process |
| `DENY` | `ARTIFACT_DRIFT` | the image changed (`execve` or replacement) |
| `DENY` | `FINGERPRINT_MISMATCH` | instance and artifact match, another observation changed |
| `ERROR` | `WEAK_OBSERVATIONS` | an observation is unreadable — never a PASS |
| `ERROR` | `PROCESS_UNREADABLE` | the process could not be observed |
| `ERROR` | `UNSUPPORTED_PLATFORM` | no process source for this OS |
| `ERROR` | `BASELINE_UNSEALED` | the baseline seal does not verify |

Exit codes: 0 `PASS`, 1 `DENY`, 2 `ERROR`.

## Commands

```bash
python3 tools/process_verify.py observe <pid>
python3 tools/process_verify.py store   <pid> --baseline /path/proc.baseline.json
python3 tools/process_verify.py verify  <pid> --baseline /path/proc.baseline.json
```

## Measured evidence (2026-09-22, Linux)

`tests/test_process_identity.py` is the regression gate; the scenarios were
measured first as a standalone experiment (script sha256
`10996ec8d521cd4cb7a0dfa0ace9d41b07e0dc8920d915efa2a2d4399dc01a1b`):

| Scenario | Result |
|---|---|
| C stability within one instance | same fingerprint |
| I1 two identical commands | distinct fingerprints |
| I2 instance fields ablated | collide (those fields carry identity) |
| D binary deleted under a live process | `ARTIFACT_DELETED`, path ≠ running image |
| X `execve` | instance unchanged, image readable and changed |
| P observer without permission on `/proc/1/exe` | `WEAK` |

Correction kept on the record: the first run of scenario X used `exec /bin/true`,
which exits immediately; the observation then hit a **zombie** whose
`/proc/<pid>/exe` is unreadable, so "image changed" was true for the wrong
reason. The corrected target is long-lived (`exec sleep 30`) and the test
refuses to count an unreadable image.

## Platform status

| Platform | Status |
|---|---|
| Linux | `DEMONSTRATED` (this repository, `/proc` source) |
| Windows | `NOT_DEMONSTRATED` — the seam is ready (`ProcessSource`); it needs a real-machine experiment before any claim |
| macOS | `NOT_DEMONSTRATED` — no source, no hardware |

Next experiment (before any Windows implementation): determine whether
`Get-Process`/WMI and a handle-based observation (`NtQueryInformationProcess`)
are genuinely two layers or the same one, and measure the TOCTOU window between
observing and verifying.
