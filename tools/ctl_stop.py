#!/usr/bin/env python3
"""isymotron ctl stop -- stop the control channel / app."""
from __future__ import annotations

import sys
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

for _path in (REPO, REPO / "core"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


def _call(method: str, url: str, token: str, timeout: float, body=None):
    """(status, text) over stdlib urllib -- the runtime has no third-party deps."""
    import urllib.error
    import urllib.request
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="isymotron ctl stop",
        description="Stop the control channel / app"
    )
    parser.add_argument("--force", action="store_true", help="Force kill")
    
    args = parser.parse_args()
    
    import os, json
    user_data = os.path.expanduser("~/.config/isymotron")
    cfg_path = os.path.join(user_data, "isymotron-control.json")
    
    if not os.path.exists(cfg_path):
        print("No hay canal de control activo", file=sys.stderr)
        return 1
    
    with open(cfg_path) as f:
        cfg = json.load(cfg_path)
    
    try:
        status, text = _call("POST", f"http://127.0.0.1:{cfg['port']}/shutdown",
                             cfg['token'], 5, {"force": args.force})
        if status == 200:
            print("Apagado solicitado")
            return 0
        else:
            print(f"Error: {status} - {text}")
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())