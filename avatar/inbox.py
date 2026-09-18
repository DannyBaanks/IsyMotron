"""The open channel: an inbox reader for companion-event-v1 lines.

Existing Companion producers keep working unchanged: they append JSON lines
to an inbox file (see C:\\Development\\ISyCo Git\\Companion\\integrations\\*.ts);
IsyMotron tails that file and feeds every line to ``AvatarBus.publish_open``,
which stamps it ``channel="open"`` (R1). The reader is a bounded poller, not
a watcher: it never re-reads the whole file — each poll costs O(new bytes),
never O(file size) — and no watcher libraries are used.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Callable
import os

from avatar.model import AvatarBus

POLL_INTERVAL = 0.25  # seconds; polled from the console process (daemon thread)


def resolve_inbox_path(environ: Mapping[str, str] | None = None) -> Path:
    """Inbox path precedence (AV2).

    1. ``$ISYMOTRON_AVATAR_INBOX`` — one env var is enough to point the
       OpenCode/OpenISy plugins at IsyMotron;
    2. ``$COMPANION_ROOT/inbox.jsonl`` — the Companion plugins' default file;
    3. ``%LOCALAPPDATA%\\IsyMotron\\avatar\\inbox.jsonl`` — standalone default.
    """
    env = os.environ if environ is None else environ
    explicit = env.get("ISYMOTRON_AVATAR_INBOX")
    if explicit:
        return Path(explicit)
    companion_root = env.get("COMPANION_ROOT")
    if companion_root:
        return Path(companion_root) / "inbox.jsonl"
    local = env.get("LOCALAPPDATA") or ""
    return Path(local) / "IsyMotron" / "avatar" / "inbox.jsonl"


class InboxTail:
    """Tail-follow one inbox file by byte offset.

    Starts at end of file — backlog present at startup is never replayed
    (contract §1) — reads only complete lines (a final line without a
    newline waits, same rule as Companion's ``read_jsonl``), survives
    truncation/rotation (``size < offset`` resets to 0), and never raises
    for per-line problems: malformed lines are counted, never shown, and
    never stop the reader (contract §5).
    """

    def __init__(
        self,
        bus: AvatarBus,
        path: Path | str,
        *,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self.bus = bus
        self.path = Path(path)
        self.offset: int | None = None  # None until the file is first seen
        self.now_fn = now_fn or time.time
        self.lines_seen = 0  # complete lines read (accepted or dropped)

    def poll_once(self) -> int:
        """Read every new complete line once; return how many were accepted."""
        try:
            size = self.path.stat().st_size
        except OSError:
            self.offset = None  # no file yet: wait for it to appear
            return 0
        if self.offset is None:
            self.offset = size  # start at end of file
            return 0
        if size < self.offset:
            self.offset = 0  # truncation / rotation: follow the new file
        if size == self.offset:
            return 0
        with self.path.open("rb") as stream:
            stream.seek(self.offset)
            chunk = stream.read()
        cut = chunk.rfind(b"\n")
        if cut == -1:
            return 0  # only a partial line so far: wait for its newline
        complete = chunk[: cut + 1]
        self.offset += len(complete)
        accepted = 0
        for raw_line in complete.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            self.lines_seen += 1
            try:
                raw = json.loads(line)
            except ValueError:  # includes UnicodeDecodeError
                self.bus.malformed += 1
                continue
            if self.bus.publish_open(raw, self.now_fn()) is not None:
                accepted += 1
        return accepted


def spawn_poller(tail: InboxTail, interval: float = POLL_INTERVAL) -> threading.Thread:
    """Run ``tail.poll_once`` on a daemon thread, every ``interval`` seconds.

    The console process (AV3) starts this; nothing here touches the
    authority channel — an inbox line can only ever reach
    ``publish_open`` (failure condition of AV2).
    """

    def loop() -> None:
        while True:
            try:
                tail.poll_once()
            except Exception:  # noqa: BLE001 — the reader never dies; next poll retries
                pass
            time.sleep(interval)

    thread = threading.Thread(target=loop, name="avatar-inbox", daemon=True)
    thread.start()
    return thread
