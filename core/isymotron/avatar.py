#!/usr/bin/env python3
"""isymotron avatar primitives -- generic pixel helpers + real PNG codec + M11 verify.

Scope is deliberately narrow: blank canvases, a stdlib PNG encode/decode, avatar-spec
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


# ─── PNG codec (stdlib zlib; fail-closed) ─────────────────────────────────
#
# A format-specific codec, not an image library: encode is always 8-bit RGBA,
# decode accepts every color type / bit depth / interlace the PNG spec allows
# and normalizes to 8-bit RGBA (16-bit samples keep their high byte). It exists
# so the runtime stays standard-library only; Pillow is the test oracle
# (tests/test_png_codec.py), never a runtime import.

_SIG = b"\x89PNG\r\n\x1a\n"
_MAX_DIM = 4096
#: channels per color type (0 gray, 2 RGB, 3 palette, 4 gray+alpha, 6 RGBA)
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
#: Adam7 passes: (x0, y0, dx, dy)
_ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
          (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def _chunk(kind: bytes, data: bytes) -> bytes:
    import struct
    import zlib
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def encode_png(w: int, h: int, rgba) -> bytes:
    """Encode a flat RGBA sequence (w*h*4) as an 8-bit RGBA PNG."""
    import struct
    import zlib
    raw = bytes(rgba)
    if len(raw) != w * h * 4:
        raise ValueError(f"buffer inesperado: {len(raw)} bytes para {w}x{h}")
    if not (0 < w <= _MAX_DIM and 0 < h <= _MAX_DIM):
        raise ValueError(f"dimensiones fuera de rango: {w}x{h}")
    stride = w * 4
    scan = b"".join(b"\x00" + raw[y * stride:(y + 1) * stride] for y in range(h))
    return (_SIG
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(scan, 9))
            + _chunk(b"IEND", b""))


def blank_canvas(w: int = W, h: int = H) -> bytes:
    """Blank transparent canvas, encoded as a real 8-bit RGBA PNG."""
    return encode_png(w, h, bytes(w * h * 4))


def _unfilter(data: bytes, pos: int, rows: int, rowlen: int, bpp: int):
    """Undo per-row filters. Returns (rows as bytearrays, new position)."""
    out = []
    prev = bytearray(rowlen)
    for _ in range(rows):
        ft = data[pos]
        cur = bytearray(data[pos + 1:pos + 1 + rowlen])
        pos += 1 + rowlen
        if ft == 1:
            for i in range(bpp, rowlen):
                cur[i] = (cur[i] + cur[i - bpp]) & 0xFF
        elif ft == 2:
            for i in range(rowlen):
                cur[i] = (cur[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(rowlen):
                left = cur[i - bpp] if i >= bpp else 0
                cur[i] = (cur[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(rowlen):
                a = cur[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                cur[i] = (cur[i] + pr) & 0xFF
        elif ft != 0:
            raise ValueError(f"PNG inválido: filtro {ft}")
        out.append(cur)
        prev = cur
    return out, pos


def _samples(row: bytes, n: int, depth: int) -> list[int]:
    """First n samples of a row at the given bit depth (16-bit samples stay 16-bit here)."""
    if depth == 8:
        return list(row[:n])
    if depth == 16:
        return [(row[2 * i] << 8) | row[2 * i + 1] for i in range(n)]
    per = 8 // depth
    mask = (1 << depth) - 1
    return [(row[i // per] >> (8 - depth * (i % per + 1))) & mask for i in range(n)]


def decodePNG(buf: bytes) -> dict:
    """Decode PNG bytes to {"w","h","rgba"} (flat 8-bit RGBA list).

    Fail-closed: anything that is not a decodable PNG raises ValueError
    with a reason. Never invents pixels.
    """
    import struct
    import zlib
    if not isinstance(buf, (bytes, bytearray)):
        raise ValueError("PNG inválido: se esperaban bytes")
    buf = bytes(buf)
    if len(buf) < 8 or buf[:8] != _SIG:
        raise ValueError("PNG inválido: firma")
    pos, ihdr, plte, trns, idat, ended = 8, None, None, None, [], False
    while pos < len(buf):
        if pos + 12 > len(buf):
            raise ValueError("PNG inválido: no decodifica (truncado)")
        (length,) = struct.unpack(">I", buf[pos:pos + 4])
        kind = buf[pos + 4:pos + 8]
        data = buf[pos + 8:pos + 8 + length]
        if len(data) != length or pos + 12 + length > len(buf):
            raise ValueError("PNG inválido: no decodifica (truncado)")
        (crc,) = struct.unpack(">I", buf[pos + 8 + length:pos + 12 + length])
        if zlib.crc32(kind + data) & 0xFFFFFFFF != crc:
            raise ValueError(f"PNG inválido: CRC de {kind!r}")
        pos += 12 + length
        if ihdr is None and kind != b"IHDR":
            raise ValueError("PNG inválido: sin IHDR")
        if kind == b"IHDR":
            if length != 13:
                raise ValueError("PNG inválido: IHDR")
            ihdr = struct.unpack(">IIBBBBB", data)
        elif kind == b"PLTE":
            plte = data
        elif kind == b"tRNS":
            trns = data
        elif kind == b"IDAT":
            idat.append(data)
        elif kind == b"IEND":
            ended = True
            break
        elif not (kind[0] & 0x20):
            raise ValueError(f"PNG inválido: chunk crítico desconocido {kind!r}")
    if ihdr is None:
        raise ValueError("PNG inválido: sin IHDR")
    if not ended or not idat:
        raise ValueError("PNG inválido: no decodifica (sin IDAT/IEND)")
    w, h, depth, ctype, comp, filt, interlace = ihdr
    if not w or not h or w > _MAX_DIM or h > _MAX_DIM:
        raise ValueError(f"PNG inválido: dimensiones absurdas {w}x{h}")
    if ctype not in _CHANNELS or depth not in _DEPTHS[ctype]:
        raise ValueError(f"PNG inválido: color {ctype} / profundidad {depth}")
    if comp or filt or interlace not in (0, 1):
        raise ValueError("PNG inválido: método de compresión/filtro/entrelazado")
    if ctype == 3 and (plte is None or len(plte) % 3):
        raise ValueError("PNG inválido: paleta ausente")
    ch = _CHANNELS[ctype]
    bpp = max(1, ch * depth // 8)
    passes = ([(0, 0, 1, 1)] if interlace == 0 else list(_ADAM7))
    geo = []
    need = 0
    for x0, y0, dx, dy in passes:
        pw = (w - x0 + dx - 1) // dx if w > x0 else 0
        ph = (h - y0 + dy - 1) // dy if h > y0 else 0
        rowlen = (pw * ch * depth + 7) // 8
        geo.append((x0, y0, dx, dy, pw, ph, rowlen))
        if pw and ph:
            need += ph * (1 + rowlen)
    # Bounded inflate: a decompression bomb stops at the size the header implies.
    try:
        d = zlib.decompressobj()
        raw = d.decompress(b"".join(idat), need + 1)
    except zlib.error as e:
        raise ValueError(f"PNG inválido: no decodifica ({e})")
    if len(raw) < need:
        raise ValueError("PNG inválido: datos de imagen cortos")
    maxv = (1 << depth) - 1
    shift16 = depth == 16
    tkey = None
    if trns is not None and ctype == 0 and len(trns) >= 2:
        tkey = (struct.unpack(">H", trns[:2])[0],)
    elif trns is not None and ctype == 2 and len(trns) >= 6:
        tkey = struct.unpack(">HHH", trns[:6])
    out = bytearray(w * h * 4)
    p = 0
    for x0, y0, dx, dy, pw, ph, rowlen in geo:
        if not (pw and ph):
            continue
        rows, p = _unfilter(raw, p, ph, rowlen, bpp)
        for j, row in enumerate(rows):
            s = _samples(row, pw * ch, depth)
            y = y0 + j * dy
            for i in range(pw):
                v = s[i * ch:(i + 1) * ch]
                if ctype == 3:
                    k = v[0]
                    if 3 * k + 2 >= len(plte):
                        raise ValueError("PNG inválido: índice fuera de paleta")
                    r, g, b = plte[3 * k], plte[3 * k + 1], plte[3 * k + 2]
                    a = trns[k] if trns is not None and k < len(trns) else 255
                else:
                    if shift16:
                        e = [x >> 8 for x in v]
                    elif depth == 8:
                        e = v
                    else:
                        e = [x * 255 // maxv for x in v]
                    if ctype == 0:
                        r = g = b = e[0]
                        a = 0 if tkey is not None and (v[0],) == tkey else 255
                    elif ctype == 4:
                        r = g = b = e[0]
                        a = e[1]
                    elif ctype == 2:
                        r, g, b = e
                        a = 0 if tkey is not None and tuple(v) == tkey else 255
                    else:
                        r, g, b, a = e
                o = ((y * w) + x0 + i * dx) * 4
                out[o:o + 4] = bytes((r, g, b, a))
    return {"w": w, "h": h, "rgba": list(out)}


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
