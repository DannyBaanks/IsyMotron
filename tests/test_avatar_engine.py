"""Avatar engine tests (portrait core + compiler + CLI verbs). Self-contained.

Espejo de ISyCo/tools/munder-cli/avatar.test.cjs adaptado a Python, sin red
salvo stub local, sin GUI. Sin dependencias entre repos: los goldens se
fijaron por verificacion diferencial contra node (no se lee el checkout
canonico en tiempo de test).

Origen del port:
  avatar-engine.cjs sha256:8338fde3df3c2c82431d8766b7ee37d19956b70294b9ba4c95d943d01898597e
  lib-avatar.cjs    sha256:922dd1bd2721b98aae044893c9c88b630baa75367386ed1d7896c96d3c76c7d9
Si el canon cambia, re-portar core/isymotron/avatar.py + avatar_parser.py y
regenerar GOLDENS (ver NOTA al pie).
"""

import base64
import hashlib
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
    AVATAR_RECIPES,
    AVATAR_VOCAB,
    blank_canvas,
    compose_avatar,
    decodePNG,
    encode_png,
    verify_avatar,
)
from core.isymotron.avatar_parser import (
    compile_avatar,
    parse_avatar_desc,
    validate_avatar_recipe,
)

SPEC = {"w": 18, "h": 28, "needAlpha": True, "maxBytes": AVATAR_MAX_BYTES}

# Goldens byte-exactos por personaje (sha256 del RGBA 18x28). Fijados por
# diferencial contra node avatar-engine.cjs@8338fde3 (15/15 identicos).
GOLDENS = {
    "michael": "de27499f620c82c80dbaaa52e871f1683197f1da2278cb6f77cc450e4452f7f8",
    "jim": "36b43961a12724bd4dfefb09a0019146d13911f566b2dfe35b3413eb42b76017",
    "pam": "341bd712df170282f0a32c4f3a4a7fc2427026ceae0f87662b1b07d4acaf84b7",
    "dwight": "17ba64aa2185eca733b94a866fc11ef72690129dad290742016b19b6a4143ebd",
    "kevin": "2758e942adb912d83bad7ae43def367174e6da25c0c0604eac770d965ed666f5",
    "angela": "e19ad39ecf07dc90a69c23795835ed6a36712bfe92dc15fda046d4a1209e8b2b",
    "oscar": "a3b4c09b9952621407593d8d2ac7f43909ad579223668999e0a0b611ca459fee",
    "stanley": "4a8f4c0123170e73219ed7c0e4d83de8e1e150212642aa416f3ddec58025db9a",
    "phyllis": "e9e2d151e1e54e53532889556d1ee04dbe805d0ae531aaa054167b110d11d0d5",
    "andy": "d652906bf746ec301f444a4f2ffb1acaf168e7e463dde48b582bcb4a0813a6dd",
    "kelly": "0bd5fec9826f6a06a96406e3935f2b74d59ba51e1ca7fcd3a66980c57a0dcf40",
    "ryan": "16aec29f54f08dfd99a2bce34fb9e9bc594b48d401100e07c5c6d224c2c0ee2a",
    "toby": "fdd33d0e02ca225141a99e8a397ce8872c81a461f8317295560b4f704a7ea61e",
    "creed": "d92f4ab730a5554aac3e0f1f28532063ae6a09cc4ca3f23ffbfa1fd7d5156f46",
    "meredith": "7fcf5f1bcbfa62e886379578ebf4ab0fd3b63b4551ac489276b512389157b054",
}


def _buf(name):
    return bytes(compose_avatar(AVATAR_RECIPES[name]))


def _alpha_counts(buf):
    opaque = transparent = 0
    for i in range(3, len(buf), 4):
        if buf[i] == 255:
            opaque += 1
        elif buf[i] == 0:
            transparent += 1
    return opaque, transparent


# ─── engine ───────────────────────────────────────────────────────────────

