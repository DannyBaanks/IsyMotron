# Host awareness

> Do not ask a model to infer host state when the host can report it
> deterministically.

## The incident

On 2026-09-17 a 25-call measurement against NVIDIA NIM produced:

- 7 clean calls,
- then one request that appeared to take **793.32 s** despite `timeout=120`,
- then **18 consecutive** failures with no HTTP status at all,
- then clean recovery, 0.89 s, a minute later.

Every number was real. The reading — sustained load triggering provider
throttling that manifests as dropped connections — was coherent, specific, and
entirely wrong. **The laptop had been closed and carried out of the house.**

The draft finding was minutes from being committed. It was caught because a
human said what had actually happened.

### Why no amount of reasoning could have recovered it

The process was frozen. The evidence was not in the process.

And the obvious defence does not work on Windows. Measured on this machine:

```
GetTickCount64                             42365.203 s
time.monotonic()                           42365.203 s      <- identical
```

`time.monotonic()` **is** `GetTickCount64()`, and both it and `time.time()`
advance through suspend. Comparing a wall clock against a monotonic clock — the
standard trick for detecting a sleep — detects nothing here. A 793-second sleep
is indistinguishable from a 793-second request using Python's clocks alone.

The gap is therefore not a model weakness and not fixable by prompting:

> **An agent cannot reliably distinguish provider latency from local host
> suspension without host evidence.** — `DEMONSTRATED`, 2026-09-17.

## The mechanism

Windows keeps a second counter that *excludes* sleep:

```
GetTickCount64                             42365.203 s   (11.77 h)  includes sleep
QueryUnbiasedInterruptTime                 35038.317 s   ( 9.73 h)  excludes sleep
-----------------------------------------------------------------
difference = suspend bias                   7326.886 s   ( 2.04 h)  time asleep
```

The difference is the **suspend bias**: total wall-clock time this machine has
spent suspended since boot. It is monotonically non-decreasing, and any
increase between two readings is exactly the time slept in between.

Measured across a two-second awake interval the bias moved **2.2 ms**. Noise is
milliseconds; a real suspend is seconds. `SUSPEND_THRESHOLD_S = 1.0`.

Two `ctypes` calls. No admin, no message pump, no thread, no handle, no
polling loop.

### Independent corroboration

The Windows System log, read without elevation, recorded:

```
21:51:44  Kernel-Power 506  entering modern standby
22:04:59  Kernel-Power 507  exiting modern standby
```

That is **795 s**. The hung request measured **793.32 s**. Two independent
sources, agreeing within two seconds, both saying the machine was asleep.

The bias is the mechanism (`DEMONSTRATED`); the event log is the cross-check
(`INFERRED` — it says *when*, not *how long a given call was affected*).

### Why not `WM_POWERBROADCAST` / `PowerRegisterSuspendResumeNotification`

Both are real, and both would give something the bias cannot: a **pre-suspend**
notification. `WM_POWERBROADCAST` needs a window and a message pump.
`PowerRegisterSuspendResumeNotification` needs a callback serviced by a thread
Windows is about to freeze. Each adds a thread, a handle and a platform
dependency to what is otherwise a CLI.

So this provider never claims `SUSPENDING`, and never emits
`HOST_SUSPEND_REQUESTED` from its own observation. Those stay
`NOT_DEMONSTRATED` rather than being faked. The bias answers the question we
actually have, which is always asked afterwards: *did we just sleep, and for
how long?*

## Architecture

```
  HostAwarenessEngine                     core/isymotron/awareness.py
      |  describe / snapshot / recent_events / health
      |
      +-- WindowsPowerProvider            hosts/windows/power.py     WORKING
      +-- LinuxPowerProvider              hosts/linux/power.py       SEAM ONLY
      +-- TestPowerProvider               core/isymotron/awareness.py
      +-- NullPowerProvider               core/isymotron/awareness.py

  attribute(before, after, error) -> OperationOutcome
                                          core/isymotron/attribution.py
      ^
      |  used by
  Provider.complete()                     agents/provider.py
```

Four operations, deliberately shaped like the host contract's eight. The engine
holds no I/O beyond reading its provider and no state beyond epochs and a
bounded event ring.

### Where it sits relative to everything else

| Component | Answers |
|---|---|
| **HostAwareness** | what happened to the machine |
| Doctor | what effects we observed |
| Sentinel / `Enforcer` | what is permitted |
| a model | what it means, what to do next |
| host engine | whether the local action can execute |

Nobody knows everything. This is the only one that answers the first question,
and it answers nothing else.

## Contract

```python
HostAwarenessSnapshot {
    host_id, boot_id, session_id,
    power_state, power_epoch,
    network_state, network_epoch,
    wall_time, monotonic_time, unbiased_time,
    contract = "HostAwareness/v0"
}
```

Take one before an operation, one after, compare the epochs. That comparison is
the entire product of this engine.

- `boot_id` — derived from boot wall time; a reboot changes it, nothing is persisted
- `session_id` — per process; a restart changes it
- `power_epoch` — +1 per observed suspend/resume cycle
- `network_epoch` — +1 per observed connectivity change
- `unbiased_time` — the sleep-excluding clock, or `None` where unavailable

`snapshot()` is what advances the epochs, so a suspend nobody was watching for
is still recorded the next time anybody looks.

### Events

`HOST_BOOT`, `HOST_SHUTDOWN`, `HOST_SUSPEND_REQUESTED`, `HOST_RESUMED`,
`NETWORK_UP`, `NETWORK_DOWN`, `NETWORK_CHANGED`, `PROCESS_STARTED`,
`PROCESS_RESTARTED`.

