"""M1 authority matrix: tool_profile behavior on the host authority path."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for sub in ("", "core", "hosts"):
    p = str(REPO / sub) if sub else str(REPO)
    if p not in sys.path:
        sys.path.insert(0, p)

from isymotron.contracts import ExecutionRequest
from isymotron.verdicts import Decision, DenyReason
from relay.loopback import LoopbackRelay
from simulator.engines import ModernHost
from windows.grants import Grants


def make_host(profile, granted=("filesystem.read", "system.info"),
              scopes=None, custom=None):
    scopes = scopes or {"filesystem.read": {"roots": ["C:/Photos"]}, "system.info": {}}
    kw = {}
    if profile != "full":
        # keep file's static grants so approvals have a non-empty bound
        pass
    return ModernHost(
        fs={"C:/Photos/a.png": "AAA", "C:/Secrets/k.txt": "NEVER"},
        granted=list(granted),
        grant_scopes=dict(scopes),
        tool_profile=profile,
        custom=custom,
    )


# -- full -------------------------------------------------------------------

def test_full_legal_capability_allows():
    host = make_host("full")
    lease, policy = host.request_lease("subj", "system.info", 120)
    assert lease is not None and policy.decision is Decision.ALLOW
    req = ExecutionRequest.make(host.identify().host_id, "subj", "system.info", {},
                                lease_id=lease.lease_id)
    rcpt = host.execute_capability(req)
    assert rcpt.decision.decision is Decision.ALLOW
    assert host.tool_profile == "full"


def test_full_unknown_capability_denied():
    host = make_host("full")
    lease, policy = host.request_lease("subj", "calendar.nuke", 120)
    assert lease is None
    assert policy.reason is DenyReason.CAPABILITY_UNAVAILABLE


def test_full_hard_bound_violation_denied():
    host = make_host("full")
    lease, policy = host.request_lease("subj", "filesystem.read", 120,
                                       {"roots": ["C:/Secrets"]})
    assert lease is not None
    req = ExecutionRequest.make(host.identify().host_id, "subj", "filesystem.read",
                                {"path": "C:/Secrets/k.txt"}, lease_id=lease.lease_id)
    rcpt = host.execute_capability(req)
    assert rcpt.decision.decision is Decision.DENY


def test_full_profile_recorded_on_host_description():
    host = make_host("full")
    assert host.tool_profile == "full"
    assert "system.info" in host.describe().granted


# -- security ----------------------------------------------------------------

def test_security_capability_triggers_approval_request():
    host = make_host("security")
    lease, policy = host.request_lease("subj", "system.info", 120)
    assert lease is None
    assert policy.reason is DenyReason.NEEDS_APPROVAL


def test_security_approval_then_mint_allows():
    host = make_host("security")
    lease, policy = host.mint_approved_lease("subj", "filesystem.read", {"roots": ["C:/Photos"]}, 120)
    assert lease is not None and policy.decision is Decision.ALLOW
    req = ExecutionRequest.make(host.identify().host_id, "subj", "filesystem.read",
                                {"path": "C:/Photos/a.png"}, lease_id=lease.lease_id)
    rcpt = host.execute_capability(req)
    assert rcpt.decision.decision is Decision.ALLOW


def test_security_missing_approval_means_deny():
    host = make_host("security")
    req = ExecutionRequest.make(host.identify().host_id, "subj", "filesystem.read",
                                {"path": "C:/Photos/a.png"}, lease_id=None)
    rcpt = host.execute_capability(req)
    assert rcpt.decision.decision is Decision.DENY


# -- custom ------------------------------------------------------------------

CUSTOM_DEF = {"capabilities": ["filesystem.read"], "allow_request_prompts": False}

def test_custom_default_enabled_allows():
    host = make_host("custom", custom=CUSTOM_DEF)
    lease, policy = host.request_lease("subj", "filesystem.read", 120)
    assert lease is not None and policy.decision is Decision.ALLOW


def test_custom_disabled_no_prompts_denied():
    host = make_host("custom", custom=CUSTOM_DEF)
    lease, policy = host.request_lease("subj", "system.info", 120)
    assert lease is None
    assert policy.reason is DenyReason.CAPABILITY_NOT_GRANTED


def test_custom_disabled_with_prompts_triggers_approval():
    host = make_host("custom", custom={"capabilities": ["filesystem.read"], "allow_request_prompts": True})
    lease, policy = host.request_lease("subj", "system.info", 120)
    assert lease is None
    assert policy.reason is DenyReason.NEEDS_APPROVAL


def test_custom_approval_allows():
    host = make_host("custom", custom={"capabilities": ["filesystem.read"], "allow_request_prompts": True})
    lease, policy = host.mint_approved_lease("subj", "system.info", {}, 120)
    assert lease is not None and policy.decision is Decision.ALLOW
    req = ExecutionRequest.make(host.identify().host_id, "subj", "system.info", {},
                                lease_id=lease.lease_id)
    rcpt = host.execute_capability(req)
    assert rcpt.decision.decision is Decision.ALLOW


# -- legacy grants -------------------------------------------------------------

def test_legacy_grants_parse_to_security(tmp_path):
    g = tmp_path / "grants.json"
    g.write_text(json.dumps({"host_id": "h", "granted": [], "scopes": {}}), encoding="utf-8")
    loaded = Grants.load(str(g))
    assert loaded.tool_profile == "security"
