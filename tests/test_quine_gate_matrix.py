"""Quine Gate — M6: the threat matrix A..J in one place.

Each attack has one test and one expected outcome. The mapping is also
asserted as a whole so a future edit cannot silently drop an attack.

  A  receipt mutation (DENY->ALLOW)        -> REJECT
  B  internal rehash (mutate + reseal)     -> REJECT
  C  fork from the same genesis            -> CONFLICT
  D  rollback to an older state            -> CONFLICT
  E  changed input                         -> REJECT
  F  changed policy                        -> REJECT
  G  changed artifact byte                 -> REJECT
  H  reproduction mismatch of the result   -> NOT_VERIFIABLE (see note)
  I  missing anchor                        -> NOT_VERIFIABLE
  J  wrong anchor                          -> REJECT

Note on H, kept explicit because it is a real boundary: M2 re-derives the
*decision*, not the *effect*. A receipt declares a `result_digest`, but nothing
in this repository re-executes the effect and recomputes it. So a mismatch
between the declared result and a re-execution is NOT detectable here, and the
matrix reports NOT_VERIFIABLE rather than pretending otherwise.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from isymotron.canon import digest
from isymotron.chain import (
    CONFLICT,
    NOT_VERIFIABLE,
    REJECT,
    make_state,
    verify_chain,
)
from isymotron.contracts import CONTRACT_V1, ExecutionRequest, PolicyDecision
from isymotron.evidence import sha256_file, verify_manifest
from isymotron.seal import HMAC_SHA256
from isymotron.verify import ClaimBundle, verify_receipt
from isymotron.verdicts import Decision
from simulator.engines import ModernHost

SECRET = "matrix-key"
SUBJECT = "mobile:matrix"
HOST_ID = "win11-matrix"
IN_SCOPE = "C:/Users/demo/Photos/shot.png"
OUT_OF_SCOPE = "C:/Users/demo/Secrets/keys.txt"

MATRIX = {
    "A": "REJECT", "B": "REJECT", "C": "CONFLICT", "D": "CONFLICT",
    "E": "REJECT", "F": "REJECT", "G": "REJECT",
    "H": "NOT_VERIFIABLE", "I": "NOT_VERIFIABLE", "J": "REJECT",
}


def _host() -> ModernHost:
    return ModernHost(
        fs={IN_SCOPE: "PNGDATA", OUT_OF_SCOPE: "hunter2"},
        granted=["filesystem.read"],
        grant_scopes={"filesystem.read": {"roots": ["C:/Users/demo/Photos"]}},
        host_id=HOST_ID,
        display_name="Matrix (M6)",
    )


def _receipt_and_bundle(path: str = OUT_OF_SCOPE):
    host = _host()
    lease, _ = host.request_lease(SUBJECT, "filesystem.read", 300)
    request = ExecutionRequest.make(HOST_ID, SUBJECT, "filesystem.read",
                                    {"path": path}, lease_id=lease.lease_id)
    receipt = host.execute_capability(request)
    bundle = ClaimBundle(host=host.describe(), request=request, lease=lease,
                         decided_at=receipt.started_at, expected=receipt.decision)
    sealed = replace(
        receipt, contract=CONTRACT_V1, claim_digest=bundle.digest(),
        policy_digest=digest({"p": 1}), capability_digest=digest({"c": 1}),
        result_digest=digest(receipt.result), seal_kind=HMAC_SHA256,
    ).sealed(key=SECRET)
    return sealed, bundle


def _chain():
    genesis = make_state(None, {"kind": "genesis"})
    s1 = make_state(genesis["sha"], {"kind": "install"})
    s2 = make_state(s1["sha"], {"kind": "execute", "result": "DENY"})
    return genesis, s1, s2


def test_attack_A_receipt_mutation():
    receipt, _ = _receipt_and_bundle()
    forged = replace(receipt, decision=PolicyDecision(Decision.ALLOW))
    assert not forged.verify(key=SECRET)
    assert MATRIX["A"] == "REJECT"


def test_attack_B_internal_rehash():
    receipt, _ = _receipt_and_bundle()
    forged = replace(receipt, decision=PolicyDecision(Decision.ALLOW))
    forged = replace(forged, seal=digest(forged.payload()))  # rehash, no key
    assert not forged.verify(key=SECRET)
    assert MATRIX["B"] == "REJECT"


def test_attack_C_fork():
    genesis, s1, s2 = _chain()
    fork_tip = make_state(s1["sha"], {"kind": "execute", "result": "ALLOW"})
    result = verify_chain([genesis, s1, fork_tip],
                          anchored_genesis=genesis["sha"], anchored_head=s2["sha"])
    assert result.status == CONFLICT and MATRIX["C"] == "CONFLICT"


def test_attack_D_rollback():
    genesis, s1, s2 = _chain()
    result = verify_chain([genesis, s1],
                          anchored_genesis=genesis["sha"], anchored_head=s2["sha"])
    assert result.status == CONFLICT and MATRIX["D"] == "CONFLICT"


def test_attack_E_changed_input():
    receipt, bundle = _receipt_and_bundle()
    other = replace(bundle, request=ExecutionRequest.make(
        HOST_ID, SUBJECT, "filesystem.read", {"path": IN_SCOPE},
        lease_id=bundle.request.lease_id))
    assert not verify_receipt(receipt, other).passed
    assert MATRIX["E"] == "REJECT"


def test_attack_F_changed_policy():
    receipt, bundle = _receipt_and_bundle()
    stripped = replace(bundle, host=replace(bundle.host, granted=[]))
    assert not verify_receipt(receipt, stripped).passed
    assert MATRIX["F"] == "REJECT"


def test_attack_G_changed_artifact(tmp_path):
    artifact = tmp_path / "app.bin"
    artifact.write_bytes(b"release-bytes")
    manifest = tmp_path / "hashes.json"
    manifest.write_text(json.dumps({"algorithm": "SHA-256",
                                    "artifacts": {"app.bin": sha256_file(artifact)}}))
    assert verify_manifest(manifest).passed

    artifact.write_bytes(b"release-bytez")
    assert not verify_manifest(manifest).passed
    assert MATRIX["G"] == "REJECT"


def test_attack_H_reproduction_mismatch_is_not_covered():
    """Honest boundary: the decision is reproduced; the effect is not."""
    receipt, _ = _receipt_and_bundle()
    assert receipt.result_digest is not None, "a result hash is declared"
    # Nothing recomputes it. The matrix records that gap as NOT_VERIFIABLE.
    assert MATRIX["H"] == "NOT_VERIFIABLE"


def test_attack_I_missing_anchor():
    genesis, s1, s2 = _chain()
    result = verify_chain([genesis, s1, s2], anchored_genesis=genesis["sha"],
                          anchored_head=None)
    assert result.status == NOT_VERIFIABLE and MATRIX["I"] == "NOT_VERIFIABLE"


def test_attack_J_wrong_anchor():
    genesis, s1, s2 = _chain()
    other = make_state(None, {"kind": "genesis", "base": "other"})
    result = verify_chain([genesis, s1, s2], anchored_genesis=other["sha"],
                          anchored_head=s2["sha"])
    assert result.status == REJECT and MATRIX["J"] == "REJECT"


def test_matrix_is_complete():
    assert set(MATRIX) == set("ABCDEFGHIJ")
    assert set(MATRIX.values()) <= {"REJECT", "CONFLICT", "NOT_VERIFIABLE"}
