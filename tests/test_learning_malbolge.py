"""Learning Pack V0 gate — the Malbolge vertical slice.

What this gate proves (compose requirements, 2026-09-19):

A. known-good exercise -> PASS                    (machine verdict)
B. wrong character -> FAIL                         (never faked)
C. malformed input -> INVALID                      (never a crash, never PASS)
D. verifier unavailable -> UNAVAILABLE            (never model-derived PASS)
E. pack absent -> IsyMotron core remains healthy   (the seam boundary)
F. the avatar cannot forge a verifier result
G. the receipt names the actual verifier tooling
H. existing gates keep passing (this suite is green alongside them)

Plus the differentials that keep the verdict real:
- the vendored oracle runs the canonical published hello-world program;
- the vendored codec/encoder keep their exhaustive parity (spot grid);
- the codec opcode table maps onto the oracle's reference letters
  (two independently-derived formulations agreeing);
- on dev machines with the sibling repositories present, the vendored
  copies are checked against their sources (copy integrity; skips in CI).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import re

import pytest

from learning import (
    FAIL, INVALID, PASS, UNAVAILABLE, LessonReceipt, verify_exercise,
)
from learning.packs.malbolge import lesson, verifier
from learning.packs.malbolge.verifier import MalbolgeVerifier

REPO = Path(__file__).resolve().parents[1]

# The canonical Malbolge hello-world program, widely published (Wikipedia,
# esolangs.org) — the same literal used by the oracle repository's own tests.
HELLO_WORLD = (
    "(=<`#9]~6ZY32Vx/4Rs+0No-&Jk)\"Fh}|Bcy?`=*z]Kw%oG4UUS0/@-ejc(:'8dc"
)
# opcode -> reference instruction letter, verified against the vendored
# oracle's XLAT1 before this lesson shipped (the classic +33 offset).
OPCODE_TO_REFERENCE = {
    4: "i", 5: "<", 23: "/", 39: "*", 40: "j", 62: "p", 68: "o", 81: "v",
}


@pytest.fixture
def malbolge():
    return lesson(), MalbolgeVerifier()


# -- A: known good --------------------------------------------------------

def test_known_good_answer_passes(malbolge):
    les, ver = malbolge
    exercise = les.exercise("malbolge-nop-17")
    receipt = verify_exercise(les, ver, exercise, "3")
    assert receipt.verdict == PASS
    assert receipt.observed["decoded_opcode"] == 68
    assert receipt.observed["reference_instruction"] == "o"
    assert receipt.verify(), "the seal must check out"
    assert receipt.verdict_source == "machine"
    # execution witness: the composed program really ran with the answer
    assert receipt.execution["halted"] is True
    assert receipt.execution["steps"] == 19
    assert receipt.execution["accumulator"] == 0


# -- B: wrong character ---------------------------------------------------

def test_wrong_character_fails(malbolge):
    les, ver = malbolge
    receipt = verify_exercise(les, ver, les.exercise("malbolge-nop-17"), "4")
    assert receipt.verdict == FAIL
    assert receipt.observed["decoded_opcode"] != 68  # '4' at 17 decodes to 69
    assert receipt.observed["decoded_opcode"] == 69
    assert receipt.verify()


# -- C: malformed input ---------------------------------------------------

@pytest.mark.parametrize("answer", ["", "ab", "\n", "é", chr(200), chr(32)])
def test_out_of_contract_input_is_invalid(malbolge, answer):
    les, ver = malbolge
    receipt = verify_exercise(les, ver, les.exercise("malbolge-nop-17"), answer)
    assert receipt.verdict == INVALID
    assert "reason" in receipt.observed
    assert receipt.verify()


# -- D: verifier unavailable ----------------------------------------------

def test_unavailable_tooling_is_unavailable_never_pass(monkeypatch, malbolge):
    les, _ver = malbolge
    monkeypatch.setitem(sys.modules, "learning.packs.malbolge.vendor", None)
    fresh = MalbolgeVerifier()  # tooling not yet loaded
    receipt = verify_exercise(les, fresh, les.exercise("malbolge-nop-17"), "3")
    assert receipt.verdict == UNAVAILABLE
    assert receipt.verified_by == []
    assert receipt.verify()
    assert "never produces PASS" in " ".join(receipt.notes)


# -- E: the seam boundary -------------------------------------------------

def test_importing_the_seam_does_not_import_any_pack():
    code = ("import sys; import learning; "
            "print('malbolge' if [m for m in sys.modules if m.startswith('learning.packs')] else 'clean')")
    r = subprocess.run([sys.executable, "-c", code], cwd=str(REPO),
                        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "clean" in r.stdout, "the seam imported a pack on its own"


def test_core_console_avatar_never_learn_malbolge():
    """The boundary is the code edge, not the vocabulary: the desktop pet's
    art pack is legitimately named "malbolge-cat" (pre-existing provenance),
    and a name in a string is not an import (the three-genealogies rule).
    What core areas must never do is *import* the learning seam or the
    vendored tooling."""
    import_edge = re.compile(r"^\s*(from|import)\s+(learning|learning\.)",
                             re.MULTILINE)
    vendor_edge = re.compile(r"classic_(codec|encoder)|from\s+\.vendor|\boracle\b")
    for area in ("core", "console", "avatar", "agents", "relay", "clients"):
        for path in (REPO / area).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert not import_edge.search(source), \
                f"{path} reaches into the learning seam"
            if path.name == "window.py" or "packs" in path.parts:
                continue  # art assets + their loader are data, not semantics
            assert "learning.packs" not in source, f"{path} knows the pack"


def test_unknown_pack_is_a_clean_error():
    from learning.__main__ import run
    assert run(["nosuchpack"]) == 4


# -- F: the avatar cannot forge a result -----------------------------------

def test_projection_is_third_party_speech_only(tmp_path):
    """A say line — forged or genuine — can only ever be a bubble."""
    from avatar.inbox import InboxTail, resolve_inbox_path
    from avatar.model import AvatarBus

    bus = AvatarBus()
    inbox = tmp_path / "inbox.jsonl"
    inbox.touch()  # the tail must SEE the file before lines exist (contract §1:
    # backlog before the first sighting is never replayed — the known trap)
    tail = InboxTail(bus, inbox)
    tail.poll_once()  # establishes its offset on the empty file

    les, ver = lesson(), MalbolgeVerifier()
    from learning import project_line
    assert project_line(inbox, les, "lesson: prove the encoding")
    assert project_line(inbox, les,
                        "malbolge-nop-17: PASS — the machine says so")
    tail.poll_once()
    assert tail.lines_seen == 2

    # A forged claim is indistinguishable from this speech, by design: both
    # are open-channel events. What neither can ever do is produce a
    # LessonReceipt — the only source of receipts is verify_exercise.
    events = bus.since(0)
    assert all(event["channel"] == "open" for event in events)
    assert all(event["agent_verified"] is False for event in events)


def test_tampered_receipt_breaks_its_own_seal(malbolge):
    les, ver = malbolge
    receipt = verify_exercise(les, ver, les.exercise("malbolge-nop-17"), "3")
    forged = json.loads(json.dumps(receipt.to_dict()))
    assert LessonReceipt.from_dict(forged).verify()
    forged["verdict"] = "PASS" if forged["verdict"] != "PASS" else "FAIL"
    assert not LessonReceipt.from_dict(forged).verify(), \
        "a receipt with an edited verdict must fail its own seal"


def test_avatar_and_console_cannot_create_receipts():
    for area in ("avatar", "console", "console/static"):
        folder = REPO / area
        for path in list(folder.rglob("*.py")) + list(folder.rglob("*.js")):
            source = path.read_text(encoding="utf-8")
            assert "LessonReceipt" not in source, f"{path} can build receipts"
            assert "verify_exercise" not in source, f"{path} can mint verdicts"


# -- G: the receipt names the real verifier --------------------------------

def test_receipt_names_the_machine_not_a_model(malbolge):
    les, ver = malbolge
    receipt = verify_exercise(les, ver, les.exercise("malbolge-nop-17"), "3")
    joined = " ".join(receipt.verified_by).lower()
    assert "classic_codec" in joined
    assert "oracle" in joined
    for banned in ("model", "planner", "provider", "llm"):
        assert banned not in joined
    assert receipt.verdict_source == "machine"
    assert any("malbolge-oracle" in line for line in receipt.provenance)
    assert any("MALBOLGE" in line for line in receipt.provenance)


# -- differentials ----------------------------------------------------------

def test_vendored_oracle_runs_the_canonical_hello_world():
    from learning.packs.malbolge.vendor.oracle import Oracle
    machine = Oracle()
    machine.load_ascii(list(HELLO_WORLD))
    result = machine.run(max_steps=100_000)
    assert result.output == "Hello World!"
    assert result.halted is True
    assert result.halt_reason == "halt_opcode"
    assert result.steps == 40


def test_vendored_codec_keeps_parity():
    from learning.packs.malbolge.vendor.classic_encoder import OPCODES, encode
    from learning.packs.malbolge.vendor.classic_codec import decode
    for position in list(range(0, 120)) + [300, 1000, 59048]:
        for opcode in OPCODES:
            _, _, char = encode(opcode, position)
            assert decode(char, position) == opcode, (opcode, position)


def test_opcode_table_maps_onto_reference_letters():
    from learning.packs.malbolge.vendor.oracle import XLAT1
    for opcode, letter in OPCODE_TO_REFERENCE.items():
        assert XLAT1[(opcode - 33) % 94] == letter, opcode


def test_clasesbolge_worked_examples_hold(malbolge):
    """The lesson's numbers are the educational material's numbers."""
    from learning.packs.malbolge.vendor.classic_encoder import encode
    assert encode(68, 3)[2] == "A"
    assert encode(68, 17)[2] == "3"


@pytest.mark.skipif(
    not Path(r"C:\Development\ISyCo Git\malbolge-oracle\oracle.py").exists()
    or not Path(r"C:\Development\ISyCo Git\MALBOLGE\classic_encoder.py").exists(),
    reason="sibling repositories not present (this check is dev-machine only)")
def test_vendored_copies_match_their_sources():
    """Copy integrity, not fake independence: the vendored behaviour must be
    the source repositories' behaviour, checked against the originals."""
    import importlib.util

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module  # dataclasses needs the module registered
        spec.loader.exec_module(module)
        return module

    src_encoder = load("src_encoder", r"C:\Development\ISyCo Git\MALBOLGE\classic_encoder.py")
    src_oracle = load("src_oracle", r"C:\Development\ISyCo Git\malbolge-oracle\oracle.py")
    from learning.packs.malbolge.vendor import classic_encoder, oracle

    assert classic_encoder.OPCODES == src_encoder.OPCODES
    assert oracle.XLAT1 == src_oracle.XLAT1
    assert oracle.XLAT2 == src_oracle.XLAT2
    assert oracle.op(1234, 5678) == src_oracle.op(1234, 5678)
    assert oracle.rot(9876) == src_oracle.rot(9876)
    for position in range(0, 94):
        for opcode in src_encoder.OPCODES:
            assert classic_encoder.encode(opcode, position) == \
                src_encoder.encode(opcode, position)


