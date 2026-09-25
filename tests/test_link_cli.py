"""M3: link CLI verbs. Hermetic via XDG_STATE_HOME; no servers, no network."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
LINK_CLI = REPO / "tools" / "link_cli.py"


@pytest.fixture()
def state_home(tmp_path, monkeypatch):
    home = tmp_path / "xdg"
    monkeypatch.setenv("XDG_STATE_HOME", str(home))
    return home


def run_cli(*args, **kwargs):
    return subprocess.run(
        [sys.executable, str(LINK_CLI), *args],
        capture_output=True,
        text=True,
        timeout=60,
        **kwargs,
    )


def test_help_lists_verbs_and_runs_nothing(state_home):
    proc = run_cli("--help")
    assert proc.returncode == 0
    for verb in ("estado", "buscar", "emparejar", "aceptar", "enviar", "tarea", "servir"):
        assert verb in proc.stdout


def test_estado_bootstraps_identity(state_home):
    proc = run_cli("estado")
    assert proc.returncode == 0
    assert "ESTA OFICINA" in proc.stdout
    assert (state_home / "isymotron" / "link" / "identity.json").is_file()


def test_aceptar_bad_code_rejected(state_home):
    run_cli("estado")
    proc = run_cli("aceptar", "000000")
    assert proc.returncode == 1
    assert "no coincide" in proc.stdout


def test_olvidar_unknown_is_clean_error(state_home):
    run_cli("estado")
    proc = run_cli("olvidar", "nadie")
    assert proc.returncode == 1


def test_unknown_subcommand_is_exit_two(state_home):
    proc = run_cli("nosub")
    assert proc.returncode == 2