def test_cast_buffers_pinned():
    assert set(GOLDENS) == set(AVATAR_RECIPES), "goldens y cast deben coincidir"
    for name, golden in GOLDENS.items():
        assert hashlib.sha256(_buf(name)).hexdigest() == golden, f"{name} cambió"


def test_cast_regression():
    names = list(AVATAR_RECIPES)
    assert len(names) >= 14, f"cast completo, hay {len(names)}"
    for n in names:
        assert validate_avatar_recipe(AVATAR_RECIPES[n], AVATAR_VOCAB) == [], f"{n} valida"
        buf = compose_avatar(AVATAR_RECIPES[n])
        assert len(buf) == 18 * 28 * 4, f"{n} dims"
        opaque, transparent = _alpha_counts(bytes(buf))
        assert opaque > 50, f"{n} tiene cuerpo opaco"
        assert transparent > 50, f"{n} tiene fondo transparente"


def test_vocab_covers_frontend():
    for k in ("skins", "hairs", "cloths", "facials", "brows", "mouths"):
        assert isinstance(AVATAR_VOCAB[k], list) and AVATAR_VOCAB[k], f"vocab {k}"
    assert "styleShort" in AVATAR_VOCAB["hairs"] and "styleBald" in AVATAR_VOCAB["hairs"]


# ─── parser ───────────────────────────────────────────────────────────────

def test_parse_categories():
    r = parse_avatar_desc("piel morena, pelo negro corto, camisa azul, gafas")
    assert r["recipe"]["skin"] == "tan"
    assert r["recipe"]["hair"] == "styleShort"
    assert r["recipe"]["hairc"] == [30, 22, 18]
    assert r["recipe"]["cloth"] == "dressshirt"
    assert r["recipe"]["c1"] == [110, 140, 180]
    assert r["recipe"]["glasses"] is True
    assert r["warnings"] == []
    assert len(r["matched"]) >= 5


def test_parse_last_wins():
    r = parse_avatar_desc("camisa azul, no, roja")
    assert r["recipe"]["c1"] == [176, 65, 58]


def test_parse_warnings():
    r = parse_avatar_desc("piel morena con ojos verdes y sombrero")
    assert any("ojos verdes" in w for w in r["warnings"])
    assert any("sombrero" in w for w in r["warnings"])


def test_parse_empty_uses_neutral_base():
    r = parse_avatar_desc("")
    assert r["warnings"] and r["recipe"]["skin"] == "light"


def test_parse_case_and_accents():
    r = parse_avatar_desc("Piel OSCURA, Pelo RUBIO largo, Traje NEGRO, bigote, BARBA de días")
    assert r["recipe"]["skin"] == "dark"
    assert r["recipe"]["hair"] == "styleFrame"
    assert r["recipe"]["hairc"] == [190, 158, 95]


def test_parse_orphan_modifier_inherits_ctx():
    r = parse_avatar_desc("pelo negro con pinchos")
    assert r["recipe"]["hair"] == "styleSpiky"
    assert r["warnings"] == []


def test_parse_unknown_still_warns():
    r = parse_avatar_desc("camisa azul con rayas")
    assert r["recipe"]["cloth"] == "dressshirt"
    assert any("rayas" in w for w in r["warnings"])


def test_compile_e2e():
    c = compile_avatar("piel morena, pelo negro corto, camisa azul, gafas")
    assert c["recipe"]["skin"] == "tan"
    d = decodePNG(c["png"])
    assert (d["w"], d["h"]) == (18, 28)
    v = verify_avatar(c["png"], SPEC)
    assert v["ok"], f"verify: {v.get('reason')}"
    assert c["warnings"] == []


# ─── codec + verify ───────────────────────────────────────────────────────

def test_codec_roundtrip():
    px = [255, 0, 0, 255, 0, 255, 0, 128, 0, 0, 255, 0, 1, 2, 3, 4]
    d = decodePNG(encode_png(2, 2, px))
    assert (d["w"], d["h"]) == (2, 2)
    assert d["rgba"] == px


