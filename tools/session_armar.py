#!/usr/bin/env python3
"""isymotron session armar -- create a new agent in the session (like munder sesion armar)."""
from __future__ import annotations

import sys
import os
import json
import uuid
from datetime import datetime
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
        prog="isymotron session armar",
        description="Create a new agent in the session (like munder 'sesion armar')"
    )
    parser.add_argument("--nombre", "-n", help="Agent name (e.g., jim)")
    parser.add_argument("--comando", "-c", help="Command to run (e.g., 'claude --model opus')")
    parser.add_argument("--cwd", "-d", help="Working directory (default: ~/Development)")
    parser.add_argument("--proveedor", "-p", help="Provider: claude, codex, gemini, opencode, antigravity, qwen, cursor, pi, copilot")
    parser.add_argument("--rol", "-r", help="Role: developer, researcher, assistant, etc.")
    parser.add_argument("--interactivo", "-i", action="store_true", help="Interactive mode (prompt for missing)")
    
    args = parser.parse_args()
    
    # If no args and not interactive, show help
    if len(sys.argv) == 1 and not args.interactivo:
        print("Usage: isymotron session armar [--nombre NOMBRE] [--comando CMD] [--cwd DIR] [--proveedor PROV] [--rol ROL] [--interactivo]")
        return 1
    
    nombre = args.nombre
    comando = args.comando
    cwd = args.cwd or os.path.expanduser("~/Development")
    proveedor = args.proveedor or "claude"
    rol = args.rol or "assistant"
    
    if args.interactivo:
        # Interactive mode - prompt for missing values
        if not args.nombre:
            nombre = input("  Nombre del agente (ej. jim): ").strip()
        if not args.comando:
            comando = input("  Comando (ej. claude --model opus): ").strip()
        if not args.cwd:
            cwd_input = input(f"  Carpeta de trabajo [{os.path.expanduser('~/Development')}: ").strip()
            if cwd_input:
                cwd = cwd_input
        if not args.proveedor:
            proveedor = input("  Proveedor [claude/codex/gemini/opencode/antigravity/qwen/cursor/pi/copilot]: ").strip() or "claude"
        if not args.rol:
            rol = input("  Rol [developer/researcher/assistant]: ").strip() or "assistant"
    
    if not nombre or not comando:
        print("Error: nombre y comando son requeridos", file=sys.stderr)
        return 1
    
    # Expand ~ in cwd
    cwd = os.path.expanduser(cwd)
    if not os.path.exists(cwd):
        print(f"Error: carpeta no existe: {cwd}", file=sys.stderr)
        return 1
    
    # Create agent
    session = load_session()
    agent_id = f"{nombre.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}"
    agent = {
        "id": agent_id,
        "name": nombre,
        "command": comando,
        "cwd": cwd,
        "provider": proveedor,
        "role": rol,
        "alive": False,
        "pid": None,
        "created": datetime.now().isoformat(),
    }
    
    session["agents"].append(agent)
    save_session(session)
    
    print(f"✓ Agente '{nombre}' creado con ID: {agent_id}")
    print(f"  Proveedor: {proveedor}")
    print(f"  Rol: {rol}")
    print(f"  Directorio: {cwd}")
    print(f"  Comando: {comando}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())