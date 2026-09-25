"""The stdlib PNG codec in core/isymotron/avatar.py against an independent oracle.

Pillow is a DEV dependency (requirements-dev.txt), used here only as the
reference encoder/decoder. The runtime never imports it: that is asserted below
too, so the codec cannot quietly lean on it again.
"""
from __future__ import annotations

import io
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest
from PIL import Image

from core.isymotron.avatar import decodePNG, encode_png

REPO = Path(__file__).resolve().parent.parent


def _pil_png(img: Image.Image, **kw) -> bytes:
    b = io.BytesIO()
    img.save(b, format="PNG", **kw)
    return b.getvalue()


def _oracle(png: bytes) -> list[int]:
    with Image.open(io.BytesIO(png)) as im:
        return list(im.convert("RGBA").tobytes())


def _pattern(w, h):
    return [((x * 37 + y * 11) % 256, (x * 5) % 256, (y * 9) % 256, (x * y * 13) % 256)
            for y in range(h) for x in range(w)]


def _images():
    w, h = 13, 11          # odd sizes exercise Adam7 edge passes
    px = _pattern(w, h)
    rgba = Image.new("RGBA", (w, h)); rgba.putdata(px)
    yield "RGBA8", rgba
    yield "RGB8", rgba.convert("RGB")
    yield "LA8", rgba.convert("LA")
    yield "L8", rgba.convert("L")
    yield "1bit", rgba.convert("L").point(lambda v: 255 if v > 127 else 0).convert("1")
    yield "P8", rgba.convert("RGB").quantize(200)
    yield "P4", rgba.convert("RGB").quantize(16)
    yield "P2", rgba.convert("RGB").quantize(4)
    pa = rgba.convert("RGB").quantize(8)
    pa.info["transparency"] = bytes([0, 128, 255, 10, 200, 255, 255, 0])
    yield "P+tRNS", pa
    lt = rgba.convert("L"); lt.info["transparency"] = px[3][0] and lt.getpixel((3, 0))
    yield "L+tRNS", lt
    rt = rgba.convert("RGB"); rt.info["transparency"] = rt.getpixel((0, 0))
    yield "RGB+tRNS", rt
    import random
    rnd = random.Random(7)             # low-entropy noise: many Paeth ties
    noise = Image.new("RGBA", (w, h))
    noise.putdata([tuple(rnd.choice((0, 64, 128)) for _ in range(4)) for _ in range(w * h)])
    yield "noise", noise


@pytest.mark.parametrize("interlace", [False, True])
def test_decode_matches_pillow_all_color_types(interlace):
    seen = []
    for name, img in _images():
        kw = {"transparency": img.info["transparency"]} if "transparency" in img.info else {}
        if name.startswith("P") and img.mode == "P":
            kw["bits"] = {"P4": 4, "P2": 2}.get(name, 8)
        png = _pil_png(img, **kw)
        if interlace:
            png = _reencode_interlaced(png)
        d = decodePNG(png)
        assert (d["w"], d["h"]) == img.size, name
        assert d["rgba"] == _oracle(png), name
        seen.append(name)
    assert len(seen) == 12


def test_decode_16bit_matches_pillow():
    w, h = 7, 5
    rgba16 = b"".join(struct.pack(">HHHH", x * 9000, y * 12000, 65535 - x * 257, 40000 + y)
                      for y in range(h) for x in range(w))
    png = _raw_png(w, h, 16, 6, rgba16, 8)
    d = decodePNG(png)
    assert d["rgba"] == [b for i, b in enumerate(rgba16) if i % 2 == 0]
    rgb16 = b"".join(rgba16[i:i + 6] for i in range(0, len(rgba16), 8))
    png = _raw_png(w, h, 16, 2, rgb16, 6)
    assert decodePNG(png)["rgba"] == _oracle(png)


@pytest.mark.parametrize("ft", range(5))
def test_every_filter_type_forced(ft):
    """Every row uses one filter, encoded by this file's own predictor; both
    the codec and Pillow must recover the random source pixels."""
    import random
    rnd = random.Random(ft)
    w, h, bpp = 16, 16, 4
    src = bytes(rnd.randrange(256) for _ in range(w * h * bpp))
    out, prv = bytearray(), bytes(w * bpp)
    for y in range(h):
        line = src[y * w * bpp:(y + 1) * w * bpp]
        enc = bytes((v - _predict(ft, line[i - bpp] if i >= bpp else 0, prv[i],
                                  prv[i - bpp] if i >= bpp else 0)) & 0xFF
                    for i, v in enumerate(line))
        out += bytes([ft]) + enc
        prv = line
    png = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + _chunk(b"IDAT", zlib.compress(bytes(out))) + _chunk(b"IEND", b""))
    assert _oracle(png) == list(src)
    assert decodePNG(png)["rgba"] == list(src)


def test_encode_is_read_by_pillow():
    px = [v for p in _pattern(18, 28) for v in p]
    png = encode_png(18, 28, px)
    assert _oracle(png) == px
    assert decodePNG(png)["rgba"] == px


