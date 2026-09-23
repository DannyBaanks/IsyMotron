#!/usr/bin/env python3
"""isymotron avatar inspect -- matriz textual de un avatar para LLMs (como munder avatar inspect)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

for _path in (REPO, REPO / "core"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.isymotron.avatar import compose_avatar, decodePNG, AVATAR_RECIPES

# Regiones medidas en portraitArt.ts (NO el sketch ilustrativo: ojos en y=9
# por drawFace, cabeza x=4..13 por HX0/HX1, torso y>=19 por drawClothing).
# Idénticas a AVATAR_REGIONS del munder canónico.
AVATAR_REGIONS = [
    "head    x=4..13 y=2..18",
    "eyes    x=5..6,10..11 y=9",
    "torso   x=4..13 y=19..27",
]

# Sin I ni O (se confunden con 1/0). Idéntico al canónico.
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="isymotron avatar inspect",
        description="Matriz textual de un avatar para LLMs (personaje del cast o ruta .png)",
    )
    parser.add_argument("target", help="Personaje (p. ej. pam) o ruta a un .png")
    args = parser.parse_args(argv)

    target = args.target
    names = list(AVATAR_RECIPES or {})

    if target.lower() in names:
        recipe = AVATAR_RECIPES[target.lower()]
        buf = bytes(compose_avatar(recipe))
        w, h = 18, 28
        title = f"{target} (receta del cast)"
    else:
        p = Path(target).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        if not p.exists():
            known = ", ".join(names) if names else (
                "el cast aún no está portado a IsyMotron (NOT_DEMONSTRATED)"
            )
            print(
                f"ni personaje conocido ni archivo: {target}. Personajes: {known}",
                file=sys.stderr,
            )
            return 1
        try:
            d = decodePNG(p.read_bytes())
        except ValueError as e:
            print(f"{p}: {e}", file=sys.stderr)
            return 1
        buf = bytes(d["rgba"])
        w, h = d["w"], d["h"]
        title = str(p)

    # Leyenda: colores opacos distintos por frecuencia (máx 16), '.' = transparente.
    # Letras genéricas + hex (sin nombres inventados: el modelo ve estructura + regiones).
    freq: dict[str, int] = {}
    for i in range(0, len(buf), 4):
        if buf[i + 3] == 0:
            continue
        k = f"{buf[i]},{buf[i + 1]},{buf[i + 2]}"
        freq[k] = freq.get(k, 0) + 1
    legend: dict[str, str] = {}
    for i, k in enumerate(sorted(freq, key=lambda k: -freq[k])[:16]):
        legend[k] = LETTERS[i] if i < len(LETTERS) else "?"

    def hex_of(k: str) -> str:
        return "#" + "".join(f"{int(n):02x}" for n in k.split(","))

    print(f"CANVAS {w}x{h}  ({title})")
    print()
    for y in range(h):
        row = []
        for x in range(w):
            o = (y * w + x) * 4
            if buf[o + 3] == 0:
                row.append(".")
                continue
            row.append(legend.get(f"{buf[o]},{buf[o + 1]},{buf[o + 2]}", "?"))
        print(f"{y:02d} " + "".join(row))
    print()
    for k, L in legend.items():
        print(f"{L} = {hex_of(k)}")
    print()
    for r in AVATAR_REGIONS:
        print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
