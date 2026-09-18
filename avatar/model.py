"""The pure avatar model: two channels, one bus, one precedence.

No I/O, no UI (docs/AVATAR_CONTRACT.md). The channel is assigned by where an
event came from, never by what it says (R1): authority events exist only
through :meth:`AvatarBus.publish_authority`, called by the IsyMotron process;
open events go through :meth:`AvatarBus.publish_open`, which strips every
field an inbox line could use to look like authority and can never mint a
verdict.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from avatar.protocol import ProtocolError, validate_event

AUTHORITY_KINDS = {
    "mode", "planning", "planned", "step", "verdict", "host", "provider_error",
}
KIND_STATE = {"planning": "thinking", "planned": "waiting", "step": "working"}
VERDICT_TTL = 8.0          # contract §4: default verdict TTL
DENY_TTL = 12.0            # contract §4: DENY outlives ALLOW
SAY_TTL = 8.0              # contract §3.2: the reader stamps say TTL 8
STALENESS_SECONDS = 60.0   # contract §5: 60 s past or future is dropped
RING_SIZE = 200            # contract §5: in-memory ring buffer
REPLAY_WINDOW = 1000       # contract §5: ids seen in the last 1000 events
RESERVED_AGENTS = frozenset({"isymotron", "host", "system", "authority"})
# R1: an inbox line never keeps these; the rest of the payload passes
# through verbatim so unknown fields stay framed, not filtered (R3).
FORBIDDEN_FIELDS = ("channel", "decision", "receipt_id", "seal_ok", "host_id", "badge", "verified")
DROP_FIELDS = FORBIDDEN_FIELDS + ("id", "version", "created_at")


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _epoch(created_at: Any) -> float | None:
    """Parse an ISO ``created_at`` into epoch seconds; ``None`` if unusable."""
    if not isinstance(created_at, str):
        return None
    try:
        stamp = datetime.fromisoformat(created_at.strip())
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.timestamp()


@dataclass
class View:
    """What a renderer may draw right now."""

    state: str
    host_frame: dict | None
    third_party: list


class AvatarBus:
    """Stamps channels by source, keeps precedence, renders a :class:`View`.

    Single-threaded by design for AV1; the console (AV2/AV3) owns any
    cross-thread wiring.
    """

    def __init__(self) -> None:
        self._timeline: list[tuple[dict, float, float | None]] = []  # (event, epoch, ttl)
        self._seen_ids: deque = deque(maxlen=REPLAY_WINDOW)
        self._host_ids: set = set()
        self._seq = 0
        self.malformed = 0

    # ------------------------------------------------------------ authority
    def publish_authority(self, kind: str, *, now: float | None = None, **fields: Any) -> dict:
        """The only way to create an authority event.

        Called in-process by the IsyMotron server; ``now`` exists so tests
        (and future producers) can drive a fake clock.
        """
        if kind not in AUTHORITY_KINDS:
            raise ValueError(f"unsupported authority kind: {kind}")
        at = time.time() if now is None else float(now)
        event: dict = {"seq": self._next_seq(), "channel": "authority", "kind": kind, "at": _iso(at)}
        ttl = None
        if kind == "verdict":
            ttl = DENY_TTL if fields.get("decision") == "DENY" else VERDICT_TTL
            event["ttl"] = ttl
        event.update(fields)
        host_id = fields.get("host_id")
        if isinstance(host_id, str) and host_id.strip():
            self._host_ids.add(host_id.strip().lower())
        self._timeline.append((event, at, ttl))
        self._trim()
        return event

    # ----------------------------------------------------------------- open
    def publish_open(self, raw: Any, now: float) -> dict | None:
        """Validate and stamp one inbox line.

        Returns the stamped open event, or ``None`` when the line is
        malformed (counted, never raised), replayed, stale or future.
        """
        try:
            validate_event(raw)
            created = _epoch(raw.get("created_at"))
            if created is None:
                raise ProtocolError("created_at must be an ISO timestamp")
        except ProtocolError:
            self.malformed += 1
            return None
        if raw["id"] in self._seen_ids:
            return None
        age = float(now) - created
        if age > STALENESS_SECONDS or age < -STALENESS_SECONDS:
            return None
        agent = raw["agent"]
        payload = {key: value for key, value in raw.items() if key not in DROP_FIELDS}
        ttl = payload.get("ttl")
        if ttl is None and raw["type"] == "say":
            ttl = SAY_TTL
            payload["ttl"] = SAY_TTL
        event: dict = {
            "seq": self._next_seq(),
            "channel": "open",
            "agent": agent,
            "agent_verified": False,  # contract §3.2: always false in v1
            "agent_unverified": agent.strip().lower() in RESERVED_AGENTS,
            "type": raw["type"],
        }
        event.update(payload)
        self._seen_ids.append(raw["id"])
        self._timeline.append((event, created, ttl))
        self._trim()
        return event

    # -------------------------------------------------------------- reading
    def since(self, seq: int) -> list:
        """Every stored event with ``seq`` greater than the given one."""
        return [event for event, _, _ in self._timeline if event["seq"] > seq]

    def view(self, now: float) -> View:
        """Resolve precedence (contract §4) at instant ``now``."""
        now = float(now)
        active = [entry for entry in self._timeline if self._active(entry, now)]
        verdict = self._latest_entry(active, kind="verdict")
        frame = verdict \
            or self._latest_entry(active, kinds={"host", "provider_error"}) \
            or self._latest_entry(active, kinds=set(KIND_STATE))
        state = None
        if verdict is not None:
            event = verdict[0]
            state = event.get("state") or ("error" if event.get("decision") == "DENY" else "success")
        elif frame is not None:
            event = frame[0]
            state = event.get("state") or KIND_STATE.get(event["kind"])
        if state is None:
            for event, _, _ in reversed(active):
                if event.get("channel") == "open" and event.get("type") in {"state", "mood"}:
                    value = event.get("value")
                    if isinstance(value, str):
                        state = value
                        break
        return View(state or "idle", self._host_frame(frame), self._third_party(active))

    # -------------------------------------------------------------- private
    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _trim(self) -> None:
        while len(self._timeline) > RING_SIZE:
            del self._timeline[0]

    @staticmethod
    def _active(entry: tuple, now: float) -> bool:
        _, epoch, ttl = entry
        return ttl is None or epoch + ttl > now

    @staticmethod
    def _latest_entry(entries: list, kind: str | None = None, kinds: set | None = None):
        picked = None
        for entry in entries:
            event = entry[0]
            if kind is not None and event.get("kind") != kind:
                continue
            if kinds is not None and event.get("kind") not in kinds:
                continue
            if picked is None or event["seq"] > picked[0]["seq"]:
                picked = entry
        return picked

    def _host_frame(self, entry: tuple | None) -> dict | None:
        if entry is None:
            return None
        event = entry[0]
        verdict = None
        if event["kind"] == "verdict":
            verdict = {
                "decision": event.get("decision"),
                "reason": event.get("reason"),
                "receipt_id": event.get("receipt_id"),
                "seal_ok": event.get("seal_ok"),
                "host_id": event.get("host_id"),
            }
        return {
            "text": event.get("text"),
            "host_id": event.get("host_id"),
            "verdict": verdict,
        }

    def _label(self, event: dict) -> str:
        agent = event["agent"]
        if event.get("agent_unverified") or agent.strip().lower() in self._host_ids:
            return f"unverified: {agent}"
        return agent

    def _third_party(self, active: list) -> list:
        bubbles = []
        for event, _, _ in active:
            if event.get("channel") == "open" and event.get("type") == "say":
                bubbles.append({
                    "seq": event["seq"],
                    "label": self._label(event),
                    "text": event.get("text", ""),
                })
        return bubbles
