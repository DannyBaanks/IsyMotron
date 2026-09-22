"""Quine Gate — the live demo must produce its expected verdicts.

The demo is the judge-facing artifact, so it self-checks: every step must land
on its expected verdict and the package it writes must verify from disk
against the anchors it reports. If any of that drifts, this gate fails.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from isymotron.bundle import verify_bundle
from isymotron.evidence import verify_manifest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "tools" / "quine_gate_demo.py"
FOOTER_MARK = "=== DEMO_RESULT_JSON ==="
EXPECTED_STEPS = {
    "legit_receipt": True,       # PASS
    "mutated_receipt": True,     # the attack is caught (REJECT)
    "fork": True,                # CONFLICT
    "rollback": True,            # CONFLICT
    "reproduce_chain": True,     # PASS
    "bundle_on_disk": True,      # PASS
}


def _run_demo(out: Path):
    proc = subprocess.run([sys.executable, str(SCRIPT), "--out", str(out)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"demo failed:\n{proc.stdout}\n{proc.stderr}"
    footer = json.loads(proc.stdout.split(FOOTER_MARK, 1)[1])
    return proc.stdout, footer


def test_demo_steps_all_hit_their_expected_verdicts(tmp_path):
    out = tmp_path / "qg"
    stdout, footer = _run_demo(out)

    assert footer["all_expected"] is True
    assert footer["steps"] == EXPECTED_STEPS
    assert footer["genesis"].startswith("sha256:")
    assert footer["head"].startswith("sha256:")
    # the human-readable transcript mentions every step's outcome
    assert "REJECT" in stdout and "CONFLICT" in stdout and "PASS" in stdout


def test_demo_package_verifies_from_disk(tmp_path):
    out = tmp_path / "qg"
    _, footer = _run_demo(out)

    for name in ("receipt.json", "claim.json", "chain.json",
                 "RUN.md", "hashes.json"):
        assert (out / name).is_file(), f"missing {name}"

    report = verify_bundle(out, anchored_genesis=footer["genesis"],
                           anchored_head=footer["head"])
    assert report.passed, report.to_dict()
    assert report.properties["reproducibility"]["status"] == "PASS"
    assert report.properties["anchor"]["status"] == "PASS"
    assert report.properties["occurrence"]["status"] == "NOT_DEMONSTRATED"

    manifest = verify_manifest(out / "hashes.json")
    assert manifest.passed, manifest.to_dict()
    assert all(check.ok for check in manifest.artifacts)


def test_demo_bundle_fails_when_a_written_artifact_is_tampered(tmp_path):
    out = tmp_path / "qg"
    _, footer = _run_demo(out)

    receipt = json.loads((out / "receipt.json").read_text(encoding="utf-8"))
    receipt["decision"]["decision"] = "ALLOW"
    (out / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")

    after = verify_bundle(out, anchored_genesis=footer["genesis"],
                          anchored_head=footer["head"])
    assert not after.passed, "a tampered package must not verify"
