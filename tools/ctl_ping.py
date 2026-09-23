#!/usr/bin/env python3
"""isymotron ctl ping -- test control channel connectivity."""
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
        prog="isymotron ctl ping",
        description="Test control channel connectivity"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    
    args = parser.parse_args()
    
    # Find control channel config
    user_data = os.path.expanduser("~/.config/isymotron")
    cfg_path = os.path.join(user_data, "isymotron-control.json")
    
    if not os.path.exists(cfg_path):
        print("No hay canal de control activo (¿app corriendo?)", file=sys.stderr)
        return 1
    
    with open(cfg_path) as f:
        cfg = json.load(f)
    
    import requests
    try:
        resp = requests.post(
            f"http://127.0.0.1:{cfg['port']}/ping",
            headers={"Authorization": f"Bearer {cfg['token']}"},
            timeout=3
        )
        if resp.status_code == 200:
            data = resp.json()
            if args.json:
                import json
                print(json.dumps({"ok": True, "port": cfg['port'], "data": data}))
            else:
                print(f"munder: pong (canal en puerto {cfg['port']})")
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