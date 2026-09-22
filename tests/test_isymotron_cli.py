"""isymotron CLI — M0: the verb table is complete, and stays complete.

The point of this gate is the property the old CLI could not hold: an
entrypoint that exists on disk must be reachable from `isymotron`, or be
excluded on the record. Deleting a verb has to turn this suite red.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI_PATH = REPO / "tools" / "isymotron_cli.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("isymotron_cli", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves `cls.__module__` through sys.modules, so the module
    # must be registered before exec_module runs.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # M0 has no side effects at import time
    return module


cli = _load_cli()

#: Verbs the product documented before this plan (isymotron.ps1) plus the
#: groups this plan adds. A subset check, so the surface may grow.
DOCUMENTED_SURFACE = {
    "start", "console", "pet", "test", "build", "spoof", "host", "demo",
    "learn", "install", "where", "help",
    "keys", "quine", "process", "evidence", "nemotron", "host-watch",
}


def test_no_entrypoint_is_orphaned():
    """Every tools/*.py, root script and `-m` package is reachable or excluded."""
    assert cli.orphan_entrypoints() == []


def test_removing_a_verb_makes_the_check_bite():
    """The check is not decorative: drop a verb and its entrypoint is orphaned."""
    reduced = {name: verb for name, verb in cli.VERBS.items() if name != "host"}
    assert "tools/host_cli.py" in cli.orphan_entrypoints(reduced)


def test_the_documented_surface_is_present():
    assert DOCUMENTED_SURFACE <= set(cli.VERBS)


def test_verb_keys_match_their_names():
    for key, verb in cli.VERBS.items():
        assert key == verb.name, f"table key {key!r} != Verb.name {verb.name!r}"


def test_every_entrypoint_that_is_a_path_exists_on_disk():
    for verb in cli.VERBS.values():
        refs = verb.referenced_entrypoints()
        refs.add(verb.entrypoint) if verb.entrypoint else None
        for ref in refs:
            if ref.endswith(".py"):
                assert (REPO / ref).is_file(), f"{verb.name} points at missing {ref}"


def test_exclusions_exist_and_state_a_reason():
    for path, reason in cli.EXCLUDED.items():
        assert (REPO / path).exists(), f"excluded {path} does not exist"
        assert reason.strip(), f"excluded {path} has no reason"


def test_known_entrypoints_are_discovered_not_guessed():
    known = cli.known_entrypoints()
    assert "tools/host_cli.py" in known
    assert "tools/quine_gate_verify.py" in known
    assert "-m console" in known
    assert "build_exe.py" in known
    # the discovery walks the real tree
    assert "tools/process_verify.py" in known


def test_grouped_verbs_reference_their_subcommands():
    quine = cli.VERBS["quine"]
    assert set(quine.subcommands) == {"demo", "verify", "publish"}
    assert set(quine.referenced_entrypoints()) == {
        "tools/quine_gate_demo.py",
        "tools/quine_gate_verify.py",
        "tools/quine_gate_publish.py",
    }


def test_verbs_implemented_inside_the_cli_have_no_entrypoint():
    for name in ("keys", "install", "where", "help"):
        assert cli.VERBS[name].entrypoint is None
        assert cli.VERBS[name].subcommands == {}
