"""keys validation (control chars) + demo --help guard."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLI_PATH = REPO / "tools" / "isymotron_cli.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("isymotron_cli_keys", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cli = _load_cli()


def test_escape_sequence_value_rejected():
    problem = cli._validate_value("NVIDIA_NIM_API_KEY", "\x1b[B")
    assert problem is not None
    assert "control" in problem


def test_normal_key_accepted():
    assert cli._validate_value("NVIDIA_NIM_API_KEY", "nvapi-abc123DEF456") is None


def test_empty_still_rejected():
    assert cli._validate_value("NVIDIA_NIM_API_KEY", "") == "empty value"


def test_demo_help_does_not_run(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools" / "m0_demo.py"), "--help"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0
    assert "usage:" in proc.stdout
