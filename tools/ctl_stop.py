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
    
    import requests
    try:
        resp = requests.post(
            f"http://127.0.0.1:{cfg['port']}/shutdown",
            headers={"Authorization": f"Bearer {cfg['token']}"},
            json={"force": args.force},
            timeout=5
        )
        if resp.status_code == 200:
            print("Apagado solicitado")
            return 0
        else:
            print(f"Error: {resp.status_code} - {resp.text}")
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())