# -- end to end -------------------------------------------------------------

def _cli(argv):
    return subprocess.run(
        [sys.executable, "-m", "learning"] + argv,
        cwd=str(REPO), capture_output=True, text=True, timeout=120,
    )


def test_cli_pass_end_to_end():
    r = _cli(["malbolge", "--exercise", "1", "--answer", "3",
              "--no-project", "--json"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout
    receipt = json.loads(r.stdout[r.stdout.index("{"):])
    assert receipt["verdict"] == "PASS"
    assert receipt["verdict_source"] == "machine"
    sealed = LessonReceipt.from_dict(receipt)
    assert sealed.verify()


def test_cli_fail_and_invalid_exit_codes():
    r = _cli(["malbolge", "--exercise", "1", "--answer", "4", "--no-project"])
    assert r.returncode == 1
    r = _cli(["malbolge", "--exercise", "1", "--answer", "zz", "--no-project"])
    assert r.returncode == 2


def test_cli_saves_receipts(tmp_path):
    out = tmp_path / "receipts"
    r = _cli(["malbolge", "--exercise", "1", "--answer", "3",
              "--no-project", "--save", str(out)])
    assert r.returncode == 0
    files = list(out.glob("rcpt_*.json"))
    assert len(files) == 1
    receipt = LessonReceipt.from_dict(json.loads(files[0].read_text(encoding="utf-8")))
    assert receipt.verdict == PASS
    assert receipt.verify()


def test_cli_projects_through_the_inbox(tmp_path):
    inbox = tmp_path / "inbox.jsonl"
    r = _cli(["malbolge", "--exercise", "1", "--answer", "3",
              "--inbox", str(inbox)])
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [json.loads(line) for line in
             inbox.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2  # lesson intro + machine verdict
    assert all(item["type"] == "say" and item["agent"] == "malbolge-cat"
               for item in lines)
    assert "PASS" in lines[-1]["text"]
    assert any(item["text"].startswith("malbolge-nop-17: PASS")
               for item in lines)
