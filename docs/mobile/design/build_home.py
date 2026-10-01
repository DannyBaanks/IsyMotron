"""Inline Malbolgato's six Companion GIFs (avatar/packs/malbolge-cat) into the home prototype."""
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
pack = ROOT / "avatar" / "packs" / "malbolge-cat"
manifest = json.loads((pack / "manifest.json").read_text())
html = (Path(__file__).parent / "home-malbolgato.src.html").read_text(encoding="utf-8")
for state, name in manifest["animations"].items():
    uri = "data:image/gif;base64," + base64.b64encode((pack / name).read_bytes()).decode()
    html = html.replace("{{" + state + "}}", uri)
assert "{{" not in html, "unfilled placeholder"
out = Path(sys.argv[1])
out.write_text(html, encoding="utf-8")
print(f"{out} {out.stat().st_size // 1024} KB")
