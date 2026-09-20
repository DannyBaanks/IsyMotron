# Sandbox V0

`core/isymotron/sandbox.py` provides the first Doctor observation provider.
It runs one Python activity in a temporary working directory, traces mutating
audit events, blocks writes outside that directory, and feeds the trace to the
Doctor.

This is **not** an OS-level security boundary or a hostile-code containment
claim. It is a deterministic provider seam for the current Python activity
format. A stronger host-specific provider can replace it without changing the
Doctor report contract.

## Verified behaviour

- a declared write inside `activity://` produces `PASS_FOR_SCOPE`;
- a write to `hostfs://` is blocked and produces `DENY`;
- process creation is blocked and produces `DENY`;
- every report is sealed and independently verifiable.

Run the focused gate:

```text
py -m pytest tests/test_doctor.py tests/test_sandbox.py -q
7 passed
```
