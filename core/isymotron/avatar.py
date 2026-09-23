#!/usr/bin/env python3
"""isymotron avatar engine -- procedural 18x28 portraits (port of the munder portrait core).

PORTADO DE (no editar a ciegas; si el canon cambia, re-portar y re-fijar goldens):
  ISyCo/tools/munder-cli/avatar-engine.cjs  sha256:8338fde3df3c2c82431d8766b7ee37d19956b70294b9ba4c95d943d01898597e
  ISyCo/tools/munder-cli/lib-avatar.cjs     sha256:922dd1bd2721b98aae044893c9c88b630baa75367386ed1d7896c96d3c76c7d9
  (generado a su vez de portraitArt.ts     sha256:5a06ab48a8b2ed5a6137c2a5bfef998b318f648adfee238ab0f52d2bf19c0158)

Alcance del port: el busto-retrato (compose_avatar = compose JS). NO portado a
proposito: el cuerpo de escena 18x32 (drawSceneLegs/Torso/HeadBack/composeScene),
caches y paintPortrait (DOM/Electron). El CLI solo necesita retratos.

Semantica preservada: clamp con redondeo-half-up de JS, set() con clip,
outline de dos fases (solo alfa==255 dispara), orden de capas
ropa -> cuello -> cabeza -> outline. Verificacion diferencial contra node en
tests/test_avatar_engine.py (goldens byte-exactos por personaje).
"""

from __future__ import annotations

import math

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow is installed in this repo
    Image = None

# ─── canvas ───────────────────────────────────────────────────────────────

PORTRAIT_W = 18
PORTRAIT_H = 28

W = PORTRAIT_W
H = PORTRAIT_H
AVATAR_W = PORTRAIT_W
AVATAR_H = PORTRAIT_H

OUTLINE = [38, 34, 46]
HX0, HX1 = 4, 13  # head skin columns

AVATAR_MAX_BYTES = 512 * 1024


def clamp(v: float) -> int:
    """JS Math.round semantics (half-up), clamped to a byte."""
    if v < 0:
        return 0
    if v > 255:
        return 255
    return int(math.floor(v + 0.5))


def shades(rgb, dl: float = 1.22, dd: float = 0.68):
    """[hi, base, sh] variants of a color (same defaults as the canon)."""
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


# `set` is the canonical name (JS parity); setpx is the historical alias.
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


# ─── skin ─────────────────────────────────────────────────────────────────

SKIN = {
    "light": {"hi": [255, 221, 189], "base": [247, 201, 170], "sh": [212, 158, 126], "line": [168, 112, 82]},
    "tan": {"hi": [232, 182, 136], "base": [214, 162, 116], "sh": [176, 126, 86], "line": [138, 92, 60]},
    "brown": {"hi": [180, 130, 94], "base": [158, 112, 78], "sh": [124, 86, 58], "line": [90, 60, 40]},
    "dark": {"hi": [142, 98, 70], "base": [120, 80, 56], "sh": [94, 62, 42], "line": [64, 42, 28]},
}


# ─── head + face ──────────────────────────────────────────────────────────

def draw_head(buf: list[int], skin: str) -> None:
    s = SKIN[skin]
    for y in range(4, 17):
        for x in range(HX0, HX1 + 1):
            if ((x == HX0 or x == HX1) and (y == 4 or y == 5 or y == 16)) or ((x == 5 or x == 12) and y == 4):
                continue
            set(buf, x, y, s["base"])
    for y in range(6, 12):
        set(buf, 5, y, s["hi"])
    set(buf, 6, 5, s["hi"])
    set(buf, 7, 5, s["hi"])
    for y in range(6, 15):
        set(buf, 12, y, s["sh"])
    for x in (7, 8, 9, 10, 11):
        set(buf, x, 16, s["sh"])
    for ex in (HX0 - 1, HX1 + 1):
        set(buf, ex, 9, s["base"])
        set(buf, ex, 10, s["base"])
        set(buf, ex, 11, s["sh"])
    rect(buf, 7, 17, 10, 18, s["sh"])
    rect(buf, 7, 17, 9, 17, s["base"])


