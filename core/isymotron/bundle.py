"""Quine Gate verification bundle (milestone M7).

A bundle is a directory a third party can check offline::

    bundle/
      receipt.json   ExecutionReceipt v1 (to_dict shape)
      claim.json     ClaimBundle (to_dict shape)
      chain.json     [state, ...]                 (optional)
      hashes.json    SHA-256 artifact manifest     (optional)

Anchors are NOT part of the bundle: they are passed in by the caller, because
an anchor stored next to the chain it anchors can be rewritten with it.

``verify_bundle`` reports each property separately. It deliberately has no
single "secure" verdict: artifact identity, state integrity, transition
validity, reproducibility, provenance, anchor, occurrence and host attestation
are different things, and two of them (occurrence, host attestation) this
system does not establish at all.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .chain import CONFLICT, NOT_VERIFIABLE, PASS, REJECT, verify_chain
from .contracts import ExecutionReceipt
from .evidence import verify_manifest
from .verify import ClaimBundle, verify_receipt

ABSENT = "ABSENT"
NOT_DEMONSTRATED = "NOT_DEMONSTRATED"

#: Properties that must be PASS for the bundle as a whole to pass.
REQUIRED = ("seal_integrity", "reproducibility")


@dataclass(frozen=True)
class BundleReport:
    bundle: str
    verdict: str
    passed: bool
    properties: dict
    not_demonstrated: tuple

    def to_dict(self) -> dict:
        return {
            "bundle": self.bundle,
            "verdict": self.verdict,
            "passed": self.passed,
            "properties": self.properties,
            "not_demonstrated": list(self.not_demonstrated),
        }


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _prop(status: str, detail: str = "") -> dict:
    return {"status": status, "detail": detail}


def verify_bundle(bundle_dir: str | Path, key: str | None = None, *,
                  anchored_genesis: str | None = None,
                  anchored_head: str | None = None) -> BundleReport:
    """Verify a bundle directory.

    Anchors must come from OUTSIDE the bundle. A file inside the bundle cannot
    anchor it: an attacker who rewrites the chain would rewrite the anchor
    with it. If the caller supplies no anchor, the ``anchor`` property is
    ``NOT_VERIFIABLE`` -- never taken from ``anchors.json``.

    Never raises on bad input.
    """
    base = Path(bundle_dir)
    props: dict[str, dict] = {}

    raw_receipt = _read_json(base / "receipt.json")
    raw_claim = _read_json(base / "claim.json")

    receipt = None
    claim = None
    if raw_receipt is not None:
        try:
            receipt = ExecutionReceipt.from_dict(raw_receipt)
        except (KeyError, ValueError, TypeError) as exc:
            props["seal_integrity"] = _prop(REJECT, f"unreadable receipt: {exc}")
    if raw_claim is not None:
        try:
            claim = ClaimBundle.from_dict(raw_claim)
        except (KeyError, ValueError, TypeError) as exc:
            props["reproducibility"] = _prop(REJECT, f"unreadable claim: {exc}")

    if "seal_integrity" not in props:
        props["seal_integrity"] = (
            _prop(PASS, "receipt seal verifies")
            if receipt is not None and receipt.verify(key)
            else _prop(NOT_VERIFIABLE if receipt is None else REJECT,
                       "no receipt or seal does not verify")
        )

    if "reproducibility" not in props:
        if receipt is None or claim is None:
            props["reproducibility"] = _prop(NOT_VERIFIABLE,
                                             "receipt/claim pair is incomplete")
        else:
            vr = verify_receipt(receipt, claim, key)
            props["reproducibility"] = _prop(
                PASS if vr.passed else ("NOT_VERIFIABLE" if vr.status == NOT_VERIFIABLE
                                        else REJECT),
                vr.reason,
            )

    # -- artifact identity (manifest) --------------------------------------
    if (base / "hashes.json").is_file():
        mv = verify_manifest(base / "hashes.json")
        props["artifact_identity"] = _prop(PASS if mv.passed else REJECT, mv.reason)
    else:
        props["artifact_identity"] = _prop(NOT_VERIFIABLE, "no hashes.json")

    # -- chain: integrity, transitions, anchor -----------------------------
    # `anchors.json` inside the bundle is NOT read: an anchor that travels with
    # the thing it anchors is not an anchor. Only the caller's values count.
    chain = _read_json(base / "chain.json")
    if isinstance(chain, list) and chain:
        cv = verify_chain(chain, anchored_genesis=anchored_genesis,
                          anchored_head=anchored_head)
        props["state_integrity"] = _prop(
            PASS if cv.internal_ok else REJECT,
            "chain hashes recompute and link" if cv.internal_ok else "chain is inconsistent")
        props["transition_validity"] = _prop(
            PASS if cv.internal_ok else REJECT,
            "every state names its verified parent" if cv.internal_ok
            else "a state does not link to its parent")
        props["anchor"] = _prop(cv.status, cv.reason)
    else:
        for name in ("state_integrity", "transition_validity", "anchor"):
            props[name] = _prop(NOT_VERIFIABLE, "no chain in the bundle")

    # -- properties this system does NOT establish -------------------------
    props["occurrence"] = _prop(NOT_DEMONSTRATED,
                                "reproduction is not proof that the run happened")
    props["host_attestation"] = _prop(ABSENT,
                                      "no TPM/TEE/measured boot; out of scope")

    required = list(REQUIRED)
    if isinstance(chain, list) and chain:
        required.append("anchor")
    passed = all(props[name]["status"] == PASS for name in required)
    statuses = {props[name]["status"] for name in required}
    if passed:
        verdict = PASS
    elif REJECT in statuses or CONFLICT in statuses:
        verdict = REJECT
    else:
        verdict = NOT_VERIFIABLE

    not_demonstrated = tuple(
        name for name, value in props.items()
        if value["status"] in (NOT_DEMONSTRATED, ABSENT, NOT_VERIFIABLE)
    )

    return BundleReport(base.as_posix(), verdict, passed, props, not_demonstrated)
