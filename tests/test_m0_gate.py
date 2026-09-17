"""M0 acceptance gate (roadmap section 30, M0).

"A fake Win11 host and a fake mobile client can exchange a typed
 describe -> request -> receipt roundtrip without product-specific hacks."

Plus section 31 steps 9 and 10: prove outside-scope DENY, produce a receipt.
"""
from __future__ import annotations

import time

import pytest

from clients.fake_mobile import FakeMobile
from isymotron.contracts import ExecutionRequest
from isymotron.host import OPERATIONS
from isymotron.verdicts import Decision, DenyReason, Evidence
from relay.loopback import LoopbackRelay
from simulator.engines import LegacyHost, ModernHost

SUBJECT = "mobile:iphone-danny"


@pytest.fixture
def world():
    modern = ModernHost(
        fs={
            "C:/Users/danny/Photos/shot-2026-09-17.png": "PNGDATA",
            "C:/Users/danny/Secrets/keys.txt": "hunter2",
            "C:/Users/danny/NemoInbox/.keep": "",
        },
        granted=["filesystem.read", "filesystem.write", "apps.launch",
                 "system.info", "process.inspect"],
        grant_scopes={
            "filesystem.read": {"roots": ["C:/Users/danny/Photos"]},
            "filesystem.write": {"roots": ["C:/Users/danny/NemoInbox"]},
            "apps.launch": {"allowlist": ["notepad.exe"]},
            "system.info": {},
            "process.inspect": {},
        },
        admin_granted=False,
    )
    legacy = LegacyHost(
        fs={"C:/NEMO/INBOX/.keep": "", "C:/GAMES/DOOM/README.TXT": "rip and tear"},
        granted=["filesystem.read", "filesystem.write", "apps.launch", "system.info"],
        grant_scopes={
            "filesystem.read": {"roots": ["C:/GAMES"]},
            "filesystem.write": {"roots": ["C:/NEMO/INBOX"]},
            "apps.launch": {"allowlist": ["DOOM.EXE"]},
            "system.info": {},
        },
    )
    relay = LoopbackRelay()
    relay.attach(modern)
    relay.attach(legacy)
    return relay, modern, legacy, FakeMobile(relay, SUBJECT)


# -- the gate itself --------------------------------------------------------

def test_gate_describe_request_receipt_roundtrip(world):
    relay, modern, _, phone = world

    desc = relay.describe("win11-victus")
    assert desc["identity"]["contract"] == "NemoHostContract/v0"
    assert "filesystem.read" in desc["granted"]

    assert phone.approve("win11-victus", "filesystem.read",
                         scope={"roots": ["C:/Users/danny/Photos"]}) is not None

    rcpt = phone.act("win11-victus", "filesystem.read",
                     path="C:/Users/danny/Photos/shot-2026-09-17.png")

    assert rcpt.decision.decision is Decision.ALLOW
    assert rcpt.result["content"] == "PNGDATA"
    assert rcpt.verify(), "receipt seal must validate"
    assert relay.receipt("win11-victus", rcpt.receipt_id).receipt_id == rcpt.receipt_id


def test_all_eight_operations_exist_on_every_host(world):
    _, modern, legacy, _ = world
    for host in (modern, legacy):
        for op in OPERATIONS:
            assert callable(getattr(host, op)), f"{host.identify().host_id} missing {op}"


# -- deny-by-default --------------------------------------------------------

def test_outside_scope_is_denied_and_still_receipted(world):
    _, _, _, phone = world
    phone.approve("win11-victus", "filesystem.read",
                  scope={"roots": ["C:/Users/danny/Photos"]})
    rcpt = phone.act("win11-victus", "filesystem.read",
                     path="C:/Users/danny/Secrets/keys.txt")
    assert rcpt.decision.decision is Decision.DENY
    assert rcpt.decision.reason is DenyReason.OUT_OF_SCOPE
    assert rcpt.result == {}, "a denied request must not leak the payload"
    assert rcpt.verify()


def test_sibling_prefix_is_not_inside_root(world):
    _, modern, _, phone = world
    modern.fs.write("C:/Users/danny/Photos2/leak.txt", "x")
    phone.approve("win11-victus", "filesystem.read",
                  scope={"roots": ["C:/Users/danny/Photos"]})
    rcpt = phone.act("win11-victus", "filesystem.read",
                     path="C:/Users/danny/Photos2/leak.txt")
    assert rcpt.decision.reason is DenyReason.OUT_OF_SCOPE