def draw_face(buf: list[int], skin: str, brow: str, mouth: str, blush: bool, lashes: bool = False) -> None:
    s = SKIN[skin]
    white = [250, 248, 244]
    pup = [46, 38, 42]
    for a, b, p in ((5, 6, 6), (10, 11, 10)):
        set(buf, a, 9, white)
        set(buf, b, 9, white)
        set(buf, p, 9, pup)
    if lashes:
        lash = [54, 40, 48]
        glint = [252, 250, 248]
        for x in (5, 6, 10, 11):
            set(buf, x, 8, lash)
        set(buf, 4, 8, lash)
        set(buf, 12, 8, lash)
        set(buf, 5, 9, glint)
        set(buf, 10, 9, glint)
    if brow == "flat":
        for x in (5, 6, 10, 11):
            set(buf, x, 7, s["line"])
    elif brow == "angry":
        set(buf, 5, 8, s["line"])
        set(buf, 6, 7, s["line"])
        set(buf, 10, 7, s["line"])
        set(buf, 11, 8, s["line"])
    elif brow == "raised":
        for x in (5, 6, 10, 11):
            set(buf, x, 6, s["line"])
    elif brow == "soft":
        for x in (5, 11):
            set(buf, x, 7, s["line"])
        for x in (6, 10):
            set(buf, x, 7, s["sh"])
    set(buf, 8, 11, s["sh"])
    set(buf, 8, 12, s["sh"])
    set(buf, 7, 12, s["sh"])
    mc = [158, 86, 80]
    mouths = {
        "neutral": [(7, 14), (8, 14), (9, 14), (10, 14)],
        "smile": [(7, 14), (8, 14), (9, 14), (10, 14), (6, 13), (11, 13)],
        "frown": [(7, 15), (8, 15), (9, 15), (10, 15), (6, 14), (11, 14)],
        "grin": [(7, 14), (8, 14), (9, 14), (10, 14), (7, 13), (8, 13), (9, 13), (10, 13), (6, 13), (11, 13)],
    }
    for x, y in mouths[mouth]:
        set(buf, x, y, mc)
    if blush:
        for x in (5, 12):
            set(buf, x, 12, [235, 150, 140], 140)


# ─── hair styles ──────────────────────────────────────────────────────────

def style_short(buf, color, skin_base, args=None):
    args = args or {}
    hi, base, sh = shades(color)
    part = args.get("part", "L")
    recede = args.get("recede", 0)
    rect(buf, HX0, 2, HX1, 4, base)
    for x in range(HX0 - 1, HX1 + 2):
        set(buf, x, 3, base)
    rect(buf, HX0 - 1, 4, HX1 + 1, 5, base)
    for y in range(6, 9):
        set(buf, HX0 - 1, y, base)
        set(buf, HX0, y, base)
        set(buf, HX1, y, base)
        set(buf, HX1 + 1, y, base)
    for x in range(HX0, HX1 + 1):
        set(buf, x, 5, base)
    if recede:
        for y in range(3, 6):
            for x in range(6, 12):
                if eq(rgb_at(buf, x, y), base):
                    set(buf, x, y, skin_base)
        set(buf, 8, 5, base)  # widow's peak
    hx = 6 if part == "L" else 11
    for y in range(2, 6):
        set(buf, hx, y, sh)
    for x in range(HX0, hx):
        if alpha_at(buf, x, 3):
            set(buf, x, 3, hi)
    for x in range(HX0, HX1 + 1):
        if alpha_at(buf, x, 2):
            set(buf, x, 2, hi)


def style_floppy(buf, color, skin_base=None, args=None):
    hi, base, _sh = shades(color)
    rect(buf, HX0, 2, HX1, 4, base)
    for x in range(HX0 - 1, HX1 + 2):
        set(buf, x, 3, base)
    rect(buf, HX0 - 1, 4, HX1 + 1, 5, base)
    for x in range(HX0, HX1 + 1):
        set(buf, x, 5, base)
    for x in range(6, 13):
        set(buf, x, 6, base)
    set(buf, 9, 7, base)
    set(buf, 10, 7, base)
    set(buf, 11, 7, base)
    for y in range(6, 9):
        set(buf, HX0 - 1, y, base)
        set(buf, HX0, y, base)
        set(buf, HX1, y, base)
        set(buf, HX1 + 1, y, base)
    for x in range(HX0, HX1 + 1):
        if alpha_at(buf, x, 2):
            set(buf, x, 2, hi)
    for x in (7, 8, 9):
        set(buf, x, 6, hi)


