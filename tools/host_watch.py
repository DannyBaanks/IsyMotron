"""Manual test: prove suspend detection on real hardware.

    python tools/host_watch.py                 # watch until Ctrl-C
    python tools/host_watch.py --probe         # also make real model calls
    python tools/host_watch.py --seconds 600

It prints the host's continuity state on a slow tick, and prints a timeline
when anything discontinuous happens. To exercise it:

    1. start it
    2. close the laptop lid (or Win+X, U, S)
    3. wait a minute
    4. open it again
    5. read the timeline

**This never suspends the machine itself.** Putting a person's computer to
sleep is not something a tool should do on its own, so it asks you to do it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "core"), os.path.join(ROOT, "hosts")):
    sys.path.insert(0, p)

from isymotron.attribution import Attribution                     # noqa: E402
from isymotron.awareness import HostAwarenessEngine, HostEventType  # noqa: E402

OUT = os.path.join(ROOT, "evidence", "M4")


def build_engine(host_id: str):
    if sys.platform == "win32":
        from windows.power import WindowsPowerProvider
        return HostAwarenessEngine(host_id, WindowsPowerProvider())
    if sys.platform.startswith("linux"):
        from linux.power import LinuxPowerProvider
        print("note: the Linux provider is a documented seam, not a backend.")
        return HostAwarenessEngine(host_id, LinuxPowerProvider())
    from isymotron.awareness import NullPowerProvider
    print(f"note: no power backend for {sys.platform}; everything will be UNKNOWN.")
    return HostAwarenessEngine(host_id, NullPowerProvider())


def stamp(wall: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(wall))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="win11-danny")
    ap.add_argument("--seconds", type=float, default=0.0, help="0 = until Ctrl-C")
    ap.add_argument("--tick", type=float, default=3.0)
    ap.add_argument("--probe", action="store_true",
                    help="also make real model calls, so attribution is exercised")
    ap.add_argument("--save", action="store_true", default=True)
    args = ap.parse_args(argv)

    engine = build_engine(args.host)
    print(json.dumps(engine.describe(), indent=2))

    log = engine.corroborating_history()
    if log:
        print("\nWindows event log, most recent power events (corroboration only):")
        for e in log[-6:]:
            print(f"  {stamp(e.wall_time)}  {e.event_type.value:24s} "
                  f"[{e.evidence.value}]")

    provider = None
    if args.probe:
        from agents.provider import Provider, ProviderError
        provider = Provider(awareness=engine)
        if not provider.configured():
            print(f"\n--probe needs {provider.key_env}; continuing without it.")
            provider = None

    print("\n" + "=" * 68)
    print("  Close the laptop lid now, wait a minute, then open it again.")
    print("  This tool will NOT suspend the machine for you.")
    print("  Ctrl-C to stop.")
    print("=" * 68 + "\n")

    started = time.time()
    baseline = engine.snapshot()
    last = baseline
    calls = {"ok": 0, "provider": 0, "host": 0, "unknown": 0}

    try:
        while True:
            time.sleep(args.tick)
            now = engine.snapshot()

            if not last.same_continuity_as(now):
                wall = last.elapsed_wall(now)
                awake = last.elapsed_awake(now)
                asleep = None if awake is None else wall - awake
                print(f"\n  !! DISCONTINUITY at {stamp(now.wall_time)}")
                print(f"     power_epoch   {last.power_epoch} -> {now.power_epoch}")
                print(f"     network_epoch {last.network_epoch} -> {now.network_epoch}")
                print(f"     wall elapsed  {wall:.1f}s")
                print(f"     awake elapsed {'unknown' if awake is None else f'{awake:.1f}s'}")
                if asleep is not None and asleep > 1.0:
                    print(f"     ==> the machine was asleep for {asleep:.1f}s")
                for e in engine.recent_events(limit=3):
                    print(f"     event {e.event_type.value} "
                          f"({e.source}, {e.evidence.value})")
                print()
            else:
                mark = f"power_epoch={now.power_epoch} net={now.network_state.value}"
                print(f"  {stamp(now.wall_time)}  {now.power_state.value:8s} {mark}",
                      end="\r", flush=True)

            if provider is not None:
                from agents.provider import ProviderError
                try:
                    c = provider.complete(
                        [{"role": "user", "content": "Reply with exactly: OK"}],
                        max_tokens=80)
                    attr = c.outcome.attribution if c.outcome else Attribution.UNKNOWN
                except ProviderError as exc:
                    attr = (exc.outcome.attribution if exc.outcome
                            else Attribution.UNKNOWN)
                    print(f"\n  call failed -> {attr.value}"
                          f"{'' if exc.outcome is None else ': ' + exc.outcome.reason}")
                if attr is Attribution.OK:
                    calls["ok"] += 1
                elif attr is Attribution.PROVIDER_ERROR:
                    calls["provider"] += 1
                elif attr in (Attribution.HOST_SUSPENDED,
                              Attribution.HOST_NETWORK_LOSS,
                              Attribution.PROCESS_INTERRUPTED):
                    calls["host"] += 1
                    print(f"\n  call attributed to the HOST: {attr.value}"
                          f"  (excluded from provider stats)")
                else:
                    calls["unknown"] += 1

            last = now
            if args.seconds and time.time() - started > args.seconds:
                break
    except KeyboardInterrupt:
        print("\n")

    print("\n" + "=" * 68)
    print("  TIMELINE")
    print("=" * 68)
    for e in engine.recent_events(limit=40):
        extra = ""
        if "suspend_wall_gap_s" in e.detail:
            extra = f"  asleep {e.detail['suspend_wall_gap_s']:.1f}s"
        print(f"  {stamp(e.wall_time)}  {e.event_type.value:24s} "
              f"[{e.evidence.value:14s}] {e.source}{extra}")

    print(f"\n  health: {json.dumps(engine.health())}")
    if provider is not None:
        print(f"  reliability: {json.dumps(provider.reliability(), indent=2)}")
        print(f"  call attribution: {calls}")

    if args.save:
        os.makedirs(OUT, exist_ok=True)
        report = {
            "describe": engine.describe(),
            "health": engine.health(),
            "events": [e.to_dict() for e in engine.recent_events(limit=64)],
            "calls": calls if provider else None,
            "reliability": provider.reliability() if provider else None,
        }
        path = os.path.join(OUT, "host_watch.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print(f"\n  report -> evidence/M4/host_watch.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
