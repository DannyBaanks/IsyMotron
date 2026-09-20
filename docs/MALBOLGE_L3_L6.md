# Malbolge L3-L6

The advanced pack is exposed as `malbolge-advanced`. It extends the source
encoding vertical slice without changing the original V0 lesson or verifier.

```text
py -m learning malbolge-advanced --all --no-project
```

The four exercises are oracle-backed:

- **L3** — reset registers A/C/D;
- **L4** — ternary crazy operation `op(1, 2)`;
- **L5** — encryption after a ROT instruction changes memory;
- **L6** — the canonical program emits `Hello World!` in 40 steps.

Each result uses the normal sealed `learning-receipt-v1` contract. The levels
remain scoped to the vendored classic oracle; translation, differential
backends, quines, MalbolgeLISP, MalbolgeFree, and episodic execution remain
future levels.
