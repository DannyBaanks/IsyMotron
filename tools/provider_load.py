"""Provider continuity workload: measured numbers, not adjectives (claim H).

    python tools/provider_load.py --provider nebius --calls 20 --interval 0.5
    python tools/provider_load.py --provider ollama --json evidence/H/run.json

Sends N identical minimal round trips through the provider seam with a fixed
interval, and reports what was observed: per-call latency and final outcome,
counts, error rate, and quantiles. It does not promise reliability; it
measures one run, on one machine, against one provider, and the report says so.

Notes the report bakes in:

- An error here is a *post-retry* error. The provider seam retries transient
  statuses (429/5xx, etc.) up to MAX_ATTEMPTS; a 503 that recovers on retry
  shows up as a slower success, not as an error.
- Latency includes the seam's retry backoff when retries happen.
- n is written into the report. An error rate from n=12 is honest about n.

No SDK, stdlib only, like everything else here.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "core"), os.path.join(ROOT, "hosts")):
    sys.path.insert(0, p)

from agents.provider import Provider, ProviderError  # noqa: E402

PROBE = [{"role": "user", "content": "Reply with exactly: OK"}]


def run_workload(provider: Provider, calls: int, interval_s: float,
                 sleep=time.sleep) -> dict:
    """Time `calls` round trips and return the raw observations."""
    samples = []
    for i in range(calls):
        t0 = time.monotonic()
        wall0 = time.time()
        try:
            c = provider.complete(PROBE, max_tokens=16)
            samples.append({
                "i": i, "ok": True, "latency_s": round(time.monotonic() - t0, 3),
                "wall": wall0, "model": c.model,
                "prompt_tokens": c.prompt_tokens, "completion_tokens": c.completion_tokens,
            })
        except ProviderError as exc:
            samples.append({
                "i": i, "ok": False, "latency_s": round(time.monotonic() - t0, 3),
                "wall": wall0, "error": str(exc), "status": exc.status,
            })
        if interval_s and i + 1 < calls:
            sleep(interval_s)
    return {"samples": samples}


def summarize(samples: list[dict]) -> dict:
    """Honest statistics: n is always reported next to every rate."""
    n = len(samples)
    ok = [s for s in samples if s["ok"]]
    bad = [s for s in samples if not s["ok"]]
    lat = sorted(s["latency_s"] for s in samples)

    def pct(q: float) -> float | None:
        if not lat:
            return None
        k = (len(lat) - 1) * q
        f = int(k)
        if f + 1 < len(lat):
            return round(lat[f] + (lat[f + 1] - lat[f]) * (k - f), 3)
        return round(lat[f], 3)

    return {
        "calls": n,
        "ok": len(ok),
        "errors": len(bad),
        "error_rate": round(len(bad) / n, 4) if n else None,
        "latency_s": {
            "min": round(min(lat), 3) if lat else None,
            "median": round(statistics.median(lat), 3) if lat else None,
            "p95": pct(0.95),
            "max": round(max(lat), 3) if lat else None,
        },
        "error_statuses": sorted({str(s.get("status")) for s in bad}) if bad else [],
    }


def report(provider: Provider, workload: dict, args) -> dict:
    desc = provider.describe()
    desc.pop("key_present", None)
    return {
        "contract": "provider-load/v0",
        "scope": ("one run, one machine, one provider; errors are post-retry; "
                  "an error rate is honest only about its own n"),
        "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "provider": desc,
        "calls_requested": args.calls,
        "interval_s": args.interval,
        "summary": summarize(workload["samples"]),
        "samples": workload["samples"],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider")
    ap.add_argument("--model")
    ap.add_argument("--calls", type=int, default=20)
    ap.add_argument("--interval", type=float, default=0.5,
                    help="seconds between calls (0 to go back-to-back)")
    ap.add_argument("--json", help="write the full report here")
    args = ap.parse_args(argv)

    try:
        provider = Provider(name=args.provider, model=args.model)
    except ProviderError as exc:
        print(f"config error: {exc}")
        return 2
    if not provider.configured():
        print(f"No key. Set {provider.key_env} and re-run.")
        return 2

    print(f"provider : {provider.describe()['label']}  model={provider.model}")
    print(f"workload : {args.calls} calls, {args.interval}s apart (errors counted post-retry)")
    workload = run_workload(provider, args.calls, args.interval)
    rep = report(provider, workload, args)
    s = rep["summary"]
    print(f"\n  n={s['calls']}  ok={s['ok']}  errors={s['errors']}"
          f"  rate={s['error_rate']}")
    lat = s["latency_s"]
    print(f"  latency_s: min={lat['min']} median={lat['median']}"
          f" p95={lat['p95']} max={lat['max']}")
    if s["error_statuses"]:
        print(f"  statuses : {', '.join(s['error_statuses'])}")
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=2)
            fh.write("\n")
        print(f"  report   : {args.json}")
    print("\n  This run measured. It did not conclude 'reliable'.")
    return 0 if s["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