def style_frame(buf, color, skin_base, args=None):
    args = args or {}
    hi, base, sh = shades(color)
    length = args.get("length", 17)
    vol = args.get("vol", 1)
    rect(buf, HX0 - 1, 2, HX1 + 1, 5, base)
    for x in range(HX0 - 1, HX1 + 2):
        set(buf, x, 3, base)
    for x in range(HX0, HX1 + 1):
        set(buf, x, 5, base)
    for x in range(6, 12):
        set(buf, x, 6, base)
    set(buf, 8, 6, skin_base)
    set(buf, 9, 6, skin_base)
    for y in range(6, length + 1):
        for dx in range(vol):
            set(buf, HX0 - 1 - dx, y, base)
            set(buf, HX1 + 1 + dx, y, base)
        set(buf, HX0, y, base)
        set(buf, HX1, y, base)
    for x in range(HX0 - 1, HX0 + 1):
        set(buf, x, length + 1, base)
    for x in range(HX1, HX1 + 2):
        set(buf, x, length + 1, base)
    for y in range(2, 6):
        if alpha_at(buf, HX1, y):
            set(buf, HX1, y, sh)
    for x in range(HX0, 9):
        if alpha_at(buf, x, 2):
            set(buf, x, 2, hi)


def style_bun(buf, color, skin_base, args=None):
    hi, base, _sh = shades(color)
    rect(buf, HX0, 3, HX1, 5, base)
    for x in range(HX0 - 1, HX1 + 2):
        set(buf, x, 4, base)
    for x in range(HX0, HX1 + 1):
        set(buf, x, 5, base)
    for x in range(6, 12):
        set(buf, x, 6, base)
    set(buf, 8, 6, skin_base)
    set(buf, 9, 6, skin_base)
    for y in range(6, 9):
        set(buf, HX0, y, base)
        set(buf, HX1, y, base)
    rect(buf, 7, 1, 10, 2, base)
    for x in range(HX0, HX1 + 1):
        if alpha_at(buf, x, 3):
            set(buf, x, 3, hi)


def style_curly(buf, color, skin_base, args=None):
    hi, base, _sh = shades(color)
    pts = [(4, 3), (5, 2), (6, 3), (7, 2), (8, 3), (9, 2), (10, 3), (11, 2), (12, 3), (13, 3),
           (3, 4), (4, 4), (13, 4), (14, 4), (3, 5), (4, 5), (13, 5), (14, 5), (3, 6), (13, 6),
           (4, 6), (12, 6), (3, 7), (13, 7), (4, 7)]
    rect(buf, HX0, 3, HX1, 5, base)
    for x in range(HX0 - 1, HX1 + 2):
        set(buf, x, 4, base)
    for x, y in pts:
        set(buf, x, y, base)
    for x in range(6, 12):
        set(buf, x, 6, base)
    set(buf, 8, 6, skin_base)
    set(buf, 9, 6, skin_base)
    for x, y in ((5, 2), (7, 2), (9, 2), (11, 2)):
        set(buf, x, y, hi)


def style_messy(buf, color, skin_base, args=None):
    args = args or {}
    hi, base, _sh = shades(color)
    length = args.get("length", 8)
    rect(buf, HX0 - 1, 2, HX1 + 1, 5, base)
    spikes = [(3, 2), (5, 1), (7, 2), (9, 1), (11, 2), (13, 1), (14, 2), (4, 2), (12, 2)]
    for x, y in spikes:
        set(buf, x, y, base)
    for x in range(HX0, HX1 + 1):
        set(buf, x, 5, base)
    for x in range(6, 12):
        set(buf, x, 6, base)
    set(buf, 8, 6, skin_base)
    set(buf, 9, 6, skin_base)
    for y in range(6, length + 1):
        set(buf, HX0 - 1, y, base)
        set(buf, HX0, y, base)
        set(buf, HX1, y, base)
        set(buf, HX1 + 1, y, base)
    for x, y in spikes:
        set(buf, x, y, hi)


