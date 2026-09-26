"""M2 parity gate: ONE scenario table, run against the real engine of whatever
OS executes it (native.real_host()).

CI runs this file on Windows (the reference engine, `nt-real`) and on Linux
(`linux-real`). The same rows passing on both runners is what
docs/PLATFORM_SUPPORT.md calls PARITY_DEMONSTRATED for these capabilities; a
row that must differ by OS says so explicitly, with the reason.

The only OS-specific code here is how a directory link is made: a junction on
Windows, a symlink on Linux. Everything asserted is the contract.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

import native

if not native.has_real_host():
    pytest.skip(f"no real host engine on {sys.platform}", allow_module_level=True)

from isymotron.contracts import ExecutionRequest
from isymotron.host import OPERATIONS
from isymotron.verdicts import Decision, DenyReason, Evidence
from windows.grants import Grants
from windows.win11 import CAPABILITIES

SUBJECT = "test:parity"
WINDOWS = sys.platform == "win32"
EXPECTED_ENGINE = "nt-real/" if WINDOWS else "linux-real/"


def make_host(granted, scopes):
    g = Grants(host_id="parity-host", display_name="parity", granted=list(granted),
               scopes=dict(scopes), source="<test>")
    return native.real_host(g)


def act(host, capability, **params):
    lease, _ = host.request_lease(SUBJECT, capability, 120)
    req = ExecutionRequest.make(host.identify().host_id, SUBJECT, capability,
                                params, lease.lease_id if lease else None)
    return host.execute_capability(req)


def dir_link(link: str, target: str) -> bool:
    """A directory link the OS will follow: junction (Windows) / symlink (Linux)."""
    if WINDOWS:
        try:
            subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                           capture_output=True, check=True, timeout=20)
            return True
        except (OSError, subprocess.SubprocessError):
            return False
    os.symlink(target, link, target_is_directory=True)
    return True


@pytest.fixture
def box(tmp_path):
    (tmp_path / "granted").mkdir()
    (tmp_path / "secret").mkdir()
    (tmp_path / "granted" / "ok.txt").write_text("hola", encoding="utf-8")
    (tmp_path / "secret" / "loot.txt").write_text("NEVER", encoding="utf-8")
    return tmp_path


def read_host(box):
    return make_host(["filesystem.read"],
                     {"filesystem.read": {"roots": [str(box / "granted")]}})


def write_host(box):
    return make_host(["filesystem.write"],
                     {"filesystem.write": {"roots": [str(box / "granted")]}})


# -- identity: the right engine, the same contract ----------------------------

def test_native_engine_is_this_os(box):
    host = make_host([], {})
    assert host.identify().engine.startswith(EXPECTED_ENGINE)
    assert [c.id for c in host._capabilities] == [c.id for c in CAPABILITIES]
    assert all(a is b for a, b in zip(host._capabilities, CAPABILITIES)), \
        "one contract: the manifests are shared objects, not per-OS copies"
    for op in OPERATIONS:
        assert callable(getattr(host, op))


def test_inert_without_a_grant_file(tmp_path):
    host = native.real_host(Grants.load(str(tmp_path / "missing.json")))
    assert host.list_capabilities() == []
    r = act(host, "system.info")
    assert r.decision.reason is DenyReason.CAPABILITY_NOT_GRANTED


def test_grant_without_scope_denies(box):
    host = make_host(["filesystem.read"], {"filesystem.read": {}})
    r = act(host, "filesystem.read", path=str(box / "granted" / "ok.txt"))
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE


# -- filesystem: the parity table ----------------------------------------------

def test_read_inside_scope(box):
    r = act(read_host(box), "filesystem.read", path=str(box / "granted" / "ok.txt"))
    assert r.decision.decision is Decision.ALLOW
    assert r.result["text"] == "hola" and r.result["sha256"].startswith("sha256:")
    assert r.verify()


def test_read_outside_scope(box):
    r = act(read_host(box), "filesystem.read", path=str(box / "secret" / "loot.txt"))
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE and r.result == {}


def test_dotdot_escape(box):
    r = act(read_host(box), "filesystem.read",
            path=str(box / "granted" / ".." / "secret" / "loot.txt"))
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE and r.result == {}


def test_link_escape_read_is_overridden_by_the_engine(box):
    if not dir_link(str(box / "granted" / "escape"), str(box / "secret")):
        pytest.skip("cannot create a directory link here")
    host = read_host(box)
    attack = str(box / "granted" / "escape" / "loot.txt")
    lease, _ = host.request_lease(SUBJECT, "filesystem.read", 120)
    req = ExecutionRequest.make(host.identify().host_id, SUBJECT, "filesystem.read",
                                {"path": attack}, lease.lease_id)
    assert host._enforcer.decide(req, lease).decision is Decision.ALLOW, \
        "the lexical check alone is fooled; that is what the engine is for"
    r = host.execute_capability(req)
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE
    assert r.result == {} and r.evidence is Evidence.DEMONSTRATED and r.verify()


def test_link_escape_through_a_logical_name(box):
    if not dir_link(str(box / "granted" / "escape"), str(box / "secret")):
        pytest.skip("cannot create a directory link here")
    r = act(read_host(box), "filesystem.read", path="hostfs://granted/escape/loot.txt")
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE and r.result == {}


def test_link_escape_write_plants_nothing(box):
    if not dir_link(str(box / "granted" / "escape"), str(box / "secret")):
        pytest.skip("cannot create a directory link here")
    r = act(write_host(box), "filesystem.write",
            path=str(box / "granted" / "escape" / "planted.txt"), content="x")
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE
    assert not (box / "secret" / "planted.txt").exists()


def test_write_creates_nested_file(box):
    target = box / "granted" / "sub" / "new.txt"
    r = act(write_host(box), "filesystem.write", path=str(target), content="escrito")
    assert r.decision.decision is Decision.ALLOW
    assert target.read_text(encoding="utf-8") == "escrito"
    assert r.result["overwrote"] is False and r.verify()
    r2 = act(write_host(box), "filesystem.write", path=str(target), content="otra")
    assert r2.result["overwrote"] is True
    assert target.read_text(encoding="utf-8") == "otra"


def test_write_to_nonexistent_path_outside_is_denied(box):
    r = act(write_host(box), "filesystem.write",
            path=str(box / "secret" / "deep" / "planted.txt"), content="x")
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE
    assert not (box / "secret" / "deep").exists()


def test_listing_carries_size_mtime_newest_first_in_logical_names(box):
    time.sleep(1.1)  # the mtime grammar has one-second resolution
    newer = box / "granted" / "later.txt"
    newer.write_text("nuevo", encoding="utf-8")
    r = act(read_host(box), "filesystem.read", path="hostfs://granted")
    assert r.result["kind"] == "directory" and r.result["order"] == "modified_desc"
    assert r.result["entries"][0]["name"] == "later.txt"
    ok = next(e for e in r.result["entries"] if e["name"] == "ok.txt")
    assert ok["bytes"] == 4 and ok["modified"].endswith("Z")
    assert r.result["newest"] == "hostfs://granted/later.txt"
    physical = str(box).replace("\\", "/").lower()
    assert physical not in str(r.result).replace("\\\\", "/").lower(), \
        "a listing answers in logical names only"
    back = act(read_host(box), "filesystem.read", path=r.result["newest"])
    assert back.result["text"] == "nuevo"


def test_case_variant_of_a_root(box):
    """The one row that MUST differ, because the filesystems differ.

    NTFS: `GRANTED` is the same directory as `granted` -> in scope.
    ext4: `GRANTED` is a different directory -> out of scope, even though the
    lexical check (which folds case) says ALLOW. Before M2 the Windows engine
    ran on Linux via tools/host_cli.py and handed this file over.
    """
    upper = box / "GRANTED"
    if not WINDOWS:
        upper.mkdir()
        (upper / "loot.txt").write_text("OTHER DIR", encoding="utf-8")
    else:
        (box / "granted" / "loot.txt").write_text("SAME DIR", encoding="utf-8")
    r = act(read_host(box), "filesystem.read", path=str(upper / "loot.txt"))
    if WINDOWS:
        assert r.decision.decision is Decision.ALLOW
        assert r.result["text"] == "SAME DIR"
    else:
        assert r.decision.reason is DenyReason.OUT_OF_SCOPE
        assert r.result == {}


# -- the other three capabilities ---------------------------------------------

def test_system_info(box):
    r = act(make_host(["system.info"], {"system.info": {}}), "system.info")
    assert r.decision.decision is Decision.ALLOW
    assert r.result["cores"] >= 1
    assert r.result["engine"].startswith(EXPECTED_ENGINE)
    assert set(r.result) == {"os", "build", "machine", "cores", "engine", "python"}
    assert r.result["os"].startswith("Windows") == WINDOWS


def test_process_inspect_is_read_only(box):
    host = make_host(["process.inspect"], {"process.inspect": {}})
    ok = act(host, "process.inspect")
    assert ok.decision.decision is Decision.ALLOW and ok.result["count"] > 0
    assert act(host, "process.inspect", mutate=True).decision.reason \
        is DenyReason.EXCESS_AUTHORITY


def test_app_not_on_allowlist_is_denied(box):
    host = make_host(["apps.launch"], {"apps.launch": {"allowlist": ["allowed-app"]}})
    r = act(host, "apps.launch", app="something-else")
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE and r.result == {}


def _kill(pid: int) -> None:
    if WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=20)
    else:
        import signal
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_launch_seals_a_verifiable_fingerprint(box, tmp_path):
    """The allowlisted app is a COPY of this interpreter, so the test launches
    something real without depending on what the machine has installed."""
    import shutil
    from isymotron.process import ERROR, PASS, STANDARD, ProcessIdentity, verify
    copy = tmp_path / ("launched.exe" if WINDOWS else "launched")
    shutil.copy2(sys.executable, copy)
    host = make_host(["apps.launch"], {"apps.launch": {"allowlist": [str(copy)]}})
    r = act(host, "apps.launch", app=str(copy), args=["-c", "import time; time.sleep(20)"])
    assert r.decision.decision is Decision.ALLOW and r.verify()
    proof = r.result["proc"]
    assert "fingerprint" in proof, proof
    pid = r.result["pid"]
    baseline = ProcessIdentity.from_dict({
        "pid": pid, "platform": proof["platform"], "observations": proof["observations"],
        "fingerprint": proof["fingerprint"], "strength": proof["strength"]})
    try:
        assert baseline.strength == STANDARD
        assert verify(pid, baseline).status == PASS
    finally:
        _kill(pid)
        if not WINDOWS:
            try:
                os.waitpid(pid, 0)   # our child: reap it so the pid is really gone
            except ChildProcessError:
                pass
    assert verify(pid, baseline).status == ERROR
