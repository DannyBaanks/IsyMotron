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
from urllib.request import Request, urlopen

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "core"))
sys.path.insert(0, os.path.join(ROOT, "hosts"))

from isymotron.link import pairing  # noqa: E402
from isymotron.link.server import LinkServer  # noqa: E402
from simulator.engines import ModernHost  # noqa: E402


def main() -> None:
    state = Path(tempfile.mkdtemp(prefix="isy-link-pc-"))
    host = ModernHost(
        {}, granted=["filesystem.read"],
        grant_scopes={"filesystem.read": {"roots": ["/srv/photos"]}},
    )
    server = LinkServer(state, tcp_port=0, udp_port=0, permission_host=host).start()
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
        elif cmd == "request-permission":
            url = f"http://{server.tcp_address}/link/v1/local/permissions"
            data = json.dumps({
                "subject": "agent:local",
                "capability": "filesystem.read",
                "scope": {"roots": ["/srv/photos"]},
                "ttl_s": 120,
                "reason": "Read the requested photo",
            }).encode("utf-8")
            request = Request(url, data=data, headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=10) as response:
                print(response.read().decode("utf-8"), flush=True)
        elif cmd == "permission-status":
            url = f"http://{server.tcp_address}/link/v1/local/permissions/{arg}"
            with urlopen(url, timeout=10) as response:
                print(response.read().decode("utf-8"), flush=True)
        elif cmd == "quit":
            break
    server.stop()


if __name__ == "__main__":
    main()