def style_recede(buf, color, skin_base, args=None):
    _hi, base, sh = shades(color)
    for y in range(4, 10):
        set(buf, HX0 - 1, y, base)
        set(buf, HX0, y, base)
        set(buf, HX1, y, base)
        set(buf, HX1 + 1, y, base)
    for x in range(HX0, HX1 + 1):
        set(buf, x, 4, base)
    for x in range(HX0 + 1, HX1):
        set(buf, x, 5, base)
    for y in range(5, 9):
        for x in range(6, 12):
            if eq(rgb_at(buf, x, y), base):
                set(buf, x, y, skin_base)
    for x in range(HX0, HX1 + 1):
        if alpha_at(buf, x, 4):
            set(buf, x, 4, sh)


def style_spiky(buf, color, skin_base, args=None):
    hi, base, _sh = shades(color)
    rect(buf, HX0, 3, HX1, 5, base)
    for x in range(HX0 - 1, HX1 + 2):
        set(buf, x, 4, base)
    for x in range(HX0, HX1 + 1):
        set(buf, x, 5, base)
    spikes = [(5, 2), (7, 1), (9, 2), (11, 1), (6, 2), (8, 2), (10, 2), (12, 2)]
    for x, y in spikes:
        set(buf, x, y, base)
    for x in range(6, 12):
        set(buf, x, 6, base)
    set(buf, 8, 6, skin_base)
    set(buf, 9, 6, skin_base)
    for y in range(6, 8):
        set(buf, HX0, y, base)
        set(buf, HX1, y, base)
    for x, y in spikes:
        set(buf, x, y, hi)


def style_bald(buf, color, skin_base, args=None):
    args = args or {}
    shi, sbase, ssh = shades(skin_base, 1.1, 0.82)
    for x in range(6, 12):
        set(buf, x, 2, sbase)
    for x in range(5, 13):
        set(buf, x, 3, sbase)
    for x in range(HX0, HX1 + 1):
        set(buf, x, 4, sbase)
    for x in (7, 8, 9):
        set(buf, x, 2, shi)
    set(buf, 6, 3, shi)
    set(buf, 7, 3, shi)
    set(buf, 5, 3, ssh)
    set(buf, 12, 3, ssh)
    set(buf, HX1, 4, ssh)
    _hi, base, sh = shades(color)
    top = 8 if args.get("recede") else 6
    for y in range(top, 11):
        set(buf, HX0 - 1, y, base)
        set(buf, HX0, y, base)
        set(buf, HX1, y, base)
        set(buf, HX1 + 1, y, base)
    for y in range(top, 11):
        set(buf, HX0 - 1, y, sh)
        set(buf, HX1 + 1, y, sh)


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


# ─── facial hair + glasses ────────────────────────────────────────────────

def draw_facial(buf: list[int], kind: str, color) -> None:
    _hi, base, sh = shades(color)
    if kind == "mustache":
        for x in (6, 7, 8, 9, 10):
            set(buf, x, 13, base)
        set(buf, 6, 12, base)
        set(buf, 10, 12, base)
    elif kind == "mustacheSm":
        for x in (7, 8, 9):
            set(buf, x, 13, base)
    elif kind == "stubble":
        for x, y in ((5, 14), (6, 15), (7, 15), (8, 15), (9, 15), (10, 15),
                     (11, 14), (12, 13), (4, 13), (5, 15), (10, 15)):
            set(buf, x, y, sh, 150)
    elif kind == "goatee":
        for x in (8, 9):
            set(buf, x, 15, base)
        set(buf, 8, 14, base)
        set(buf, 9, 14, base)
        for x in (7, 8, 9, 10):
            set(buf, x, 13, base)


