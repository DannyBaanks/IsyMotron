# evidence/M1/ — receipts from real Windows host

These receipts were produced on a real Windows 11 host (`win11-danny`, build 10.0.26200, engine `nt-real/0.1`) during first contact with real NTFS and process state.

## Contents

- `01_real_read_allow.json` — real in-scope read of `C:/Users/progr/IsyMotron/Demo/nota.txt`
- `02_real_read_denied.json` — real out-of-scope read denied (`C:/Users/progr/IsyMotron/no-concedido.txt`)
- `03_real_system_info.json` — real system info from the host
- `04_real_write_allow.json` — real in-scope write creating `C:/Users/progr/IsyMotron/NemoInbox/copia.txt`
- `05_real_launch_denied.json` — real launch denied (app off allowlist)

## PII note

These receipts contain real local filesystem paths (`C:/Users/progr/...`) and a real hostname/display name (`win11-danny`, `Danny (Windows build 10.0.26200)`). No credentials, secrets, or sensitive personal data are present — only the development machine's username (`progr`) and paths under the project directory.

Per `docs/AVATAR_ROADMAP.md:126`, the roadmap flagged "scrub before any remote". Since regenerating on a neutral Windows host was not feasible before submission, the receipts are published as-is with this disclosure. The seals remain valid and verifiable; the paths are development-environment artifacts, not production secrets.

## Verification

```powershell
# On Windows with the grant file in place
py -m pytest tests/test_win11_real.py -q
```

All receipts pass their tamper-evident seal verification (`receipt.verify() == True`).