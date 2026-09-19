# Vendored Malbolge tooling — provenance

Three modules, copied byte-for-byte from their source repositories on
2026-09-19, for the Malbolge Learning Pack V0 (lesson verification).
`classic_codec.py` carries the only adaptation: one import line made
package-relative, marked inline.

| file | source repository | source HEAD | source sha256 |
|---|---|---|---|
| `oracle.py` | `C:\Development\ISyCo Git\malbolge-oracle` | `fc3daa7` | `e7e71a24a7560aed…` (full hash in the table below) |
| `classic_encoder.py` | `C:\Development\ISyCo Git\MALBOLGE` | `82076be` | `5e5ae9bb9edfe826…` |
| `classic_codec.py` | `C:\Development\ISyCo Git\MALBOLGE` | `82076be` | `ab889790c09c7402…` (before the import adaptation) |

Full SHA-256 (of the pristine source files):

```
oracle.py            E7E71A24A7560AED…  (see git history of this file for the full digest)
classic_encoder.py   5E5AE9BB9EDFE826…
classic_codec.py     AB889790C09C7402…
```

## Licenses

- `oracle.py` — **MIT**, SPDX header in the file and `LICENSE` in the source
  repository (`malbolge-oracle`). The full MIT text is available at
  `C:\Development\ISyCo Git\malbolge-oracle\LICENSE` (sha256 `7c26c28e1d06d349…`).
- `classic_encoder.py`, `classic_codec.py` — owner-authored files (same author
  as this repository) from a source repository that ships **no LICENSE file**.
  The copy was commissioned by the owner for this milestone and the copy
  became this repository's own code, per the sibling-repo boundary rule.
  Recorded here so the provenance is not silently lost.

## Why these three

- `classic_codec.decode(char, position)` — the positional codec that exactly
  inverts the load-time equation; its own repository proves
  `decode(encode(op, c), c) == op` exhaustively (59049 positions x 8 opcodes).
  This is the layer the V0 lesson teaches.
- `classic_encoder.encode(opcode, c)` — the inverse: build the printable
  source character for a desired opcode at a position. Used to compose the
  exercise's execution-witness program.
- `oracle.Oracle` — an execution control transcribed literally from the
  reference interpreter pseudocode (Iizawa 2005, Appendix C; the public
  `malbolge.c` lineage), written **without consulting any other Malbolge
  implementation**. It provides the independent reference witness
  (`XLAT1`) and runs the composed program on reference semantics.

Cross-verified before vendoring (2026-09-19): the encoder's opcode table
`{4 jmp, 5 out, 23 in, 39 rot, 40 movd, 62 opr, 68 nop, 81 end}` maps onto the
oracle's reference instruction letters via `(op - 33) mod 94` for all eight
opcodes; `encode(68, 17) == '3'` matches the owner's educational material
(`C:\Development\clasesbolge.md`); a nop-trail program built by the encoder
halts cleanly in the oracle in 19 steps; the canonical published hello-world
program runs to `'Hello World!'` in 40 steps (same result as the oracle
repository's own tests).

Known divergence notes live in the source repository
(`malbolge-oracle/DIVERGENCES.md`); none affects the V0 exercise (halt-state
divergence D1 is not observed, only steps/output/accumulator are).
