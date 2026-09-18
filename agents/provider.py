"""Inference provider seam.

NVIDIA NIM and Nebius Token Factory are the same protocol behind different
doors: both speak the OpenAI chat-completions shape and both serve the same
model id strings (`nvidia/nemotron-3-super-120b-a12b` is literally the same
string on both). Only `base_url` and the key differ.

So the provider is configuration, not code. Develop against whichever one
answers today, submit against whichever one the rules require, change one
environment variable.

    ISYMOTRON_PROVIDER=nvidia|nebius   (default: nvidia)
    NVIDIA_NIM_API_KEY=nvapi-...
    NEBIUS_API_KEY=...
    ISYMOTRON_MODEL=nvidia/nemotron-3-super-120b-a12b
    ISYMOTRON_BASE_URL=...             (overrides the preset)

No SDK. urllib only, so the whole repo stays dependency-free and a legacy host
could in principle carry this file too.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from isymotron.attribution import OperationOutcome, attribute
from isymotron.awareness import HostAwarenessEngine

DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"

PRESETS: dict[str, dict[str, str]] = {
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_env": "NVIDIA_NIM_API_KEY",
        "label": "NVIDIA NIM",
    },
    "nebius": {
        "base_url": "https://api.tokenfactory.us-central1.nebius.com/v1",
        "key_env": "NEBIUS_API_KEY",
        "label": "Nebius Token Factory",
    },
}


# Statuses worth retrying. Measured 2026-09-17: 1 HTTP 503 "Service
# temporarily overloaded" in 12 back-to-back calls to NVIDIA NIM, with no
# pattern and no warning. At ~8% a three-minute live demo has roughly a coin
# flip of hitting one. See docs/FINDINGS.md #7.
RETRYABLE = frozenset({408, 409, 429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4
BACKOFF_BASE_S = 0.6

# The machine losing its network mid-run is not an exotic case: it happened on
# the first day, when the laptop was closed during a 25-call measurement. One
# request hung for 793 s despite timeout=120, then eighteen consecutive
# connection-level failures with no HTTP status, then clean recovery once the
# machine was back. See docs/FINDINGS.md #7.
#
# Two consequences, both of them our bug rather than the provider's:
#   - urllib's `timeout` is per socket operation, not a deadline. A socket that
#     stops producing without closing never trips it. DEADLINE_S is the wall
#     clock that does.
#   - a status-less transport error was classified non-retryable, which is
#     backwards for the common case: a network that comes back.
DEADLINE_S = 90.0
MIN_INTERVAL_S = 0.25


class ProviderError(Exception):
    """Anything that stopped a completion. Carries the status when there is one."""

    def __init__(self, message: str, status: int | None = None, body: str = "",
                 attempts: int = 1, transport: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.body = body
        self.attempts = attempts
        self.transport = transport
        #: Set by Provider.complete when host awareness is wired in. Without it
        #: the caller is left guessing exactly as we were on 2026-09-17.
        self.outcome = None

    @property
    def retryable(self) -> bool:
        # A transport failure with no status is retryable: that is the shape
        # throttling took when we measured it.
        return self.status in RETRYABLE or self.transport


class DeadlineExceeded(ProviderError):
    """The wall clock ran out. Never retried -- the budget is already spent."""

    @property
    def retryable(self) -> bool:
        return False


@dataclass
class Completion:
    """One model response, with the numbers the evidence ledger will want."""

    text: str
    model: str
    provider: str
    latency_s: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None
    reasoning: str = ""
    attempts: int = 1
    outcome: Any = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def truncated(self) -> bool:
        """The token budget ran out before the model finished.

        On a reasoning model this is not a cosmetic truncation. Measured on
        nemotron-3-super-120b-a12b: at max_tokens=16 the reply came back with
        finish_reason="length" and `content` holding raw chain-of-thought
        prose instead of the answer; at 48 the same prompt returned a clean
        "OK". Under-budgeting does not shorten the answer, it replaces the
        answer with thinking. Always check this before blaming the prompt.
        """
        return self.finish_reason == "length"

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "latency_s": round(self.latency_s, 3),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "finish_reason": self.finish_reason,
            "truncated": self.truncated,
            "reasoning_chars": len(self.reasoning),
            "attempts": self.attempts,
            "outcome": self.outcome.to_dict() if self.outcome else None,
        }


class Provider:
    """A chat-completions endpoint. Knows nothing about IsyMotron."""

    def __init__(self, name: str | None = None, model: str | None = None,
                 base_url: str | None = None, api_key: str | None = None,
                 timeout_s: float = 120.0,
                 awareness: HostAwarenessEngine | None = None) -> None:
        self.name = (name or os.environ.get("ISYMOTRON_PROVIDER") or "nvidia").lower()
        preset = PRESETS.get(self.name)
        if preset is None:
            raise ProviderError(
                f"unknown provider {self.name!r}; known: {', '.join(sorted(PRESETS))}")
        self.label = preset["label"]
        self.base_url = (base_url or os.environ.get("ISYMOTRON_BASE_URL")
                         or preset["base_url"]).rstrip("/")
        self.model = model or os.environ.get("ISYMOTRON_MODEL") or DEFAULT_MODEL
        self.api_key = api_key or os.environ.get(preset["key_env"], "")
        self.key_env = preset["key_env"]
        self.timeout_s = timeout_s
        self.attempts_used = 0
        self.retries = 0
        self.deadline_s = float(os.environ.get("ISYMOTRON_DEADLINE_S", DEADLINE_S))
        self._last_call = 0.0
        #: Optional, but strongly advised. Without it every failure below is
        #: attributed from the error alone, which is how a closed laptop got
        #: within minutes of being recorded as provider throttling.
        self.awareness = awareness
        #: Only outcomes that actually say something about the provider. Host
        #: faults are excluded explicitly, and counted separately.
        self.countable_calls = 0
        self.provider_faults = 0
        self.excluded_host_faults = 0

    # -- diagnostics --------------------------------------------------------
    def configured(self) -> bool:
        return bool(self.api_key)

    def describe(self) -> dict:
        return {
            "provider": self.name,
            "label": self.label,
            "base_url": self.base_url,
            "model": self.model,
            "key_env": self.key_env,
            "key_present": self.configured(),
        }

    def models(self) -> list[str]:
        payload = self._get("/models")
        return sorted(m.get("id", "") for m in payload.get("data", []))

    # -- the one call that matters -----------------------------------------
    def complete(self, messages: Sequence[Mapping[str, str]], *,
                 max_tokens: int = 1024, temperature: float = 0.2,
                 stop: Sequence[str] | None = None) -> Completion:
        if not self.configured():
            raise ProviderError(
                f"no API key: set {self.key_env} for provider {self.name!r}")
        body: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if stop:
            body["stop"] = list(stop)

        before = self.awareness.snapshot() if self.awareness else None
        t0 = time.time()
        self.attempts_used = 1
        try:
            payload = self._post("/chat/completions", body)
        except ProviderError as exc:
            exc.outcome = self._attribute(before, exc)
            self._tally(exc.outcome)
            raise
        latency = time.time() - t0
        if self.attempts_used > 1:
            self.retries += self.attempts_used - 1
        outcome = self._attribute(before, None)
        self._tally(outcome)

        try:
            choice = payload["choices"][0]
            message = choice["message"]
            text = message.get("content") or ""
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"malformed completion: {exc}") from exc

        usage = payload.get("usage") or {}
        return Completion(
            text=text, model=payload.get("model", self.model), provider=self.name,
            latency_s=latency,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            finish_reason=choice.get("finish_reason"),
            # Reasoning models return their chain of thought in a separate
            # field. We keep the length for the ledger and drop the text: it is
            # not evidence and it is not ours to store.
            reasoning=message.get("reasoning_content") or "",
            attempts=self.attempts_used,
            outcome=outcome,
            raw=payload,
        )

    # -- attribution --------------------------------------------------------
    def _attribute(self, before, exc):
        """Classify what just happened, using host facts around the error.

        Returns None when no awareness engine is attached: an absent
        attribution is honest, a guessed one is not.
        """
        if before is None or self.awareness is None:
            return None
        after = self.awareness.snapshot()
        return attribute(
            before, after,
            error=exc,
            http_status=exc.status if exc else None,
            transport=bool(exc and exc.transport),
            deadline_s=self.deadline_s,
        )

    def _tally(self, outcome):
        """Keep provider-reliability counts clean.

        A call the host interrupted is not a data point about the provider. It
        is counted separately and visibly as excluded, never dropped silently
        and never folded into the denominator.
        """
        if outcome is None:
            return
        if outcome.countable:
            self.countable_calls += 1
            if outcome.provider_fault:
                self.provider_faults += 1
        elif outcome.host_interruption:
            self.excluded_host_faults += 1

    def reliability(self):
        """Measured provider reliability, with the exclusions stated."""
        return {
            "provider": self.name,
            "model": self.model,
            "countable_calls": self.countable_calls,
            "provider_faults": self.provider_faults,
            "excluded_host_faults": self.excluded_host_faults,
            "retries": self.retries,
            "fault_rate": (round(self.provider_faults / self.countable_calls, 4)
                           if self.countable_calls else None),
            "host_awareness": bool(self.awareness),
            "note": ("host-interrupted calls are excluded from fault_rate"
                     if self.awareness else
                     "NO host awareness attached: fault_rate cannot tell a "
                     "provider failure from a local suspend or network loss"),
        }

    # -- transport ----------------------------------------------------------
    def _request(self, path: str, data: bytes | None) -> dict:
        """Send, retrying transient provider failures with backoff.

        A retry is only ever a *transport* decision. It never changes the
        request and never touches a verdict: a host that said DENY is not
        asked twice.
        """
        self._pace()
        started = time.time()
        last: ProviderError | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if time.time() - started > self.deadline_s:
                raise DeadlineExceeded(
                    f"{self.label}: gave up after {self.deadline_s:.0f}s",
                    attempts=attempt - 1)
            try:
                return self._send_once(path, data)
            except ProviderError as exc:
                last = exc
                self.attempts_used = attempt
                if not exc.retryable or attempt == MAX_ATTEMPTS:
                    exc.attempts = attempt
                    raise
                # Exponential, with the jitter that keeps several clients from
                # retrying in lockstep.
                import random
                delay = BACKOFF_BASE_S * (2 ** (attempt - 1))
                time.sleep(delay + random.uniform(0, delay / 2))
        assert last is not None
        raise last

    def _send_once(self, path: str, data: bytes | None) -> dict:
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST" if data is not None else "GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:600]
            # Never let the key reach an error string.
            raise ProviderError(f"{self.label} returned HTTP {exc.code}",
                                status=exc.code, body=body) from None
        except urllib.error.URLError as exc:
                raise ProviderError(f"{self.label} unreachable: {exc.reason}",
                                transport=True) from None
        except (TimeoutError, OSError) as exc:
            raise ProviderError(f"{self.label} transport failure: {exc}",
                                transport=True) from None

    def _pace(self) -> None:
        """Keep a floor between calls. Cheap insurance against our own burst."""
        gap = time.time() - self._last_call
        if self._last_call and gap < MIN_INTERVAL_S:
            time.sleep(MIN_INTERVAL_S - gap)
        self._last_call = time.time()

    def _get(self, path: str) -> dict:
        return self._request(path, None)

    def _post(self, path: str, body: Mapping[str, Any]) -> dict:
        return self._request(path, json.dumps(body).encode("utf-8"))


class ScriptedProvider(Provider):
    """A provider that replays canned answers. For tests, never for evidence.

    Every test that exercises the planner's *validation* uses this, so the
    suite stays offline, deterministic and free. Tests that exercise the
    *model* are marked live and are skipped without a key.
    """

    #: pytest would otherwise try to collect this as a test class.
    __test__ = False

    def __init__(self, replies: Sequence[str], model: str = "scripted/0",
                 awareness: HostAwarenessEngine | None = None,
                 during: Any = None) -> None:
        self.name = "scripted"
        self.label = "scripted"
        self.base_url = "<none>"
        self.model = model
        self.api_key = "<none>"
        self.key_env = "<none>"
        self.timeout_s = 0.0
        self._replies = list(replies)
        self.calls: list[list[Mapping[str, str]]] = []
        self.awareness = awareness
        #: Called between the before and after snapshots, so a test can make
        #: the machine suspend or lose its network *during* a call rather than
        #: between two of them. Without this the deterministic provider cannot
        #: reproduce the one scenario it exists for.
        self.during = during
        self.deadline_s = DEADLINE_S
        self.countable_calls = 0
        self.provider_faults = 0
        self.excluded_host_faults = 0
        self.retries = 0

    def configured(self) -> bool:
        return True

    def complete(self, messages, *, max_tokens=1024, temperature=0.2, stop=None):
        self.calls.append(list(messages))
        if not self._replies:
            raise ProviderError("scripted provider ran out of replies")
        before = self.awareness.snapshot() if self.awareness else None
        if self.during is not None:
            self.during()
        reply = self._replies.pop(0)
        finish = "length" if reply.startswith("<TRUNCATED>") else "stop"
        outcome = self._attribute(before, None)
        self._tally(outcome)
        return Completion(text=reply.replace("<TRUNCATED>", "", 1),
                          model=self.model, provider="scripted", latency_s=0.0,
                          finish_reason=finish, outcome=outcome)