def draw_glasses(buf: list[int]) -> None:
    frame = [60, 54, 62]
    glint = [236, 240, 246]
    for x in (5, 6):
        set(buf, x, 8, frame)
        set(buf, x, 10, frame)
    set(buf, 4, 9, frame)
    set(buf, 7, 9, frame)
    set(buf, 4, 8, frame)
    set(buf, 7, 8, frame)
    for x in (10, 11):
        set(buf, x, 8, frame)
        set(buf, x, 10, frame)
    set(buf, 9, 9, frame)
    set(buf, 12, 9, frame)
    set(buf, 9, 8, frame)
    set(buf, 12, 8, frame)
    set(buf, 8, 8, frame)
    set(buf, 3, 9, frame)
    set(buf, 13, 9, frame)
    set(buf, 4, 8, glint)
    set(buf, 9, 8, glint)


# ─── body + clothing ──────────────────────────────────────────────────────

def body_shape(buf: list[int], col, heavy: bool = False) -> None:
    _hi, base, sh = shades(col)
    rows = ([[19, 5, 12], [20, 3, 14], [21, 2, 15], [22, 1, 16], [23, 1, 16],
             [24, 0, 17], [25, 0, 17], [26, 0, 17], [27, 0, 17]] if heavy else
            [[19, 6, 11], [20, 4, 13], [21, 3, 14], [22, 2, 15], [23, 2, 15],
             [24, 1, 16], [25, 1, 16], [26, 1, 16], [27, 1, 16]])
    for y, a, b in rows:
        rect(buf, a, y, b, y, base)
    lo, hi = (1, 16) if heavy else (2, 15)
    for y in range(22, 28):
        set(buf, lo, y, sh)
        set(buf, hi, y, sh)


def draw_clothing(buf: list[int], kind: str, c1, c2, tie, skin: str, heavy: bool = False) -> None:
    hi, base, sh = shades(c1)
    body_shape(buf, c1, heavy)
    if kind == "suit":
        white = [238, 238, 236]
        for x, y in ((8, 19), (9, 19), (7, 20), (8, 20), (9, 20), (10, 20), (8, 21), (9, 21)):
            set(buf, x, y, white)
        for x, y in ((6, 20), (7, 21), (11, 20), (10, 21), (6, 21), (11, 21)):
            set(buf, x, y, sh)
        if tie:
            for y in range(20, 26):
                set(buf, 8, y, tie)
                set(buf, 9, y, tie)
            set(buf, 8, 20, shades(tie)[0])
        else:
            for y in range(22, 26):
                set(buf, 8, y, white)
                set(buf, 9, y, white)
    elif kind == "dressshirt":
        for x, y in ((6, 19), (7, 19), (10, 19), (11, 19), (7, 20), (10, 20)):
            set(buf, x, y, sh)
        for y in range(20, 27, 2):
            set(buf, 8, y, sh)
        if tie:
            for y in range(19, 26):
                set(buf, 8, y, tie)
                set(buf, 9, y, tie)
    elif kind == "polo":
        for x, y in ((6, 19), (7, 19), (10, 19), (11, 19)):
            set(buf, x, y, hi)
        set(buf, 8, 20, sh)
        set(buf, 8, 22, sh)
        accent = shades(c2)[1] if c2 else hi
        for x, y in ((7, 20), (9, 20)):
            set(buf, x, y, accent)
    elif kind == "blouse":
        s = SKIN[skin]
        for x, y in ((7, 19), (8, 19), (9, 19), (10, 19), (8, 20), (9, 20)):
            set(buf, x, y, s["sh"])
        for x in range(5, 13):
            if eq(rgb_at(buf, x, 20), base):
                set(buf, x, 20, hi)
    elif kind == "cardigan":
        inner = shades(c2)[1] if c2 else [235, 233, 226]
        for y in range(19, 27):
            set(buf, 8, y, inner)
            set(buf, 9, y, inner)
        for x, y in ((6, 19), (7, 19), (10, 19), (11, 19)):
            set(buf, x, y, sh)
    elif kind == "sweater":
        for x, y in ((6, 19), (7, 19), (8, 19), (9, 19), (10, 19), (11, 19)):
            set(buf, x, y, sh)


