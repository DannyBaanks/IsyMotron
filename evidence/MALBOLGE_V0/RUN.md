# ISYMOTRON_MALBOLGE_V0 — evidence bundle

Date: 2026-09-19 · IsyMotron HEAD at close: see the commit that adds this
directory · All outputs in this bundle were executed, not paraphrased.

## Baseline (pre-change)

- Local suite before any change: **196 passed in 40.84s** (IsyMotron HEAD
  `0443893`, clean tree).
- CI at that HEAD: gates `191 passed, 5 skipped in 24.68s` (the 5 skips are
  the live-model gate without a provider secret), binary job green
  (run `35463873894`).
- After the change: **221 passed in 143.28s** locally (196 + 25 new gate
  tests). One earlier full-suite run had `1 failed, 220 passed` on
  `test_live_model.py::test_an_undersized_budget_truncates_rather_than_shortens`
  — a live-provider test that passed in isolation (1 passed) and as a module
  (5 passed in 83.25s) immediately after: remote variance of a live
  reasoning-model budget, not a code change (the learning pack shares zero
  code with the provider path).

## The vertical slice

Lesson `malbolge-source-encoding-1`: given a desired normalized opcode and a
source position, derive the printable character that decodes to it
(`r = (op - c) mod 94`, fold into 33..126). Three exercises (nop@17, out@0,
end@2). The verifier composes vendored real tooling:

1. **decode witness** — `classic_codec.decode` (positional codec, exhaustive
   parity in its source repo);
2. **reference witness** — `malbolge-oracle` XLAT1 instruction letter for the
   learner's character (independent provenance: transcribed from the
   reference interpreter without consulting any other implementation);
3. **execution witness** — a nop-trail program composed with
   `classic_encoder.encode`, with the learner's character at the target
   position, executed on the `Oracle` under reference semantics (PASS
   requires the clean halt at the expected step).

The verdict is PASS/FAIL/INVALID/UNAVAILABLE — machine-produced or absent;
no model is involved anywhere in the verification path, and the receipt
(`learning-receipt-v1`) is sealed with the system's canonical digest
machinery with `verdict_source: "machine"`.

## Traces (all executed 2026-09-19)

| file | what it shows |
|---|---|
| `traces/good_pass.txt` | answer `3` for nop@17 → **PASS**, receipt `rcpt_70a00e1131d049b8`, seal ok, execution halted in 19 steps |
| `traces/bad_fail.txt` | answer `4` (decodes to opcode 69) → **FAIL**, receipt `rcpt_e5ada8d037c3469b`, seal ok |
| `traces/invalid_input.txt` | answer `zz` → **INVALID**, receipt `rcpt_eaa6d8cffa3e411f`, seal ok |
| `traces/unavailable.txt` | vendored tooling import poisoned → **UNAVAILABLE**, `verified_by: []`, "an unavailable verifier never produces PASS" |
| `receipts/*.json` | sealed receipts for exercises 1–3 (nop@17 PASS, out@0 PASS, end@2 PASS) + the UNAVAILABLE receipt |

## Live proof — the cat projects the machine's verdict

Console + desktop pet running (`console --avatar --no-browser --port 8809`,
temp inbox via `ISYMOTRON_AVATAR_INBOX`), then the lesson CLI run with
`--answer 3`:

```
  VERDICT: PASS   (verdict_source: machine; receipt rcpt_84c5a2fcc8724542; seal ok)
```

`GET /api/avatar?since=0` (read-only avatar token) returned the open-channel
bubble, live:

```
third_party bubbles:
  [3] malbolge-nop-17: PASS - nop decoded from '3'. Receipt rcpt_84c5a2fcc8724542.
```

That is the whole product thesis in one receipt id: the cat speaks the
verdict, the tooling produced it, and the open channel could never have
manufactured it (the adversarial suite already proves a forged say-line stays
a third-party bubble; the gate adds that avatar/console sources cannot
construct a LessonReceipt at all).

## Semantics verification (before the lesson was written)

Executed 2026-09-19 against the source repositories, before vendoring:

- encode/decode parity: 200 positions x 8 opcodes — PASS;
- opcode table ↔ oracle reference letters via `(op - 33) mod 94` for all 8
  opcodes — PASS (`4→i 5→< 23→/ 39→* 40→j 62→p 68→o 81→v`);
- the educational material's worked example `encode(68, 17) == '3'` — PASS;
- nop-trail + `3` + end executes on the Oracle: halted, 19 steps — PASS;
- canonical published hello-world program: `'Hello World!'`, 40 steps,
  halt_opcode — matches the oracle repository's own tests;
- `clasesbolge.md` prose vs executable semantics: the opcode table and the
  `r=(op-c) mod 94` fold are byte-identical to the tooling. No discrepancy
  was found to report.

## Provenance

See `learning/packs/malbolge/vendor/PROVENANCE.md` — three modules copied
byte-for-byte (sha256 recorded): `oracle.py` (malbolge-oracle `fc3daa7`,
MIT), `classic_encoder.py` and `classic_codec.py` (MALBOLGE `82076be`,
owner-authored, no LICENSE file in the source repo — copy commissioned by
the owner; recorded so provenance is not silently lost). One documented
adaptation: a single package-relative import line in `classic_codec.py`.

## What V0 does NOT claim

- No claim that Malbolge is "the hardest language" or that IsyMotron
  "masters" it. V0 demonstrates: **learn → build → execute → verify →
  receipt, on one real lesson, with machine verdicts.**
- The execution witness alone cannot distinguish a no-op-equivalent wrong
  character in this program shape; the verdict comes from the codec +
  reference letters, and every receipt says so.
- Future curriculum levels are mapped, not implemented — see
  `capability_map.md`.

## Reproduce

```
isymotron learn malbolge                       # interactive
isymotron learn malbolge --exercise 1 --answer 3 --json
py -m pytest tests/test_learning_malbolge.py -q
```
