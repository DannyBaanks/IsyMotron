"""M4: link web panel. Existing console must stay pixel-identical."""
import json
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture()
def console(tmp_path, monkeypatch):
    import sys

    for path in (str(REPO), str(REPO / "core")):
        if path not in sys.path:
            sys.path.insert(0, path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
    from console.server import ConsoleState, serve
    from relay.loopback import LoopbackRelay

    relay = LoopbackRelay()
    state = ConsoleState(relay, None, str(tmp_path / "grants.json"))
    httpd, url = serve(state, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield state, base
    httpd.shutdown()
    httpd.server_close()


def get(base, path, token=None, expect=200):
    url = f"{base}{path}" + (f"?t={token}" if token else "")
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            assert resp.status == expect
            ctype = resp.headers.get("Content-Type", "")
            body = resp.read()
            return json.loads(body) if "json" in ctype else body
    except urllib.error.HTTPError as exc:
        assert exc.code == expect, f"expected {expect}, got {exc.code}"
        return json.loads(exc.read() or b"{}")


def post(base, path, body, token=None, expect=200):
    url = f"{base}{path}" + (f"?t={token}" if token else "")
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            assert resp.status == expect
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        assert exc.code == expect, f"expected {expect}, got {exc.code}"
        return json.loads(exc.read() or b"{}")


def test_link_page_and_assets_served(console):
    _, base = console
    page = get(base, "/link")
    assert b"Oficinas enlazadas" in page
    css = get(base, "/link.css")
    assert b".link-card" in css
    js = get(base, "/link.js")
    assert b"/api/link" in js


def test_link_css_has_no_global_rules():
    css = (REPO / "console" / "static" / "link.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    for chunk in css.split("}"):
        if "{" not in chunk:
            continue
        selectors = chunk.split("{")[0]
        for selector in selectors.split(","):
            selector = selector.strip()
            if selector:
                assert selector.startswith(".link-"), selector


def test_api_link_needs_token(console):
    state, base = console
    get(base, "/api/link", expect=401)
    status = get(base, "/api/link", token=state.token)
    assert "office" in status and "peers" in status and "inbox_queued" in status
    assert status["peers"] == []


def test_delegate_unknown_office_fails_clean(console):
    state, base = console
    body = post(
        base, "/api/link/delegate",
        {"to": "nadie", "title": "t", "body": "b"},
        token=state.token, expect=502,
    )
    assert "error" in body


def test_forget_unknown_is_404(console):
    state, base = console
    post(base, "/api/link/forget", {"query": "nadie"}, token=state.token, expect=404)


def test_avatar_token_stays_read_only(console):
    state, base = console
    post(
        base, "/api/link/delegate",
        {"to": "x", "title": "t", "body": "b"},
        token=state.avatar_token, expect=403,
    )


def test_existing_index_untouched(console):
    _, base = console
    page = get(base, "/")
    assert b"IsyMotron" in page or b"isymotron" in page.lower()
