"""M1 gate — the real Windows engine, against a real filesystem.

These tests create actual files, actual directories and (where the OS allows)
an actual junction. They never touch anything outside the pytest tmp dir, and
the host under test is granted nothing but that dir.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

if sys.platform != "win32":
    pytest.skip("real Windows engine", allow_module_level=True)

from isymotron.contracts import ExecutionRequest
from isymotron.host import OPERATIONS
from isymotron.verdicts import Decision, DenyReason, Evidence
from windows.grants import Grants
from windows.win11 import Win11Host

SUBJECT = "test:local"


def make_host(tmp_path, granted, scopes, **kw) -> Win11Host:
    g = Grants(host_id="win11-test", display_name="test host",
               granted=list(granted), scopes=dict(scopes), source="<test>", **kw)
    return Win11Host(g)


def act(host, capability, **params):
    lease, _ = host.request_lease(SUBJECT, capability, 120)
    req = ExecutionRequest.make(host.identify().host_id, SUBJECT, capability,
                                params, lease.lease_id if lease else None)
    return host.execute_capability(req)


@pytest.fixture
def sandbox(tmp_path):
    (tmp_path / "granted").mkdir()
    (tmp_path / "secret").mkdir()
    (tmp_path / "granted" / "ok.txt").write_text("hola", encoding="utf-8")
    (tmp_path / "secret" / "loot.txt").write_text("NEVER", encoding="utf-8")
    return tmp_path


# -- the host boots inert ---------------------------------------------------

def test_missing_grant_file_yields_an_inert_host(tmp_path):
    g = Grants.load(str(tmp_path / "nope.json"))
    assert g.granted == []
    assert g.source.startswith("<inert:")
    host = Win11Host(g)
    assert host.list_capabilities() == []
    assert host.health()["ok"] is True


def test_unparseable_grant_file_yields_an_inert_host(tmp_path):
    bad = tmp_path / "grants.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    g = Grants.load(str(bad))
    assert g.granted == []
    assert "unreadable" in g.source


def test_a_grant_with_no_scope_still_denies(sandbox):
    host = make_host(sandbox, ["filesystem.read"], {"filesystem.read": {}})
    r = act(host, "filesystem.read", path=str(sandbox / "granted" / "ok.txt"))
    assert r.decision.decision is Decision.DENY
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE


def test_grant_roundtrips_through_the_file(tmp_path):
    p = str(tmp_path / "grants.json")
    Grants(host_id="h", display_name="d", granted=["system.info"],
           scopes={"system.info": {}}).save(p)
    back = Grants.load(p)
    assert back.granted == ["system.info"]
    assert back.source == p


# -- the finding: a junction defeats the lexical check ----------------------

def _junction(link: str, target: str) -> bool:
    try:
        subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                       capture_output=True, check=True, timeout=20)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def test_junction_inside_a_granted_root_is_denied(sandbox):
    """Regression for FINDINGS.md #1.

    The enforcer sees a path that is lexically inside the root and says ALLOW.
    The engine resolves it, finds it leaves, and overrides with DENY.
    """
    link = str(sandbox / "granted" / "escape")
    if not _junction(link, str(sandbox / "secret")):
        pytest.skip("this environment cannot create a junction")

    host = make_host(sandbox, ["filesystem.read"],
                     {"filesystem.read": {"roots": [str(sandbox / "granted")]}})
    attack = str(sandbox / "granted" / "escape" / "loot.txt")

    lease, _ = host.request_lease(SUBJECT, "filesystem.read", 120)
    req = ExecutionRequest.make(host.identify().host_id, SUBJECT,
                                "filesystem.read", {"path": attack}, lease.lease_id)

    # The lexical enforcer alone is fooled. This is the point of the test.
    assert host._enforcer.decide(req, lease).decision is Decision.ALLOW

    # The host as a whole is not.
    rcpt = host.execute_capability(req)
    assert rcpt.decision.decision is Decision.DENY
    assert rcpt.decision.reason is DenyReason.OUT_OF_SCOPE
    assert rcpt.result == {}, "a scope escape must not leak the payload"
    assert rcpt.evidence is Evidence.DEMONSTRATED, \
        "a refusal is demonstrated, not an unknown outcome"
    assert rcpt.verify()


def test_junction_write_is_denied_too(sandbox):
    link = str(sandbox / "granted" / "escape")
    if not _junction(link, str(sandbox / "secret")):
        pytest.skip("this environment cannot create a junction")
    host = make_host(sandbox, ["filesystem.write"],
                     {"filesystem.write": {"roots": [str(sandbox / "granted")]}})
    r = act(host, "filesystem.write",
            path=str(sandbox / "granted" / "escape" / "planted.txt"), content="x")
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE
    assert not (sandbox / "secret" / "planted.txt").exists()


def test_junction_is_denied_through_a_logical_path_too(sandbox):
    """A `hostfs://` name is translated before the engine runs, so it must meet
    the same resolved-path check a physical path does (FINDINGS.md #1, #9)."""
    link = str(sandbox / "granted" / "escape")
    if not _junction(link, str(sandbox / "secret")):
        pytest.skip("this environment cannot create a junction")
    host = make_host(sandbox, ["filesystem.read"],
                     {"filesystem.read": {"roots": [str(sandbox / "granted")]}})
    r = act(host, "filesystem.read", path="hostfs://granted/escape/loot.txt")
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE
    assert r.result == {}


def test_real_listing_answers_in_logical_names_only(sandbox):
    host = make_host(sandbox, ["filesystem.read"],
                     {"filesystem.read": {"roots": [str(sandbox / "granted")]}})
    newer = sandbox / "granted" / "newer.txt"
    newer.write_text("fresh", encoding="utf-8")
    os.utime(newer, (2_000_000_000, 2_000_000_000))

    listing = act(host, "filesystem.read", path="hostfs://granted")
    assert listing.decision.decision is Decision.ALLOW
    assert listing.result["newest"] == "hostfs://granted/newer.txt"
    assert str(sandbox).replace("\\", "/").lower() not in str(listing.result).replace("\\\\", "/").lower()

    read = act(host, "filesystem.read", path=listing.result["newest"])
    assert read.result["text"] == "fresh"
    assert read.result["path"] == "hostfs://granted/newer.txt"


# -- real filesystem behaviour ---------------------------------------------

def test_real_read_inside_scope(sandbox):
    host = make_host(sandbox, ["filesystem.read"],
                     {"filesystem.read": {"roots": [str(sandbox / "granted")]}})
    r = act(host, "filesystem.read", path=str(sandbox / "granted" / "ok.txt"))
    assert r.decision.decision is Decision.ALLOW
    assert r.result["text"] == "hola"
    assert r.result["sha256"].startswith("sha256:")
    assert r.verify()


def test_real_read_outside_scope(sandbox):
    host = make_host(sandbox, ["filesystem.read"],
                     {"filesystem.read": {"roots": [str(sandbox / "granted")]}})
    r = act(host, "filesystem.read", path=str(sandbox / "secret" / "loot.txt"))
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE
    assert r.result == {}


def test_real_directory_listing_carries_size_and_mtime(sandbox):
    """Regression for FINDINGS.md #4: names alone cannot answer 'the most
    recent one', and the planner refused a legitimate request over it."""
    host = make_host(sandbox, ["filesystem.read"],
                     {"filesystem.read": {"roots": [str(sandbox / "granted")]}})
    r = act(host, "filesystem.read", path=str(sandbox / "granted"))
    assert r.result["kind"] == "directory"
    names = [e["name"] for e in r.result["entries"]]
    assert "ok.txt" in names
    entry = next(e for e in r.result["entries"] if e["name"] == "ok.txt")
    assert entry["bytes"] == 4
    assert entry["modified"].endswith("Z")


def test_real_directory_listing_is_newest_first(sandbox):
    import time as _t
    host = make_host(sandbox, ["filesystem.read"],
                     {"filesystem.read": {"roots": [str(sandbox / "granted")]}})
    _t.sleep(1.1)  # the mtime grammar has one-second resolution
    (sandbox / "granted" / "later.txt").write_text("nuevo", encoding="utf-8")
    r = act(host, "filesystem.read", path=str(sandbox / "granted"))
    assert r.result["order"] == "modified_desc"
    assert r.result["entries"][0]["name"] == "later.txt"


def test_real_write_creates_the_file(sandbox):
    host = make_host(sandbox, ["filesystem.write"],
                     {"filesystem.write": {"roots": [str(sandbox / "granted")]}})
    target = sandbox / "granted" / "sub" / "new.txt"
    r = act(host, "filesystem.write", path=str(target), content="escrito")
    assert r.decision.decision is Decision.ALLOW
    assert target.read_text(encoding="utf-8") == "escrito"
    assert r.result["overwrote"] is False


def test_write_to_a_nonexistent_path_outside_scope_is_denied(sandbox):
    """The nearest existing ancestor is what gets resolved, so a write to a
    path that does not exist yet is still checked against the real tree."""
    host = make_host(sandbox, ["filesystem.write"],
                     {"filesystem.write": {"roots": [str(sandbox / "granted")]}})
    r = act(host, "filesystem.write",
            path=str(sandbox / "secret" / "deep" / "planted.txt"), content="x")
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE
    assert not (sandbox / "secret" / "deep").exists()


def test_dotdot_on_a_real_tree(sandbox):
    host = make_host(sandbox, ["filesystem.read"],
                     {"filesystem.read": {"roots": [str(sandbox / "granted")]}})
    r = act(host, "filesystem.read",
            path=str(sandbox / "granted" / ".." / "secret" / "loot.txt"))
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE


def test_real_system_info(sandbox):
    host = make_host(sandbox, ["system.info"], {"system.info": {}})
    r = act(host, "system.info")
    assert r.decision.decision is Decision.ALLOW
    assert r.result["os"].startswith("Windows")
    assert r.result["cores"] >= 1


def test_real_process_inspect_is_read_only(sandbox):
    host = make_host(sandbox, ["process.inspect"], {"process.inspect": {}})
    ok = act(host, "process.inspect")
    assert ok.decision.decision is Decision.ALLOW
    assert ok.result["count"] > 0
    bad = act(host, "process.inspect", mutate=True)
    assert bad.decision.reason is DenyReason.EXCESS_AUTHORITY


def test_app_not_on_allowlist_is_denied(sandbox):
    host = make_host(sandbox, ["apps.launch"],
                     {"apps.launch": {"allowlist": ["notepad.exe"]}})
    r = act(host, "apps.launch", app="cmd.exe")
    assert r.decision.reason is DenyReason.OUT_OF_SCOPE
    assert r.result == {}


def test_all_eight_operations_on_the_real_host(sandbox):
    host = make_host(sandbox, [], {})
    for op in OPERATIONS:
        assert callable(getattr(host, op))


# -- step 3: launch seals the instance fingerprint into the receipt ---------
#
# The engine observes at spawn time (the trust root) and the receipt seals
# the fingerprint, so a later `verify` detects post-launch drift and PID
# reuse. Boundary kept: instance + artifact identity only — not a
# certificate of the in-memory image, not a benign-process verdict.

def _kill(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                   capture_output=True, timeout=20)


def _launch_sleep(host, exe: str):
    from isymotron.process import ProcessIdentity
    r = act(host, "apps.launch", app=exe,
            args=["-c", "import time; time.sleep(20)"])
    assert r.decision.decision is Decision.ALLOW
    assert r.verify(), "the launch receipt must seal with the fingerprint inside"
    proof = r.result["proc"]
    assert "fingerprint" in proof and "observations" in proof, proof
    pid = r.result["pid"]
    baseline = ProcessIdentity.from_dict({
        "pid": pid, "platform": proof["platform"],
        "observations": proof["observations"],
        "fingerprint": proof["fingerprint"], "strength": proof["strength"],
    })
    return pid, baseline


def test_launch_seals_a_verifiable_fingerprint(sandbox, tmp_path):
    import shutil
    from isymotron.process import ERROR, PASS, STANDARD, verify
    copy = tmp_path / "launched.exe"
    shutil.copy2(sys.executable, copy)
    host = make_host(sandbox, ["apps.launch"],
                     {"apps.launch": {"allowlist": [str(copy)]}})
    pid, baseline = _launch_sleep(host, str(copy))
    try:
        assert baseline.strength == STANDARD
        assert verify(pid, baseline).status == PASS
    finally:
        _kill(pid)
    # The instance is gone: the same sealed baseline now fails closed.
    assert verify(pid, baseline).status == ERROR


def test_sealed_fingerprint_catches_instance_reuse(sandbox, tmp_path):
    from dataclasses import replace
    from isymotron.process import DENY, INSTANCE_MISMATCH, verdict_for
    import shutil
    copy = tmp_path / "launched.exe"
    shutil.copy2(sys.executable, copy)
    host = make_host(sandbox, ["apps.launch"],
                     {"apps.launch": {"allowlist": [str(copy)]}})
    pid, baseline = _launch_sleep(host, str(copy))
    try:
        # A different instance behind the same pid: the sealed receipt says DENY.
        impostor = replace(baseline, observations=dict(
            baseline.observations, starttime="1", proc_inode="1"))
        v = verdict_for(baseline, impostor)
        assert v.status == DENY and v.reason == INSTANCE_MISMATCH
    finally:
        _kill(pid)
