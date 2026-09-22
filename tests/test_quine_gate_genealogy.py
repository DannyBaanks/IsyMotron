"""Quine Gate — M5: the state genealogy.

Proves the rule the design rests on: a state is only written when it names the
current head as its parent. A wrong parent halts the transition and leaves the
ledger unchanged. Verification then delegates to the anchored chain (M4), so a
fork or a rollback is caught against the published HEAD.
"""
from __future__ import annotations

import pytest

from isymotron.canon import digest
from isymotron.chain import CONFLICT, NOT_VERIFIABLE, PASS, REJECT, make_state
from isymotron.contracts import ExecutionRequest
from isymotron.genealogy import (
    Genealogy,
    GenealogyError,
    ParentMismatch,
    Transition,
    state_digest,
    verify_genealogy,
)
from simulator.engines import ModernHost


def _chain() -> Genealogy:
    ledger = Genealogy()
    ledger.start(Transition.genesis(label="S0", base_digest=digest({"base": "debian-min"})))
    ledger.append(ledger.head, Transition(
        kind="install", label="S1", operation="install:python",
        artifact_digest=digest({"python": "3.12"})))
    ledger.append(ledger.head, Transition(
        kind="execute", label="S2", operation="filesystem.read",
        inputs=(digest({"path": "C:/x"}),), policy_digest=digest({"granted": []}),
        output_digest=digest({"error": "OUT_OF_SCOPE"})))
    return ledger


def test_linear_genealogy_links_each_state_to_its_parent():
    ledger = _chain()
    states = ledger.states()
    assert len(states) == 3
    assert states[0]["parent"] is None
    assert states[1]["parent"] == states[0]["sha"]
    assert states[2]["parent"] == states[1]["sha"]
    assert ledger.head == states[2]["sha"]


def test_wrong_parent_halts_the_transition_and_changes_nothing():
    ledger = _chain()
    before = ledger.states()
    with pytest.raises(ParentMismatch):
        ledger.append("sha256:" + "f" * 64, Transition(kind="configure", label="S3"))
    assert ledger.states() == before, "a refused transition must not mutate the ledger"


def test_no_parent_on_a_non_empty_genealogy_is_refused():
    ledger = _chain()
    with pytest.raises(ParentMismatch):
        ledger.append(None, Transition(kind="configure", label="S3"))


def test_a_stale_head_is_refused():
    ledger = _chain()
    stale = ledger.states()[0]["sha"]
    with pytest.raises(ParentMismatch):
        ledger.append(stale, Transition(kind="configure", label="S3-fork"))


def test_start_is_only_valid_once():
    ledger = _chain()
    with pytest.raises(GenealogyError):
        ledger.start(Transition.genesis())


def test_unknown_transition_kind_is_refused():
    with pytest.raises(GenealogyError):
        Transition(kind="teleport", label="S?")


def test_verify_genealogy_passes_with_both_anchors():
    ledger = _chain()
    result = verify_genealogy(ledger.to_list(), anchored_genesis=ledger.genesis,
                              anchored_head=ledger.head)
    assert result.passed and result.status == PASS


def test_genesis_only_is_not_verifiable():
    ledger = _chain()
    result = verify_genealogy(ledger.to_list(), anchored_genesis=ledger.genesis,
                              anchored_head=None)
    assert not result.passed and result.status == NOT_VERIFIABLE


def test_tampered_transition_without_rehash_is_rejected():
    states = _chain().to_list()
    states[1] = dict(states[1])
    states[1]["transition"] = dict(states[1]["transition"], operation="backdoor")
    result = verify_genealogy(states, anchored_genesis=states[0]["sha"],
                              anchored_head=states[-1]["sha"])
    assert not result.passed and result.status == REJECT


def test_fork_from_an_old_head_conflicts():
    ledger = _chain()
    states = ledger.states()
    fork_tip = make_state(states[1]["sha"], Transition(
        kind="execute", label="S2'", operation="filesystem.write",
        output_digest=digest({"wrote": "backdoor"})).to_dict())
    result = verify_genealogy([states[0], states[1], fork_tip],
                              anchored_genesis=states[0]["sha"],
                              anchored_head=states[2]["sha"])
    assert not result.passed and result.status == CONFLICT


def test_rollback_to_an_older_head_conflicts():
    ledger = _chain()
    states = ledger.states()
    result = verify_genealogy([states[0], states[1]],
                              anchored_genesis=states[0]["sha"],
                              anchored_head=states[2]["sha"])
    assert not result.passed and result.status == CONFLICT


def test_from_states_roundtrips():
    ledger = _chain()
    restored = Genealogy.from_states(ledger.to_list())
    assert restored.to_list() == ledger.to_list()
    assert restored.head == ledger.head


def test_state_digest_matches_a_built_state():
    ledger = _chain()
    last = ledger.states()[-1]
    rebuilt = make_state(last["parent"], last["transition"])
    assert rebuilt["sha"] == last["sha"]


def test_transition_from_a_real_receipt_seals_the_execution():
    host = ModernHost(
        fs={"C:/Users/demo/Photos/s.png": "P", "C:/Users/demo/Secrets/k.txt": "h"},
        granted=["filesystem.read"],
        grant_scopes={"filesystem.read": {"roots": ["C:/Users/demo/Photos"]}},
        host_id="win11-genealogy", display_name="Genealogy",
    )
    lease, _ = host.request_lease("mobile:g", "filesystem.read", 300)
    request = ExecutionRequest.make("win11-genealogy", "mobile:g", "filesystem.read",
                                    {"path": "C:/Users/demo/Secrets/k.txt"},
                                    lease_id=lease.lease_id)
    receipt = host.execute_capability(request)

    ledger = Genealogy()
    ledger.start(Transition.genesis(label="S0"))
    transition = Transition.from_receipt(receipt, label="S1")
    state = ledger.append(ledger.head, transition)

    assert transition.operation == "filesystem.read"
    assert transition.inputs == (receipt.request_digest,)
    assert transition.output_digest == receipt.result_digest
    assert transition.policy_digest == receipt.policy_digest
    assert state["transition"]["label"] == "S1"
    assert verify_genealogy(ledger.to_list(), anchored_genesis=ledger.genesis,
                            anchored_head=ledger.head).passed
