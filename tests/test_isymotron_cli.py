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


# -- M1: the skeleton, exercised as a real process ---------------------------

def _run(*args, timeout=30, **kwargs):
    import subprocess
    return subprocess.run(
        [sys.executable, str(CLI_PATH), *args],
        cwd=str(REPO), capture_output=True, text=True, timeout=timeout, **kwargs)


def test_help_exits_zero_and_lists_every_verb():
    done = _run("help")
    assert done.returncode == 0
    assert "Usage: isymotron" in done.stdout
    for name in cli.VERBS:
        assert name in done.stdout, f"{name} missing from help"


def test_short_and_long_help_are_available():
    assert _run("-h").returncode == 0
    assert _run("--help").returncode == 0
    assert "Usage: isymotron" in _run("-h").stdout


def test_unknown_command_is_exit_two_and_points_at_help():
    done = _run("zzz")
    assert done.returncode == 2
    assert "unknown command 'zzz'" in done.stdout
    assert "isymotron help" in done.stdout


def test_no_args_without_a_tty_prints_help_and_never_hangs():
    done = _run(timeout=20)          # a hang raises TimeoutExpired and fails
    assert done.returncode == 0
    assert "Usage: isymotron" in done.stdout


def test_stdout_closed_does_not_hang():
    import subprocess
    done = subprocess.run([sys.executable, str(CLI_PATH), "help"],
                          cwd=str(REPO), stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=20)
    assert done.returncode == 0


def test_where_prints_the_repository():
    done = _run("where")
    assert done.returncode == 0
    assert done.stdout.strip() == str(REPO)


def test_version_mentions_the_product():
    done = _run("--version")
    assert done.returncode == 0
    assert done.stdout.startswith("isymotron")


def test_unimplemented_verbs_fail_closed():
    for name, milestone in (("keys", "M3"), ("install", "M6")):
        done = _run(name)
        assert done.returncode == 2, f"{name} must not look like it worked"
        assert milestone in done.stdout


def test_a_verb_passes_through_and_propagates_the_exit_code():
    # `host --help` is argparse's own help: safe, side-effect free, exit 0.
    done = _run("host", "--help")
    assert done.returncode == 0
    assert "status" in done.stdout

    # `process verify` with a missing baseline exits 2; the CLI must not mask it.
    missing = _run("process", "verify", "1", "--baseline", str(REPO / "nope.json"))
    assert missing.returncode == 2
    assert "NO_BASELINE" in missing.stdout


# -- M2: parity with the invocations isymotron.ps1 already documented ---------

#: verb -> argv after the interpreter, exactly as the PowerShell CLI ran them.
PS1_PARITY = {
    "start": ["-m", "console", "--avatar"],
    "console": ["-m", "console"],
    "pet": ["-m", "console", "--avatar-worker", "--port", "8760"],
    "test": ["-m", "pytest", "-q"],
    "build": ["build_exe.py"],
    "spoof": ["tools/avatar_spoof.py"],
    "host": ["tools/host_cli.py", "status"],
    "demo": ["tools/m0_demo.py"],
    "learn": ["-m", "learning"],
}


def test_argv_matches_the_powershell_cli_for_every_inherited_verb():
    for name, expected in PS1_PARITY.items():
        argv = cli.build_argv(cli.VERBS[name], [], executable="PY")
        assert argv == ["PY", *expected], f"{name} drifted from isymotron.ps1"


def test_defaults_only_apply_when_no_arguments_are_passed():
    # a bare `test` is `pytest -q`; with arguments there is no implicit -q
    assert cli.build_argv(cli.VERBS["test"], [], executable="PY") == \
        ["PY", "-m", "pytest", "-q"]
    assert cli.build_argv(cli.VERBS["test"], ["-k", "keys"], executable="PY") == \
        ["PY", "-m", "pytest", "-k", "keys"]
    # a bare `host` is `host_cli.py status`
    assert cli.build_argv(cli.VERBS["host"], [], executable="PY") == \
        ["PY", "tools/host_cli.py", "status"]
    assert cli.build_argv(cli.VERBS["host"], ["grant", "filesystem.read"],
                          executable="PY") == \
        ["PY", "tools/host_cli.py", "grant", "filesystem.read"]


def test_flags_reach_the_child_verbatim():
    flags = ["grant", "filesystem.read", "--root", "C:/Users/demo/Photos"]
    assert cli.build_argv(cli.VERBS["host"], flags, executable="PY") == \
        ["PY", "tools/host_cli.py", *flags]
    # a flag-like argument is forwarded, never swallowed by the top level
    assert cli.build_argv(cli.VERBS["console"], ["--lan", "--no-browser"],
                          executable="PY") == \
        ["PY", "-m", "console", "--lan", "--no-browser"]
