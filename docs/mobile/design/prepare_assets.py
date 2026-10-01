"""Make the light WebP assets from a Companion checkout (main has Malbolgato v2).

    python3 docs/mobile/design/prepare_assets.py /path/to/Companion
"""
import sys
from pathlib import Path

from PIL import Image

pet = Path(sys.argv[1]) / "packs" / "malbolge-cat" / "codex-pet"
out = Path(__file__).parent / "assets"
out.mkdir(exist_ok=True)
for src, dst in (("spritesheet.webp", "malbolgato-v2-atlas.webp"), ("malbolgato-carry.png", "malbolgato-v2-carry.webp")):
    im = Image.open(pet / src).convert("RGBA")
    im = im.resize((int(im.width * 0.75), int(im.height * 0.75)), Image.LANCZOS)
    im.save(out / dst, "WEBP", quality=82, method=6)
    print(dst, im.size)
