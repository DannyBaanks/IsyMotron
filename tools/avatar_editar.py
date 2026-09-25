#!/usr/bin/env python3
"""isymotron avatar editar -- edita un PNG con un modelo (endpoint openai-compatible).

La key viaja SOLO en el header Authorization de una llamada que el usuario
pidió explícitamente; jamás se imprime, loguea ni escribe.
"""
from __future__ import annotations

import base64
import json
import os
import random
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

for _path in (REPO, REPO / "core"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.isymotron.avatar import AVATAR_MAX_BYTES, decodePNG, verify_avatar

ENDPOINTS = [
    {"id": "openai", "label": "OpenAI", "baseURL": "https://api.openai.com/v1",
     "keyEnv": "OPENAI_API_KEY", "wire": "openai-compatible"},
    {"id": "anthropic", "label": "Anthropic", "baseURL": "https://api.anthropic.com",
     "keyEnv": "ANTHROPIC_API_KEY", "wire": "nativo"},
    {"id": "google", "label": "Google (Gemini)", "baseURL": "https://generativelanguage.googleapis.com",
     "keyEnv": "GEMINI_API_KEY", "wire": "nativo"},
    {"id": "nvidia", "label": "NVIDIA NIM", "baseURL": "https://integrate.api.nvidia.com/v1",
     "keyEnv": "NVIDIA_API_KEY", "wire": "openai-compatible"},
    {"id": "groq", "label": "Groq", "baseURL": "https://api.groq.com/openai/v1",
     "keyEnv": "GROQ_API_KEY", "wire": "openai-compatible"},
    {"id": "openrouter", "label": "OpenRouter", "baseURL": "https://openrouter.ai/api/v1",
     "keyEnv": "OPENROUTER_API_KEY", "wire": "openai-compatible"},
    {"id": "deepseek", "label": "DeepSeek", "baseURL": "https://api.deepseek.com/v1",
     "keyEnv": "DEEPSEEK_API_KEY", "wire": "openai-compatible"},
    {"id": "mistral", "label": "Mistral", "baseURL": "https://api.mistral.ai/v1",
     "keyEnv": "MISTRAL_API_KEY", "wire": "openai-compatible"},
    {"id": "xai", "label": "xAI", "baseURL": "https://api.x.ai/v1",
     "keyEnv": "XAI_API_KEY", "wire": "openai-compatible"},
    {"id": "together", "label": "Together AI", "baseURL": "https://api.together.xyz/v1",
     "keyEnv": "TOGETHER_API_KEY", "wire": "openai-compatible"},
]

# Semilla de restricciones M10 (compacta, en inglés: los modelos de imagen
# entrenan mayormente en inglés). Idéntica al canon.
AVATAR_EDIT_SUFFIX = ("Pixel art, exactly 18x28 pixels, transparent background, "
                      "no background, no text, facing forward, sharp pixels, office worker portrait")

SPEC = {"w": 18, "h": 28, "needAlpha": True, "maxBytes": AVATAR_MAX_BYTES}


class EndpointNoEdita(Exception):
    pass


def _base36(n: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
        return "0"
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = digits[r] + out
    return out


def _pending_dir() -> Path:
    # Pendientes fuera de repos (input futuro, no canónicos).
    d = Path.home() / ".config" / "isymotron" / "avatars"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _multipart(image_buf: bytes, fields: dict) -> tuple[bytes, str]:
    boundary = "----isymotron" + _base36(int(time.time() * 1000)) + _base36(random.randrange(36 ** 6))
    parts: list[bytes] = []

    def push(s) -> None:
        parts.append(s if isinstance(s, bytes) else str(s).encode("utf-8"))

    for k, v in fields.items():
        push(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    push(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
         f'filename="canvas.png"\r\nContent-Type: image/png\r\n\r\n')
    push(image_buf)
    push("\r\n")
    push(f"--{boundary}--\r\n")
    return b"".join(parts), boundary


def edit_image_endpoint(*, base_url: str, key: str, model: str, image_buf: bytes, prompt: str) -> bytes:
    """POST {baseURL}/images/edits (OpenAI-compatible). Devuelve el PNG resultante."""
    body, boundary = _multipart(image_buf, {"model": model, "prompt": prompt})
    req = urllib.request.Request(
        base_url.rstrip("/") + "/images/edits",
        data=body,
        headers={"content-type": f"multipart/form-data; boundary={boundary}",
                 "authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as res:
            status = res.status
            raw = res.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise EndpointNoEdita("endpoint-no-edita")
        try:
            text = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            text = ""
        raise RuntimeError(f"el endpoint respondió {e.code}: {text}")
    except Exception as e:
        raise RuntimeError(f"sin respuesta del endpoint ({e})")
    if status == 404:
        raise EndpointNoEdita("endpoint-no-edita")
    if status < 200 or status >= 300:
        raise RuntimeError(f"el endpoint respondió {status}: {raw[:200].decode('utf-8', 'replace')}")
    try:
        j = json.loads(raw.decode("utf-8"))
    except Exception:
        j = None
    item = (j or {}).get("data", [None])[0] if isinstance((j or {}).get("data"), list) else None
    if item and item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item and item.get("url"):
        try:
            with urllib.request.urlopen(item["url"], timeout=120) as dl:
                return dl.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"el endpoint devolvió URL pero no se pudo descargar ({e.code})")
        except Exception as e:
            raise RuntimeError(f"el endpoint devolvió URL pero no se pudo descargar ({e})")
    raise RuntimeError("el endpoint no devolvió imagen (sin b64_json ni url)")


def main(argv: list[str] | None = None) -> int:
    # A redirected Windows stdout is cp1252: a glyph it lacks (✓, ●) must
    # degrade to '?', never crash the verb after its work is done.
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(errors="replace")
    import argparse
    parser = argparse.ArgumentParser(
        prog="isymotron avatar editar",
        description="Edita un PNG con un modelo (endpoint openai-compatible)",
    )
    parser.add_argument("png", help="PNG a editar")
    parser.add_argument("--endpoint", "-e", help="Endpoint: " + ", ".join(e["id"] for e in ENDPOINTS))
    parser.add_argument("--model", "-m", help="Modelo que edita")
    parser.add_argument("--prompt", "-p", help="Qué pintar sobre el lienzo")
    parser.add_argument("--key-env", help="Variable con la API key (default: la del endpoint)")
    parser.add_argument("--base-url", help="Override para gateways propios/proxies/self-hosted")
    parser.add_argument("--si", "--yes", dest="si", action="store_true", help="Omitir confirmación")
    args = parser.parse_args(argv)

    if not args.png:
        print("uso: isymotron avatar editar <png> --endpoint <id> --model <id> [--key-env VAR] "
              "[--prompt \"...\"] [--si]", file=sys.stderr)
        return 1
    abs_png = Path(args.png).expanduser()
    if not abs_png.is_absolute():
        abs_png = Path.cwd() / abs_png
    if not abs_png.exists():
        print(f"no existe: {abs_png}", file=sys.stderr)
        return 1
    endpoint = next((e for e in ENDPOINTS if e["id"] == (args.endpoint or "")), None)
    if not endpoint:
        print(f"endpoint desconocido '{args.endpoint or ''}'. "
              f"Opciones: {', '.join(e['id'] for e in ENDPOINTS)}", file=sys.stderr)
        return 1
    if endpoint["wire"] != "openai-compatible":
        print(f"{endpoint['label']} es wire '{endpoint['wire']}': edición de imágenes solo "
              "para endpoints openai-compatibles por ahora.", file=sys.stderr)
        return 1
    if not args.model:
        print("falta --model (¿qué modelo edita?).", file=sys.stderr)
        return 1
    base_url = endpoint["baseURL"]
    if args.base_url:
        if not args.base_url.startswith(("http://", "https://")):
            print("--base-url debe empezar con http:// o https://", file=sys.stderr)
            return 1
        base_url = args.base_url
    key_name = args.key_env or endpoint["keyEnv"]
    key = os.environ.get(key_name)
    if not key:
        print(f"falta {key_name} en el entorno. Expórtala (export {key_name}=...) e inténtalo de nuevo.",
              file=sys.stderr)
        return 1
    prompt = args.prompt
    if not prompt:
        if not sys.stdin.isatty():
            print("falta --prompt y no hay TTY para pedirlo.", file=sys.stderr)
            return 1
        try:
            prompt = input("  Describe la edición (qué pintar sobre el lienzo): ").strip()
        except EOFError:
            prompt = ""
        if not prompt:
            print("sin prompt, cancelado.", file=sys.stderr)
            return 1
    full_prompt = f"{prompt} {AVATAR_EDIT_SUFFIX}"

    print()
    print("  Revisa antes de enviar (llamada con costo potencial):")
    print(f"    endpoint: {endpoint['label']} ({base_url})")
    print(f"    modelo:   {args.model}")
    print(f"    imagen:   {abs_png} ({abs_png.stat().st_size} bytes)")
    print(f"    key:      ● {key_name} (en memoria, no se guarda ni se muestra)")
    if not args.si:
        try:
            ans = input("¿Enviar a edición? [s/N] ").strip().lower()
        except EOFError:
            ans = ""
        if ans not in ("s", "si", "sí", "y", "yes"):
            print("cancelado: nada se envió.")
            return 0

    image_buf = abs_png.read_bytes()
    try:
        out_buf = edit_image_endpoint(base_url=base_url, key=key, model=args.model,
                                      image_buf=image_buf, prompt=full_prompt)
    except EndpointNoEdita:
        print("el endpoint respondió 404: ESTE endpoint no edita imágenes. Prueba con otro "
              "(p. ej. OpenAI) o genera por otra vía (compilar/manual). Nada se cobró en vano: "
              "no se reintentó.", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1

    # M11: verificar antes de instalar. Sin reescalados mágicos.
    v = verify_avatar(out_buf, SPEC)
    if not v["ok"]:
        print(f"  AVATAR_REJECTED: {v['reason']}")
        print("  (la salida no se instaló en ningún lado)")
        return 2
    dest = _pending_dir() / f"avatar-{_base36(int(time.time() * 1000))}.png"
    dest.write_bytes(out_buf)
    d = decodePNG(out_buf)
    print("  ✓ avatar válido instalado en pendientes:")
    print(f"    {dest} ({d['w']}x{d['h']}, {v['info']['bytes']} bytes, con alpha)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
