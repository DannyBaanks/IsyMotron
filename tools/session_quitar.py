#!/usr/bin/env python3
"""isymotron session quitar -- remove an agent from the session (like munder 'sesion quitar')."""
from __future__ import annotations

import sys
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

for _path in (REPO, REPO / "core"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# Simple session file management
SESSION_FILE = Path.home() / ".config" / "isymotron" / "session.json"

def load_session() -> dict:
    """Load session data."""
    if not SESSION_FILE.exists():
        return {"agents": []}
    try:
        return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"agents": []}

def save_session(data: dict) -> None:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="isymotron session quitar",
        description="Remove an agent from the session (like munder 'sesion quitar')"
    )
    parser.add_argument("id", nargs="?", help="Agent ID or PTY ID to remove")
    parser.add_argument("--force", "-f", action="store_true", help="Force removal without confirmation")
    
    args = parser.parse_args()
    
    if not args.id:
        print("Usage: isymotron session quitar <agent_id|pty_id> [--force]", file=sys.stderr)
        return 1
    
    session = load_session()
    agents = session.get("agents", [])
    
    # Try to find agent by ID or PTY ID
    target_id = args.id
    
    # Check if it's a PTY ID (pty-...)
    if args.id.startswith("pty-"):
        # Find agent by PTY ID
        agent = None
        for agent_data in load_session().get("agents", []):
            if agent_data.get("pty_id") == args.id:
                agent = agent_data
                break
        if not agent:
            print(f"Error: no agent found with PTY ID '{args.id}'", file=sys.stderr)
            return 1
        target_id = agent["id"]
    else:
        # Check if it's an agent ID
        agents_list = load_session().get("agents", [])
        agent = next((a for a in agents if a["id"] == args.id), None)
        if not agent:
            print(f"Error: no agent found with ID '{args.id}'", file=sys.stderr)
            return 1
        target_id = args.id
    
    if not args.force:
        confirm = input(f"¿Eliminar agente '{target_id}'? [s/N]: ").strip().lower()
        if confirm not in ("s", "si", "sí", "yes", "y"):
            print("Cancelado.")
            return 0
    
    try:
        session = load_session()
        agents = session.get("agents", [])
        session["agents"] = [a for a in agents if a["id"] != target_id]
        save_session(session)
        print(f"✓ Agente '{args.id}' eliminado")
        return 0
    except Exception as e:
        print(f"Error eliminando agente: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())