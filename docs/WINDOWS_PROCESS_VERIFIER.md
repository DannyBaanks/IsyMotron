# Windows process source — experiment and implementation protocol

**Status.** Steps 1–3 are done (2026-09-22, Windows 11, sealed in
`evidence/WINDOWS_PROCESS_V0/`): the experiment measured one layer (no `STRONG`
tier), `pid` + `CreationTime` instance identity with detectable reuse, a loader
lock that refuses unlink/replace (`WinError 5` / `Errno 13`), and fail-closed
observer limits. `WindowsProcessSource` exists in `core/isymotron/process.py`,
`apps.launch` seals the launch-time fingerprint into the receipt
(`hosts/windows/win11.py`), and both are gated by tests. What remains
`NOT_DEMONSTRATED` is listed in `evidence/WINDOWS_PROCESS_V0/RUN.md`
(other-user spawn, the observe→verify TOCTOU window, any `STRONG` tier).

**Do not** widen the Windows claim beyond that list without new measurements.
A source written from assumptions has to be marked `NOT_DEMONSTRATED` anyway,
so it is wasted work.

---

## 0. Preconditions

| Fact | Value at the time this was written |
|---|---|
| Repository | `https://github.com/DannyBaanks/IsyMotron.git`, branch `master` |
| Base commit | `df3b382` |
| Worktree | clean (`git status --porcelain` empty) |
| Baseline suite (Linux host) | `354 passed, 7 skipped` |
| Baseline suite (Windows CI) | `364 passed, 15 skipped` |
| Windows CI workflow | `.github/workflows/ci.yml`, runs `python -m pytest -q` |

```powershell
git clone https://github.com/DannyBaanks/IsyMotron.git
cd IsyMotron
git log --oneline -1                 # expect df3b382 or a descendant
git status --porcelain               # expect empty
py -m pytest -q                      # record the exact count you get
```

### Environment check — hard stop

```powershell
py -c "import sys, platform; print(sys.platform, platform.win32_ver())"
```

- If `sys.platform` is **not** `win32`: **STOP.** Report
  `BLOCKED_PLATFORM` and do not modify anything. A Windows claim cannot be
  produced from a non-Windows machine, and this repository will not accept a
  fabricated one.
- If it is `win32`: record the OS build, the Python version, and whether the
  shell is elevated. Privilege changes what is observable and therefore the
  strength tier.

---

## 1. The experiment (do this before writing any source)

The questions below are the ones the Linux experiment answered; Windows may
answer them differently. For each, state a hypothesis, a control, and the raw
output. Save everything under `evidence/WINDOWS_PROCESS_V0/`.

### E1 — Are tooling and raw observation two layers, or one?

The Linux result is **one layer**: `ps` and `/proc` are the same kernel, so
corroboration is not independent and no `STRONG` tier exists.

Test whether Windows differs. Compare, for the same process:

- tooling: `Get-Process` and `Get-CimInstance Win32_Process`;
- raw: `OpenProcess` + `GetProcessTimes` + `QueryFullProcessImageNameW` via
  `ctypes`.

Record which kernel/userland layer each one reads. **Expected outcome if
Windows behaves like Linux: one layer, no `STRONG` tier.** If you believe you
found two genuinely independent layers, that is a strong claim: say exactly
which layer is which and why one can contradict the other.

### E2 — Instance identity and PID reuse

The Linux analog of `pid + starttime + /proc/<pid>` inode is
`pid + CreationTime` (from `GetProcessTimes`). Measure:

1. Open a handle to a short-lived process; read `CreationTime`.
2. Let it exit; spawn until the PID is reused (may take a while; script it).
3. Read `CreationTime` for the new process with the same PID.
4. **Expected:** same PID, different `CreationTime` → the pair identifies the
   instance and PID reuse is detectable.

Control: two identical commands get different `CreationTime`.

### E3 — What does hashing the executable actually mean on Windows?

Linux: `/proc/<pid>/exe` can be hashed after the file is unlinked, and a
deleted or replaced binary is detectable. Windows may refuse to unlink a
running image at all (the loader holds it), so the failure mode could differ.

Measure:

1. Start a process from a copy of a binary in a temp directory.
2. Hash the running image (through the process path) and the file on disk.
3. Try to delete and to overwrite the file while the process runs; record the
   exact error, if any.
4. **Record honestly** whether deletion/replacement is observable at all on
   Windows. If it is not, that scenario is `NOT_DEMONSTRATED` on Windows — do
   not invent a reason code for it.

### E4 — Observer limits

Start a process as another user (or observe a system process) and record which
observations fail (`Access is denied`). The Linux result: an unreadable
executable degrades the tier to `WEAK`. Confirm the Windows behavior and map
it to the same rule.

### Evidence package (required)

Create `evidence/WINDOWS_PROCESS_V0/` with:

