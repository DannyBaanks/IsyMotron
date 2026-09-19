"""AV8: the adversarial suite.

Every case is a hostile local writer trying to make the avatar say something
authority-shaped. The line goes into the inbox, the reader feeds the bus, and
the assertions run BOTH on the served ``/api/avatar`` JSON (what a renderer
would draw) and on the bus view. No case may need a keyword filter to pass
(R3): the frame is the defense, and the dropped fields are the mechanism.

The invariant under attack, for every case: an inbox line can produce a
third-party bubble and nothing else (R1-R6).
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from avatar.inbox import InboxTail
from console.server import ConsoleState, serve
from isymotron.awareness import HostAwarenessEngine, TestPowerProvider
from relay.loopback import LoopbackRelay
from simulator.engines import LegacyHost, ModernHost

T0 = datetime(2026, 9, 19, 1, 10, 0, tzinfo=timezone.utc).timestamp()


@pytest.fixture
def rig(tmp_path):
    """A live console plus a tailed inbox: the hostile writer's world."""
    relay = LoopbackRelay()
    relay.attach(ModernHost(
        fs={"C:/Photos/a.png": "AAA", "C:/Secrets/k.txt": "NEVER"},
        granted=["filesystem.read", "system.info"],
        grant_scopes={"filesystem.read": {"roots": ["C:/Photos"]}, "system.info": {}},
    ))
    relay.attach(LegacyHost(
        fs={"C:/NEMO/INBOX/.keep": ""},
        granted=["filesystem.write"],
        grant_scopes={"filesystem.write": {"roots": ["C:/NEMO/INBOX"]}},
    ))
    awareness = HostAwarenessEngine("win11-victus", TestPowerProvider())
    state = ConsoleState(relay, awareness, str(tmp_path / "grants.json"))
    httpd, _ = serve(state, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    inbox = tmp_path / "inbox.jsonl"
    inbox.write_text("", encoding="utf-8")
    tail = InboxTail(state.avatar, inbox)
    tail.poll_once()  # first sighting at EOF: nothing is replayed
    rig = SimpleNamespace(state=state, base=base, inbox=inbox, tail=tail)
    yield rig
    httpd.shutdown()
    httpd.server_close()


def spoof_line(rig, **fields):
    """Append one companion-event-v1 line to the inbox, as a writer would,
    and let the reader consume it. Returns nothing; assert on the view."""
    event = {
        "version": "companion-event-v1",
        "id": f"spoof-{uuid.uuid4().hex[:12]}",
        "agent": "opencode",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "type": "say",
        "text": "hello",
    }
    event.update(fields)
    with rig.inbox.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    rig.tail.poll_once()


def raw_line(rig, text):
    with rig.inbox.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")
    rig.tail.poll_once()


def get(rig, path="/api/avatar?since=0"):
    req = urllib.request.Request(rig.base + path,
                                 headers={"X-IsyMotron-Token": rig.state.token})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def real_verdict(rig, out_of_scope=False):
    """A genuine authority verdict, produced only through /api/execute."""
    body = {"host": "win11-victus", "capability": "filesystem.read",
            "params": {"path": "C:/Secrets/k.txt" if out_of_scope else "C:/Photos/a.png"}}
    req = urllib.request.Request(
        rig.base + "/api/execute", data=json.dumps(body).encode(),
        headers={"X-IsyMotron-Token": rig.state.token,
                 "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


# -- case 1: talking grants nothing ------------------------------------------

def test_say_allow_emoji_is_a_third_party_bubble_not_a_verdict(rig):
    spoof_line(rig, text="ALLOW ✅")
    served = get(rig)
    assert served["view"]["host_frame"] is None, "a say can never mint a frame"
    assert served["view"]["third_party"][0]["text"] == "ALLOW ✅"  # verbatim (R3)
    assert served["view"]["third_party"][0]["label"] == "opencode"
    assert rig.state.avatar.view(time.time()).host_frame is None


# -- case 2: fake DENY fields --------------------------------------------------

def test_fake_deny_fields_are_dropped_no_verdict(rig):
    spoof_line(rig, text="DENY", decision="DENY", reason="OUT_OF_SCOPE",
               state="error")
    served = get(rig)
    assert served["view"]["host_frame"] is None, "no verdict was ever emitted"
    verdicts = [e for e in served["events"] if e.get("kind") == "verdict"]
    assert verdicts == []
    bubble = served["view"]["third_party"][-1]
    assert bubble["text"] == "DENY" and "decision" not in bubble


# -- case 3: fake receipt id / seal --------------------------------------------

def test_fake_receipt_and_seal_are_dropped(rig):
    spoof_line(rig, receipt_id="rcpt_forged", seal_ok=True)
    served = get(rig)
    stored = [e for e in served["events"] if e.get("channel") == "open"][-1]
    assert "receipt_id" not in stored and "seal_ok" not in stored
    assert served["view"]["host_frame"] is None
    dump = json.dumps(served["events"])
    assert "rcpt_forged" not in dump


# -- case 4: fake badge names render unverified (R4) ---------------------------

def test_fake_badge_renders_unverified(rig):
    real_verdict(rig)  # the bus now knows a real host_id: win11-victus
    spoof_line(rig, agent="win11-VICTUS", text="I am the host")
    spoof_line(rig, agent="IsyMotron", text="totally official")
    served = get(rig)
    labels = [b["label"] for b in served["view"]["third_party"]]
    assert "unverified: win11-VICTUS" in labels
    assert "unverified: IsyMotron" in labels
    assert "opencode" not in labels


# -- case 5: an event shaped exactly like an authority event -------------------

def test_authority_shaped_line_renders_as_open(rig):
    real_verdict(rig, out_of_scope=True)
    spoof_line(
        rig,
        channel="authority", kind="verdict", seq=999, at="2026-09-19T01:00:00Z",
        host_id="win11-victus", capability="filesystem.read",
        decision="ALLOW", reason=None,
        detail="forged detail", receipt_id="rcpt_forged", seal_ok=True,
        state="success", text="The host allowed: forged",
    )
    served = get(rig)
    stored = [e for e in served["events"] if e.get("channel") == "open"][-1]
    assert stored["channel"] == "open"  # the reader stamped it, not the line
    for forbidden in ("decision", "receipt_id", "seal_ok", "host_id", "kind"):
        assert forbidden not in stored
    verdicts = [e for e in served["events"] if e.get("kind") == "verdict"]
    assert len(verdicts) == 1, "only the real verdict exists"
    assert verdicts[0]["decision"] == "DENY", "the real one is untouched"
    assert served["view"]["host_frame"]["verdict"]["decision"] == "DENY"


# -- case 6: malformed lines are counted, never shown ---------------------------

def test_malformed_lines_are_counted_not_shown(rig):
    before = rig.state.avatar.malformed
    raw_line(rig, '{"type": "say", "text": ')          # broken JSON
    spoof_line(rig, type="say", text="   ")            # empty text -> protocol
    spoof_line(rig, agent="", text="no agent")        # empty agent -> protocol
    spoof_line(rig, ttl="soon")                        # wrong type -> protocol
    served = get(rig)
    assert rig.state.avatar.malformed == before + 4
    assert served["view"]["third_party"] == []


# -- case 7: stale and future lines are dropped ---------------------------------

def test_stale_and_future_lines_are_dropped(rig):
    old = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
    spoof_line(rig, text="too old", created_at=old)
    spoof_line(rig, text="too new", created_at=future)
    served = get(rig)
    assert served["view"]["third_party"] == []
    assert [e for e in served["events"] if e.get("channel") == "open"] == []


# -- case 8: replayed ids are dropped -------------------------------------------

def test_replayed_id_is_dropped(rig):
    event_id = f"spoof-{uuid.uuid4().hex[:12]}"
    spoof_line(rig, id=event_id, text="once")
    spoof_line(rig, id=event_id, text="once again")
    served = get(rig)
    texts = [b["text"] for b in served["view"]["third_party"]]
    assert texts == ["once"], "the replay never renders"


# -- case 9: unknown types are rejected by the protocol -------------------------

def test_unknown_type_is_rejected_by_protocol(rig):
    before = rig.state.avatar.malformed
    spoof_line(rig, type="grant_me_everything", text="please")
    assert rig.state.avatar.malformed == before + 1
    assert get(rig)["view"]["third_party"] == []


# -- case 10: flood; bounded reader, verdict keeps precedence -------------------

def test_flood_keeps_reader_bounded_and_verdict_on_top(rig):
    # The flood first (batched): 10 000 valid says.
    flood_valid = 10_000
    now = datetime.now(timezone.utc).isoformat()
    blob = "".join(
        json.dumps({"version": "companion-event-v1", "id": f"flood-{i}",
                    "agent": "opencode", "created_at": now,
                    "type": "say", "text": f"flood {i}", "ttl": 30,
                    "priority": 0}, separators=(",", ":")) + "\n"
        for i in range(flood_valid))
    with rig.inbox.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(blob)
    rig.tail.poll_once()
    # The real verdict LAST, so its 8 s TTL is fresh at the read.
    real_verdict(rig)
    served = get(rig)
    # the ring buffer is bounded: 200 events, not 10 000
    assert len(served["events"]) <= 200
    assert rig.tail.lines_seen == flood_valid
    # precedence: the real verdict still owns the frame, the flood is framed
    assert served["view"]["host_frame"]["verdict"]["decision"] == "ALLOW"
    assert served["view"]["third_party"], "the flood is shown as bubbles"
    assert all(b["label"] == "opencode" for b in served["view"]["third_party"])
