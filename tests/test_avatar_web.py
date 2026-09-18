"""AV4 tests: the web renderer and its pack.

The avatar must draw only what the server stamped. The pack is served through
the exact-name allowlist; the avatar JS injects text only via textContent.
The pre-existing console renderers (app.js) keep their own esc()+innerHTML
convention from before AV4; the avatar renderer is a separate file exactly
so the stricter rule can be enforced on it.
"""

from __future__ import annotations

import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from console.server import PACK_DIR, PACK_MIME, PACK_SERVABLE, ConsoleState, serve
from isymotron.awareness import HostAwarenessEngine, TestPowerProvider
from relay.loopback import LoopbackRelay
from simulator.engines import LegacyHost, ModernHost

STATIC_DIR = Path(__file__).resolve().parents[1] / "console" / "static"


@pytest.fixture
def console(tmp_path):
    relay = LoopbackRelay()
    relay.attach(ModernHost(
        fs={"C:/Photos/a.png": "AAA"},
        granted=["filesystem.read", "system.info"],
        grant_scopes={"filesystem.read": {"roots": ["C:/Photos"]}, "system.info": {}},
    ))
    relay.attach(LegacyHost(
        fs={"C:/NEMO/INBOX/.keep": ""},
        granted=["filesystem.write"],
        grant_scopes={"filesystem.write": {"roots": ["C:/NEMO/INBOX"]}},
    ))
    awareness = HostAwarenessEngine("win11-victus", TestPowerProvider())
    state = ConsoleState(relay, awareness, str(tmp_path / "grants.json"))
    httpd, _ = serve(state, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield state, base
    httpd.shutdown()
    httpd.server_close()


def fetch(base, path, token=None):
    sep = "&" if "?" in path else "?"
    url = f"{base}{path}" + (f"{sep}t={token}" if token else "")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, "", exc.read()


def test_pack_files_are_served_by_allowlist_only(console):
    state, base = console
    on_disk = set()
    for root, _dirs, files in os.walk(PACK_DIR):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), PACK_DIR).replace("\\", "/")
            if Path(fn).suffix.lower() in PACK_MIME:
                on_disk.add("avatar/packs/" + rel)
    assert set(PACK_SERVABLE) == on_disk, "the allowlist is exactly the pack"
    assert any(n.endswith(".gif") for n in PACK_SERVABLE), "the pack ships GIFs"
    for name, ctype in PACK_SERVABLE.items():
        status, got, _body = fetch(base, "/" + name, token=state.avatar_token)
        assert status == 200, name
        assert got == ctype, name
    status, _, _ = fetch(base, "/avatar/packs/nope.gif", token=state.avatar_token)
    assert status == 404


def test_no_directory_traversal_into_packs(console):
    state, base = console
    for evil in ("/avatar/packs/../console/server.py",
                 "/avatar/packs/malbolge-cat/../../../console/server.py",
                 "/avatar/packs/..%2fconsole%2fserver.py",
                 "/avatar/packs/malbolge-cat%2f..%2f..%2fserver.py",
                 "/avatar/packs/malbolge-cat/../NOTICE"):
        status, _, _ = fetch(base, evil, token=state.avatar_token)
        assert status == 404, evil


def test_static_js_never_uses_innerHTML():
    js = (STATIC_DIR / "avatar.js").read_text(encoding="utf-8")
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML",
                      "document.write"):
        assert forbidden not in js, \
            f"the avatar renderer must not use {forbidden}"


def test_index_loads_the_avatar_renderer():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert 'src="avatar.js"' in html
    assert 'src="app.js"' in html
    assert 'id="avatar-gif"' in html
    assert 'id="avatar-frame"' in html
    assert 'id="avatar-bubbles"' in html
