#!/usr/bin/env python3
"""isymotron avatar lienzo -- create a blank 18x28 RGBA canvas PNG."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

for _path in (REPO, REPO / "core"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.isymotron.avatar import blank_canvas


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="isymotron avatar lienzo",
        description="Create blank 18x28 RGBA canvas (like munder avatar lienzo)"
    )
    parser.add_argument("salida", nargs="?", help="Output path (default: ./avatar-lienzo-18x28.png)")
    
    args = parser.parse_args()
    
    from core.isymotron.avatar import blank_canvas
    
    salida = args.salida or "./avatar-lienzo-18x28.png"
    salida = Path(salida).resolve()
    
    if Path(args.salida).exists() if args.salida else False:
        print(f"Error: {args.salida} ya existe", file=sys.stderr)
        return 1
    
    salida.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        from core.isymotron.avatar import blank_canvas
        png_bytes = blank_canvas()
        Path(args.salida or "./avatar-lienzo-18x28.png").write_bytes(png_bytes)
        print(f"✓ Lienzo creado: {Path(args.salida or './avatar-lienzo-18x28.png').resolve()}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())