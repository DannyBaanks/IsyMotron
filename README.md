<div align="center">

<img src="docs/assets/hero.png" alt="ISyMotron capability fabric hero" width="100%" />

# ISyMotron

### One AI. Many hosts. One capability fabric.

**Plan with Nemotron. Execute through explicit capabilities. Keep authority local. Verify every action with receipts.**

[![CI](https://github.com/DannyBaanks/IsyMotron/actions/workflows/ci.yml/badge.svg)](https://github.com/DannyBaanks/IsyMotron/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-76B900.svg)](LICENSE)
[![Platform: Windows 11 (10=product scope)](https://img.shields.io/badge/platform-Windows%2011%20%2810%3Dproduct%20scope%29-202124.svg)](#what-is-demonstrated)
[![Track: Best Apps and Agents](https://img.shields.io/badge/track-Best%20Apps%20%26%20Agents-76B900.svg)](#what-is-demonstrated)

<sub>Hackathon project for the Nebius × NVIDIA / Devpost challenge. `docs/GUIA.es.md` is supplementary Spanish documentation; all submission materials are in English.</sub>

</div>

> The model proposes. The local host decides. Execution produces evidence.

## Why this matters

AI should not gain authority merely because it can reason.

ISyMotron gives an agent a typed capability fabric instead of raw host access:
filesystem roots, process inspection, allowlisted applications and system
facts. Every request is checked locally, every refusal is explicit, and every
execution ends in a tamper-evident receipt.

```text
model proposes  →  local authority decides  →  receipt records
```

## Architecture

<img src="docs/assets/architecture.svg" alt="ISyMotron architecture: model proposal through planner, resolver, relay, hosts and sealed receipt" width="100%" />

ISyMotron separates interpretation from authority:

- Nemotron and the provider live in the planning plane.
- The contract, leases, scopes and enforcer live at the host boundary.
- The relay transports requests; it does not grant permission.
- The host executes only after local policy accepts the request.
- The receipt carries the decision, result, observed effects and seal.

## Authority never comes from the model

<img src="docs/assets/authority-flow.svg" alt="Authority flow: missing capability, invalid scope and policy refusal deny; only the final branch executes" width="100%" />

The model cannot mint a capability, widen a lease, create a grant or seal a
receipt. An ungranted capability is absent from the agent's catalogue. A
malformed request, expired lease, invalid scope or host-level escape is denied
without returning the protected payload.

## See it in 60 seconds

```text
1. Grant a narrow capability        →  filesystem.read on one root
2. Let Nemotron plan                →  typed capability request
3. Execute an in-scope action       →  ALLOW + observed result
4. Try an out-of-scope action       →  DENY + no payload
5. Inspect the receipt              →  seal verified
```

### Real project evidence

The video below is a real ShitVid + OBS capture of the judge-facing demo. The
generated hero above remains illustrative artwork, not proof of a product run.

<div align="center">
<video controls width="720" poster="docs/assets/hero.png">
  <source src="isymotron-demo-final.mp4" type="video/mp4" />
  <a href="isymotron-demo-final.mp4">Watch the ISyMotron demo video</a>
</video>
<br /><sub>ShitVid + OBS demo: policy check, sealed capability lease and explicit host denial.</sub>
<br /><br />
<img src="docs/assets/malbolgato-clean.gif" alt="Malbolgato animated avatar" width="192" />
<br /><sub>Malbolgato, the packaged read-only avatar mascot.</sub>
</div>

## What is demonstrated

The project uses the evidence vocabulary from [`docs/EVIDENCE.md`](docs/EVIDENCE.md).
The labels below are deliberately narrower than marketing claims.

| Claim | Status | Evidence |
|---|---|---|
| Deny-by-default contract with leases, scopes and sealed receipts | **DEMONSTRATED** | [`tests/test_m0_gate.py`](tests/test_m0_gate.py) |
| Real filesystem and process surface on a Windows host | **DEMONSTRATED** | [`tests/test_win11_real.py`](tests/test_win11_real.py), [`evidence/M1/`](evidence/M1/) |
| Planner refuses hallucinated or ungranted capabilities | **DEMONSTRATED** | [`tests/test_planner.py`](tests/test_planner.py) |
| Live Nemotron planning path (Nebius Token Factory) | **DEMONSTRATED, scoped** | [`tests/test_live_model.py`](tests/test_live_model.py), [`evidence/M3/RUN.md`](evidence/M3/RUN.md), [`evidence/M3/hashes.json`](evidence/M3/hashes.json) |
| Host-awareness attribution: suspend is not provider failure | **DEMONSTRATED** | [`tests/test_awareness.py`](tests/test_awareness.py), [`docs/HOST_AWARENESS.md`](docs/HOST_AWARENESS.md) |
| Console and read-only avatar authority channel | **DEMONSTRATED** | [`tests/test_console.py`](tests/test_console.py), [`tests/test_avatar_adversarial.py`](tests/test_avatar_adversarial.py), [`evidence/AV9/`](evidence/AV9/) |
| Malbolge lesson with machine verdicts and sealed receipts | **DEMONSTRATED, scoped** | [`learning/`](learning/), [`evidence/MALBOLGE_V0/`](evidence/MALBOLGE_V0/) |
| Nebius Token Factory provider execution | **DEMONSTRATED** | Sealed keyed run 2026-09-22: round trip, plan and adversarial refusal all pass. [`evidence/M3/RUN.md`](evidence/M3/RUN.md), [`evidence/M3/hashes.json`](evidence/M3/hashes.json) |
| A real Windows 10 host | **NOT_DEMONSTRATED** | Windows 11 is the demonstrated real host; Windows 10 remains the product target |
| Universal security or production safety on arbitrary hosts | **NOT_DEMONSTRATED** | Explicitly outside the evidence scope |

## The capability fabric

<img src="docs/assets/capability-fabric.svg" alt="ISyMotron capability fabric showing filesystem, process, apps and system capabilities" width="100%" />

The current Windows host exposes a small, inspectable contract:

| Capability | Bounds |
|---|---|
| `filesystem.read` | Granted roots; files and directory metadata |
| `filesystem.write` | Granted roots; explicit create/overwrite |
| `apps.launch` | Case-insensitive executable allowlist |
| `process.inspect` | Read-only process names |
| `system.info` | Non-identifying machine facts |

The contract is intentionally small. Adding a ninth operation is a contract
version change, not an invisible feature.

## Built with Nebius + NVIDIA

ISyMotron includes a provider seam for NVIDIA NIM and Nebius Token Factory:

```text
Nebius or NVIDIA endpoint
          ↓
       Nemotron
          ↓
        Planner
          ↓
     Host policy
          ↓
        Receipt
```

The provider changes how a plan is proposed; it does not change the grants,
scope bounds or authority held by a host. Nebius Token Factory is demonstrated
live and sealed: [`evidence/M3/RUN.md`](evidence/M3/RUN.md) (2026-09-22) records
a real round trip, a real plan and a real adversarial refusal, with
[`evidence/M3/hashes.json`](evidence/M3/hashes.json) sealing the artifacts. The
same seam also reaches NVIDIA NIM (`evidence/M3/probe_nvidia.json`); its earlier
`HTTP 503` is kept as a historical negative result.

## Verification

The CI workflow runs on `windows-latest`, because the real host gate exercises
Windows filesystem semantics, NTFS junctions and process state. It also builds
the packaged executable and runs its HTTP/authentication smoke test.

```powershell
# From the repository root on Windows
py -m pytest -q
py tests/test_m0_gate.py -q
py tests/test_win11_real.py -q
py tests/test_planner.py -q
py tests/test_console.py -q
```

The live provider tests run only when a provider key is present; otherwise they
skip without making the offline contract suite depend on an external service.
The exact current count belongs to the CI run, not to a hand-maintained badge.

## Quickstart

### Windows 10/11

```powershell
git clone https://github.com/DannyBaanks/IsyMotron.git
cd IsyMotron

.\isymotron.ps1 help
.\isymotron.ps1 start --demo-host
```

Make a real Windows machine inert until a human grants a scope:

```powershell
.\isymotron.ps1 host status
.\isymotron.ps1 host grant filesystem.read --root "C:/Users/you/Pictures"
.\isymotron.ps1 host do filesystem.read --path "C:/Users/you/Pictures"
.\isymotron.ps1 host do filesystem.read --path "C:/Users/you/Documents" # DENY
```

Optional model planning (Nebius Token Factory is the hackathon path):

```powershell
$env:NEBIUS_API_KEY = "..."
$env:ISYMOTRON_PROVIDER = "nebius"
py tools/nemotron_check.py
# NVIDIA NIM is the same seam: $env:NVIDIA_NIM_API_KEY + ISYMOTRON_PROVIDER = "nvidia"
```

Linux native host awareness is demonstrated for retrospective suspend timing
and local interface state. The product host scope remains Windows 10/11; Linux
does not claim pre-suspend notifications or a desktop avatar without Tk.

## Repository map

```text
core/isymotron/     contract, policy, leases, receipts, awareness, Doctor
hosts/windows/      real Windows host, grants and power provider
hosts/simulator/    deterministic fixture engines
agents/             provider, planner and executor roles
relay/              transport-only loopback relay
console/            local web console and avatar API
avatar/             trust-separated web/desktop avatar
web/                Next.js surface (optional, requires console backend)
learning/           Malbolge lesson packs and verifiers
evidence/           sealed run artifacts and screenshots
tests/              contract, host, planner, console and adversarial gates
docs/               architecture, findings and operational guides
```

## Security and authority model

- Missing or unreadable grants produce an inert host, not an unrestricted one.
- A remote console may use granted authority but cannot widen it.
- The avatar has a separate read-only token and cannot POST authority actions.
- Receipts are produced for both `ALLOW` and `DENY` outcomes.
- A denied receipt has no protected result payload.
- The Python sandbox/Doctor is a scoped verification provider, not a universal
  OS security boundary; see [`docs/SANDBOX_V0.md`](docs/SANDBOX_V0.md).
- Network paths, device paths, NTFS alternate data streams and TOCTOU races
  remain explicitly unverified; see [`docs/FINDINGS.md`](docs/FINDINGS.md).

## Roadmap

| NOW | NEXT | RESEARCH |
|---|---|---|
| Typed host contract | Sealed Nebius evidence ✓ | Marketplace trust at scale |
| Local authority and receipts | Real Windows 10 verification | Additional host generations |
| Nemotron planner/executor | Harden malformed grant handling | Network relay transports |
| Console + avatar demo | CI count refresh and evidence refresh | Stronger OS-level sandbox providers |

## License

ISyMotron is released under the [MIT License](LICENSE).

## Asset provenance

The README artwork and evidence screenshots are catalogued in
[`docs/assets/PROVENANCE.md`](docs/assets/PROVENANCE.md). The hero is generated
illustration only; it is not a screenshot, benchmark or proof of execution.
