#!/usr/bin/env python3
"""isymotron session ver -- show current session agents (like munder sesion ver)."""
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


def cmd_session_ver(rest: list[str]) -> int:
    """Show current session agents in a table (like munder 'sesion ver')."""
    if len(sys.argv) > 2:
        print("Usage: isymotron session ver", file=sys.stderr)
        return 2

    session = load_session()
    agents = session.get("agents", [])
    
    if not agents:
        print("No agents in current session.")
        return 0

    # Print table header
    print(f"{'ID':<20} {'NAME':<15} {'PROVIDER':<12} {'ROLE':<15} {'STATUS':<8} {'PID'}")
    print("-" * 85)
    
    for agent in agents:
        status = "vivo" if agent.get("alive", False) else "apagado"
        pid = str(agent.get("pid", "—"))
        print(f"{agent['id']:<20} {agent['name']:<15} {agent.get('provider', '—'):<12} "
              f"{agent.get('role', '—'):<15} {status:<8} {pid}")
    
    print(f"\nTotal: {len(agents)} agents")
    return 0


def main() -> int:
    import sys
    if len(sys.argv) > 1:
        print("Usage: isymotron session ver", file=sys.stderr)
        return 2
    return cmd_session_ver([])


if __name__ == "__main__":
    import sys
    sys.exit(main())