"""A real IsyMotron Link server for the phone's live test (mobile/tests/live.test.ts).

Starts core/isymotron/link's LinkServer on an ephemeral port with a throwaway state dir,
prints {"port": N} and then answers line commands on stdin, standing in for the human at
the PC:  accept <code>  |  inbox  |  receipts  |  quit
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "core"))

from isymotron.link import pairing  # noqa: E402
from isymotron.link.server import LinkServer  # noqa: E402


def main() -> None:
    state = Path(tempfile.mkdtemp(prefix="isy-link-pc-"))
    server = LinkServer(state, tcp_port=0, udp_port=0).start()
    print(json.dumps({"port": server.http.server_address[1]}), flush=True)
    for line in sys.stdin:
        cmd, _, arg = line.strip().partition(" ")
        if cmd == "accept":
            peer = pairing.accept(arg, state)
            print(json.dumps({"accepted": bool(peer), "peer": peer}), flush=True)
        elif cmd == "inbox":
            print(json.dumps({"inbox": server.state.inbox()}), flush=True)
        elif cmd == "receipts":
            path = state / "receipts.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
            print(json.dumps({"receipts": [json.loads(x) for x in lines]}), flush=True)
        elif cmd == "quit":
            break
    server.stop()


if __name__ == "__main__":
    main()
