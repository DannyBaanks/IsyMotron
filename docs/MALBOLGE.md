# Malbolge in IsyMotron

This document is the long form of the README's
[Learn Malbolge with Malbolgato](../README.md#learn-malbolge-with-malbolgato)
section: what the learning pack is, how a verdict is produced, which
curriculum levels are actually demonstrated, and where the tooling came from.

The rule that governs everything below: **a lesson verdict is produced by
machinery, never by a model.**

## Why Malbolge

Malbolge was published in 1998 with nothing but a reference interpreter. It is
named after the eighth circle of Dante's Inferno. Its first "Hello World" was
not written by a human — it was found by an automated beam search (Lou
Scheffer). Every memory cell is encrypted after the instruction in it executes,
and the operation on two cells is a tritwise table rather than ordinary integer
arithmetic. It is widely described as the hardest programming language ever put
on a machine.

IsyMotron takes it as a stress test of its own thesis. The product claim is
*the model proposes, the host decides, execution produces evidence*. If that
claim only held for easy domains, it would not be a claim. A lesson that needs
a paid model opinion to grade a student would be architecturally wrong, so the
learning pack is built with **no model anywhere in the verification path**.

## The lesson model

Every lesson follows the same five steps:

```
learn  ->  build  ->  execute  ->  verify  ->  receipt
```

The learner derives an answer from a small explanation. Tooling builds a real
artifact (a program, a roundtrip, a witness lookup). The artifact is executed or
checked against an independent implementation. A verifier issues one of four
machine verdicts and seals a `learning-receipt-v1`.

## Lesson 1 — source encoding (the vertical slice)

Classic Malbolge stores one printable ASCII character (33..126) per memory
cell. At load position `c`, that character decodes to a normalized opcode:

```text
    op    = (ASCII(char) + c) mod 94       the decode

    r     = (op - c) mod 94                the inverse: choose the instruction,
    ASCII = r        if 33 <= r <= 93        derive the character
    ASCII = r + 94   if 0  <= r <= 32
    char  = chr(ASCII)
```

Worked examples shipped in the lesson:

```text
nop at position 3:  r = (68 -  3) mod 94 = 65 -> ASCII 65 -> 'A'
nop at position 17: r = (68 - 17) mod 94 = 51 -> ASCII 51 -> '3'
```

Exercise 1 (`malbolge-nop-17`) asks for the character that puts `NOP` at
position 17. The answer is `3`.

## The three witnesses

No single check decides the verdict. Three independent pieces of real tooling
compose it, and none of them is a model:

1. **Positional codec** — `classic_codec.decode(char, position)` returns the
   opcode. Its own source repository proves `decode(encode(op, c), c) == op`
   exhaustively over all 59049 positions and 8 opcodes.
2. **Reference witness** — `oracle.XLAT1` maps the opcode to the reference
   instruction letter (`68 -> 'o'`). The oracle's semantics were transcribed
   from the reference interpreter (Iizawa 2005, Appendix C; the public
   `malbolge.c` lineage) **without consulting any other Malbolge
   implementation**.
3. **Execution witness** — a 19-cell program is composed with
   `classic_encoder.encode`, with the learner's character at position 17, and
   executed on the oracle under reference semantics. A clean halt is required,
   but the verdict does not rest on it alone (see below).

Real output, captured on this repository:

```text
  Exercise 1 (malbolge-nop-17)
  The cat wants NOP at position 17. Which single printable character produces it?
  your answer: 3
  expected: opcode 68 (nop) — reference instruction 'o'
  observed: opcode 68 (nop) — reference instruction 'o'
  execution: 19-cell program, halted=True reason=halt_opcode steps=19 (expected 19)
  VERDICT: PASS   (verdict_source: machine; receipt rcpt_091a3441c935452f; seal ok)
```

The execution witness alone cannot distinguish a no-op-equivalent wrong
character; the verdict comes from the codec plus the reference letter, and
every receipt says so in its `notes`.

## Verdicts and receipts

A verdict is one of `PASS`, `FAIL`, `INVALID`, `UNAVAILABLE`. There is no
`SAFE`, no default-pass, and no verdict derived from prose.

| answer | the machines say | verdict |
|---|---|---|
| `3` | opcode 68 (nop) — reference `'o'`, clean 19-step halt | **PASS** |
| `4` | opcode 69 — not nop | **FAIL** |
| `zz` | out of contract (not one character) | **INVALID** |
| *(tooling unloaded)* | no tooling, no verdict | **UNAVAILABLE** |

`UNAVAILABLE` is a first-class outcome: an unloaded verifier answers it rather
than turning a model's opinion into a verdict. The receipt is a sealed
`learning-receipt-v1`; editing any field breaks its own seal. The `receipt_id`
is generated per run (`new_receipt_id()`), so it changes between runs — the
seal is what is reproducible, not the id.

Two properties are enforced by tests:

- a lesson `PASS` is a correctness fact about source encoding, **never** an
  authority `ALLOW` — the receipt shape makes conflation with the host contract
  impossible by accident;
- a forged line in the avatar's open channel renders as a third-party bubble
  and can never become a verdict.

## Curriculum: L0–L13

Two packs are registered: `malbolge` (L1–L2) and `malbolge-advanced` (L3–L13).

| level | topic | status | how it is verified |
|---|---|---|---|
| L0 | what Malbolge is | lesson data only | `COMPOSABLE` — explanation text |
| L1 | printable source / normalized opcode | **DEMONSTRATED** | positional codec |
| L2 | build individual instructions | **DEMONSTRATED** | codec + oracle reference letters + execution |
| L3 | A, C, D registers and memory | **VERIFIED** | oracle reset state (`0,0,0`) |
| L4 | the crazy operation | **VERIFIED** | `oracle.op(1, 2) == 29525` |
| L5 | self-modification (encrypt-after-execute) | **VERIFIED** | oracle mutation of cell 0 |
| L6 | small executable programs | **VERIFIED** | canonical `Hello World!` in 40 steps |
| L7 | translation / roundtrip | **VERIFIED** | `disassemble` → `assemble` preserves the program |
| L8 | differential verification | **VERIFIED** | primary oracle vs an independent runner agree (`CONSISTENT`) |
| L9 | real published programs | **VERIFIED** | canonical published fixture runs to `Hello World!` |
| L10 | Lutter quine | **VERIFIED (evidence-only)** | copied witness metadata; not re-executed here |
| L11 | MalbolgeLISP forensics | **VERIFIED (evidence-only)** | copied witness metadata; 3^19 image not present |
| L12 | MalbolgeFree | **VERIFIED (evidence-only)** | copied witness metadata; not re-executed here |
| L13 | sealed / episodic execution | **VERIFIED** | one-bit tamper is rejected by a hash-linked witness |

`EVIDENCE_ONLY` means exactly that: IsyMotron has the recorded witness
(`evidence/MALBOLGE_V0/*_witness.json`) but not the source artifact, so the
receipt claims no re-execution. The full discovery inventory — what exists on
disk, what is composable, what would need a small adapter — is
[`evidence/MALBOLGE_V0/capability_map.md`](../evidence/MALBOLGE_V0/capability_map.md).
No aspirational checkmarks: anything not demonstrated says `NOT_DEMONSTRATED`.

## Vendored tooling and provenance

Three modules were copied **byte-for-byte** on 2026-09-19; the only adaptation
is one package-relative import line in `classic_codec.py`.

| file | source repository | source HEAD | license |
|---|---|---|---|
| `oracle.py` | `malbolge-oracle` | `fc3daa7` | MIT (SPDX header + LICENSE) |
| `classic_encoder.py` | `MALBOLGE` | `82076be` | owner-authored; source repo ships no LICENSE |
| `classic_codec.py` | `MALBOLGE` | `82076be` | owner-authored; source repo ships no LICENSE |
| `secondary.py` | `malbolge-anchuring` | — | independent runner used for the L8 differential |

The `MALBOLGE` files are the author's own work; the copy was commissioned for
this milestone and became this repository's own code. Full SHA-256 digests and
the longer provenance note live in
[`learning/packs/malbolge/vendor/PROVENANCE.md`](../learning/packs/malbolge/vendor/PROVENANCE.md).

Before the lesson was written, the tooling was cross-verified: the encoder's
opcode table maps onto the oracle's reference letters via `(op - 33) mod 94`
for all eight opcodes; `encode(68, 17) == '3'` matches the owner's educational
material; a nop-trail program halts cleanly in the oracle in 19 steps; the
canonical hello-world program runs to `Hello World!` in 40 steps, matching the
oracle repository's own tests.

## Malbolgato

The teaching cat is the read-only avatar (`avatar/packs/malbolge-cat/`, adapted
from the author's prior MIT-licensed **Companion** work; see
[`avatar/packs/NOTICE`](../avatar/packs/NOTICE)). It is the **projection
surface, never the verifier**: when the console and pet are running, the cat
announces the machine's verdict live through the open channel — a bubble it can
speak but never forge. The avatar token can read `/api/avatar` and `/api/state`
and every POST route answers 403.

## Evidence bundle

[`evidence/MALBOLGE_V0/`](../evidence/MALBOLGE_V0/):

- `RUN.md` — the executed runs, the live proof, and the semantics checks;
- `traces/` — raw terminal traces for PASS, FAIL, INVALID and UNAVAILABLE;
- `receipts/` — sealed receipts for exercises 1–3 and the UNAVAILABLE case;
- `*_witness.json` — the L10–L12 evidence-only witness metadata;
- `capability_map.md` — the discovery inventory and future-level mapping.

## Reproduce

```powershell
isymotron learn malbolge                     # the whole lesson, interactive
isymotron learn malbolge --exercise 1 --answer 3
isymotron learn malbolge --all               # every exercise, interactive
isymotron learn malbolge-advanced --all      # L3-L13, interactive
py -m pytest tests/test_learning_malbolge.py tests/test_learning_malbolge_advanced.py -q
```

Exit codes carry the machine verdict: `0` PASS, `1` FAIL, `2` INVALID,
`3` UNAVAILABLE, `4` pack/lesson not found.

## What this does not claim

- No claim that Malbolge is "the hardest language" as a formal result, or that
  IsyMotron "masters" Malbolge.
- No claim that L10–L12 were re-executed here: they are witness metadata.
- No claim of a generic plugin/marketplace for lesson packs — V0 builds the
  minimum seam only.
- The scope of V0 is: **learn → build → execute → verify → receipt, with
  machine verdicts, on a real lesson.** The rest of the curriculum is earned one
  milestone at a time.
