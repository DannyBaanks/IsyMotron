# Malbolge capability map — evidence-backed (2026-09-19)

What exists in the workspace, what was verified, what V0 composes, and what
future lesson levels could use. No aspirational checkmarks: anything not
demonstrated in a lesson says NOT_DEMONSTRATED.

Statuses: **DISCOVERED** (found on disk) · **VERIFIED** (executed/checked in
this milestone or by its own repo's tests) · **COMPOSABLE** (vendored or
reachable through a real interface from IsyMotron) · **ADAPTER_NEEDED** (a
small, nameable adapter is missing) · **NOT_DEMONSTRATED** (not shown in a
lesson) · **ABSENT** (searched, not found).

| capability | where | status | note |
|---|---|---|---|
| Classic execution control (reference transcription) | `malbolge-oracle` @ fc3daa7 (MIT) | VERIFIED, COMPOSABLE | vendored; hello-world + nop-trail executed in V0 |
| Positional source codec (assemble/disassemble, exhaustive parity) | `MALBOLGE` @ 82076be (`classic_codec.py`, `classic_encoder.py`) | VERIFIED, COMPOSABLE | vendored; the V0 verdict layer |
| Pedagogical material (source encoding) | `C:\Development\clasesbolge.md` | VERIFIED (against tooling) | lesson content extracted; no prose/tooling discrepancy found |
| Hand calculator for the same equation | `Calcbolge` (`calcbolge.py`, no git) | DISCOVERED, NOT_DEMONSTRATED | same layer the lesson teaches; not needed by V0 |
| The teaching cat + pack | IsyMotron `avatar/` (Companion provenance, pre-existing) | VERIFIED, COMPOSABLE | used as the projection surface, never the verifier |
| Second classic engine (C/exe + IPC) | `Malbolge-Engine` | DISCOVERED | could be an alternate oracle; not needed in V0 |
| Classic interpreter (python) + quine harness + MBIR + labeled asm + PITON mirror + episodic | `MALBOLGE` repo (`malbolge.py`, `quine_harness.py`, `mbir_classic.py`, `labeled_asm.py`, `piton_malbolge_mirror.py`, `episodic.py`) | DISCOVERED, ADAPTER_NEEDED | per-file adapters; each is its own future level |
| Differential/parity harness | `malbolge-differential` @ 2466139 | DISCOVERED, ADAPTER_NEEDED | corpus/backends exist; lesson-level adapter not built |
| Walbolge roundtrip / translation | `Walbolge` repo | DISCOVERED, ADAPTER_NEEDED | L7 candidate |
| MalbolgeLISP forensics | `malbolge-lisp`, `malbolge-lisp-forensics` | DISCOVERED, ADAPTER_NEEDED | L11 candidate |
| MalbolgeFree execution | `malbolge-free` | DISCOVERED, ADAPTER_NEEDED | L12 candidate |
| Episodic anchoring / sealed execution | `MALBOLGE/episodic.py`, `malbolge-anchuring` | DISCOVERED, ADAPTER_NEEDED | L13 candidate; IsyMotron's own seals already exist for lessons |
| Lutter quine material | `GENEALOGIA_MALBOLGE`, `MALBOLGE/quine_harness.py` | DISCOVERED, ADAPTER_NEEDED | L10 candidate |
| Any generic marketplace/plugin system for packs | — | ABSENT (deliberately) | V0 builds the minimum seam only |

## Future curriculum, mapped to its capability (document, not implement)

- L0 what Malbolge is — lesson data only (COMPOSABLE)
- L1 printable source / normalized opcode — **V0 demonstrates this**
- L2 build individual instructions — **V0 demonstrates this** (nop/out/end)
- L3 A/C/D and memory — oracle internals (**VERIFIED in `malbolge-l3-registers`**)
- L4 crazy operation — oracle `op` (**VERIFIED in `malbolge-l4-crazy-op`**)
- L5 self-modification — oracle encrypt-after-execute (**VERIFIED in `malbolge-l5-encryption`**)
- L6 small executable programs — oracle run / canonical Hello World (**VERIFIED in `malbolge-l6-hello-world`**)
- L7 translation/roundtrip — Walbolge (ADAPTER_NEEDED, NOT_DEMONSTRATED)
- L8 differential verification — malbolge-differential (ADAPTER_NEEDED, NOT_DEMONSTRATED)
- L9 real existing programs — corpus in MALBOLGE fixtures + oracle (COMPOSABLE, NOT_DEMONSTRATED)
- L10 Lutter quine analysis — quine_harness + GENEALOGIA_MALBOLGE (ADAPTER_NEEDED, NOT_DEMONSTRATED)
- L11 MalbolgeLISP forensics — malbolge-lisp-forensics (ADAPTER_NEEDED, NOT_DEMONSTRATED)
- L12 MalbolgeFree — malbolge-free (ADAPTER_NEEDED, NOT_DEMONSTRATED)
- L13 sealed/episodic execution — episodic.py / anchuring + IsyMotron seals (ADAPTER_NEEDED, NOT_DEMONSTRATED)
