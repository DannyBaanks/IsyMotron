"""Avatar surface tests (generic PNG ops only -- COMPOSE repair).

IsyMotron's avatar surface is generic file tooling: blank canvas (lienzo),
model edit (editar), matrix inspect of a PNG (inspect), M11 verify. There is
NO cast, NO renderer, NO text->recipe compiler here: that engine belongs to
Munder (read-only reference, never modified, never invoked at runtime).

Proves: Munder untouched (env-gated) · no Office names/symbols in IsyMotron ·
removed pieces stay removed · no dangling imports · generic verbs work
without Munder · behavior driven by input, not hard-coded names.
"""

import base64
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "core"))

from core.isymotron import avatar
from core.isymotron.avatar import (
    AVATAR_MAX_BYTES,
    blank_canvas,
    decodePNG,
    encode_png,
    verify_avatar,
)

SPEC = {"w": 18, "h": 28, "needAlpha": True, "maxBytes": AVATAR_MAX_BYTES}

OFFICE_NAMES = ["michael", "jim", "pam", "dwight", "kevin", "angela", "oscar",
                "stanley", "phyllis", "andy", "kelly", "ryan", "toby", "creed",
                "meredith"]
OFFICE_SYMBOLS = ["styleShort", "styleFloppy", "styleFrame", "styleBun",
                  "styleCurly", "styleMessy", "styleRecede", "styleSpiky",
                  "styleBald", "compose_avatar", "AVATAR_RECIPES",
                  "avatar_parser", "draw_head", "draw_face", "draw_facial",
                  "draw_glasses", "draw_clothing", "HAIR_FNS", "RECIPES"]

SCAN_DIRS = ["core", "tools", "tests", "docs"]
SKIP_DIRS = {".venv", "__pycache__", ".git", ".pytest_cache"}
SELF = Path(__file__).resolve()


def _scan_files():
    for d in SCAN_DIRS:
        root = REPO / d
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.resolve() == SELF:
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.is_file() and p.suffix in (".py", ".md"):
                yield p
    for p in REPO.glob("*.py"):
        yield p


# ─── 1. Munder untouched (read-only reference; env-gated, never a hard dep) ─

def test_munder_tree_untouched():
    root = os.environ.get("ISYCO_ROOT")
    if not root:
        pytest.skip("ISYCO_ROOT unset: cross-repo check stays out of the suite by default")
    out = subprocess.run(
        ["git", "status", "--short", "--", "tools/munder-cli/"],
        capture_output=True, text=True, timeout=30, cwd=root)
    assert out.returncode == 0, "ISYCO_ROOT is not a git checkout"
    assert out.stdout.strip() == "", f"munder-cli modificado: {out.stdout.strip()}"


# ─── 2/8. no Office contamination, removed pieces stay removed ──────────────

def test_no_office_cast_names():
    bad = []
    for p in _scan_files():
        try:
            text = p.read_text("utf-8", errors="ignore")
        except OSError:
            continue
        for name in OFFICE_NAMES:
            if re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE):
                bad.append(f"{p.relative_to(REPO)}:{name}")
    assert bad == [], f"nombres del cast en IsyMotron: {bad}"


def test_no_office_renderer_symbols():
    bad = []
    for p in _scan_files():
        try:
            text = p.read_text("utf-8", errors="ignore")
        except OSError:
            continue
        for sym in OFFICE_SYMBOLS:
            if re.search(r"\b" + re.escape(sym) + r"\b", text):
                bad.append(f"{p.relative_to(REPO)}:{sym}")
    assert bad == [], f"símbolos del renderer Office en IsyMotron: {bad}"


def test_removed_office_pieces_absent():
    for rel in ("core/isymotron/avatar_parser.py",
                "tools/avatar_compilar.py",
                "tests/test_avatar_engine.py",
                "avatar-lienzo-18x28.png",
                "core/isymotron/avatar"):
        assert not (REPO / rel).exists(), f"debió eliminarse: {rel}"


