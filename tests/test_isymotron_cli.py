"""isymotron CLI — M0: the verb table is complete, and stays complete.

The point of this gate is the property the old CLI could not hold: an
entrypoint that exists on disk must be reachable from `isymotron`, or be
excluded on the record. Deleting a verb has to turn this suite red.
"""
from __future__ import annotations

import importlib.util
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CLI_PATH = REPO / "tools" / "isymotron_cli.py"

LINUX_ONLY = pytest.mark.skipif(not sys.platform.startswith("linux"),
                                reason="the pty menu test is POSIX-only")


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
    done = _run("install")
    assert done.returncode == 2, "install must not look like it worked"
    assert "M6" in done.stdout


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


# -- M3: keys — stored outside the repo, never echoed ------------------------

SECRET = "nvapi-SUPERSECRET-0123456789"


def _keyed_run(*args, store, stdin_text=None, env_extra=None):
    import subprocess
    env = dict(os.environ, ISYMOTRON_KEY_STORE=str(store))
    env.update(env_extra or {})
    return subprocess.run([sys.executable, str(CLI_PATH), *args], cwd=str(REPO),
                          capture_output=True, text=True, timeout=30,
                          env=env, input=stdin_text)


def test_keys_set_stores_outside_the_repo_and_never_prints_the_secret(tmp_path):
    store = tmp_path / "keys.env"
    done = _keyed_run("keys", "set", "NVIDIA_NIM_API_KEY",
                      store=store, stdin_text=SECRET + "\n")
    assert done.returncode == 0, done.stdout
    assert SECRET not in done.stdout, "the value must never be echoed"

    assert store.is_file()
    if os.name != "nt":
        assert (store.stat().st_mode & 0o777) == 0o600, "the store must be private"
    assert SECRET in store.read_text(encoding="utf-8")

    listed = _keyed_run("keys", "list", store=store)
    assert listed.returncode == 0
    assert SECRET not in listed.stdout, "list must show a fingerprint, not the value"
    assert "sha256:" in listed.stdout
    assert "NVIDIA_NIM_API_KEY" in listed.stdout

    unset = _keyed_run("keys", "unset", "NVIDIA_NIM_API_KEY", store=store)
    assert unset.returncode == 0
    assert SECRET not in store.read_text(encoding="utf-8")
    assert "missing" in _keyed_run("keys", "list", store=store).stdout


def test_keys_shows_non_secret_config_plainly(tmp_path):
    store = tmp_path / "keys.env"
    _keyed_run("keys", "set", "ISYMOTRON_PROVIDER", store=store, stdin_text="nebius\n")
    listed = _keyed_run("keys", "list", store=store).stdout
    assert "nebius" in listed


def test_keys_rejects_unknown_names_and_invalid_provider(tmp_path):
    store = tmp_path / "keys.env"
    bad_name = _keyed_run("keys", "set", "AWS_SECRET", store=store, stdin_text="x\n")
    assert bad_name.returncode == 2
    bad_value = _keyed_run("keys", "set", "ISYMOTRON_PROVIDER",
                           store=store, stdin_text="gemini\n")
    assert bad_value.returncode == 2
    assert "nvidia" in bad_value.stdout


def test_keys_refuses_to_write_inside_the_repository(tmp_path):
    inside = REPO / "keys.env"
    done = _keyed_run("keys", "set", "NEBIUS_API_KEY",
                      store=inside, stdin_text="x\n")
    assert done.returncode == 2
    assert "inside the repository" in done.stdout
    assert not inside.exists()


def test_keys_check_reports_missing_and_ok(tmp_path):
    store = tmp_path / "keys.env"
    assert _keyed_run("keys", "check", store=store).returncode == 2
    _keyed_run("keys", "set", "NVIDIA_NIM_API_KEY", store=store, stdin_text=SECRET + "\n")
    partial = _keyed_run("keys", "check", store=store)
    assert "missing" in partial.stdout and "ok" in partial.stdout


def test_child_env_injects_the_store(monkeypatch, tmp_path):
    store = tmp_path / "keys.env"
    store.write_text("NEBIUS_API_KEY=injected-value\n", encoding="utf-8")
    monkeypatch.setenv("ISYMOTRON_KEY_STORE", str(store))
    env = cli.child_env()
    assert env["NEBIUS_API_KEY"] == "injected-value"


# -- M4: every capability is reachable from the one command ------------------

def test_grouped_verb_needs_a_known_subcommand():
    bare = _run("quine")
    assert bare.returncode == 2
    for sub in ("demo", "verify", "publish"):
        assert sub in bare.stdout

    bogus = _run("quine", "bogus")
    assert bogus.returncode == 2
    assert "unknown quine subcommand 'bogus'" in bogus.stdout


def test_grouped_verb_routes_to_its_subcommand_entrypoint():
    # argparse's own help proves the routing without running the demo.
    done = _run("quine", "verify", "--help")
    assert done.returncode == 0
    assert "bundle" in done.stdout


def test_evidence_verify_reports_a_real_manifest():
    done = _run("evidence", "verify", "evidence/M3/hashes.json")
    assert done.returncode == 0, done.stdout
    payload = json.loads(done.stdout)
    assert payload["passed"] is True
    assert payload["algorithm"] == "SHA-256"


def test_evidence_verify_exit_codes(tmp_path):
    artifact = tmp_path / "a.txt"
    artifact.write_bytes(b"bytes")
    manifest = tmp_path / "hashes.json"
    manifest.write_text(json.dumps({
        "algorithm": "SHA-256",
        "artifacts": {"a.txt": "0" * 64},          # wrong on purpose
    }), encoding="utf-8")

    mismatch = _run("evidence", "verify", str(manifest))
    assert mismatch.returncode == 1, mismatch.stdout        # ran, found a mismatch
    unreadable = _run("evidence", "verify", str(tmp_path / "nope.json"))
    assert unreadable.returncode == 2, unreadable.stdout    # could not verify
    assert _run("evidence", "verify").returncode == 2       # usage error


def test_new_verbs_are_wired():
    for name in ("nemotron", "host-watch"):
        done = _run(name, "--help")
        assert done.returncode == 0, f"{name} did not reach its entrypoint"
    # process is wired through the same pass-through
    done = _run("process", "observe", "--help")
    assert done.returncode == 0


# -- M5: the interactive menu (munder's model, POSIX backend here) -----------

def _run_in_pty(keys=b"q", timeout=20.0):
    import pty
    master, slave = pty.openpty()
    proc = subprocess.Popen([sys.executable, str(CLI_PATH)], cwd=str(REPO),
                            stdin=slave, stdout=slave, stderr=slave, close_fds=True)
    os.close(slave)
    out = b""
    try:
        time.sleep(0.5)                     # let the menu render
        os.write(master, keys)
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
            elif proc.poll() is not None:
                break
        proc.wait(timeout=5)
    finally:
        if proc.poll() is None:
            proc.kill()
        os.close(master)
    return proc.returncode, out.decode("utf-8", "replace")


@LINUX_ONLY
def test_menu_appears_with_a_tty_and_q_exits_without_hanging():
    code, out = _run_in_pty(b"q")
    assert code == 0, out
    assert "What do we do?" in out, out
    assert "bye" in out, out


@LINUX_ONLY
def test_menu_number_key_selects_an_entry():
    # "1" is "Show help and every command"; then "q" leaves.
    code, out = _run_in_pty(b"1q")
    assert code == 0, out
    assert "Usage: isymotron" in out, out


@LINUX_ONLY
def test_menu_ctrl_c_aborts_with_130():
    code, out = _run_in_pty(b"\x03")
    assert code == 130, (code, out)