def test_codec_rejects_garbage():
    with pytest.raises(ValueError, match="firma"):
        decodePNG(b"hola")
    with pytest.raises(ValueError, match="firma|decodifica|inesperado|sin IHDR"):
        decodePNG(blank_canvas()[:20])


def test_lienzo_blank():
    d = decodePNG(blank_canvas(18, 28))
    assert (d["w"], d["h"]) == (18, 28)
    assert all(a == 0 for a in d["rgba"][3::4])


def test_verify_matrix():
    rgba = [0] * (18 * 28 * 4)
    rgba[0:4] = [255, 0, 0, 255]
    good = encode_png(18, 28, rgba)
    assert verify_avatar(good, SPEC)["ok"] is True
    wrong_dims = encode_png(10, 10, [1, 2, 3, 255] * 100)
    r = verify_avatar(wrong_dims, SPEC)
    assert r["ok"] is False and re.search("dimensiones", r["reason"])
    opaque = encode_png(18, 28, [1, 2, 3, 255] * (18 * 28))
    assert re.search("sin canal alpha", verify_avatar(opaque, SPEC)["reason"])
    assert re.search("vacío", verify_avatar(blank_canvas(18, 28), SPEC)["reason"])
    assert re.search("decodifica", verify_avatar(b"basura", SPEC)["reason"])
    tiny = dict(SPEC, maxBytes=10)
    assert re.search("pesa", verify_avatar(good, tiny)["reason"])


# ─── CLI ──────────────────────────────────────────────────────────────────

def _run_cli(*args, env=None, cwd=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, str(REPO / "tools" / "isymotron_cli.py"), *args],
        capture_output=True, text=True, timeout=60, cwd=str(cwd or REPO), env=e,
    )


def test_cli_inspect_matrix(tmp_path):
    r = _run_cli("avatar", "inspect", "pam")
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0].startswith("CANVAS 18x28")
    rows = [l for l in r.stdout.splitlines() if re.match(r"^[0-9]{2} [.A-Z?]{18}$", l)]
    assert len(rows) == 28
    assert re.search(r"^[A-Z] = #[0-9a-f]{6}$",
                     next(l for l in r.stdout.splitlines() if re.match(r"^[A-Z] = #", l)),
                     re.M)
    assert "eyes" in r.stdout and "torso" in r.stdout
    png = tmp_path / "x.png"
    png.write_bytes(blank_canvas(18, 28))
    r = _run_cli("avatar", "inspect", str(png))
    assert r.returncode == 0 and "CANVAS 18x28" in r.stdout
    r = _run_cli("avatar", "inspect", "nadie-existe-ni-archivo")
    assert r.returncode != 0
    assert re.search("ni personaje|Personajes", r.stderr + r.stdout)


def test_cli_compilar(tmp_path):
    out = tmp_path / "pj.png"
    r = _run_cli("avatar", "compilar", "piel clara, pelo rubio corto, traje negro",
                 "--salida", str(out))
    assert r.returncode == 0, r.stderr[-200:]
    assert "avatar compilado" in r.stdout
    d = decodePNG(out.read_bytes())
    assert (d["w"], d["h"]) == (18, 28)
    r = _run_cli("avatar", "compilar", "   ", "--salida", str(tmp_path / "x.png"))
    assert r.returncode != 0


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
            rgba = [5, 5, 5, 255] * (1024 * 64)
            png = encode_png(1024, 64, rgba)
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


# NOTA re-port: si avatar-engine.cjs o lib-avatar.cjs cambian en el canon,
# portar de nuevo core/isymotron/avatar.py + avatar_parser.py, re-correr el
# diferencial contra node y regenerar GOLDENS con:
#   python3 -c "import sys,hashlib; sys.path.insert(0,'.'); sys.path.insert(0,'core')
#   from core.isymotron.avatar import compose_avatar,AVATAR_RECIPES
#   [print(repr(n), hashlib.sha256(bytes(compose_avatar(r))).hexdigest())
#    for n,r in AVATAR_RECIPES.items()]"