def test_no_dangling_avatar_imports():
    have = set(dir(avatar))
    bad = []
    candidates = [p for p in list((REPO / "tools").glob("*.py"))
                  + list((REPO / "tests").glob("test_*.py"))
                  if p.resolve() != SELF]
    for p in candidates:
        text = p.read_text("utf-8")
        m = re.search(r"from core\.isymotron\.avatar import ([^\n]+)", text)
        if m:
            names = [n.strip() for n in m.group(1).split(",")]
            for n in names:
                if n not in have:
                    bad.append(f"{p.name}:{n}")
        if "avatar_parser" in text:
            bad.append(f"{p.name}:avatar_parser")
    assert bad == [], f"imports colgando: {bad}"


# ─── 3/4. generic works without Munder; driven by input ─────────────────────

def _run_cli(*args, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, str(REPO / "tools" / "isymotron_cli.py"), *args],
        capture_output=True, text=True, timeout=60, cwd=str(REPO), env=e)


def test_lienzo_inspect_roundtrip_cli(tmp_path):
    out = tmp_path / "l.png"
    r = _run_cli("avatar", "lienzo", str(out))
    assert r.returncode == 0, r.stderr
    d = decodePNG(out.read_bytes())
    assert (d["w"], d["h"]) == (18, 28)
    assert all(a == 0 for a in d["rgba"][3::4])
    r = _run_cli("avatar", "inspect", str(out))
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0].startswith("CANVAS 18x28")
    rows = [l for l in r.stdout.splitlines() if re.match(r"^[0-9]{2} [.A-Z?]{18}$", l)]
    assert len(rows) == 28 and all(set(l[3:]) == {"."} for l in rows)
    lowered = r.stdout.lower()
    for name in OFFICE_NAMES:
        assert re.search(r"\b" + name + r"\b", lowered) is None


def test_inspect_generic_png_driven_by_input(tmp_path):
    from PIL import Image
    im = Image.new("RGBA", (18, 28), (0, 0, 0, 0))
    px = im.load()
    for x in range(2, 6):
        for y in range(2, 6):
            px[x, y] = (10, 20, 30, 255)
    for x in range(8, 12):
        for y in range(8, 12):
            px[x, y] = (200, 100, 50, 255)
    p = tmp_path / "in.png"
    im.save(p)
    r = _run_cli("avatar", "inspect", str(p))
    assert r.returncode == 0, r.stderr
    assert "A = #0a141e" in r.stdout and "B = #c86432" in r.stdout
    assert "head" not in r.stdout and "torso" not in r.stdout  # no Office geometry
    r = _run_cli("avatar", "inspect", str(tmp_path / "noexiste.png"))
    assert r.returncode != 0


def test_codec_roundtrip_and_rejects():
    px = [255, 0, 0, 255, 0, 255, 0, 128, 0, 0, 255, 0, 1, 2, 3, 4]
    d = decodePNG(encode_png(2, 2, px))
    assert (d["w"], d["h"]) == (2, 2) and d["rgba"] == px
    with pytest.raises(ValueError, match="firma"):
        decodePNG(b"hola")
    with pytest.raises(ValueError, match="firma|decodifica|inesperado|sin IHDR"):
        decodePNG(blank_canvas()[:20])


def test_verify_matrix():
    rgba = [0] * (18 * 28 * 4)
    rgba[0:4] = [255, 0, 0, 255]
    good = encode_png(18, 28, rgba)
    assert verify_avatar(good, SPEC)["ok"] is True
    wrong = encode_png(10, 10, [1, 2, 3, 255] * 100)
    r = verify_avatar(wrong, SPEC)
    assert r["ok"] is False and re.search("dimensiones", r["reason"])
    opaque = encode_png(18, 28, [1, 2, 3, 255] * (18 * 28))
    assert re.search("sin canal alpha", verify_avatar(opaque, SPEC)["reason"])
    assert re.search("vacío", verify_avatar(blank_canvas(18, 28), SPEC)["reason"])
    assert re.search("decodifica", verify_avatar(b"basura", SPEC)["reason"])
    assert re.search("pesa", verify_avatar(good, dict(SPEC, maxBytes=10))["reason"])


