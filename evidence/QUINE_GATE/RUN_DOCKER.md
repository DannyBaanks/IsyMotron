# Quine Gate reproducibility image run — 2026-09-22

Status: `DEMONSTRATED`, scoped to the offline gate suite reproducing inside a
digest-pinned container image. This is the M9 down payment, not the full
"Reproducible Evidence Appliance": the image is pinned, not bit-for-bit
reproducible.

## Environment

| Fact | Value |
|---|---|
| Date (UTC) | 2026-09-22T10:24:56Z |
| Host | Linux 7.0.0-31-generic x86_64, Docker 29.8.1 |
| Base image | `python:3.12-slim` @ `sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9` |
| Built image | `isymotron-quine-gate:v1` → image id `sha256:09094c5589624…` |
| Extra packages | `git` (the marketplace gates build temporary git repositories; a bare slim image fails 5 tests with `FileNotFoundError` — recorded, not hidden) |
| Repository commit at run time | `cdd6c6c` |

## Exact commands

```bash
docker build -t isymotron-quine-gate:v1 .
docker run --rm isymotron-quine-gate:v1
```

## Raw output (tail)

```text
........................................................................ [ 63%]
........................................................................ [ 84%]
....................................................................................            [100%]
332 passed, 9 skipped in 22.50s
```

## Result

| Check | Verdict |
|---|---|
| Full offline suite inside the image | `332 passed, 9 skipped`, exit 0 |
| Same test count as the dev host (341 total) | yes: host `334 passed, 7 skipped` |
| The 2 extra skips | vendored-copy parity checks that look for sibling repositories present only on the dev machine; they skip by design off-host |
| First attempt (no `git` in image) | `5 failed, 327 passed` — the marketplace gates need the `git` binary; kept here as the negative result |

## Not demonstrated

- Bit-for-bit reproducible builds (apt/pip layers carry timestamps). The pin
  is by digest: same base + same code = same suite outcome.
- VM packaging or Windows/Linux parity inside a VM: no hypervisor access on
  this host (`/dev/kvm` present, user not in the `kvm` group), and Windows
  media/licensing remains out of scope per the product docs.
- Any host attestation: the image proves environment pinning, not host honesty.