- `RUN.md` — environment table (OS build, Python, elevation, commit), the
  exact commands, the raw output, a result-per-question table, and an explicit
  `Not demonstrated` section. Follow the shape of `evidence/M3/RUN.md`.
- the raw probe outputs (JSON or text) exactly as produced;
- `hashes.json` — a SHA-256 manifest of the artifacts above, in the format of
  `evidence/M3/hashes.json` (`{"algorithm": "SHA-256", "artifacts": {...}}`).

Write files with `newline="\n"` or explicitly as UTF-8 with LF. Sealed
evidence must hash the same on every platform; `.gitattributes` pins
`evidence/** -text` for exactly this reason, and a CRLF checkout has already
broken CI once.

---

## 2. Implementation — `WindowsProcessSource`

Only after step 1. Mirror `LinuxProcessSource` exactly so the shared logic
(`fingerprint`, `verdict_for`, the store) works unchanged.

Add to `core/isymotron/process.py`:

```python
class WindowsProcessSource:
    platform = "windows"

    def get_observations(self, pid: int) -> dict:
        # ctypes only: the project has no third-party runtime dependency.
        ...
```

Required observation keys (same names as the Linux source):

| Key | Windows source | Unreadable marker |
|---|---|---|
| `pid` | the pid | — |
| `starttime` | `CreationTime` from `GetProcessTimes`, as a string | `<unreadable: ...>` |
| `proc_inode` | use `CreationTime`-derived identity; if you have no inode analog, make this equal to `starttime` and say so in the docstring | `<unreadable: ...>` |
| `exe_link` | `QueryFullProcessImageNameW` | `<unreadable: ...>` |
| `exe_deleted` | see E3; if not observable on Windows, keep it `False` and document that | — |
| `exe_sha256` | SHA-256 of the executable file (via the process path if possible) | `<unreadable: ...>` |
| `uid` | owner SID (`OpenProcessToken` + `GetTokenInformation`) | `<unreadable: ...>` |
| `cmdline` | command line from the PEB or WMI; record which one | `<unreadable: ...>` |

Rules that must not change:

- `strength_for()` stays as it is: `STANDARD` iff the instance fields are
  readable **and** the executable could be hashed; otherwise `WEAK`.
  **There is no `STRONG` tier and you must not add one.**
- `verdict_for()` stays pure and fail-closed: an unreadable observation is
  `ERROR`, never `PASS`.
- `get_source()` selects the source by `sys.platform` (`win32` → Windows).

Add tests in `tests/test_process_identity.py`, in the same two layers:

- the existing pure-logic tests must pass on Windows unchanged;
- add `@WINDOWS = pytest.mark.skipif(sys.platform != "win32", ...)` scenarios
  mirroring C, I1, I2, D (if observable), X, P from the Linux half.

`process.py` is not listed in `build_exe.py`'s `HIDDEN` list because nothing in
the shipped app imports it yet. If step 3 wires it in, add it there.

### Acceptance for step 2

```powershell
py -m pytest -q                     # all Linux-only tests skip, Windows ones run
py -m pytest tests/test_process_identity.py -v
python build_exe.py                 # the packaged app still builds and smokes
```

CI must be green on the pushed commit. The suite count on Windows will grow by
the number of Windows-only tests you add; record it.

---

## 3. Integration (only if steps 1–2 are done)

`hosts/windows/win11.py` launches apps and returns a pid. Capture
`observe(pid)` at launch time (that moment is the trust root: the engine itself
is doing the observing) and seal the fingerprint into the receipt, so a later
`verify` detects post-launch drift and PID reuse.

Boundary to preserve: this establishes **instance + artifact** identity. It
does not certify the in-memory image, and it does not make the process benign.
Do not phrase it otherwise.

---

## 4. Push back

One commit per unit, with the exact verification command and its raw output in
the message:

```powershell
py -m pytest -q
git add <paths>
git commit -m "<unit>: <what changed and the measured result>"
git push origin master
gh run watch $(gh run list --limit 1 --json databaseId --jq '.[0].databaseId')
```

Then report back:

1. the environment (OS build, Python, elevation);
2. for each question E1–E4: hypothesis, control, raw output, verdict;
3. the `evidence/WINDOWS_PROCESS_V0/` package and its `hashes.json`;
4. the suite count on Windows and the CI conclusion;
5. **what remains `NOT_DEMONSTRATED`** — this section is mandatory and is not
   a failure to hide. An honest gap is a result; a fabricated pass is not.

---

## Never do

- Never claim Windows support without the step-1 evidence.
- Never invent a `STRONG` tier or an independent corroboration layer.
- Never make `verdict_for` return `PASS` on an unreadable observation.
- Never edit a sealed artifact in place; add a new one.
- Never store a key next to a baseline or inside a public artifact.