def collar_neck(buf: list[int], skin: str) -> None:
    rect(buf, 7, 18, 10, 19, SKIN[skin]["sh"])


# ─── outline + heavy ──────────────────────────────────────────────────────

def outline_pass(buf: list[int]) -> None:
    pts = []
    for y in range(H):
        for x in range(W):
            if alpha_at(buf, x, y) != 0:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if alpha_at(buf, x + dx, y + dy) == 255:
                    pts.append((x, y))
                    break
    for x, y in pts:
        set(buf, x, y, OUTLINE)


def draw_heavy_face(buf: list[int], skin: str) -> None:
    s = SKIN[skin]
    for y in range(11, 16):
        set(buf, HX0 - 1, y, s["base"])
        set(buf, HX1 + 1, y, s["base"])
    set(buf, HX0 - 1, 15, s["sh"])
    set(buf, HX1 + 1, 15, s["sh"])
    for x in (5, 6, 11, 12):
        set(buf, x, 16, s["base"])
    rect(buf, 6, 17, 11, 18, s["base"])
    for x in (6, 7, 8, 9, 10, 11):
        set(buf, x, 18, s["sh"])
    set(buf, 7, 17, s["sh"])
    set(buf, 10, 17, s["sh"])


# ─── compose ──────────────────────────────────────────────────────────────

def draw_head_group(buf: list[int], r: dict) -> None:
    skin_base = SKIN[r["skin"]]["base"]
    draw_head(buf, r["skin"])
    if r.get("heavy"):
        draw_heavy_face(buf, r["skin"])
    draw_face(buf, r["skin"], r.get("brow", "flat"), r.get("mouth", "neutral"),
              r.get("blush", False), r.get("lashes", False))
    if r.get("facial"):
        draw_facial(buf, r["facial"], r["hairc"])
    HAIR_FNS[r["hair"]](buf, r["hairc"], skin_base, r.get("hairargs") or {})
    if r.get("glasses"):
        draw_glasses(buf)


def compose(r: dict) -> list[int]:
    """Portrait bust: shoulders-height clothing + front head group."""
    buf = [0] * (PORTRAIT_W * PORTRAIT_H * 4)
    draw_clothing(buf, r["cloth"], r["c1"], r.get("c2"), r.get("tie"), r["skin"], r.get("heavy", False))
    collar_neck(buf, r["skin"])
    draw_head_group(buf, r)
    outline_pass(buf)
    return buf


def compose_avatar(recipe: dict) -> list[int]:
    """Standalone portrait composer: recipe in, 18x28 RGBA buffer out."""
    return compose(recipe)


# ─── vocabulary + cast ────────────────────────────────────────────────────

AVATAR_VOCAB = {
    "skins": list(SKIN.keys()),
    "hairs": list(HAIR_FNS.keys()),
    "cloths": ["suit", "dressshirt", "polo", "blouse", "cardigan", "sweater"],
    "facials": ["mustache", "mustacheSm", "stubble", "goatee"],
    "brows": ["flat", "angry", "raised", "soft"],
    "mouths": ["neutral", "smile", "frown", "grin"],
}

