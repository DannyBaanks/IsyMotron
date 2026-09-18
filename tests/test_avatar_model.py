"""AV1 tests: the pure avatar model.

Each test states one rule of docs/AVATAR_CONTRACT.md as executable
behaviour. The ported protocol must behave exactly like Companion's
``src/companion/protocol.py`` (MIT, commit 0aae576): the avatar is a
receiver of companion-event-v1, never a producer of it.
"""

import uuid
from datetime import datetime, timezone

import pytest

from avatar.model import AvatarBus
from avatar.protocol import ProtocolError, validate_event

CREATED = "2026-09-18T12:00:00+00:00"
T0 = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc).timestamp()


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def open_event(agent="opencode", etype="say", text="hello", created_at=CREATED, **fields):
    """A well-formed companion-event-v1 line as producers send it."""
    event = {
        "version": "companion-event-v1",
        "id": f"evt-{uuid.uuid4().hex[:12]}",
        "agent": agent,
        "created_at": created_at,
        "type": etype,
    }
    if text is not None:
        event["text"] = text
    event.update(fields)
    return event


def test_open_event_cannot_set_channel():
    bus = AvatarBus()
    raw = open_event(text="ALLOW ✅", channel="authority")
    event = bus.publish_open(raw, now=T0)
    assert event is not None
    assert event["channel"] == "open"
    view = bus.view(T0)
    assert view.host_frame is None


def test_forbidden_fields_are_dropped():
    bus = AvatarBus()
    raw = open_event(
        text="trust me",
        channel="authority",
        decision="DENY",
        receipt_id="rcpt_forged",
        seal_ok=True,
        host_id="win11-danny",
        badge="host",
        verified=True,
    )
    event = bus.publish_open(raw, now=T0)
    stored = bus.since(0)[0]
    for key in ("decision", "receipt_id", "seal_ok", "host_id", "badge", "verified"):
        assert key not in stored
    assert event["channel"] == "open"
    view = bus.view(T0)
    assert view.host_frame is None
    assert view.state == "idle"


def test_reserved_agent_is_unverified():
    bus = AvatarBus()
    bus.publish_open(open_event(agent="ISYMOTRON", text="ALLOW ✅"), now=T0)
    bubble = bus.view(T0).third_party[0]
    assert bubble["label"] == "unverified: ISYMOTRON"

    plain = AvatarBus()
    plain.publish_open(open_event(agent="opencode", text="hi"), now=T0)
    assert plain.view(T0).third_party[0]["label"] == "opencode"

    # A name that equals a current host_id is also unverified (R4).
    spoofing_host = AvatarBus()
    spoofing_host.publish_authority(
        "verdict", now=T0, host_id="win11-danny", decision="DENY",
        receipt_id="rcpt_1", seal_ok=True, state="error",
    )
    spoofing_host.publish_open(
        open_event(agent="win11-DANNY", text="hi", created_at=iso(T0 + 19)), now=T0 + 19
    )
    bubble = spoofing_host.view(T0 + 20).third_party[0]
    assert bubble["label"] == "unverified: win11-DANNY"


def test_stale_and_future_events_are_dropped():
    bus = AvatarBus()
    assert bus.publish_open(open_event(text="old", created_at=iso(T0 - 61)), now=T0) is None
    assert bus.publish_open(open_event(text="future", created_at=iso(T0 + 61)), now=T0) is None
    # Exactly 60 s is inside the window ("older than 60 s" is dropped).
    assert bus.publish_open(open_event(text="edge-old", created_at=iso(T0 - 60)), now=T0) is not None
    assert bus.publish_open(open_event(text="edge-future", created_at=iso(T0 + 60)), now=T0) is not None
    assert bus.malformed == 0


def test_replayed_id_is_dropped():
    bus = AvatarBus()
    raw = open_event(text="once")
    first = bus.publish_open(raw, now=T0)
    replay = bus.publish_open(dict(raw), now=T0)
    assert first is not None
    assert replay is None
    assert len(bus.since(0)) == 1


