"""AV5 tests: the desktop avatar.

The pet is Companion's window, minus everything that could act: no State
menu, no pack editing, no file writes, and a transport that only ever GETs
with the read-only avatar token (R5).
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

import pytest

from console.server import ConsoleState, serve
from isymotron.awareness import HostAwarenessEngine, TestPowerProvider
from relay.loopback import LoopbackRelay
from simulator.engines import LegacyHost, ModernHost

WINDOW_SRC = Path(__file__).resolve().parents[1] / "avatar" / "window.py"
STATES = {"idle", "thinking", "working", "success", "error", "waiting", "hidden"}


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
    yield state, httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def test_window_module_imports_without_display():
    try:
        import tkinter  # noqa: F401
    except ImportError:
        pytest.skip("no tkinter on this host")
    # Importing the module must not open a window: prove it in a subprocess.
    code = "import avatar.window; print('ok')"
    repo = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-c", code], cwd=str(repo),
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout


def test_window_has_no_write_paths():
    src = WINDOW_SRC.read_text(encoding="utf-8")
    assert "append_jsonl" not in src, "the pet never writes the inbox"
    pos = src.find("open(")
    while pos != -1:
        seg = src[pos: pos + 120]
        for needle in ('"w"', "'w'", '"a"', "'a'"):
            assert needle not in seg, f"write mode {needle} near open( at {pos}"
        pos = src.find("open(", pos + 1)


def test_avatar_client_uses_read_only_token(tmp_path, console):
    state, port = console
    token_file = tmp_path / "avatar.token"
    token_file.write_text(state.avatar_token, encoding="utf-8")
    from avatar.window import AvatarClient
    client = AvatarClient(port, token_path=token_file)
    view = client.view()
    assert view is not None
    assert view["state"] in STATES
    # the transport has no write surface at all
    src = WINDOW_SRC.read_text(encoding="utf-8")
    assert "POST" not in src, "the pet's transport never writes"
    assert not hasattr(client, "post")


def test_pet_body_renders_without_console():
    """The 2x17 bug (2026-09-19): `isymotron pet` with no console running
    showed nothing -- the window collapsed to a 2x17 sliver because the body
    label was never configured with an image or a text when no view arrived.
    With a dead client the pet must render its own offline body.

    Run in a subprocess (the module-Import pattern above) because this opens
    a real Tk root; the window is withdrawn before it can paint to screen.
    """
    try:
        import tkinter  # noqa: F401
    except ImportError:
        pytest.skip("no tkinter on this host")
    repo = Path(__file__).resolve().parents[1]
    code = (
        "from avatar.window import AvatarWindow, _pack_root\n"
        "from avatar.pack import AssetPack\n"
        "class DeadClient:\n"
        "    def view(self):\n"
        "        return None\n"
        "w = AvatarWindow(DeadClient(), AssetPack.load(_pack_root() / 'malbolge-cat'))\n"
        "w.root.withdraw()\n"
        "w.root.update_idletasks()\n"
        "label = w.image_label\n"
        "body = bool(label.cget('image')) or bool(label.cget('text'))\n"
        "print('REQ %d %d BODY %s' % (label.winfo_reqwidth(), label.winfo_reqheight(), body))\n"
        "print('OK' if body and label.winfo_reqwidth() > 8 else 'DEGENERATE')\n"
        "w.root.destroy()\n"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=str(repo),
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert "DEGENERATE" not in r.stdout, r.stdout
    assert "BODY True" in r.stdout, r.stdout
