"""Cross-process advisory locking for Link state files.

The Link server and the task runner are separate processes. A threading lock
protects one process, but it cannot stop a runner from rewriting an inbox that
grew while it was executing. This module provides one advisory lock per state
file so every reader/append/rewrite uses the same door.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import IO


if sys.platform == "win32":  # pragma: no cover - exercised on the Windows CI host
    import msvcrt

    def _lock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

    def _unlock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class locked:
    """Hold an exclusive advisory lock for ``path``.

    The lock lives in ``<path>.lock``. The state file itself keeps being
    rewritten atomically by callers; the sidecar lock is the rendezvous point.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self._handle: IO[bytes] | None = None

    def __enter__(self) -> None:
        self._handle = open(self.lock_path, "a+b")
        _lock(self._handle)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._handle is not None:
            _unlock(self._handle)
            self._handle.close()
            self._handle = None
