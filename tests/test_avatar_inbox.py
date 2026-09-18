"""AV2 tests: the open channel reader.

The inbox is Companion's transport unchanged: companion-event-v1 lines,
append-only JSONL. The reader starts at end of file (contract §1: backlog is
never replayed), waits for complete lines, survives truncation, and every
line it sees is third party (R1).
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from avatar.inbox import InboxTail, resolve_inbox_path
from avatar.model import AvatarBus


def make_event(agent="opencode", etype="say", text="hola", **fields):
    event = {
        "version": "companion-event-v1",
        "id": f"opencode-{uuid.uuid4().hex[:12]}",
        "agent": agent,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "type": etype,
    }
    if text is not None:
        event["text"] = text
    event.update(fields)
    return event


def write_line(path: Path, event: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")


def test_tail_starts_at_end(tmp_path):
    path = tmp_path / "inbox.jsonl"
    write_line(path, make_event(text="backlog one"))
    write_line(path, make_event(text="backlog two"))
    bus = AvatarBus()
    tail = InboxTail(bus, path)
    assert tail.poll_once() == 0  # backlog present at startup is not replayed
    assert bus.since(0) == []
    write_line(path, make_event(text="live"))
    assert tail.poll_once() == 1
    events = bus.since(0)
    assert len(events) == 1
    assert events[0]["channel"] == "open"
    assert events[0]["text"] == "live"


def test_partial_line_waits(tmp_path):
    path = tmp_path / "inbox.jsonl"
    write_line(path, make_event(text="one"))
    bus = AvatarBus()
    tail = InboxTail(bus, path)
    assert tail.poll_once() == 0  # starts at EOF over the completed line
    payload = json.dumps(make_event(text="two"), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(payload[:20])
    assert tail.poll_once() == 0  # a final line without \n waits
    assert bus.since(0) == []
    with path.open("a", encoding="utf-8") as stream:
        stream.write(payload[20:] + "\n")
    assert tail.poll_once() == 1
    assert bus.since(0)[0]["text"] == "two"


def test_truncation_resets(tmp_path):
    path = tmp_path / "inbox.jsonl"
    write_line(path, make_event(text="before"))
    bus = AvatarBus()
    tail = InboxTail(bus, path)
    assert tail.poll_once() == 0
    write_line(path, make_event(text="one"))
    assert tail.poll_once() == 1
    # rotation: the file is replaced by a shorter one
    path.write_text(
        json.dumps(make_event(text="after rotation"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    assert tail.poll_once() == 1  # size < offset -> reset to 0
    assert [event["text"] for event in bus.since(0)] == ["one", "after rotation"]


def test_env_precedence(tmp_path, monkeypatch):
    explicit = tmp_path / "explicit.jsonl"
    companion = tmp_path / "companion"
    local = tmp_path / "local"
    monkeypatch.setenv("ISYMOTRON_AVATAR_INBOX", str(explicit))
    monkeypatch.setenv("COMPANION_ROOT", str(companion))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    assert resolve_inbox_path() == explicit
    monkeypatch.delenv("ISYMOTRON_AVATAR_INBOX")
    assert resolve_inbox_path() == companion / "inbox.jsonl"
    monkeypatch.delenv("COMPANION_ROOT")
    assert resolve_inbox_path() == local / "IsyMotron" / "avatar" / "inbox.jsonl"


def test_companion_plugin_line_is_accepted(tmp_path):
    # Exact shape emitted by C:\Development\ISyCo Git\Companion
    # \integrations\opencode-plugin.ts on session.idle (say with ttl 8,
    # priority 0; JSON.stringify drops the undefined value/text keys).
    path = tmp_path / "inbox.jsonl"
    bus = AvatarBus()
    tail = InboxTail(bus, path)
    path.touch()  # the plugin's inbox exists before the console starts
    tail.poll_once()  # first sighting: start at end of file (contract §1)
    line = json.dumps(
        {
            "version": "companion-event-v1",
            "id": "opencode-ses_demo123",
            "agent": "opencode",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "type": "say",
            "text": "OpenCode terminó la sesión",
            "ttl": 8,
            "priority": 0,
        },
        ensure_ascii=False,
    )
    path.write_text(line + "\n", encoding="utf-8")
    assert tail.poll_once() == 1
    event = bus.since(0)[0]
    assert event["channel"] == "open"
    assert event["agent"] == "opencode"
    assert event["agent_verified"] is False
    assert event["text"] == "OpenCode terminó la sesión"  # verbatim (R3)
    assert event["ttl"] == 8
    view = bus.view(datetime.now(timezone.utc).timestamp())
    assert view.third_party[0]["label"] == "opencode"
