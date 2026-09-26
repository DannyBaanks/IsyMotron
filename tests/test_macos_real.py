"""Real macOS host gate (claim: parity matrix row for macOS).

Two groups live here deliberately:

- `test_mac_engine_refuses_to_exist_off_macos` runs everywhere: on Linux and
  Windows the engine must not even boot.
- Everything else is skipped off `darwin` and runs in CI on `macos-latest`
  (Apple Silicon), making the host claim real without Apple hardware in the
  loop.

Scoped like every other claim: process launch observation has no macOS source
yet (UnsupportedProcessSource), and awareness clocks are Linux-only.
"""
from __future__ import annotations

import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBJECT = "test:macos"


def test_mac_engine_refuses_to_exist_off_macos():
    if sys.platform == "darwin":
        pytest.skip("only meaningful off macOS")
    from mac.host import MacHost
    from windows.grants import Grants
    with pytest.raises(RuntimeError, match="darwin"):
        MacHost(Grants(host_id="x", display_name="x", granted=[], scopes={},
                       source="<test>"))


if sys.platform != "darwin":
    pytest.skip("real macOS engine (runs in CI on macos-latest)",
                allow_module_level=True)

from isymotron.contracts import ExecutionRequest          # noqa: E402
from isymotron.verdicts import Decision                    # noqa: E402
from mac.host import MacHost                               # noqa: E402
from windows.grants import Grants                          # noqa: E402


def make_host(granted, scopes) -> MacHost:
    return MacHost(Grants(host_id="mac-test", display_name="t", granted=list(granted),
                          scopes=dict(scopes), source="<test>"))


def act(host, capability, **params):
    lease, _ = host.request_lease(SUBJECT, capability, 120)
    req = ExecutionRequest.make(host.identify().host_id, SUBJECT, capability,
                                params, lease.lease_id if lease else None)
    return host.execute_capability(req)


@pytest.fixture
def box(tmp_path):
    (tmp_path / "granted").mkdir()
    (tmp_path / "secret").mkdir()
    (tmp_path / "secret" / "loot.txt").write_text("NEVER", encoding="utf-8")
    return tmp_path


def rw(box):
    root = {"roots": [str(box / "granted")]}
    return make_host(["filesystem.read", "filesystem.write"],
                     {"filesystem.read": root, "filesystem.write": root})


def test_identity_says_macos_and_the_mac_engine():
    host = make_host([], {})
    identity = host.identify()
    assert identity.os_family == "macos"
    assert identity.engine == "mac-real/0.1"
    assert identity.os_release.startswith("macos-")


def test_real_read_inside_scope(box):
    (box / "granted" / "a.txt").write_text("mac data", encoding="utf-8")
    out = act(rw(box), "filesystem.read", path=str(box / "granted" / "a.txt"))
    assert out.decision.decision is Decision.ALLOW
    assert out.result["text"] == "mac data"
    assert out.result["sha256"]


def test_real_read_outside_scope_is_denied_with_no_payload(box):
    out = act(rw(box), "filesystem.read", path=str(box / "secret" / "loot.txt"))
    assert out.decision.decision is Decision.DENY
    assert "text" not in (out.result or {})


def test_symlink_escape_is_denied(box):
    os.symlink(box / "secret" / "loot.txt", box / "granted" / "hole.txt")
    out = act(rw(box), "filesystem.read", path=str(box / "granted" / "hole.txt"))
    assert out.decision.decision is Decision.DENY


def test_real_write_creates_and_reports(box):
    out = act(rw(box), "filesystem.write",
              path=str(box / "granted" / "new.txt"), content="hello mac")
    assert out.decision.decision is Decision.ALLOW
    assert out.result["overwrote"] is False
    assert (box / "granted" / "new.txt").read_text(encoding="utf-8") == "hello mac"


def test_dotdot_is_denied(box):
    out = act(rw(box), "filesystem.read",
              path=str(box / "granted" / ".." / "secret" / "loot.txt"))
    assert out.decision.decision is Decision.DENY


def test_system_info_reports_the_real_machine():
    out = act(make_host(["system.info"], {"system.info": {}}), "system.info")
    assert out.decision.decision is Decision.ALLOW
    assert out.result["os"].startswith("macOS")
    assert out.result["engine"] == "mac-real/0.1"
    assert out.result["machine"]  # arm64 on the CI runner


def test_process_inspect_lists_real_processes():
    out = act(make_host(["process.inspect"], {"process.inspect": {}}),
              "process.inspect")
    assert out.decision.decision is Decision.ALLOW
    assert out.result["count"] > 0
    assert any("kernel" in name or "launchd" in name for name in out.result["processes"])


def test_app_not_on_allowlist_is_denied():
    host = make_host(["apps.launch"], {"apps.launch": {"allowlist": ["Safari"]}})
    out = act(host, "apps.launch", app="mailto")
    assert out.decision.decision is Decision.DENY
