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

| Platform | Runtime deps | BUILDABLE | PACKAGED | STARTABLE | HOST_SUPPORTED | PARITY_DEMONSTRATED |
|---|---|---|---|---|---|---|
| Windows 11 (x64) | stdlib only | DEMONSTRATED (CI) | DEMONSTRATED (v1.0.0 release) | DEMONSTRATED (CI smoke) | DEMONSTRATED (`tests/test_win11_real.py`, engine `nt-real`) | reference platform |
| Windows 10 | stdlib only | same binary | same binary | NOT_DEMONSTRATED | NOT_DEMONSTRATED (product target) | NOT_DEMONSTRATED |
| Linux (x86_64) | stdlib only | CI smoke on `ubuntu-22.04` | release workflow | CI smoke, fixtures only | **NOT_DEMONSTRATED** | **NOT_DEMONSTRATED** |
| macOS (arm64) | stdlib only | CI smoke on `macos-latest` | release workflow | CI smoke, fixtures only | **NOT_DEMONSTRATED** | **NOT_DEMONSTRATED** |

The CI and release runs are the receipts: each binary job uploads
`smoke-<platform>.json`, which names the binary's SHA-256, the host engines it
attached, the checks it passed and the five states above.

## What the Linux and macOS binaries do today

They start the console on **simulated fixtures** (`--demo-host`, engine
`dos-bridge`). The contract, policy, leases, receipts and the console all run;
nothing acts on the machine. The binary says so on start, verbatim:

```text
NOT_DEMONSTRATED: no real host backend for linux. Only simulated fixtures (--demo-host) can attach; ...
```

Without `--demo-host` there is no host to attach and the console exits with
code 2. Pieces that are real on Linux today (process identity via `/proc`,
retrospective suspend timing) are demonstrated by their own tests; they are not
a host backend. A `LinuxHost` (M2) and a `MacHost` (M3) are separate
milestones with their own evidence.

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