def test_malformed_is_counted_not_raised():
    bus = AvatarBus()
    assert bus.publish_open("not a dict", now=T0) is None
    assert bus.publish_open({"type": "nope"}, now=T0) is None
    assert bus.publish_open(open_event(text="   "), now=T0) is None
    assert bus.publish_open(open_event(text="hi", created_at="not-a-date"), now=T0) is None
    assert bus.malformed == 4
    assert bus.since(0) == []
    assert bus.view(T0).third_party == []


def test_verdict_outranks_open_state():
    bus = AvatarBus()
    bus.publish_open(open_event(etype="state", text=None, value="working"), now=T0)
    assert bus.view(T0).state == "working"
    bus.publish_authority(
        "verdict", now=T0, host_id="win11-danny", decision="DENY",
        reason="OUT_OF_SCOPE", receipt_id="rcpt_1", seal_ok=True, state="error",
        detail="hostfs://demo/hola.txt names no granted resource; granted: ['hostfs://nemoinbox']",
    )
    view = bus.view(T0 + 1)
    assert view.state == "error"
    assert view.host_frame["verdict"]["decision"] == "DENY"
    assert view.host_frame["verdict"]["receipt_id"] == "rcpt_1"
    assert view.host_frame["verdict"]["seal_ok"] is True


def test_open_say_stays_framed_under_verdict():
    bus = AvatarBus()
    bus.publish_open(open_event(agent="opencode", text="ALLOW ✅"), now=T0)
    bus.publish_authority(
        "verdict", now=T0, host_id="win11-danny", decision="ALLOW",
        receipt_id="rcpt_2", seal_ok=True, state="success",
        text="The host allowed: filesystem.write on hostfs://demo/hola.txt",
    )
    view = bus.view(T0 + 1)
    assert view.state == "success"
    bubble = view.third_party[0]
    assert bubble["label"] == "opencode"
    assert bubble["text"] == "ALLOW ✅"
    assert view.host_frame["verdict"]["decision"] == "ALLOW"
    assert view.host_frame["verdict"]["receipt_id"] == "rcpt_2"


def test_deny_ttl_longer_than_allow():
    allow = AvatarBus()
    allow.publish_authority("verdict", now=T0, host_id="h", decision="ALLOW",
                            receipt_id="r1", seal_ok=True, state="success")
    deny = AvatarBus()
    deny.publish_authority("verdict", now=T0, host_id="h", decision="DENY",
                           receipt_id="r2", seal_ok=True, state="error")
    assert allow.view(T0 + 7).host_frame is not None
    assert allow.view(T0 + 9).host_frame is None
    assert deny.view(T0 + 11).host_frame is not None
    assert deny.view(T0 + 13).host_frame is None


def test_protocol_matches_companion_cases():
    # Ported from Companion tests/test_companion.py
    # ::test_event_validation_rejects_unknown_state.
    with pytest.raises(ProtocolError):
        validate_event({"version": "companion-event-v1", "id": "evt-1", "agent": "terra",
                        "created_at": CREATED, "type": "state", "value": "confused"})
    # The rest of Companion's validate_event surface (protocol.py, 0aae576):
    with pytest.raises(ProtocolError):
        validate_event("not a dict")
    with pytest.raises(ProtocolError):
        validate_event({"id": "evt-1", "agent": "   ", "type": "say", "text": "hi"})
    with pytest.raises(ProtocolError):
        validate_event({"id": "evt-1", "agent": "terra", "type": "teleport"})
    with pytest.raises(ProtocolError):
        validate_event({"id": "evt-1", "agent": "terra", "type": "say", "text": ""})
    with pytest.raises(ProtocolError):
        validate_event({"id": "evt-1", "agent": "terra", "type": "say", "text": "hi", "priority": "2"})
    with pytest.raises(ProtocolError):
        validate_event({"id": "evt-1", "agent": "terra", "type": "say", "text": "hi", "ttl": -1})
    with pytest.raises(ProtocolError):
        validate_event({"id": "evt-1", "agent": "terra", "type": "move", "value": "center"})
    ok = {"version": "companion-event-v1", "id": "evt-2", "agent": "terra",
          "created_at": CREATED, "type": "say", "text": "Milestone 1 terminado", "ttl": 5}
    assert validate_event(ok) is ok