def test_dotdot_traversal_is_denied(world):
    _, _, _, phone = world
    phone.approve("win11-victus", "filesystem.read",
                  scope={"roots": ["C:/Users/danny/Photos"]})
    rcpt = phone.act("win11-victus", "filesystem.read",
                     path="C:/Users/danny/Photos/../Secrets/keys.txt")
    assert rcpt.decision.reason is DenyReason.OUT_OF_SCOPE


def test_backslashes_do_not_bypass_scope(world):
    _, _, _, phone = world
    phone.approve("win11-victus", "filesystem.read",
                  scope={"roots": ["C:/Users/danny/Photos"]})
    ok = phone.act("win11-victus", "filesystem.read",
                   path=r"c:\users\danny\photos\shot-2026-09-17.png")
    assert ok.decision.decision is Decision.ALLOW
    bad = phone.act("win11-victus", "filesystem.read",
                    path=r"C:\Users\danny\Secrets\keys.txt")
    assert bad.decision.reason is DenyReason.OUT_OF_SCOPE


def test_no_lease_is_a_hard_deny(world):
    relay, _, _, _ = world
    req = ExecutionRequest.make("win11-victus", SUBJECT, "filesystem.read",
                                {"path": "C:/Users/danny/Photos/shot-2026-09-17.png"})
    rcpt = relay.execute(req)
    assert rcpt.decision.reason is DenyReason.LEASE_MISSING


def test_ungranted_capability_is_absent_not_forbidden(world):
    relay, modern, _, _ = world
    listed = [c.id for c in modern.list_capabilities()]
    assert "system.admin_task" not in listed
    assert "system.admin_task" in [c.id for c in modern.describe().capabilities]


def test_capability_the_host_does_not_implement(world):
    _, _, _, phone = world
    assert phone.approve("win98-retrobox", "process.inspect") is None
    rcpt = phone.act("win98-retrobox", "process.inspect")
    assert rcpt.decision.reason is DenyReason.CAPABILITY_UNAVAILABLE


def test_admin_capability_denied_without_admin_grant(world):
    relay, modern, _, phone = world
    # Force-grant it locally to reach the admin check rather than the grant check.
    modern._granted.append("system.admin_task")
    modern._grant_scopes["system.admin_task"] = {}
    modern._enforcer = type(modern._enforcer)(modern.describe(), admin_granted=False)
    lease = phone.approve("win11-victus", "system.admin_task")
    assert lease is not None
    rcpt = phone.act("win11-victus", "system.admin_task", action="wipe")
    assert rcpt.decision.reason is DenyReason.EXCESS_AUTHORITY


def test_expired_lease_is_denied(world):
    relay, modern, _, phone = world
    lease = phone.approve("win11-victus", "filesystem.read", ttl_s=1.0)
    req = ExecutionRequest.make("win11-victus", SUBJECT, "filesystem.read",
                                {"path": "C:/Users/danny/Photos/shot-2026-09-17.png"},
                                lease_id=lease.lease_id)
    rcpt = modern.execute_capability(req, now=time.time() + 10.0)
    assert rcpt.decision.reason is DenyReason.LEASE_EXPIRED


def test_revoked_lease_is_denied(world):
    _, modern, _, phone = world
    lease = phone.approve("win11-victus", "filesystem.read")
    modern.revoke_lease(lease.lease_id)
    rcpt = phone.act("win11-victus", "filesystem.read",
                     path="C:/Users/danny/Photos/shot-2026-09-17.png")
    assert rcpt.decision.reason is DenyReason.LEASE_REVOKED


def test_lease_cannot_be_widened_by_the_caller(world):
    _, _, _, phone = world
    lease = phone.approve("win11-victus", "filesystem.read",
                          scope={"roots": ["C:/", "C:/Users/danny/Photos"]})
    assert lease.scope["roots"] == ["C:/Users/danny/Photos"], \
        "asking for more must not grant more"


def test_lease_ttl_is_capped_by_the_host(world):
    _, _, _, phone = world
    lease = phone.approve("win11-victus", "system.info", ttl_s=10 ** 6)
    assert lease.expires_at - lease.issued_at <= 900.0


def test_undeclared_param_is_rejected(world):
    _, _, _, phone = world
    phone.approve("win11-victus", "system.info")
    rcpt = phone.act("win11-victus", "system.info", sudo=True)
    assert rcpt.decision.reason is DenyReason.MALFORMED_REQUEST


