"""L3-L6 Malbolge gate: oracle-backed semantics, not model answers."""

from learning import PASS, verify_exercise
from learning.packs.malbolge.advanced import lesson, verifier


def test_all_advanced_levels_have_machine_passes():
    les, ver = lesson(), verifier()
    answers = {
        "malbolge-l3-registers": "0,0,0",
        "malbolge-l4-crazy-op": "29525",
        "malbolge-l5-encryption": "yes",
        "malbolge-l6-hello-world": "Hello World!",
    }
    for exercise in les.exercises[:4]:
        receipt = verify_exercise(les, ver, exercise, answers[exercise.exercise_id])
        assert receipt.verdict == PASS, exercise.exercise_id
        assert receipt.verify()
        assert receipt.verdict_source == "machine"


def test_wrong_semantics_fail():
    les, ver = lesson(), verifier()
    receipt = verify_exercise(les, ver, les.exercise("malbolge-l4"), "29524")
    assert receipt.verdict == "FAIL"
    assert receipt.verify()


def test_canonical_hello_world_is_still_forty_steps():
    les, ver = lesson(), verifier()
    receipt = verify_exercise(les, ver, les.exercise("malbolge-l6"), "Hello World!")
    assert receipt.execution["output"] == "Hello World!"
    assert receipt.execution["steps"] == 40


def test_l7_l8_l9_and_l13_machine_witnesses_pass():
    les, ver = lesson(), verifier()
    answers = {
        "malbolge-l7-roundtrip": "yes",
        "malbolge-l8-differential": "consistent",
        "malbolge-l9-existing": "Hello World!",
        "malbolge-l13-episodic": "yes",
    }
    for exercise_id, answer in answers.items():
        receipt = verify_exercise(les, ver, les.exercise(exercise_id), answer)
        assert receipt.verdict == PASS, exercise_id
        assert receipt.verify()


def test_l10_to_l12_are_explicitly_unavailable():
    les, ver = lesson(), verifier()
    receipt = verify_exercise(les, ver, les.exercise("malbolge-l10"), "69547437")
    assert receipt.verdict == PASS
    assert receipt.execution is None
    assert "evidence-only" in receipt.notes[0]
    assert receipt.verify()
    for prefix in ("malbolge-l11", "malbolge-l12"):
        receipt = verify_exercise(les, ver, les.exercise(prefix), "")
        assert receipt.verdict == "UNAVAILABLE"
        assert receipt.verify()
        assert "NOT_DEMONSTRATED" in receipt.notes[0]