def test_rejections_fail_closed():
    good = encode_png(2, 2, [1] * 16)
    bad_crc = bytearray(good); bad_crc[-5] ^= 1
    with pytest.raises(ValueError, match="CRC"):
        decodePNG(bytes(bad_crc))
    with pytest.raises(ValueError, match="no decodifica"):
        decodePNG(good[:-12])                 # no IEND
    with pytest.raises(ValueError, match="dimensiones"):
        decodePNG(_raw_png(5000, 1, 8, 6, b"", 4, fake=True))
    # decompression bomb: header says 1x1, IDAT inflates to 64 MB -> bounded
    bomb = zlib.compress(b"\0" * (64 << 20))
    png = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
           + _chunk(b"IDAT", bomb) + _chunk(b"IEND", b""))
    assert decodePNG(png)["rgba"] == [0, 0, 0, 0]


def test_runtime_imports_no_third_party_package():
    """Import every runtime module in a fresh interpreter with site-packages
    hidden: a stdlib-only runtime must still import cleanly."""
    code = (
        "import sys; sys.path=[p for p in sys.path if 'site-packages' not in p "
        "and 'dist-packages' not in p]; "
        f"sys.path[:0]=[{str(REPO)!r},{str(REPO / 'core')!r},{str(REPO / 'hosts')!r},"
        f"{str(REPO / 'tools')!r}]; "
        "import importlib, pkgutil; "
        "mods=['isymotron.'+m.name for m in pkgutil.iter_modules([sys.path[1]+'/isymotron'])]; "
        "mods+=['console.server','agents.provider','agents.planner','agents.executor',"
        "'relay.loopback','avatar.model','avatar.window','isymotron_cli',"
        "'native','linux.host','linux.power','windows.grants',"
        "'avatar_lienzo','avatar_inspect','avatar_editar','ctl_ping','ctl_status',"
        "'ctl_stop','repaint']; "
        "[importlib.import_module(m) for m in mods]; "
        "bad=[m for m in ('PIL','requests') if m in sys.modules]; "
        "assert not bad, bad; print(len(mods))"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]


# -- helpers ---------------------------------------------------------------

def _chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def _raw_png(w, h, depth, ctype, raw, bpp, fake=False):
    stride = w * bpp
    scan = b"" if fake else b"".join(b"\0" + raw[y * stride:(y + 1) * stride] for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ctype, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(scan)) + _chunk(b"IEND", b""))


def _predict(ft, a, b, c):
    if ft == 0:
        return 0
    if ft == 1:
        return a
    if ft == 2:
        return b
    if ft == 3:
        return (a + b) >> 1
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def _reencode_interlaced(png: bytes) -> bytes:
    """Rewrite a non-interlaced PNG as Adam7, with varied filters, by hand
    (Pillow cannot write interlaced PNGs). Ancillary chunks are preserved."""
    chunks, pos = [], 8
    while pos < len(png):
        (n,) = struct.unpack(">I", png[pos:pos + 4])
        chunks.append((png[pos + 4:pos + 8], png[pos + 8:pos + 8 + n]))
        pos += 12 + n
    ihdr = dict(chunks)[b"IHDR"]
    w, h, depth, ctype = struct.unpack(">IIBB", ihdr[:10])
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bits = ch * depth
    rowlen = (w * bits + 7) // 8
    raw = zlib.decompress(b"".join(d for k, d in chunks if k == b"IDAT"))
    bpp = max(1, bits // 8)
    rows, prv = [], bytes(rowlen)
    for y in range(h):                 # undo the oracle's filters (independent code)
        ft = raw[y * (rowlen + 1)]
        cur = bytearray(raw[y * (rowlen + 1) + 1:(y + 1) * (rowlen + 1)])
        for i in range(rowlen):
            a = cur[i - bpp] if i >= bpp else 0
            c = prv[i - bpp] if i >= bpp else 0
            cur[i] = (cur[i] + _predict(ft, a, prv[i], c)) & 0xFF
        rows.append(bytes(cur))
        prv = cur

    def get(row, x):
        bit = x * bits
        if bits >= 8:
            return row[bit // 8: bit // 8 + bits // 8]
        return (row[bit // 8] >> (8 - bits - bit % 8)) & ((1 << bits) - 1)

    out = bytearray()
    for pi, (x0, y0, dx, dy) in enumerate(((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
                                           (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))):
        xs = list(range(x0, w, dx))
        prev = None
        for y in range(y0, h, dy):
            if not xs:
                break
            if bits >= 8:
                line = b"".join(get(rows[y], x) for x in xs)
            else:
                acc = bytearray((len(xs) * bits + 7) // 8)
                for i, x in enumerate(xs):
                    b = i * bits
                    acc[b // 8] |= get(rows[y], x) << (8 - bits - b % 8)
                line = bytes(acc)
            ft = (pi + y) % 5          # exercise every filter type
            prv = prev or bytes(len(line))
            enc = bytearray(len(line))
            for i, v in enumerate(line):
                a = line[i - bpp] if i >= bpp else 0
                c = prv[i - bpp] if i >= bpp else 0
                b = prv[i]
                enc[i] = (v - _predict(ft, a, b, c)) & 0xFF
            out += bytes([ft]) + enc
            prev = line
    new_ihdr = ihdr[:12] + b"\x01"
    body = b"".join(_chunk(k, new_ihdr if k == b"IHDR" else d) for k, d in chunks
                    if k not in (b"IDAT", b"IEND"))
    return b"\x89PNG\r\n\x1a\n" + body + _chunk(b"IDAT", zlib.compress(bytes(out))) + _chunk(b"IEND", b"")
