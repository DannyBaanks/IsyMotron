#!/usr/bin/env python3
"""isymotron avatar compilar -- texto en español -> PNG 18x28 (como munder avatar compilar)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

for _path in (REPO, REPO / "core"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.isymotron.avatar import decodePNG, verify_avatar
from core.isymotron.avatar_parser import compile_avatar, parse_avatar_desc

VAL_FLAGS = {"--salida", "--out", "-o"}
SPEC = {"w": 18, "h": 28, "needAlpha": True, "maxBytes": 512 * 1024}


def _base36(n: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
        return "0"
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = digits[r] + out
    return out


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    desc_parts: list[str] = []
    salida: str | None = None
    i = 0
    while i < len(args):
        a = args[i]
        if a in VAL_FLAGS:
            if i + 1 >= len(args):
                print(f"Error: {a} requiere un valor", file=sys.stderr)
                return 1
            salida = args[i + 1]
            i += 2
        elif a.startswith("-"):
            print(f"Error: flag desconocido {a}", file=sys.stderr)
            return 1
        else:
            desc_parts.append(a)
            i += 1
    desc = " ".join(desc_parts)

    if not desc or not desc.strip():
        if sys.stdin.isatty():
            print("sin descripción, cancelado.", file=sys.stderr)
        else:
            print('uso: isymotron avatar compilar "piel morena, pelo negro corto..." [--salida x.png]',
                  file=sys.stderr)
        return 1

    parsed = parse_avatar_desc(desc)
    try:
        compiled = compile_avatar(desc)
    except (ValueError, RuntimeError) as e:
        print(f"no se pudo compilar: {e}", file=sys.stderr)
        return 1

    for w in parsed["warnings"]:
        print(f"  ~ {w}")
    out = Path(salida).expanduser() if salida else Path.cwd() / f"avatar-18x28-{_base36(int(time.time() * 1000))}.png"
    if not out.is_absolute():
        out = Path.cwd() / out
    if out.exists():
        print(f"ya existe {out} (bórralo o pasa --salida).", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(compiled["png"])

    # Verificación M11 sobre lo compilado (debe pasar: el engine pinta alfa real).
    raw = out.read_bytes()
    v = verify_avatar(raw, SPEC)
    d = decodePNG(raw)
    opaque = sum(1 for k in range(3, len(d["rgba"]), 4) if d["rgba"][k] == 255)
    print("  ✓ avatar compilado:")
    print(f"    {out} ({d['w']}x{d['h']}, {opaque} px opacos)")
    r = compiled["recipe"]
    print(f"    receta: piel={r['skin']} pelo={r['hair']} ropa={r['cloth']}")
    if not v["ok"]:
        print(f"  (aviso verify: {v['reason']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