def test_read_only_family_rejects_mutation(world):
    _, _, _, phone = world
    phone.approve("win11-victus", "process.inspect")
    assert phone.act("win11-victus", "process.inspect").decision.decision is Decision.ALLOW
    rcpt = phone.act("win11-victus", "process.inspect", mutate=True)
    assert rcpt.decision.reason is DenyReason.EXCESS_AUTHORITY


def test_unmapped_capability_family_falls_to_deny():
    """The else-branch of a verdict is never the permissive class."""
    from isymotron.contracts import CapabilityManifest, HostIdentity
    from isymotron.host import Host

    class Odd(Host):
        def run(self, req):
            return {"ran": True}, []

    cap = CapabilityManifest(id="quantum.entangle", version="0.1", summary="",
                             params=("x",))
    host = Odd(
        HostIdentity("odd-1", "Odd", "windows", "11-24h2", "odd/0.1"),
        [cap], ["quantum.entangle"], {"quantum.entangle": {}},
    )
    lease, _ = host.request_lease("s", "quantum.entangle", 60)
    req = ExecutionRequest.make("odd-1", "s", "quantum.entangle", {"x": 1}, lease.lease_id)
    rcpt = host.execute_capability(req)
    assert rcpt.decision.decision is Decision.DENY
    assert rcpt.decision.reason is DenyReason.CAPABILITY_UNAVAILABLE


# -- cross-host parity ------------------------------------------------------

def test_same_workflow_on_two_unlike_engines(world):
    """One intent, two engines, two receipts, one contract."""
    _, modern, legacy, phone = world
    receipts = []
    for host_id, root in (("win11-victus", "C:/Users/danny/NemoInbox"),
                          ("win98-retrobox", "C:/NEMO/INBOX")):
        phone.approve(host_id, "filesystem.write")
        r = phone.act(host_id, "filesystem.write",
                      path=f"{root}/hello.txt", content="hola")
        receipts.append(r)

    assert all(r.decision.decision is Decision.ALLOW for r in receipts)
    assert {r.host.engine for r in receipts} == {"nt-modern/0.1", "dos-bridge/0.1"}
    # Different engines render paths differently; the declared effect shape matches.
    assert receipts[0].result["path"] != receipts[1].result["path"]
    assert [e["kind"] for e in receipts[0].effects] == [e["kind"] for e in receipts[1].effects]


def test_cross_device_transfer_produces_two_receipts(world):
    _, _, _, phone = world
    phone.approve("win11-victus", "filesystem.read")
    phone.approve("win98-retrobox", "filesystem.write")
    src = phone.act("win11-victus", "filesystem.read",
                    path="C:/Users/danny/Photos/shot-2026-09-17.png")
    dst = phone.act("win98-retrobox", "filesystem.write",
                    path="C:/NEMO/INBOX/SHOT.PNG", content=src.result["content"])
    assert src.decision.decision is dst.decision.decision is Decision.ALLOW
    assert src.host.host_id != dst.host.host_id
    assert all(r.verify() for r in (src, dst))


# -- receipt integrity ------------------------------------------------------

def test_receipt_seal_detects_tampering(world):
    from dataclasses import replace
    _, _, _, phone = world
    phone.approve("win11-victus", "system.info")
    rcpt = phone.act("win11-victus", "system.info")
    assert rcpt.verify()
    forged = replace(rcpt, result={"os": "Windows 95"})
    assert not forged.verify()


def test_request_digest_is_stable_across_identical_intents():
    a = ExecutionRequest.make("h", "s", "filesystem.read", {"path": "C:/x"})
    b = ExecutionRequest.make("h", "s", "filesystem.read", {"path": "C:/x"})
    assert a.request_id != b.request_id
    assert a.digest() == b.digest()


def test_error_inside_the_engine_is_unknown_not_allow(world):
    _, _, _, phone = world
    phone.approve("win11-victus", "filesystem.read")
    rcpt = phone.act("win11-victus", "filesystem.read",
                     path="C:/Users/danny/Photos/does-not-exist.png")
    assert rcpt.decision.decision is Decision.ALLOW  # authority was granted
    assert rcpt.evidence is Evidence.UNKNOWN         # the outcome was not
    assert rcpt.result["error"] == "FileNotFoundError"


def test_no_verdict_vocabulary_contains_safe():
    from isymotron.verdicts import DoctorVerdict
    assert "SAFE" not in {v.value for v in DoctorVerdict}
