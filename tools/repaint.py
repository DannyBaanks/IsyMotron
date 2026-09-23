#!/usr/bin/env python3
"""isymotron repaint -- request UI repaint without restart (like munder repaint)."""
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
        prog="isymotron repaint",
        description="Request UI repaint without restart (like munder repaint)"
    )
    parser.add_argument("--all", action="store_true", help="Broadcast to all windows")
    
    args = parser.parse_args()
    
    # Broadcast ui:repaint via control channel
    try:
        import asyncio
        from core.isymotron.control import broadcast_repaint
        
        async def main():
            try:
                count = await broadcast_repaint()
                print(f"Repaint enviado a {count} ventana(s)")
                return 0
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                return 1
        
        import asyncio
        return asyncio.run(main())
    
    except ImportError:
        # Fallback: use CLI control channel
        import requests
        try:
            user_data = os.path.expanduser("~/.config/isymotron")
            cfg_path = os.path.join(user_data, "isymotron-control.json")
            if not os.path.exists(cfg_path):
                print("No hay canal de control activo (¿app corriendo?)", file=sys.stderr)
                return 1
            
            with open(cfg_path) as f:
                cfg = json.load(cfg)
            
            import requests
            resp = requests.post(
                f"http://127.0.0.1:{cfg['port']}/repaint",
                headers={"Authorization": f"Bearer {cfg['token']}"},
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                print(f"Repintado pedido a {data.get('windows', 0)} ventana(s)")
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