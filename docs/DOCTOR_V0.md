# Doctor V0

The Doctor is the verification plane for the product thesis:

> New behaviour may be learned; new authority may not be learned silently.

`core/isymotron/doctor.py` is deliberately pure. A future sandbox/provider
supplies observed effects; the Doctor compares them with the activity's
declared effects and emits a sealed, scoped `DoctorReport`.

## Verdicts

| Verdict | Meaning |
|---|---|
| `PASS_FOR_SCOPE` | Every observed effect matched a declaration in this trace. |
| `DENY` | An undeclared effect or changed artifact was detected. |
| `UNKNOWN` | Reserved for future provider failures; never a pass. |

There is intentionally no `SAFE` verdict. V0 does not execute code and does
not claim universal safety. The sandbox/provider milestone is still required
to turn an activity's real execution into the observation trace tested here.
