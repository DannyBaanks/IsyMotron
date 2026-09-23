#!/usr/bin/env python3
"""isymotron avatar primitives -- generic pixel helpers + real PNG codec + M11 verify.

Scope is deliberately narrow: blank canvases, PNG encode/decode, avatar-spec
verification, and the neutral pixel primitives the CLI surface needs. There is
NO cast, NO renderer, NO character recipes here: IsyMotron is not Munder.

Provenance note (do not re-introduce): commits d4cd44e/454164a once carried a
port of Munder's Office portrait engine (draw_*, 15 cast recipes, text->recipe
parser) in this module. It was removed by COMPOSE repair: that engine belongs
to Munder, and a byte-exact clone inside IsyMotron was an architectural
mistake no matter how well it tested. If IsyMotron ever needs its own
renderer, it must be generic (entity/model/spec -> representation) with its
own spec -- never a re-port of Munder's cast.
"""

from __future__ import annotations

import math

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow is installed in this repo
    Image = None

# ─── canvas format ────────────────────────────────────────────────────────
# 18x28 RGBA is the CLI surface's canvas format (lienzo/inspect/editar).

W = 18
H = 28
AVATAR_W = W
AVATAR_H = H
PORTRAIT_W = W
PORTRAIT_H = H

AVATAR_MAX_BYTES = 512 * 1024


# ─── neutral pixel primitives ─────────────────────────────────────────────

def clamp(v: float) -> int:
    """Clamp to a byte with half-up rounding."""
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(math.floor(v + 0.5))


def shades(rgb, dl: float = 1.22, dd: float = 0.68):
    """[hi, base, sh] variants of a color."""
    r, g, b = rgb[0], rgb[1], rgb[2]
    return (
        [clamp(r * dl), clamp(g * dl), clamp(b * dl)],
        [r, g, b],
        [clamp(r * dd), clamp(g * dd), clamp(b * dd)],
    )


def setpx(buf: list[int], x: int, y: int, c, a: int = 255) -> None:
    if x < 0 or x >= W or y < 0 or y >= H:
        return
    i = (y * W + x) * 4
    buf[i] = c[0]
    buf[i + 1] = c[1]
    buf[i + 2] = c[2]
    buf[i + 3] = a


set = setpx


def alpha_at(buf: list[int], x: int, y: int) -> int:
    if x < 0 or x >= W or y < 0 or y >= H:
        return 0
    return buf[(y * W + x) * 4 + 3]


def rgb_at(buf: list[int], x: int, y: int):
    i = (y * W + x) * 4
    return [buf[i], buf[i + 1], buf[i + 2]]


def eq(a, b) -> bool:
    return a[0] == b[0] and a[1] == b[1] and a[2] == b[2]


def rect(buf: list[int], x0: int, y0: int, x1: int, y1: int, c) -> None:
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            set(buf, x, y, c)


def blank_buffer(w: int = W, h: int = H) -> list[int]:
    """Transparent RGBA buffer (flat list, w*h*4)."""
    return [0] * (w * h * 4)


# ─── PNG codec (Pillow; fail-closed without it) ───────────────────────────

def _require_pil():
    """Pillow, or a fail-closed RuntimeError (never silently fake a PNG)."""
    if Image is None:
        raise RuntimeError(
            "Pillow no instalado: el lienzo y la inspección trabajan sobre PNG "
            "reales ('pip install pillow'). Nada se genera a ciegas."
        )
    return Image


def blank_canvas(w: int = W, h: int = H) -> bytes:
    """Blank transparent canvas, encoded as a real 8-bit RGBA PNG."""
    import io
    pil = _require_pil()
    img = pil.new("RGBA", (w, h), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def encode_png(w: int, h: int, rgba) -> bytes:
    """Encode a flat RGBA sequence (w*h*4) as an 8-bit RGBA PNG."""
    import io
    pil = _require_pil()
    raw = bytes(rgba)
    if len(raw) != w * h * 4:
        raise ValueError(f"buffer inesperado: {len(raw)} bytes para {w}x{h}")
    img = pil.frombytes("RGBA", (w, h), raw)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def decodePNG(buf: bytes) -> dict:
    """Decode PNG bytes to {"w","h","rgba"} (flat RGBA list).

    Fail-closed: anything that is not a decodable PNG raises ValueError
    with a reason. Never invents pixels.
    """
    import io
    pil = _require_pil()
    if not isinstance(buf, (bytes, bytearray)):
        raise ValueError("PNG inválido: se esperaban bytes")
    if len(buf) < 8 or bytes(buf[:8]) != b"\x89PNG\r\n\x1a\n":
        raise ValueError("PNG inválido: firma")
    try:
        with pil.open(io.BytesIO(bytes(buf))) as img:
            img = img.convert("RGBA")
            w, h = img.size
            if not w or not h or w > 4096 or h > 4096:
                raise ValueError(f"PNG inválido: dimensiones absurdas {w}x{h}")
            return {"w": w, "h": h, "rgba": list(img.tobytes())}
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"PNG inválido: no decodifica ({e})")


def verify_avatar(buf: bytes, spec: dict) -> dict:
    """Verify a PNG buffer against an avatar spec ({w,h,needAlpha,maxBytes}).

    Returns {"ok": True, "info": ...} or {"ok": False, "reason": ...}.
    Never normalizes silently: what does not comply is rejected with a reason.
    """
    fail = lambda reason: {"ok": False, "reason": reason}  # noqa: E731
    try:
        img = decodePNG(buf)
    except ValueError as e:
        return fail(f"no decodifica: {e}")
    if img["w"] != spec["w"] or img["h"] != spec["h"]:
        return fail(
            f"dimensiones {img['w']}x{img['h']}, se requieren {spec['w']}x{spec['h']} "
            "exactos (sin reescalado: destruiría el pixel-art)"
        )
    if spec.get("maxBytes") and len(buf) > spec["maxBytes"]:
        return fail(f"pesa {len(buf)} bytes (tope {spec['maxBytes']})")
    if spec.get("needAlpha"):
        opaque = transparent = 0
        rgba = img["rgba"]
        for i in range(3, len(rgba), 4):
            if rgba[i] == 0:
                transparent += 1
            elif rgba[i] == 255:
                opaque += 1
        if transparent == 0:
            return fail("sin canal alpha real (todo opaco: sin transparencia)")
        if opaque == 0:
            return fail("totalmente transparente (lienzo vacío)")
    return {"ok": True, "info": {"w": img["w"], "h": img["h"], "bytes": len(buf)}}
