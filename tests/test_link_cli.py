"""M3: link CLI verbs. Hermetic via XDG_STATE_HOME; no servers, no network."""
import os
import socket
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
LINK_CLI = REPO / "tools" / "link_cli.py"
sys.path.insert(0, str(REPO / "tools"))
from link_cli import lan_addresses


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


def test_lan_addresses_on_macos_use_bounded_interface_probes(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")

    def no_route(*_args, **_kwargs):
        raise OSError("hosted macOS runner has no configured default route")

    monkeypatch.setattr(socket, "socket", no_route)
    monkeypatch.setattr(socket, "getaddrinfo", no_route)
    calls = []

    def ipconfig(args, **kwargs):
        calls.append((args, kwargs))
        address = "192.168.1.42\n" if args[-1] == "en0" else ""
        return SimpleNamespace(returncode=0 if address else 1, stdout=address)

    monkeypatch.setattr(subprocess, "run", ipconfig)

    assert lan_addresses() == ["192.168.1.42"]
    assert calls and all(call[1]["timeout"] <= 0.25 for call in calls)


def _serve(state_home, *extra):
    proc = subprocess.Popen(
        [sys.executable, str(LINK_CLI), "servir", "--port", "0", "--udp-port", "0", *extra],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    lines = []
    deadline = __import__("time").time() + 30
    while __import__("time").time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line.rstrip("\n"))
        if not extra or "aceptar" in line:
            break
    return proc, lines


def _status(address: str) -> dict:
    import json
    import urllib.request

    host, port = address.rsplit(":", 1)
    host = "127.0.0.1" if host == "0.0.0.0" else host
    with urllib.request.urlopen(f"http://{host}:{port}/link/v1/status", timeout=10) as resp:
        return json.loads(resp.read())


def test_servir_defaults_to_this_machine_only(state_home):
    proc, lines = _serve(state_home)
    try:
        assert lines and lines[0].startswith("sirviendo enlace en 127.0.0.1:")
        assert _status(lines[0].split(" en ")[1].split(" ")[0])["office"]["protocol"] == "isymotron-link@1"
        assert not (state_home / "isymotron" / "link" / "receipts.jsonl").exists()
    finally:
        proc.kill()
        proc.wait()


def test_servir_red_listens_on_the_network_says_how_and_leaves_a_receipt(state_home):
    import json

    proc, lines = _serve(state_home, "--red")
    try:
        assert lines[0].startswith("sirviendo enlace en 0.0.0.0:")
        receipts = (state_home / "isymotron" / "link" / "receipts.jsonl").read_text(encoding="utf-8").splitlines()
        record = json.loads(receipts[-1])
        port = record["port"]
        assert any("En el teléfono escribe:" in line and line.endswith(f":{port}") for line in lines)
        assert any("isymotron link aceptar" in line for line in lines)
        assert _status(f"127.0.0.1:{port}")["paired"] == 0
        assert record["kind"] == "link_serve_lan"
        assert isinstance(port, int)
    finally:
        proc.kill()
        proc.wait()
