# Git-backed activity registry V0

The marketplace replacement is deliberately a Git snapshot, not a hosted
trust service. An activity is a commit containing `activity.json` and source.
Installation resolves the requested commit, extracts that immutable snapshot,
checks both the source tree digest and canonical `activity.json` manifest
digest, runs the local Sandbox/Doctor in private staging, and atomically
publishes the sealed scoped report beside the source.

```text
py -m pytest tests/test_marketplace.py -q
9 passed
```

The registry distributes source plus evidence. It does not grant authority,
endorse an activity globally, or bypass local policy. An undeclared effect is
still denied even when the commit is known and its tree digest is valid
(`test_adversarial_activity_is_denied_locally`, roadmap claim E).

## Fast path (roadmap claim G)

Re-running the sandbox on bits you already verified buys nothing. The registry
therefore keeps an optional local verification cache (`cache_path`) keyed by
`(tree_digest, manifest_digest)` — which pins the content exactly. On a hit:

1. The commit is still resolved and the tree is still extracted and
   re-digested; integrity is never skipped.
2. The sandbox/Doctor is **not** re-run; the sealed report is replayed and the
   installed `doctor-report.json` is marked `"verification": "reused"` so the
   audit trail distinguishes replays from fresh verdicts.

Only `PASS_FOR_SCOPE` reports with a seal that re-derives are reused; anything
else — missing entry, forged payload, a `DENY` — falls back to a full sandbox
run. A poisoned cache buys a rewrite, never a verdict. Scope: the cache is a
plain local file; an attacker able to write it already has the disk.
