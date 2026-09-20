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
    for exercise in les.exercises:
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
