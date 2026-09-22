"""Quine Gate — M7: the verification bundle and its CLI.

Builds a real bundle on disk (receipt, claim, chain, artifact manifest),
verifies it, and proves each failure mode is reported against the property that
owns it.

Anchors are passed in by the caller and are NOT read from the bundle: a bundle
that carries its own anchor can be rewritten together with it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from isymotron.bundle import NOT_DEMONSTRATED, verify_bundle
from isymotron.canon import digest
from isymotron.chain import make_state
from isymotron.contracts import CONTRACT_V1, ExecutionRequest, PolicyDecision
from isymotron.evidence import sha256_file
from isymotron.seal import HMAC_SHA256
from isymotron.verify import ClaimBundle
from isymotron.verdicts import Decision
from simulator.engines import ModernHost

REPO = Path(__file__).resolve().parent.parent
SECRET = "bundle-key"
SUBJECT = "mobile:bundle"
HOST_ID = "win11-bundle"
IN_SCOPE = "C:/Users/demo/Photos/shot.png"
OUT_OF_SCOPE = "C:/Users/demo/Secrets/keys.txt"


def _receipt_and_bundle():
    host = ModernHost(
        fs={IN_SCOPE: "PNGDATA", OUT_OF_SCOPE: "hunter2"},
        granted=["filesystem.read"],
        grant_scopes={"filesystem.read": {"roots": ["C:/Users/demo/Photos"]}},
        host_id=HOST_ID,
        display_name="Bundle (M7)",
    )
    lease, _ = host.request_lease(SUBJECT, "filesystem.read", 300)
    request = ExecutionRequest.make(HOST_ID, SUBJECT, "filesystem.read",
                                    {"path": OUT_OF_SCOPE}, lease_id=lease.lease_id)
    receipt = host.execute_capability(request)
    bundle = ClaimBundle(host=host.describe(), request=request, lease=lease,
                         decided_at=receipt.started_at, expected=receipt.decision)
    sealed = replace(
        receipt, contract=CONTRACT_V1, claim_digest=bundle.digest(),
        policy_digest=digest({"p": 1}), capability_digest=digest({"c": 1}),
        result_digest=digest(receipt.result), seal_kind=HMAC_SHA256,
    ).sealed(key=SECRET)
    return sealed, bundle


def _chain_states():
    genesis = make_state(None, {"kind": "genesis"})
    s1 = make_state(genesis["sha"], {"kind": "install"})
    s2 = make_state(s1["sha"], {"kind": "execute", "result": "DENY"})
    return genesis, s1, s2


def _write_bundle(base: Path, *, chain=True, manifest=True,
                  mutate_receipt=False, fork=False) -> tuple[Path, str | None, str | None]:
    """Write a bundle. Returns (dir, real_genesis, real_head)."""
    receipt, claim = _receipt_and_bundle()
    if mutate_receipt:
        # A forgery that IS self-consistent: DENY -> ALLOW, re-sealed with the
        # key. Only re-derivation catches this one.
        receipt = replace(receipt,
                          decision=PolicyDecision(Decision.ALLOW)).sealed(key=SECRET)
    base.mkdir(parents=True, exist_ok=True)
    (base / "receipt.json").write_text(json.dumps(receipt.to_dict()), encoding="utf-8")
    (base / "claim.json").write_text(json.dumps(claim.to_dict()), encoding="utf-8")

    genesis, s1, s2 = _chain_states()
    anchored_genesis: str | None = genesis["sha"]
    anchored_head: str | None = s2["sha"]
    if chain:
        tip = make_state(s1["sha"], {"kind": "execute", "result": "ALLOW"}) if fork else s2
        (base / "chain.json").write_text(json.dumps([genesis, s1, tip]), encoding="utf-8")
    else:
        anchored_genesis = anchored_head = None

    if manifest:
        artifact = base / "app.bin"
        artifact.write_bytes(b"release-bytes")
        (base / "hashes.json").write_text(
            json.dumps({"algorithm": "SHA-256",
                        "artifacts": {"app.bin": sha256_file(artifact)}}),
            encoding="utf-8")
    return base, anchored_genesis, anchored_head


def test_complete_bundle_passes(tmp_path):
    base, genesis, head = _write_bundle(tmp_path / "bundle")
    report = verify_bundle(base, key=SECRET,
                           anchored_genesis=genesis, anchored_head=head)
    assert report.passed, report.to_dict()
    assert report.verdict == "PASS"
    assert report.properties["reproducibility"]["status"] == "PASS"
    assert report.properties["anchor"]["status"] == "PASS"
    assert report.properties["artifact_identity"]["status"] == "PASS"
    assert report.properties["occurrence"]["status"] == NOT_DEMONSTRATED
    assert "occurrence" in report.not_demonstrated
    assert "host_attestation" in report.not_demonstrated


def test_without_key_the_seal_is_rejected(tmp_path):
    base, genesis, head = _write_bundle(tmp_path / "bundle")
    report = verify_bundle(base, key=None,
                           anchored_genesis=genesis, anchored_head=head)
    assert not report.passed
    assert report.properties["seal_integrity"]["status"] == "REJECT"


def test_self_consistent_forgery_is_rejected_by_reproduction(tmp_path):
    base, genesis, head = _write_bundle(tmp_path / "bundle", mutate_receipt=True)
    report = verify_bundle(base, key=SECRET,
                           anchored_genesis=genesis, anchored_head=head)
    assert report.properties["seal_integrity"]["status"] == "PASS", \
        "the forgery is sealed with the real key, so only re-derivation saves us"
    assert report.properties["reproducibility"]["status"] == "REJECT"
    assert not report.passed


def test_forked_chain_conflicts_on_the_external_anchor(tmp_path):
    base, genesis, head = _write_bundle(tmp_path / "bundle", fork=True)
    report = verify_bundle(base, key=SECRET,
                           anchored_genesis=genesis, anchored_head=head)
    assert not report.passed
    assert report.properties["anchor"]["status"] == "CONFLICT"


def test_in_bundle_anchor_file_is_not_trusted(tmp_path):
    """A fork with a matching anchors.json inside it must still fail."""
    base, genesis, head = _write_bundle(tmp_path / "bundle", fork=True)
    chain = json.loads((base / "chain.json").read_text(encoding="utf-8"))
    (base / "anchors.json").write_text(
        json.dumps({"genesis": chain[0]["sha"], "head": chain[-1]["sha"]}),
        encoding="utf-8")

    with_external = verify_bundle(base, key=SECRET,
                                  anchored_genesis=genesis, anchored_head=head)
    assert with_external.properties["anchor"]["status"] == "CONFLICT"

    without_external = verify_bundle(base, key=SECRET)
    assert without_external.properties["anchor"]["status"] == "NOT_VERIFIABLE"


def test_missing_anchor_is_not_verifiable(tmp_path):
    base, genesis, _ = _write_bundle(tmp_path / "bundle")
    report = verify_bundle(base, key=SECRET, anchored_genesis=genesis, anchored_head=None)
    assert not report.passed
    assert report.properties["anchor"]["status"] == "NOT_VERIFIABLE"


def test_without_chain_the_anchor_is_not_required(tmp_path):
    base, _, _ = _write_bundle(tmp_path / "bundle", chain=False)
    report = verify_bundle(base, key=SECRET)
    assert report.passed
    assert report.properties["anchor"]["status"] == "NOT_VERIFIABLE"


def test_cli_exit_codes(tmp_path):
    good, genesis, head = _write_bundle(tmp_path / "good")
    bad, _, _ = _write_bundle(tmp_path / "bad", mutate_receipt=True)
    script = str(REPO / "tools" / "quine_gate_verify.py")

    ok = subprocess.run([sys.executable, script, str(good), "--key", SECRET,
                         "--genesis", genesis, "--head", head],
                        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    assert json.loads(ok.stdout)["verdict"] == "PASS"

    ko = subprocess.run([sys.executable, script, str(bad), "--key", SECRET,
                         "--genesis", genesis, "--head", head],
                        capture_output=True, text=True)
    assert ko.returncode == 1, ko.stdout
