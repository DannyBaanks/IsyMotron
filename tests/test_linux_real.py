"""M2 gate -- what only Linux can do to a host, against the real engine.

The rows every OS shares live in tests/test_host_parity.py. This file is the
Linux-specific adversary: case-sensitive names, dangling symlinks, FIFOs,
hard links, a name swapped between check and open, and the pre-M2 path by
which the Windows engine ran here.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

import pytest

if not sys.platform.startswith("linux"):
    pytest.skip("real Linux engine", allow_module_level=True)

from isymotron.contracts import ExecutionRequest
from isymotron.verdicts import Decision, DenyReason
from linux.host import LinuxHost
from windows.grants import Grants

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBJECT = "test:linux"


def make_host(granted, scopes) -> LinuxHost:
    return LinuxHost(Grants(host_id="linux-test", display_name="t", granted=list(granted),
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


# -- the Windows engine cannot run here any more ----------------------------

def test_windows_engine_refuses_to_exist_on_linux():
    from windows.win11 import Win11Host
    with pytest.raises(RuntimeError, match="Windows engine"):
        Win11Host(Grants.inert("test"))


def test_host_cli_uses_the_linux_engine_and_denies_the_case_escape(tmp_path):
    """Regression for the measured pre-M2 escape: `host_cli do` ran Win11Host
    here, and a root `.../Photos` handed over `.../photos/loot.txt`."""
    (tmp_path / "Photos").mkdir()
    (tmp_path / "photos").mkdir()
    (tmp_path / "photos" / "loot.txt").write_text("SECRET", encoding="utf-8")
    grants = tmp_path / "grants.json"
    Grants(host_id="linux-cli", display_name="t", granted=["filesystem.read"],
           scopes={"filesystem.read": {"roots": [str(tmp_path / "Photos")]}}).save(str(grants))
    cli = [sys.executable, os.path.join(REPO, "tools", "host_cli.py"), "--grants", str(grants)]
    status = subprocess.run(cli + ["status"], capture_output=True, text=True, timeout=60)
    assert "linux-real/" in status.stdout and "nt-real" not in status.stdout
    r = subprocess.run(cli + ["do", "filesystem.read", "--path",
                              str(tmp_path / "photos" / "loot.txt")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 1
    assert "DENY OUT_OF_SCOPE" in r.stdout and "SECRET" not in r.stdout


def test_default_grant_file_follows_xdg(tmp_path, monkeypatch):
    import importlib
    import windows.grants as wg
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert wg._default_path() == str(tmp_path / "isymotron" / "grants.json")
    assert Grants.inert("t").host_id.startswith("linux-")
    importlib.reload(wg)  # leave the module as found


# -- names that only a case-sensitive, symlink-rich filesystem has ----------

def test_case_variant_is_a_different_directory(box):
    (box / "GRANTED").mkdir()
    (box / "GRANTED" / "loot.txt").write_text("OTHER", encoding="utf-8")
    host = rw(box)
    lease, _ = host.request_lease(SUBJECT, "filesystem.read", 120)
    req = ExecutionRequest.make("linux-test", SUBJECT, "filesystem.read",
                                {"path": str(box / "GRANTED" / "loot.txt")}, lease.lease_id)
    assert host._enforcer.decide(req, lease).decision is Decision.ALLOW, \
        "the lexical check folds case; the engine must not"
    r = host.execute_capability(req)
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE and r.result == {}
    w = act(host, "filesystem.write", path=str(box / "GRANTED" / "new.txt"), content="x")
    assert w.decision.reason is DenyReason.OUT_OF_SCOPE
    assert not (box / "GRANTED" / "new.txt").exists()


def test_dangling_symlink_cannot_create_a_file_outside(box):
    os.symlink(box / "secret" / "created.txt", box / "granted" / "evil")
    r = act(rw(box), "filesystem.write", path=str(box / "granted" / "evil"), content="x")
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE
    assert not (box / "secret" / "created.txt").exists()


def test_file_symlink_escape_read(box):
    os.symlink(box / "secret" / "loot.txt", box / "granted" / "link.txt")
    r = act(rw(box), "filesystem.read", path=str(box / "granted" / "link.txt"))
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE and r.result == {}


def test_symlink_inside_the_root_is_followed(box):
    """Parity with Windows: a link that resolves INSIDE the root is fine."""
    (box / "granted" / "real.txt").write_text("dentro", encoding="utf-8")
    os.symlink(box / "granted" / "real.txt", box / "granted" / "alias.txt")
    r = act(rw(box), "filesystem.read", path=str(box / "granted" / "alias.txt"))
    assert r.decision.decision is Decision.ALLOW and r.result["text"] == "dentro"


def test_listing_does_not_stat_through_links(box):
    os.symlink(box / "secret", box / "granted" / "outside")
    r = act(rw(box), "filesystem.read", path=str(box / "granted"))
    entry = next(e for e in r.result["entries"] if e["name"] == "outside")
    assert entry.get("symlink") is True and entry["kind"] == "file", \
        "a link is described as itself, never by its (outside) target"


# -- inodes that are not documents -------------------------------------------

def test_fifo_read_is_refused_without_hanging(box):
    os.mkfifo(box / "granted" / "pipe")
    out = {}
    # daemon: if the host DOES hang, the assertion below fails the test
    # instead of the blocked thread holding pytest open forever.
    t = threading.Thread(target=lambda: out.setdefault(
        "r", act(rw(box), "filesystem.read", path=str(box / "granted" / "pipe"))),
        daemon=True)
    t.start()
    t.join(10)
    assert not t.is_alive(), "a FIFO must never hang the host"
    assert out["r"].decision.reason is DenyReason.OUT_OF_SCOPE


def test_fifo_write_is_refused(box):
    os.mkfifo(box / "granted" / "pipe")
    r = act(rw(box), "filesystem.write", path=str(box / "granted" / "pipe"), content="x")
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE


def test_hardlinked_file_is_not_overwritten(box):
    target = box / "secret" / "shared.txt"
    target.write_text("ORIGINAL", encoding="utf-8")
    os.link(target, box / "granted" / "shared.txt")
    r = act(rw(box), "filesystem.write", path=str(box / "granted" / "shared.txt"), content="PWNED")
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE
    assert target.read_text(encoding="utf-8") == "ORIGINAL"


# -- the window between check and open ---------------------------------------

def test_a_name_swapped_after_the_check_is_caught_by_the_descriptor(box, monkeypatch):
    """Deterministic stand-in for the race: the resolver approved
    `granted/sub/loot.txt`, but by open time `sub` is a symlink to `secret`.
    O_NOFOLLOW only guards the last component; the descriptor check must
    catch the swapped middle one."""
    os.symlink(box / "secret", box / "granted" / "sub")
    host = rw(box)
    approved = str(box / "granted" / "sub" / "loot.txt")
    monkeypatch.setattr(host, "_resolve_inside", lambda path, cap: approved)
    r = act(host, "filesystem.read", path=approved)
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE
    assert r.result == {}, "the payload must not leave through the race"
    w = act(host, "filesystem.write", path=approved, content="x")
    assert w.decision.reason is DenyReason.OUT_OF_SCOPE
    assert (box / "secret" / "loot.txt").read_text(encoding="utf-8") == "NEVER"


def test_dangling_link_swapped_in_after_the_check_creates_nothing(box, monkeypatch):
    """With the resolver already passed, only O_NOFOLLOW stands between
    O_CREAT and a file created OUTSIDE the root -- the descriptor check would
    refuse afterwards, but the file would already exist."""
    os.symlink(box / "secret" / "created.txt", box / "granted" / "evil")
    host = rw(box)
    approved = str(box / "granted" / "evil")
    monkeypatch.setattr(host, "_resolve_inside", lambda path, cap: approved)
    r = act(host, "filesystem.write", path=approved, content="x")
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE
    assert not (box / "secret" / "created.txt").exists()


def test_final_component_swapped_to_a_link_is_refused(box, monkeypatch):
    os.symlink(box / "secret" / "loot.txt", box / "granted" / "swapped.txt")
    host = rw(box)
    approved = str(box / "granted" / "swapped.txt")
    monkeypatch.setattr(host, "_resolve_inside", lambda path, cap: approved)
    assert act(host, "filesystem.read", path=approved).decision.reason is DenyReason.OUT_OF_SCOPE
    assert act(host, "filesystem.write", path=approved, content="x").decision.reason \
        is DenyReason.OUT_OF_SCOPE
    assert (box / "secret" / "loot.txt").read_text(encoding="utf-8") == "NEVER"


# -- apps: case is part of the name --------------------------------------------

def test_app_allowlist_runs_only_the_granted_file(box, tmp_path):
    """The shared resolver matches names case-insensitively, but what runs is
    always the entry AS GRANTED -- never the spelling the request used."""
    import shutil
    exe = tmp_path / "tool"
    shutil.copy2(sys.executable, exe)
    host = make_host(["apps.launch"], {"apps.launch": {"allowlist": [str(exe)]}})
    r = act(host, "apps.launch", app=str(exe).upper(), args=["-c", "pass"])
    if r.decision.decision is Decision.ALLOW:
        assert r.result["exe"] == str(exe)
        os.waitpid(r.result["pid"], 0)
    else:
        assert r.decision.reason is DenyReason.OUT_OF_SCOPE
