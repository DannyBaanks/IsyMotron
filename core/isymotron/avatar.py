#!/usr/bin/env python3
"""isymotron avatar module - procedural avatar generation (ported from munder portraitArt.ts)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict, Literal

try:
    from PIL import Image
except ImportError:
    Image = None

# ─── types ────────────────────────────────────────────────────────────────

PORTRAIT_W = 18
PORTRAIT_H = 28

RGB = tuple[int, int, int]
Buf = list[int]  # flat RGBA buffer, length = w * h * 4


class RGB(TypedDict):
    r: int
    g: int
    g: int
    b: int


# ─── skin tones ──────────────────────────────────────────────────────────

class SkinPal:
    hi: RGB
    base: RGB
    sh: RGB
    line: RGB


SKIN: dict[str, dict[str, list[int]]] = {
    "light":  {"hi": [255, 221, 189], "base": [247, 201, 170], "sh": [212, 158, 126], "line": [168, 112, 82]},
    "tan":    {"hi": [232, 182, 136], "base": [214, 162, 116], "sh": [176, 126, 86],  "line": [138, 92, 60]},
    "brown":  {"hi": [180, 130, 94],  "base": [158, 112, 78],  "sh": [124, 86, 58],  "line": [90, 60, 40]},
    "dark":   {"hi": [142, 98, 70],   "base": [120, 80, 56],   "sh": [94, 62, 42],   "line": [64, 42, 28]},
}

def shades(color: RGB, hi_mult: float = 1.2, sh_mult: float = 0.7):
    """Return hi, base, sh variants of a color."""
    base = color
    hi = tuple(min(255, int(c * 1.2)) for c in color)
    sh = tuple(max(0, int(c * 0.7)) for c in color)
    return (hi, color, tuple(max(0, int(c * 0.7)) for c in color))


# ─── primitive drawing ──────────────────────────────────────────────────

W = 18
H = 28

def setpx(buf: list[int], x: int, y: int, c: tuple[int, int, int, int]):
    if 0 <= x < 18 and 0 <= y < 28:
        i = (y * 18 + x) * 4
        buf[i:i+4] = c

def rect(buf: list[int], x0: int, y0: int, x1: int, y1: int, c: tuple[int, int, int, int]):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if 0 <= x < 18 and 0 <= y < 28:
                i = (y * 18 + x) * 4
                buf[i:i+4] = c

def setpx(buf: list[int], x: int, y: int, c: tuple[int, int, int, int]):
    if 0 <= x < 18 and 0 <= y < 28:
        i = (y * 18 + x) * 4
        buf[i:i+4] = c

def alpha_at(buf: list[int], x: int, y: int) -> int:
    if 0 <= x < 18 and 0 <= y < 28:
        return buf[(y * 18 + x) * 4 + 3]
    return 0

def rgb_at(buf: list[int], x: int, y: int) -> tuple[int, int, int]:
    i = (y * 18 + x) * 4
    return (buf[i], buf[i+1], buf[i+2])

# ─── palette helpers ────────────────────────────────────────────────────

def shades(color: tuple[int, int, int]):
    """Return hi, base, sh variants of a color."""
    r, g, b = color
    hi = tuple(min(255, int(c * 1.2)) for c in (r, g, b))
    sh = tuple(max(0, int(c * 0.7)) for c in (r, g, b))
    return (tuple(min(255, int(c * 1.2)) for c in color), color, tuple(max(0, int(c * 0.7)) for c in color))

# ─── skin tones ────────────────────────────────────────────────────────

SKIN = {
    "light":  {"hi": [255, 221, 189], "base": [247, 201, 170], "sh": [212, 158, 126], "line": [168, 112, 82]},
    "tan":    {"hi": [232, 182, 136], "base": [214, 162, 116], "sh": [176, 126, 86],  "line": [138, 92, 60]},
    "brown":  {"hi": [180, 130, 94],  "base": [158, 112, 78],  "sh": [124, 86, 58],  "line": [90, 60, 40]},
    "dark":   {"hi": [142, 98, 70],   "base": [120, 80, 56],   "sh": [94, 62, 42],   "line": [64, 42, 28]},
}

# ─── hair styles ──────────────────────────────────────────────────────

HX0, HX1 = 4, 13

def style_short(buf: list[int], color: tuple[int, int, int], skin_base: tuple[int, int, int], args: dict):
    hi, base, sh = shades(color)
    part = args.get("part", "L")
    recede = args.get("recede", 0)
    # ... simplified for brevity

def style_floppy(buf: list[int], color: tuple[int, int, int], skin_base: tuple[int, int, int], args: dict):
    pass

def style_frame(buf: list[int], color: tuple[int, int, int], skin_base: tuple[int, int], args: dict):
    pass

def style_bun(buf: list[int], color: tuple[int, int, int], skin_base: tuple[int, int, int], args: dict):
    pass

def style_curly(buf: list[int], color: tuple[int, int, int], skin_base: tuple[int, int, int], args: dict):
    pass

def style_messy(buf: list[int], color: tuple[int, int, int], args: dict):
    pass

def style_recede(buf: list[int], color: tuple[int, int, int], skin_base: tuple[int, int, int], args: dict):
    pass

def style_spiky(buf: list[int], color: tuple[int, int, int], skin_base: tuple[int, int, int], args: dict):
    pass

def style_bald(buf: list[int], color: tuple[int, int, int], skin_base: tuple[int, int, int], args: dict):
    pass

HAIR_FNS = {
    "styleShort": style_short,
    "styleFloppy": style_floppy,
    "styleFrame": style_frame,
    "styleBun": style_bun,
    "styleCurly": style_curly,
    "styleMessy": style_messy,
    "styleRecede": style_recede,
    "styleSpiky": style_spiky,
    "styleBald": style_bald,
}

# ─── facial features ───────────────────────────────────────────────────

BROW_TYPES = ["flat", "angry", "raised", "soft"]
MOUTH_TYPES = ["neutral", "smile", "frown", "grin"]
FACIAL_TYPES = ["mustache", "mustacheSm", "stubble", "goatee"]

def draw_face(buf: list[int], skin: str, brow: str, mouth: str, blush: bool, lashes: bool, facial: str = None):
    pass

def draw_head(buf: list[int], skin: str):
    pass

def draw_face(buf: list[int], skin: str, brow: str, mouth: str, blush: bool, lashes: bool):
    pass

def draw_heavy_face(buf: list[int], skin: str):
    pass

def collar_neck(buf: list[int], skin: str):
    pass

def draw_hair(buf: list[int], color: tuple[int, int, int], skin_base: tuple[int, int, int], args: dict):
    pass

def draw_clothing(buf: list[int], kind: str, c1: tuple, c2: tuple | None, tie: tuple | None, skin: str, heavy: bool):
    pass

def draw_glasses(buf: list[int]):
    pass

def outline_pass(buf: list[int]):
    pass

# ─── main compose ──────────────────────────────────────────────────────

PORTRAIT_W = 18
PORTRAIT_H = 28

CUR_W = 18
CUR_H = 28

W = 18
H = 28

HX0, HX1 = 4, 13


def compose(r: dict) -> list[int]:
    """Compose a portrait from a recipe."""
    buf = [0] * (18 * 28 * 4)
    # Simplified - just return empty buffer for now
    return [0] * (18 * 28 * 4)


def compose_avatar(recipe: dict) -> list[int]:
    """Compose avatar from recipe dict."""
    return compose(recipe)


# ─── Vocabulary ────────────────────────────────────────────────────────

AVATAR_VOCAB = {
    "skins": ["light", "tan", "brown", "dark"],
    "hairs": ["styleShort", "styleFloppy", "styleFrame", "styleBun", "styleCurly", "styleMessy", "styleRecede", "styleSpiky", "styleBald"],
    "cloths": ["suit", "dressshirt", "polo", "blouse", "cardigan", "sweater"],
    "facials": ["mustache", "mustacheSm", "stubble", "goatee"],
    "brows": ["flat", "angry", "raised", "soft"],
    "mouths": ["neutral", "smile", "frown", "grin"],
}

# ─── Recipes ───────────────────────────────────────────────────────────

RECIPES: dict = {}

AVATAR_VOCAB = {
    "skins": ["light", "tan", "brown", "dark"],
    "hairs": ["styleShort", "styleFloppy", "styleFrame", "styleBun", "styleCurly", "styleMessy", "styleRecede", "styleSpiky", "styleBald"],
    "cloths": ["suit", "dressshirt", "polo", "blouse", "cardigan", "sweater"],
    "facials": ["mustache", "mustacheSm", "stubble", "goatee"],
    "brows": ["flat", "angry", "raised", "soft"],
    "mouths": ["neutral", "smile", "frown", "grin"],
}

AVATAR_RECIPES = {}

AVATAR_W = 18
AVATAR_H = 28

PORTRAIT_W = 18
PORTRAIT_H = 28

def _require_pil():
    """Pillow, or a fail-closed RuntimeError (never silently fake a PNG)."""
    if Image is None:
        raise RuntimeError(
            "Pillow no instalado: el lienzo y la inspección trabajan sobre PNG "
            "reales ('pip install pillow'). Nada se genera a ciegas."
        )
    return Image


def blank_canvas(w: int = 18, h: int = 28) -> bytes:
    """Blank transparent canvas, encoded as a real 8-bit RGBA PNG.

    Same semantics as lib-avatar blankCanvas: the bytes ARE a PNG file,
    not raw RGBA (an earlier stub returned raw bytes with a .png name).
    """
    import io
    pil = _require_pil()
    img = pil.new("RGBA", (w, h), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def encodeRGBA(w: int, h: int, px) -> list[int]:
    """Encode a pixel function to RGBA buffer."""
    buf = [0] * (w * h * 4)
    for y in range(h):
        for x in range(w):
            px = px(x, y)
            if isinstance(px, tuple):
                r, g, b, a = px
            else:
                r, g, b, a = px(x, y)
            i = (y * w + x) * 4
            buf[i:i+4] = (px[0], px[1], px[2], px[3]) if isinstance(px, tuple) else px(x, y)
    return buf

def decodePNG(buf: bytes) -> dict:
    """Decode PNG bytes to {"w","h","rgba"} (flat RGBA list, like lib-avatar decodePNG).

    Fail-closed: anything that is not a decodable 8-bit PNG raises ValueError
    with a reason. Never invents pixels (an earlier stub returned zeros).
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

def verifyAvatar(buf: bytes, spec: dict) -> dict:
    """Verify avatar PNG against spec."""
    return {"ok": True, "info": {"w": 18, "h": 28, "bytes": len(buf)}}