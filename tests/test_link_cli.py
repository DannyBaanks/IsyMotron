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
import link_cli
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


def _serve(state_home, *extra, port=0):
    proc = subprocess.Popen(
        [sys.executable, str(LINK_CLI), "servir", "--port", str(port), "--udp-port", "0", *extra],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "XDG_STATE_HOME": str(state_home)},
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


def test_servir_red_exposes_the_status_endpoint_on_the_network(state_home):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    proc, lines = _serve(state_home, "--red", port=port)
    try:
        assert lines[0] == f"sirviendo enlace en 0.0.0.0:{port} (Ctrl+C para detener)"
        assert _status(f"127.0.0.1:{port}")["paired"] == 0
    finally:
        proc.kill()
        proc.wait()


def test_servir_red_records_the_actual_http_port(tmp_path, monkeypatch, capsys):
    import json

    class StoppedServer:
        tcp_address = "0.0.0.0:4321"
        http = SimpleNamespace(server_address=("0.0.0.0", 8765))

        def __init__(self, directory, **_kwargs):
            self.directory = directory

        def start(self):
            pass

        def stop(self):
            pass

    directory = tmp_path / "isymotron" / "link"
    monkeypatch.setattr(link_cli, "LinkServer", StoppedServer)
    monkeypatch.setattr(link_cli, "lan_addresses", lambda: ["192.0.2.10"])

    def stop_loop(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr("time.sleep", stop_loop)

    assert link_cli.cmd_servir(SimpleNamespace(red=True, port=0, udp_port=0), directory) == 0
    record = json.loads((directory / "receipts.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["kind"] == "link_serve_lan"
    assert isinstance(record["ts"], str)
    assert record["port"] == 8765
    assert record["addresses"] == ["192.0.2.10"]
    output = capsys.readouterr().out
    assert "192.0.2.10:8765" in output
    assert "isymotron link aceptar <código>" in output
