# Git-backed activity registry V0

The marketplace replacement is deliberately a Git snapshot, not a hosted
trust service. An activity is a commit containing `activity.json` and source.
Installation resolves the requested commit, extracts that immutable snapshot,
checks both the source tree digest and canonical `activity.json` manifest
digest, runs the local Sandbox/Doctor in private staging, and atomically
publishes the sealed scoped report beside the source.

```text
py -m pytest tests/test_marketplace.py -q
6 passed
```

The registry distributes source plus evidence. It does not grant authority,
endorse an activity globally, or bypass local policy. An undeclared effect is
still denied even when the commit is known and its tree digest is valid.
