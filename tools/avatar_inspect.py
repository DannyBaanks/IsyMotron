#!/usr/bin/env python3
"""isymotron avatar inspect -- matriz textual de un PNG para LLMs.

Toma la RUTA a un .png y la imprime como matriz de letras (una por color
opaco, por frecuencia; '.' = transparente) con leyenda hex. Puro analisis
del archivo de entrada: no hay cast, no hay recetas, no hay nombres.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

for _path in (REPO, REPO / "core"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.isymotron.avatar import decodePNG

# Sin I ni O (se confunden con 1/0).
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="isymotron avatar inspect",
        description="Matriz textual de un PNG para LLMs (una letra por color, '.' transparente)",
    )
    parser.add_argument("png", help="Ruta a un archivo .png")
    args = parser.parse_args(argv)

    p = Path(args.png).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        print(f"no existe: {p}", file=sys.stderr)
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
    # Letras genéricas + hex: el modelo ve estructura, nada más.
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