# Builtin cast (verbatim from the canon; buffers pinned by tests).
RECIPES: dict = {
    "michael": {"skin": "light", "hairc": [58, 42, 28], "hair": "styleShort", "hairargs": {"part": "L"}, "cloth": "suit", "c1": [58, 63, 74], "tie": [170, 58, 58], "brow": "flat", "mouth": "smile"},
    "jim": {"skin": "light", "hairc": [92, 60, 34], "hair": "styleFloppy", "cloth": "dressshirt", "c1": [172, 196, 224], "tie": [120, 130, 150], "brow": "flat", "mouth": "smile"},
    "pam": {"skin": "light", "hairc": [120, 76, 42], "hair": "styleFrame", "hairargs": {"length": 18, "vol": 2}, "cloth": "cardigan", "c1": [236, 174, 192], "c2": [244, 242, 238], "brow": "soft", "mouth": "smile", "blush": True, "lashes": True},
    "dwight": {"skin": "light", "hairc": [64, 48, 28], "hair": "styleShort", "hairargs": {"part": "L", "recede": 1}, "cloth": "dressshirt", "c1": [184, 155, 62], "tie": [120, 82, 46], "glasses": True, "brow": "angry", "mouth": "neutral"},
    "kevin": {"skin": "light", "hairc": [58, 44, 30], "hair": "styleBald", "cloth": "polo", "c1": [110, 140, 180], "c2": [90, 120, 160], "brow": "flat", "mouth": "neutral", "heavy": True},
    "angela": {"skin": "light", "hairc": [186, 154, 90], "hair": "styleBun", "cloth": "cardigan", "c1": [150, 146, 170], "c2": [235, 233, 226], "brow": "angry", "mouth": "frown", "lashes": True},
    "oscar": {"skin": "tan", "hairc": [28, 22, 18], "hair": "styleShort", "hairargs": {"part": "L"}, "cloth": "sweater", "c1": [122, 60, 74], "brow": "flat", "mouth": "smile"},
    "stanley": {"skin": "dark", "hairc": [60, 54, 48], "hair": "styleRecede", "cloth": "dressshirt", "c1": [150, 120, 86], "tie": [120, 78, 52], "glasses": True, "facial": "mustache", "brow": "flat", "mouth": "neutral", "heavy": True},
    "phyllis": {"skin": "light", "hairc": [196, 162, 110], "hair": "styleCurly", "cloth": "blouse", "c1": [202, 160, 192], "glasses": True, "brow": "soft", "mouth": "smile", "lashes": True, "heavy": True},
    "andy": {"skin": "light", "hairc": [74, 51, 32], "hair": "styleShort", "hairargs": {"part": "R"}, "cloth": "polo", "c1": [176, 65, 58], "c2": [150, 50, 46], "brow": "raised", "mouth": "smile"},
    "kelly": {"skin": "tan", "hairc": [24, 18, 22], "hair": "styleFrame", "hairargs": {"length": 20, "vol": 1}, "cloth": "blouse", "c1": [212, 90, 158], "brow": "soft", "mouth": "smile", "blush": True, "lashes": True},
    "ryan": {"skin": "light", "hairc": [42, 32, 24], "hair": "styleSpiky", "cloth": "suit", "c1": [58, 58, 68], "tie": [40, 40, 50], "brow": "flat", "mouth": "neutral"},
    "toby": {"skin": "light", "hairc": [106, 90, 66], "hair": "styleShort", "hairargs": {"part": "L", "recede": 1}, "cloth": "dressshirt", "c1": [150, 150, 120], "facial": "mustacheSm", "brow": "soft", "mouth": "frown"},
    "creed": {"skin": "light", "hairc": [170, 166, 156], "hair": "styleBald", "cloth": "dressshirt", "c1": [126, 130, 96], "facial": "stubble", "brow": "flat", "mouth": "neutral"},
    "meredith": {"skin": "light", "hairc": [154, 82, 46], "hair": "styleMessy", "hairargs": {"length": 15}, "cloth": "blouse", "c1": [176, 86, 74], "brow": "raised", "mouth": "smile", "lashes": True},
}

AVATAR_RECIPES = RECIPES


# ─── PNG codec (Pillow; fail-closed without it) ───────────────────────────

def _require_pil():
    """Pillow, or a fail-closed RuntimeError (never silently fake a PNG)."""
    if Image is None:
        raise RuntimeError(
            "Pillow no instalado: el lienzo y la inspección trabajan sobre PNG "
            "reales ('pip install pillow'). Nada se genera a ciegas."
        )
    return Image


def blank_canvas(w: int = PORTRAIT_W, h: int = PORTRAIT_H) -> bytes:
    """Blank transparent canvas, encoded as a real 8-bit RGBA PNG (like blankCanvas)."""
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
    """Decode PNG bytes to {"w","h","rgba"} (flat RGBA list, like decodePNG).

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

    Returns {"ok": True, "info": ...} or {"ok": False, "reason": ...}
    (AVATAR_REJECTED upstream). Never normalizes silently.
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
