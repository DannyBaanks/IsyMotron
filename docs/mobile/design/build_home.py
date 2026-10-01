"""Build the home prototype: inline Malbolgato v2's sprite atlas and carry sheet as data URIs.

The two WebP files in assets/ come from Companion main (packs/malbolge-cat/codex-pet,
commit ffa2b13, MIT, same author), scaled to 0.75 and re-encoded so the page loads fast
on a phone. Regenerate them with prepare_assets.py.

    python3 docs/mobile/design/build_home.py /tmp/inicio-malbolgato.html
"""
import base64
import sys
from pathlib import Path

HERE = Path(__file__).parent
html = (HERE / "home-malbolgato.src.html").read_text(encoding="utf-8")
for key, name in (("atlas", "malbolgato-v2-atlas.webp"), ("carry", "malbolgato-v2-carry.webp")):
    uri = "data:image/webp;base64," + base64.b64encode((HERE / "assets" / name).read_bytes()).decode()
    html = html.replace("{{" + key + "}}", uri)
assert "{{" not in html, "unfilled placeholder"
out = Path(sys.argv[1])
out.write_text(html, encoding="utf-8")
print(f"{out} {out.stat().st_size // 1024} KB")
