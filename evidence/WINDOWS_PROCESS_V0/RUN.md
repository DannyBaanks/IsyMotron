# Windows process observations — 2026-09-22 (step-1 experiment)

Status: measurements only. `WindowsProcessSource` does not exist
(`core/isymotron/process.py` has `LinuxProcessSource` +
`UnsupportedProcessSource` only), so every Windows support claim stays
`NOT_DEMONSTRATED`. This package answers E1–E4 of
`docs/WINDOWS_PROCESS_VERIFIER.md` with raw outputs; it is the evidence step 2
must build on, not an implementation.

## Environment

| Fact | Value |
|---|---|
| Date (UTC) | 2026-09-22T11:32Z (probes ~11:32–11:50Z) |
| Host | Windows 11, build 10.0.26200 SP0, Multiprocessor Free, x64 |
| Python | 3.12.10 (MSC v.1943 64 bit AMD64) |
| Shell | Windows PowerShell 5.1 (non-elevated) |
| Elevation | standard user `danny\progr`; `net session` → `Error de sistema 5. Acceso denegado` |
| Repository commit | `3cc08ab` (descendant of the protocol's `df3b382`) |
| Worktree | clean (`git status --porcelain` empty) at probe time |

## Exact commands

```powershell
cd IsyMotron
git log --oneline -1; git status --porcelain
py -c "import sys, platform; print(sys.version, platform.platform(), platform.win32_ver())"
# E1 (notepad as the long-lived target, pid varies per run; shown run: 16828)
py C:/Users/progr/AppData/Local/Temp/opencode/e1_raw.py <pid> evidence/WINDOWS_PROCESS_V0/e1_raw.json
# Get-Process / Win32_Process captured to e1_getprocess.json / e1_wmi.json (same pid)
# E2
py C:/Users/progr/AppData/Local/Temp/opencode/e2_reuse.py 300 evidence/WINDOWS_PROCESS_V0/e2_reuse.json
# E3
py C:/Users/progr/AppData/Local/Temp/opencode/e3_hash.py evidence/WINDOWS_PROCESS_V0/e3_hash.json
# E4
py C:/Users/progr/AppData/Local/Temp/opencode/e4_limits.py evidence/WINDOWS_PROCESS_V0/e4_limits.json
# gates
py -m pytest tests/test_process_identity.py -v
py -m pytest -q
py tools/process_verify.py observe <pid>
```

Probe scripts live outside the repo (`C:/Users/progr/AppData/Local/Temp/opencode/e{1,2,3,4}_*.py`);
only their outputs are sealed here. All files are UTF-8 with LF
(`evidence/** -text` per `.gitattributes`).

## E1 — Tooling vs raw: one layer, not two

Hypothesis: `Get-Process`/`Win32_Process` (tooling) and
`OpenProcess`+`GetProcessTimes`+`QueryFullProcessImageNameW` via ctypes (raw)
read the same kernel object through different userland APIs, so corroboration
is single-layer and no `STRONG` tier exists — the Linux result.

Control: all three observations target the same pid in the same run.

Raw output (pid 16828, Notepad):

`e1_getprocess.json`:

```json
{
    "Id":  16828,
    "ProcessName":  "Notepad",
    "Path":  "C:\\Program Files\\WindowsApps\\Microsoft.WindowsNotepad_11.2607.14.0_x64__8wekyb3d8bbwe\\Notepad\\Notepad.exe",
    "StartTime":  "\/Date(1790077571033)\/"
}
```

`e1_wmi.json` (`Win32_Process`):

```json
{
    "ProcessId":  16828,
    "Name":  "Notepad.exe",
    "ExecutablePath":  "C:\\Program Files\\WindowsApps\\Microsoft.WindowsNotepad_11.2607.14.0_x64__8wekyb3d8bbwe\\Notepad\\Notepad.exe",
    "CreationDate":  "\/Date(1790077571033)\/",
    "ParentProcessId":  20256
}
```

`e1_raw.json` (ctypes):

```json
{
  "pid": 16828,
  "open_handle": 344,
  "query_ok": true,
  "image_path": "C:\\Program Files\\WindowsApps\\Microsoft.WindowsNotepad_11.2607.14.0_x64__8wekyb3d8bbwe\\Notepad\\Notepad.exe",
  "times_ok": true,
  "creation_time": 134345511710339280,
  "layer": "raw: OpenProcess/QueryFullProcessImageNameW/GetProcessTimes via ctypes (userland Win32 on top of NT kernel)"
}
```

Verdict: all three paths return the same image path and the same start instant
(`StartTime` == `CreationDate`; `GetProcessTimes` is the same clock in FILETIME).
`Get-Process` is `System.Diagnostics.Process` over Win32, WMI is a CIM provider
over the same NT process object, ctypes is Win32 directly. Three userland doors,
one kernel room: **one layer, no `STRONG` tier.** Matches the Linux conclusion.

## E2 — Instance identity and PID reuse

Hypothesis: `pid` + `CreationTime` (from `GetProcessTimes`) identifies the
instance; a reused pid shows a different `CreationTime`.

Control: two identical commands (`python -c "import time; time.sleep(5)"`)
must get different `CreationTime` values.

Raw output (`e2_reuse.json`, 300 spawns of `python -c "pass"`):

```json
{
  "spawns": 300,
  "distinct_pids": 281,
  "reuse_observed": true,
  "control": {
    "pid_a": 8924,
    "creation_a": 134345512043068854,
    "pid_b": 21764,
    "creation_b": 134345512043138840,
    "different": true
  }
}
```

19 pids were observed twice with two distinct `CreationTime` values each, e.g.
`"3272": [134345511808688111, 134345511969241168]`
(full list in `e2_reuse.json`).

Verdict: reuse happens fast on Windows (19/300 spawns collided) and is always
detectable via `CreationTime`. Control passes. `pid` + `CreationTime` is the
Windows analog of `pid` + `starttime` + `/proc/<pid>` inode. **PASS.**

## E3 — What hashing the executable means on Windows

Hypothesis (from the protocol): the loader may hold the running image with an
exclusive lock, so delete/replace under a live process fails instead of being
observable.

Procedure: copy `python.exe` to a temp dir, run the copy with
`sleep 15`, hash disk file vs `QueryFullProcessImageNameW` path, then delete
and overwrite while the process runs.

Raw output (`e3_hash.json`):

```json
{
  "pid": 12396,
  "image_path": "C:\\Users\\progr\\AppData\\Local\\Temp\\isymotron_e3_9ukp3ad0\\victim_python.exe",
  "hash_disk_before": "sha256:4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a",
  "hash_image_before": "sha256:4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a",
  "hash_match_before": true,
  "delete": {"ok": false, "error": "PermissionError: [WinError 5] Acceso denegado"},
  "exists_after_delete": true,
  "overwrite": {"ok": false, "error": "PermissionError: [Errno 13] Permission denied"},
  "hash_disk_after": "sha256:4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a",
  "hash_image_after": "sha256:4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
}
```

Verdict: disk and image hashes match while running; delete fails with
`WinError 5`, overwrite with `Errno 13`; the file survives. The Linux
`ARTIFACT_DELETED` scenario (unlink under a live process, keep hashing via
`/proc/<pid>/exe`) has **no observable Windows counterpart through this path**:
the mutation is refused, so there is nothing to detect. Per the protocol,
`exe_deleted` stays `False` on Windows and this scenario is recorded honestly
below as not demonstrated — no reason code is invented for it.

## E4 — Observer limits

Hypothesis (Linux rule): an unreadable observation degrades the tier to `WEAK`
and `verdict_for` stays fail-closed (`ERROR`, never `PASS`).

Procedure: `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `QueryFull…` +
`GetProcessTimes` on System pid 4 (owned by SYSTEM, observer is standard user),
self (control), pid 1 and pid 999999 (dead/nonexistent).

Raw output (`e4_limits.json`):

```json
{
  "targets": {
    "system_pid4": {"pid": 4, "handle": 0, "open_error": 5, "access_denied": true},
    "self": {"pid": 6744, "query_ok": true, "times_ok": true, "creation": 134345512229383278},
    "dead_1": {"pid": 1, "handle": 0, "open_error": 87, "access_denied": false},
    "nonexistent_999999": {"pid": 999999, "handle": 0, "open_error": 87, "access_denied": false}
  }
}
```

(`open_error` is the Win32 `GetLastError`: 5 = access denied, 87 = invalid
parameter / no such process.)

Verdict: observing pid 4 as standard user fails at `OpenProcess` with
`Access is denied`, exactly the `E4` failure mode. Mapped to the shared rule:
any observation that comes back `<unreadable: …>` forces `WEAK` via
`strength_for()` and `ERROR` via `verdict_for()` — the Windows half needs no
new rule. **Confirmed for the denied-handle case.**

## Regression gates (same machine)

| Gate | Result |
|---|---|
| `py -m pytest tests/test_process_identity.py -v` | `12 passed, 7 skipped` (all Linux-only scenarios skip; pure-logic + store + platform-selection run) — see `pytest_process_identity.txt` |
| `py -m pytest -q` (full suite) | `365 passed, 14 skipped`, exit 0 — see `pytest_full.txt` |
| `py tools/process_verify.py observe <pid>` | `{"status": "ERROR", "reason": "UNSUPPORTED_PLATFORM", ...}`, exit 2 — see `cli_observe_unsupported.json` |

Baseline note: the protocol cites Windows CI `364 passed, 15 skipped`; this
machine measures `365 passed, 14 skipped`. Drift of +1/−1, recorded as-is (a
new Windows-only test may have been added upstream since the protocol commit).

## Preserved artifacts

- `e1_getprocess.json` — `Get-Process` observation (tooling)
- `e1_wmi.json` — `Win32_Process` observation (tooling)
- `e1_raw.json` — ctypes `OpenProcess`/`QueryFull…`/`GetProcessTimes` (raw)
- `e2_reuse.json` — 300-spawn PID-reuse scan + identical-command control
- `e3_hash.json` — disk-vs-image hashes + refused delete/overwrite errors
- `e4_limits.json` — `OpenProcess` results for pid 4 / self / dead pids
- `pytest_process_identity.txt` — process-identity gate output
- `pytest_full.txt` — full-suite output
- `cli_observe_unsupported.json` — CLI refusal on `win32`
- `RUN.md` — this file
- `hashes.json` — SHA-256 manifest of the above

## Not demonstrated

- Deleting or replacing a running executable on Windows (E3): the loader lock
  refuses both (`WinError 5` / `Errno 13`), so `ARTIFACT_DELETED` has no Windows
  measurement. `exe_deleted` must stay `False` with that documented.
- Spawning a process as another user and observing it (only the denied-handle
  half, pid 4 as standard user, was measured).
- The TOCTOU window between `observe` and `verify` (named in the protocol's
  next-experiment paragraph; not measured here).
- Any `WindowsProcessSource` implementation, strength tier beyond
  `WEAK`/`STANDARD`, or integration with `hosts/windows/win11.py`.
- A `STRONG` corroboration tier on Windows (E1 rejects it: one layer).