def test_compilar_verb_gone():
    assert not (REPO / "tools" / "avatar_compilar.py").exists()
    r = _run_cli("avatar", "compilar", "piel morena")
    assert r.returncode != 0
    assert re.search("unknown avatar subcommand", r.stderr + r.stdout)
    row = next(l for l in (REPO / "docs" / "CLI.md").read_text().splitlines()
               if l.startswith("| `avatar`"))
    assert "compilar" not in row


# ─── editar (generic model edit; no cast anywhere in the path) ──────────────

def test_cli_editar_validates_without_network(tmp_path):
    png = tmp_path / "c.png"
    png.write_bytes(blank_canvas(18, 28))
    env = {"HOME": str(tmp_path)}
    r = _run_cli("avatar", "editar", "/noexiste.png", "--endpoint", "openai", "--model", "m", env=env)
    assert r.returncode != 0 and re.search("no existe", r.stderr + r.stdout)
    r = _run_cli("avatar", "editar", str(png), "--endpoint", "nope", "--model", "m", env=env)
    assert r.returncode != 0 and re.search("desconocido", r.stderr + r.stdout)
    r = _run_cli("avatar", "editar", str(png), "--endpoint", "anthropic", "--model", "m", env=env)
    assert r.returncode != 0 and re.search("openai-compatibles", r.stderr + r.stdout)
    e2 = dict(env)
    e2.pop("OPENAI_API_KEY", None)
    r = _run_cli("avatar", "editar", str(png), "--endpoint", "openai", "--model", "m", env=e2)
    assert r.returncode != 0 and re.search("OPENAI_API_KEY", r.stderr + r.stdout)


class _StubHandler(BaseHTTPRequestHandler):
    mode = "good"
    seen_auth = None

    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        raw = self.rfile.read(length)
        _StubHandler.seen_auth = self.headers.get("authorization")
        assert b"canvas.png" in raw, "imagen en el multipart"
        if self.mode == "big":
            png = encode_png(1024, 64, [5, 5, 5, 255] * (1024 * 64))
        else:
            rgba = [0] * (18 * 28 * 4)
            rgba[0:4] = [5, 5, 5, 255]
            png = encode_png(18, 28, rgba)
        body = json.dumps({"data": [{"b64_json": base64.b64encode(png).decode()}]}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_cli_editar_e2e_stub(tmp_path):
    png = tmp_path / "c.png"
    png.write_bytes(blank_canvas(18, 28))
    srv = HTTPServer(("127.0.0.1", 0), _StubHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    home = tmp_path / "home"
    home.mkdir()
    env = {"HOME": str(home), "OPENAI_API_KEY": "sk-FAKE-E2E-EDIT"}
    try:
        _StubHandler.mode = "good"
        r = _run_cli("avatar", "editar", str(png), "--endpoint", "openai", "--model", "m",
                     "--prompt", "x", "--si", "--base-url", base, env=env)
        assert r.returncode == 0, (r.stderr + r.stdout)[-300:]
        assert "válido instalado en pendientes" in r.stdout
        assert _StubHandler.seen_auth == "Bearer sk-FAKE-E2E-EDIT"
        installed = list((home / ".config" / "isymotron" / "avatars").glob("*.png"))
        assert len(installed) == 1
        d = decodePNG(installed[0].read_bytes())
        assert (d["w"], d["h"]) == (18, 28)
        _StubHandler.mode = "big"
        r = _run_cli("avatar", "editar", str(png), "--endpoint", "openai", "--model", "m",
                     "--prompt", "x", "--si", "--base-url", base, env=env)
        assert r.returncode == 2, "rechazo sale con código 2"
        assert "AVATAR_REJECTED" in r.stdout and "dimensiones" in r.stdout
        assert len(list((home / ".config" / "isymotron" / "avatars").glob("*.png"))) == 1
        bad = [str(p) for p in home.rglob("*") if p.is_file()
               and "sk-FAKE-E2E-EDIT" in p.read_text("utf-8", errors="ignore")]
        assert bad == [], f"fuga de key en: {bad}"
    finally:
        srv.shutdown()
