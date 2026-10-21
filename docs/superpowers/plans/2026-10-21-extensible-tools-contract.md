# Extensible tools Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans, inline. The user approved the written spec and explicitly requested implementation on 2026-10-21.

**Goal:** Add code-bearing tool packages, host-compiled security plans, local verification, initial approval, scoped repeat execution, revocation, model construction and a CLI.

**Architecture:** Pure contract/schema layer; replaceable execution providers; a content-bound registry; a Host adapter reusing leases and receipts; a separate Nemotron builder. Linux worker uses bubblewrap with only runtime/package/input snapshots and staged outputs. No new runtime Python dependency.

**Spec:** `docs/superpowers/specs/2026-10-21-extensible-tools-contract-design.md`.

## Global Constraints

- First provider: Linux Python, input snapshots and staged artifacts, no external network/process authority.
- Approval binds package, plan, provider/verifier versions, subject, host, roots and expiry. Changes require re-verification.
- Unknown schemas/controls are refused. Verifier observations and receipts are host-owned.
- Existing capabilities/profiles and mobile GUS boundaries stay intact. No public deployment or release.

## Review Focus

Snapshot/approval tampering; paths and symlinks; output/resource bounds; stale grants/approvals; provider failure and forged results. Each appears in the tests below.

### Task 1: Contract, schema and package

**Files:** `core/isymotron/tool_contract.py`, `tests/test_tool_contract.py`.
**Interfaces:** `ToolPackage.load(path)` validates and snapshots package files, exposes `contract`, `security`, `cases`, `files`, `package_digest`; `validate(schema, value)` validates a documented strict subset. `ToolError(code, detail)` is the common refusal.

- [x] Write tests for valid package, unknown schema/control, malformed limits, entrypoint/path escape, symlink and schema mismatches; watch RED.
- [x] Implement strict contract and content digest including cases, policy and code.
- [x] Run `python -m pytest tests/test_tool_contract.py -q`; expected all PASS, then commit.

### Task 2: Linux execution provider and verification

**Files:** `core/isymotron/tool_provider.py`, `core/isymotron/tool_worker.py`, `tests/test_tool_provider.py`.
**Interfaces:** `LinuxPythonProvider.compile(package)` → canonical security plan; `run(package, inputs, files)` → validated result/artifact bytes; `verify(package)` → host report bound to package/plan/version. `files` is logical-name → bytes. Provider never imports guest code in host.

- [x] Write real-worker tests for successful code, outside-read/write/network attempts, malformed output, timeout, bounded stdout and artifacts, missing provider; watch RED.
- [x] Implement minimal mounts, clean environment, bounds, staged output validation and mandatory host probes alongside contributed cases.
- [x] Run `python -m pytest tests/test_tool_provider.py -q`; expected PASS with real bwrap on Linux; other systems explicitly unavailable. Commit.

### Task 3: Registry, approval and Host integration

**Files:** `core/isymotron/tool_registry.py`, `core/isymotron/tool_host.py`, `core/isymotron/policy.py`, `tests/test_tool_registry.py`.
**Interfaces:** `ToolRegistry(root, providers=None)` with `stage`, `verify`, `approve`, `revoke`, `list`, `catalogue`, `run`; execution checks approval subject/host/expiry and input/output roots. `ToolHost` exposes active packages as dynamic `tools.<id>` capabilities through existing `Host`/`Enforcer`/`Planner` contracts. Host receipt embeds the tool receipt.

- [x] Write tests for initial gate, two tools, reuse, owner/expiry, tamper/revocation, outside roots/symlink, provider version change, dynamic planner catalog and lease expiry; watch RED.
- [x] Implement content-bound approval and immutable run snapshots, safe host input copy/artifact publishing, private registry records, and dynamic Host scope checking.
- [x] Run `python -m pytest tests/test_tool_registry.py tests/test_m0_gate.py tests/test_planner.py -q`; expected PASS. Commit.

### Task 4: Nemotron builder, CLI and demo packages

**Files:** `agents/tool_builder.py`, `tools/tool_cli.py`, `tools/isymotron_cli.py`, `examples/tools/`, `tests/test_tool_builder.py`, `tests/test_tool_cli.py`, `console/__main__.py`, `tools/link_task_runner.py`.
**Interfaces:** `ToolBuilder(provider).propose(intent, destination)` writes only a validated inert package from strict model JSON. CLI `isymotron tool propose|stage|verify|approve|list|run|revoke|demo`; default subject `console:local`, explicit subject for Link callers; `ISYMOTRON_TOOLS_DIR` optionally attaches ToolHost to console/runner.

- [x] Write tests for scripted provider packages, truncated/malformed proposals, no auto-execution, and real CLI verify/approve/run/revoke; watch RED.
- [x] Implement builder/CLI and opt-in host wiring; add CSV and text-statistics packages with distinct custom code.
- [x] Run `python -m pytest tests/test_tool_builder.py tests/test_tool_cli.py tests/test_isymotron_cli.py -q`; expected PASS. Run the real demo and save non-secret evidence. Attempt live builder only if provider is configured; otherwise report it untested. Commit.

### Task 5: Whole-branch verification and usage

**Files:** `docs/EXTENSIBLE_TOOLS.md`, `docs/CLI.md`, release evidence and this plan.

- [x] Document schema, approval, limits, Linux availability, extension providers and runnable flow; record decisions and explicit limits.
- [x] Run `python -m pytest -q -rs`; all tests must pass; compare platform skips to baseline. Review the whole diff and resolve important findings with regressions.
- [x] Record actual CLI/demo results and exact revision; commit reviewed implementation. Leave isolated branch available for the user.

## Resultado final

Código probado: `3146b8623165cf661948042338b7d45ec67f52e1`. Suite completa: **618 pasan, 15 omisiones**, baseline 573/15. Demo CLI exit 0 con dos tools y revocación. Revisión y límites en [la evidencia](../../../evidence/TOOLS_CONTRACT_V1/RUN.md). El proveedor configurado carece de credencial: no se ejecutó la generación real de Nemotron. La rama queda aislada y local según este plan.