Each carries `event_id`, `host_id`, `event_type`, `wall_time`,
`monotonic_time`, `unbiased_time`, `boot_id`, `session_id`, `power_epoch`,
`network_epoch`, `source`, `evidence`, and a `detail` map. Example:

```json
{
  "event_type": "HOST_RESUMED",
  "host_id": "win11-danny",
  "boot_id": "sha256:ac1a97f8f405accb",
  "power_epoch": 12,
  "source": "windows-power-bias",
  "evidence": "DEMONSTRATED",
  "detail": {
    "previous_power_epoch": 11,
    "suspend_wall_gap_s": 671.4,
    "mechanism": "suspend-bias delta (tick - unbiased interrupt time)"
  }
}
```

**This engine persists operational telemetry only.** No prompts, no file
contents, no user documents, no secrets. Nothing it records is derived from
what the machine was being used *for*.

## Attribution

```
OK · PROVIDER_ERROR · TRANSPORT_ERROR · HOST_NETWORK_LOSS
HOST_SUSPENDED · PROCESS_INTERRUPTED · DEADLINE_EXCEEDED · UNKNOWN
```

The rule:

```
HOST_SUSPENDED != PROVIDER_ERROR
```

Order matters, and it is frozen. Host continuity is checked **before** anything
about the error, because a transport failure during a suspend is a suspend:

1. session changed → `PROCESS_INTERRUPTED`
2. boot changed → `PROCESS_INTERRUPTED`
3. `power_epoch` changed → `HOST_SUSPENDED`
4. `network_epoch` changed, or network is down → `HOST_NETWORK_LOSS`
5. *only now* the error speaks: HTTP status → `PROVIDER_ERROR`; over deadline
   with the host awake → `DEADLINE_EXCEEDED`; transport failure on a host whose
   network is up → `TRANSPORT_ERROR`
6. anything else, including a transport failure on a host that cannot see its
   own network → `UNKNOWN`

### Keeping provider statistics honest

`Provider.reliability()` reports:

```json
{
  "countable_calls": 24,
  "provider_faults": 1,
  "excluded_host_faults": 1,
  "fault_rate": 0.0417,
  "host_awareness": true,
  "note": "host-interrupted calls are excluded from fault_rate"
}
```

A host-interrupted call is **excluded and counted as excluded** — never dropped
silently, never folded into the denominator. Without an awareness engine
attached the note changes to say plainly that `fault_rate` cannot tell a
provider failure from a local suspend. No historical number was rewritten; the
classification is new and says so.

### Deadlines

Four different things, deliberately not merged:

| | what it bounds | who enforces |
|---|---|---|
| socket timeout | one socket operation | `urllib`, per read |
| stream inactivity | gaps within a response | not implemented |
| **wall-clock deadline** | the whole call, all retries | `DEADLINE_S`, 90 s |
| host suspension | nothing — the process is frozen | detected, not prevented |

`urllib`'s `timeout` is the first row, which is why a 120-second timeout
permitted a 793-second call: the socket was never *inactive* from the OS's
point of view for longer than the timeout, and during suspend nothing was
running to notice. The fix was not a larger timeout. It was a wall clock, plus
the ability to say afterwards that the wall clock is not the provider's fault.

## Invariants

1. The model does not decide what happened to the host when mechanical
   evidence exists.
2. The engine produces facts, not policy.
3. It grants no capability. (`test_awareness_grants_nothing`)
4. It executes nothing arbitrary.
5. It cannot modify authority.
6. It does not depend on Nemotron, or on any model.
7. A model may interpret its events and may never create one.
   (`ingest_external` raises; `test_case_H`)
8. Every persisted event names the mechanism that produced it, in `source`.
9. `UNKNOWN` is a valid answer.
10. Absence of evidence never becomes `ACTIVE`. A missing bias is `None`,
    never `0.0`; a blind host reports `UNKNOWN`.
11. No component claims omniscience.

## Limitations

- **No pre-suspend notification.** `SUSPENDING` and `SUSPENDED` are never
  reported live. `NOT_DEMONSTRATED`.
- **Linux is a seam, not a backend.** The mechanism is documented
  (`CLOCK_BOOTTIME − CLOCK_MONOTONIC`, then logind `PrepareForSleep`) and
  `LinuxPowerProvider` reports `UNKNOWN` rather than pretending.
  `NOT_DEMONSTRATED`.
- **macOS: absent.** No hardware to demonstrate it on, so no stub.
  `NOT_DEMONSTRATED`.
- **Network probe is local belief, not reachability.** `InternetGetConnectedState`
  says whether this machine thinks it has a connection. It does not prove any
  endpoint is reachable, and nothing here claims it does.
- **Hibernation, fast startup and VM pause are untested.** Each ought to move
  the bias the same way; none has been measured. `UNKNOWN`.
- **The event ring is in memory**, capped at 256 events, and does not survive
  the process. Nothing needs it to: `boot_id` is derived, not stored.
- **Sampling is on demand.** No daemon, no background thread. A suspend is
  detected at the next `snapshot()`, which is exactly when anyone cares.

## Running it

```
python -m pytest tests/test_awareness.py -q      # 21 passed
python tools/host_watch.py                       # manual, real hardware
python tools/host_watch.py --probe               # with real model calls
```

`host_watch.py` **never suspends the machine.** It asks you to close the lid.
Putting someone's computer to sleep is not a thing a tool should decide to do.
