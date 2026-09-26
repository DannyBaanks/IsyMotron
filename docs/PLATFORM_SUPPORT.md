# Platform support

A binary that builds and starts is not a host that acts. This file keeps those
apart. Every state below is tracked separately and none implies the next.

| State | Meaning |
|---|---|
| `BUILDABLE` | PyInstaller produces the binary from a clean runner |
| `PACKAGED` | the release asset is produced, hashed (`SHA256SUMS.txt`) and attested |
| `STARTABLE` | the binary starts and passes its smoke test (`build_exe.py`) |
| `HOST_SUPPORTED` | a real host backend performs the contract's operations on that OS |
| `PARITY_DEMONSTRATED` | that host matches the reference platform's capability behavior |

## Matrix

| Platform | Engine | BUILDABLE | PACKAGED | STARTABLE | HOST_SUPPORTED | PARITY_DEMONSTRATED |
|---|---|---|---|---|---|---|
| Windows 11 (x64) | `nt-real` | DEMONSTRATED (CI) | DEMONSTRATED (v1.0.0 release) | DEMONSTRATED (CI smoke) | DEMONSTRATED (`tests/test_win11_real.py`) | reference platform |
| Windows 10 | `nt-real` | same binary | same binary | NOT_DEMONSTRATED | NOT_DEMONSTRATED (product target) | NOT_DEMONSTRATED |
| Linux (x86_64) | `linux-real` | CI smoke on `ubuntu-22.04` | release workflow | CI smoke, real engine attached | DEMONSTRATED (`tests/test_linux_real.py`, CI `ubuntu-latest`) | DEMONSTRATED for the rows of `tests/test_host_parity.py` (below) |
| macOS (arm64) | none (fixtures) | CI smoke on `macos-latest` | release workflow | CI smoke, fixtures only | **NOT_DEMONSTRATED** (M3) | **NOT_DEMONSTRATED** |

The CI and release runs are the receipts: each binary job uploads
`smoke-<platform>.json`, which names the binary's SHA-256, the host engines it
attached, the checks it passed and the five states above. The smoke only sees
that a real engine *attached*; what it can *do* is proven by the host tests.

## Parity: what "the same" means (M2)

`tests/test_host_parity.py` is one scenario table run against
`native.real_host()` on whatever OS executes it. CI runs it on Windows and on
Linux; both green is the parity claim. Same manifests (shared objects, not
copies), and the same decision for:

| Scenario | Windows | Linux |
|---|---|---|
| inert without a grant file; grant without scope denies | DENY | DENY |
| read inside / outside the root, `..` escape | ALLOW / DENY / DENY | same |
| directory link escape: read, write, via `hostfs://` | junction -> DENY | symlink -> DENY |
| write creates nested file, overwrite flag, write to a new path outside | ALLOW / ALLOW / DENY | same |
| listing: size, mtime, newest first, logical names only | yes | yes |
| `system.info` keys, `process.inspect` read-only, app off the allowlist | same | same |
| `apps.launch` seals a verifiable, STANDARD fingerprint; ERROR once gone | yes | yes |
| **case variant of a root** (`GRANTED` vs `granted`) | ALLOW: NTFS says it is the same directory | **DENY**: ext4 says it is a different one |

The last row differs on purpose: the filesystems disagree about identity, and
each engine follows its own (docs/FINDINGS.md, Finding 10).

Linux-only hardening, beyond parity (`tests/test_linux_real.py`): descriptor
re-check via `/proc/self/fd`, `O_NOFOLLOW` writes against a verified
directory, FIFO/device refusal, no overwrite of hard-linked files, listings
that never stat through a link.

Known residue on Linux, stated rather than hidden: a nested write's
`makedirs` can still race an attacker who owns a directory inside the root
(empty directories may appear outside before the descriptor check refuses the
write); bind mounts are taken as the administrator's statement; a launched
app runs with the user's full authority, exactly as on Windows.

## What the macOS binary does today

It starts the console on **simulated fixtures** (`--demo-host`, engine
`dos-bridge`). The contract, policy, leases, receipts and the console all run;
nothing acts on the machine. The binary says so on start, verbatim:

```text
NOT_DEMONSTRATED: no real host backend for darwin. Only simulated fixtures (--demo-host) can attach; ...
```

Without `--demo-host` there is no host to attach and the console exits with
code 2. A `MacHost` is M3, with its own evidence -- APFS is case-insensitive by
default, so the case row above will need its own answer there.

## Grant file location

One format everywhere; the location follows the OS:
Windows `%LOCALAPPDATA%\IsyMotron\grants.json`, Linux
`$XDG_CONFIG_HOME/isymotron/grants.json` (default `~/.config/...`).

## Dependencies

- **Runtime:** Python standard library only. Enforced by
  `tests/test_png_codec.py::test_runtime_imports_no_third_party_package`,
  which imports the runtime modules with site-packages hidden.
- **Tests:** `requirements-dev.txt` (pytest; Pillow as the independent PNG
  oracle for the stdlib codec in `core/isymotron/avatar.py`).
- **Build:** `requirements-build.txt` (PyInstaller).

## Unsigned binaries

None of the binaries are code-signed.

- Windows: SmartScreen warns on first run.
- macOS: Gatekeeper blocks a downloaded, un-notarized binary. After checking
  `SHA256SUMS.txt` and the attestation, clear the quarantine flag:
  `xattr -d com.apple.quarantine IsyMotron`.
- Linux: `chmod +x` is preserved by the tar.gz.

Verify any asset with `sha256sum -c SHA256SUMS.txt` and
`gh attestation verify <asset> --repo DannyBaanks/IsyMotron`.
